# Pente Fino do Sistema EJC — 2026-07-18

> **ADENDO (mesmo dia): correções aplicadas.** Todos os achados críticos (C1, C2), altos (A1–A4), médios e baixos acionáveis deste relatório foram corrigidos nos commits subsequentes desta branch, junto com as 8 falhas de teste. Verificação pós-correção: backend **2.751 testes passando** contra Postgres+pgvector real (0 falhas), frontend tsc + **128 testes** + build verdes, e **re-auditoria de segurança confirmou A1/A2/M-S2/M-S3 fechados sem achados novos críticos/altos**. Exceções deliberadas (decisões documentadas do titular, não corrigidas): enforcement duro de 2FA por papel (M-S4) e default `AI_AGENT_ENABLED=true`. Residuais registrados pela re-auditoria (pré-existentes/decisão de produto): `GET /agenda-eventos/` expõe eventos pessoais a qualquer interno (avaliar se agenda compartilhada é intencional); `POST` de agenda aceita `responsavel_id` de terceiro e o oráculo de conflito revela título/local; `protocolo_comprovante_doc_id` não valida pertencimento do Document ao caso; faltam testes automatizados para titularidade de procurações e IDOR de agenda.

**Escopo:** todas as mudanças mergeadas em 2026-07-18 por sessões de IA (Claude e Codex) — PRs #276–#285 e commits diretos — diff `6681910..HEAD`: **243 arquivos, ~29,5 mil inserções / ~4,1 mil remoções**.

**Método:** 5 auditorias paralelas e independentes (revisão de código backend, revisão frontend com cruzamento de contrato API, auditoria de segurança, revisão de migrations Alembic e execução da suíte completa de testes contra Postgres 16 + pgvector real). Cada achado abaixo foi confirmado lendo o código real — nenhuma hipótese não verificada foi incluída.

---

## Sumário executivo

| Frente | Veredicto |
|---|---|
| Banco / migrations Alembic | **Saudável** — head único, merge de heads correto, model↔migration consistentes, sem operação destrutiva |
| Testes backend (2.745 testes, banco real) | **8 falhas**, todas causadas por commits de hoje |
| Testes/typecheck/build frontend | **Verde** (tsc 0 erros, 120/120 vitest, build OK) |
| Instalação do backend | **QUEBRADA** — `requirements.txt` ininstalável (C2) |
| Segurança | Sem crítico, mas **2 brechas ALTAS de sigilo entre carteiras** (A1, A2) |
| Funcional | **UI do agente de IA está morta** (C1) e OCR síncrono pode travar o servidor (A3) |

**Correções prioritárias (nesta ordem):** C1, C2, A1+A2 (sigilo), A3, A4, depois os médios.

---

## CRÍTICO

### C1 — A UI do novo agente de IA não recebe nenhum evento (feature morta)
- `frontend/src/lib/stream.ts:101` + `frontend/src/pages/AgenteIA.tsx:143` vs `backend/app/routers/ia_agente.py:114`
- `streamSSE` fatia os frames SSE por `"\n\n"`, mas o endpoint `POST /api/ia/agente/stream` responde via `EventSourceResponse` do sse-starlette 2.1.0, cujo separador default é `"\r\n"` (frames terminam em `\r\n\r\n` — confirmado no wheel: `DEFAULT_SEPARATOR = "\r\n"`). A substring `\n\n` nunca ocorre; o buffer cresce e nada é parseado.
- Efeito: o advogado clica "Executar agente", a tela fica em "Agente processando…" e termina vazia, sem erro. O cartão de aprovação HITL nunca aparece — a escrita fica pendurada no backend até expirar. O resto do buffer é descartado no fim do stream (`stream.ts:96-99`), então nem o evento `final` chega. Os streams legados (peça/bancário) não são afetados porque emitem `\n\n` manualmente.
- Correção: dividir por `/\r?\n\r?\n/` (e tolerar `\r` nas linhas), ou passar `sep="\n"` no `EventSourceResponse`.

### C2 — `backend/requirements.txt` ininstalável — CI e ambientes novos quebram
- Commit `4f9027a` (PR #285, Entrada Universal) adicionou `pillow-heif==1.4.0`, que exige `pillow>=11.1.0` e conflita com o pin `Pillow==10.4.0`. `pip install -r requirements.txt` falha com `ResolutionImpossible`.
- Efeito: o job `db-validation` do CI e qualquer deploy/ambiente novo não instalam o backend. Passou despercebido porque o runner self-hosted estava offline hoje (commits "ops: recuperar runner").
- Correção: `pillow-heif<=0.22.x` (compatível com Pillow 10) ou subir o Pillow — validando os demais consumidores de PIL.

---

## ALTO

### A1 — Vazamento de PII entre carteiras via Procurações (segurança)
- `backend/app/routers/procuracoes.py:34-64` (listagem sem filtro de titularidade) e `:81-130` (minuta)
- `POST /procuracoes/{id}/minuta` monta a qualificação completa do outorgante (nome, CPF/CNPJ, profissão, endereço — `services/documental.py:19-33`) com gate apenas de papel, sem `_pode_ver_cliente`. Um advogado autenticado enumera `GET /procuracoes/` (lista a base inteira) e reconstrói a PII de todas as carteiras. É exatamente a brecha que `1c7285d` fechou em `clients.py`, deixando esta porta lateral aberta. Agravante: `db.get(Case, case_id)` sem `verificar_acesso_caso` e sem filtro `deleted_at` (`:106`).
- Relacionado (MÉDIO M-S1): `criar` e `revogar` também não checam titularidade — qualquer advogado/auxiliar pode revogar procuração vigente de cliente alheio.
- Correção: aplicar `_pode_ver_cliente` (ou equivalente) em `listar`, `gerar_minuta`, `criar` e `revogar`; trocar `db.get(Case, ...)` por `verificar_acesso_caso`.

### A2 — Segregação de clientes contornável via criação de acesso ao Portal (segurança)
- `backend/app/routers/clients.py:683-711` (`POST /clients/{client_id}/criar-acesso`)
- Gate é só `require_roles`, sem checar vínculo com o cliente. Um advogado sem relação com o cliente X cria acesso de portal com e-mail e senha que ele controla, loga como `cliente_externo` e lê casos, documentos, mensagens e financeiro de outra carteira — burlando toda a segregação interna. Lacuna residual da correção de sigilo `1c7285d` (que blindou os outros endpoints do mesmo arquivo).
- Correção: exigir `_pode_ver_cliente(cu, c, db)` (ou gestão) + audit log destacado.

### A3 — OCR/CV síncrono bloqueia o event loop inteiro
- `backend/app/routers/entrada_universal.py:249` e `backend/app/routers/defesas_revisoes.py:212` (reusado por `comparar_documentos`/`analisar_decisao`); menor escala em `entrada_universal_vinculo.py:131`
- `extrair_paginas` (render PyMuPDF 220dpi + OpenCV + PIL + pytesseract, CPU-bound) roda inline no handler async, num loop de até 60 arquivos — sem `asyncio.to_thread`, que é a convenção do próprio projeto (`documents.py:407-412`).
- Efeito: um ZIP com 40 fotos de autos congela o worker por minutos — login, portal e SSE de TODOS os usuários travam/estouram timeout.
- Correção: envolver as chamadas CPU-bound em `asyncio.to_thread` (ou fila).

### A4 — "Novo caso por documento" multi-arquivo: original duplicado e documentos órfãos
- `frontend/src/components/ImportarDocumento.tsx` (usa `EntradaUniversalDocumentos` sem `caseId`/`clientId`; `_arquivo_original = _arquivos_locais[0]`) + `frontend/src/pages/Casos.tsx:488-534`
- O fluxo agora processa via `POST /entrada-universal/processar`, que persiste TODOS os arquivos no GED com `case_id=None`/`client_id=None`; depois `Casos.tsx` cria o caso e re-anexa via `POST /documents/upload` apenas o PRIMEIRO arquivo. O `_entrada_universal_batch_id` é passado mas nunca consumido (o endpoint de vínculo lote↔caso, `entrada_universal_vinculo.py`, existe e não é usado).
- Efeito concreto: advogado importa 3 PDFs para abrir o caso → o 1º fica gravado em duplicidade no GED (uma cópia órfã + uma anexada; escopos de dedup diferentes, o sha256 não colide), o 2º e o 3º ficam órfãos sem vínculo com caso/cliente — silenciosamente. Antes do diff o componente era single-file e não persistia nada.
- Correção: após criar o caso, chamar o vínculo do lote (`/entrada-universal/{id}/vincular-caso`) em vez de re-upload do primeiro arquivo.

---

## MÉDIO

### Backend / lógica
1. **M-B1 — Protocolo fura a máquina de estados do orquestrador** — `legal_docs.py:572` + `legal_case_orchestrator.py:203,228`. `PATCH /legal-docs/{id}/protocolo` aceita peça em rascunho e qualquer papel com acesso ao caso; `derivar_estado` considera `numero_protocolo` preenchido e salta o caso para "acompanhamento", ocultando pendências de revisão/aprovação/prazo. Conflito semântico entre PRs do mesmo dia.
2. **M-B2 — Validação CNJ estrita bloqueia processos administrativos** — `schemas/case.py:9,68`. `CaseCreate`/`CaseUpdate` agora rejeitam com 422 qualquer `numero_processo` não-CNJ, mas o mesmo release entrega Defesas administrativas (JARI, SEI, auto de infração, PAD) cuja numeração não é CNJ. Bloqueia cadastro novo e regride edição de casos legados.
3. **M-B3 — Matriz de Teses: precedentes nunca vinculados** — `matriz_teses_service.py:360,388,402`. Toda tese nasce com `issue_id=None` e `precedentes=[]`; os pesos `PESO_FUNDAMENTO_VERIFICADO` (+10) e `PESO_POR_SALDO_PRECEDENTE` (+30) são inalcançáveis — o ranking de força das teses sai sistematicamente achatado, ignorando a jurisprudência que o próprio módulo pesquisou.
4. **M-B4 — Rota insegura de `/pacote` só sombreada, não removida** — `defesas_revisoes_avancado.py:442-485` + `routers/__init__.py:26-31`. A versão que gera kit MESMO com pendências impeditivas continua registrada, apenas atrás da rota segura por ordem de include. Qualquer reordenação de import a ressuscita silenciosamente. Idem `ADVOGADO_ROLES.discard(...)` como efeito colateral de import.
5. **M-B5 — Lembretes de audiência sem rollback por item** — `scheduler.py:335` (loop ~395-405). O `except` interno não faz `db.rollback()`; um erro de banco aborta a transação e todas as audiências seguintes do lote falham com `PendingRollbackError` — lembretes de 3/1/0 dias se perdem silenciosamente.

### Segurança
6. **M-S1 — Criar/revogar procuração sem titularidade** — ver A1.
7. **M-S2 — IDOR em eventos de agenda pessoais** — `agenda_eventos.py:126-142`. Evento sem `case_id` não tem NENHUMA checagem de dono: qualquer interno edita/reagenda/conclui evento alheio; o diff de hoje ampliou a superfície tornando `responsavel_id` patchável (transferência de compromissos, incl. audiências).
8. **M-S3 — Replay de refresh token pós-logout sem trilha** — `auth.py:358-367` (commit `00be75d`). O caminho continua fail-secure, mas o replay de token revogado por logout/troca de senha não gera mais `audit_log` — atacante invisível na auditoria. Registrar evento leve (`REFRESH_REPLAY_POS_LOGOUT`).
9. **M-S4 — 2FA "obrigatório" por papel não bloqueia** — `auth.py:306-307`. Papel em `REQUIRE_2FA_ROLES` sem TOTP só recebe `precisa_configurar_2fa=true` e segue logando para sempre. Sugestão: prazo de graça e depois bloquear emissão de token completo.

### Frontend
10. **M-F1 — Retomada HITL sem Redis usa o texto atual do textarea** — `AgenteIA.tsx:199-204,250`. Com Redis indisponível, "Aprovar" reenvia `mensagem` com o que estiver no textarea NAQUELE momento (reabilitado pelo `finally`); o agente pode re-executar plano diferente do revisado, ou a aprovação se perde por hash divergente. Congelar a mensagem original junto com `pending`.
11. **M-F2 — Central de Atividades descarta os campos do feed** — `CentralAtividades.tsx:761-816`. O `GET /atividades` já entrega `responsavel_id`/`prioridade`/`subtipo`, mas o load re-deriva tudo de 3 fetches extras: não-gestores veem prazos sem responsável/prioridade (filtro de `/deadlines/`), audiências além do page_size 500 são rebaixadas para "Compromisso", e são 3 requisições redundantes por carga.

### Banco
12. **M-D1 — Colunas de bytes em `Integer` (int32)** — `101_entrada_universal_documentos.py` + `models/document_intake.py`. `total_bytes`/`size_bytes` estouram com lote >2 GiB. Migrar para `BigInteger` (barato, tabela pequena).
13. **M-D2 — Downgrade no-op do enum `sucumbencia`** — `097_fee_tipo_sucumbencia.py`. Documentado e aceitável, mas em rollback de release linhas com `tipo='sucumbencia'` quebram o código antigo — constar no runbook de rollback.

---

## Falhas de teste (8 de 2.745, backend, banco real — todas de commits de hoje)

| # | Teste | Causa raiz |
|---|---|---|
| 1 | `test_seguranca_senha_2fa.py::test_alterar_senha_nova_forte_200` | `0b07ca7` adicionou `user.full_name` na resposta de `/auth/alterar-senha` (`auth.py:537`); o stub antigo do teste não tem o atributo → 500 |
| 2 | `test_usabilidade_p0_backend.py::test_alterar_senha_retorna_tokens_e_limpa_claim` | Espelho do anterior: `487d077` adicionou `validar_forca_senha(..., user.email)` (`auth.py:492`); o stub novo tem `full_name` mas não `email`. Os dois commits do mesmo PR quebraram o teste um do outro |
| 3–4 | `test_agenda_conflito_horario_dblevel.py` (2 testes) | `e40d5a2`: SQL cru `(:exc IS NULL OR e.id <> :exc)` com `exc=None` → `AmbiguousParameterError` no asyncpg (`agenda_eventos.py:62`). Precisa `CAST(:exc AS text)` ou bindparam tipado. Bug PG-only |
| 5 | `test_clients_sigilo_titularidade_dblevel.py::test_conflito_ainda_cruza...` | Teste novo de `1c7285d` nasceu quebrado: `checar_conflito` grava `audit_logs` com FK para o usuário; o cleanup faz `DELETE FROM users` direto → `ForeignKeyViolationError` e deixa cliente órfão com CPF `39053344705` |
| 6–7 | `...::test_criar_acesso_portal_{rejeita_senha_fraca,aceita_senha_forte}` | E-mail `@teste.local` rejeitado pelo `EmailStr` (email-validator 2.3.0 bloqueia TLD reservado). Usar `@teste.example` |
| 8 | `test_search_dblevel.py::test_cpf_hash_exato_encontra_cliente_sem_plaintext` | Cascata do item 5: o cliente órfão usa o mesmo CPF hard-coded e a busca devolve match extra. Reproduzido empiricamente |

O CI não pegou nada disso porque o runner self-hosted esteve offline durante os merges de hoje.

---

## BAIXO (resumo)

- `agenda_eventos.py:157` — conflito de agenda checado contra o responsável ANTIGO após patch de `responsavel_id` (aviso informativo errado).
- `scheduler.py:133` — docstring promete rollback/retentativa que o `db.commit()` intermediário de `notification_service.py:37` impede (desfecho benigno).
- `entrada_universal.py` — `except` grava `status="erro"` + `commit` sem `rollback()` prévio; se a exceção foi de banco, `PendingRollbackError` mascara a causa raiz.
- `defesas_revisoes_avancado.py:221+` — `body: dict` cru em 6 endpoints (contra o padrão Pydantic do projeto; ownership OK).
- `config.py:233` — `AI_AGENT_ENABLED=true` por default (decisão documentada do titular) somado a `AI_AGENT_MAX_TOKENS` 16k→120k no mesmo commit: ambientes novos nascem com o agente ligado e teto de custo 7,5× maior.
- `legal_docs.py` — LegalDoc sem `case_id` editável por qualquer interno (padrão preexistente).
- `entrada_universal_service.py:121-127` — teto de 100 MB do ZIP usa `file_size` declarado (forjável); mitigado pelos tetos pós-descompressão.
- `CentralAtividades.tsx:79` — prazo `cancelado` exibido como "Concluído" (selo verde) — enganoso para prazo processual.
- `Documentos.tsx:~131,350-375` — object URL da pré-visualização não é revogado no unmount (vazamento de blob até reload).
- `ImportarDocumento.tsx:~256` — `classificacao.area` da IA vai para o `POST /cases/` sem validar contra a taxonomia (antes havia guarda `areasPermitidas`); slug inválido gera 422 em vez de simplesmente não pré-preencher.
- `CentralAtividades.tsx:640` — kanban só opera via drag-and-drop HTML5, sem alternativa de teclado (WCAG 2.1.1).
- `stream.ts:96-99` — frame SSE final não terminado é descartado sem parse (compõe C1).
- `RaioXProcesso.tsx:~615/760` — erro do 409/403/429 da "Análise do advogado" aparece no banner do topo, fora da viewport quando o botão está no fim da página ("parece que nada aconteceu").
- `DefesasRevisoesComplementos.tsx:71-87` — race cosmética ao trocar de aba (resposta em voo da aba anterior pode preencher a saída da aba nova; sem guarda de cancelamento).
- Alembic: docstring errada na `100`, dois arquivos com prefixo `101_` (IDs únicos, apenas confusão de leitura), `sa.JSON` em vez de `JSONB` na `101_entrada`, `data_julgamento` como `String(40)`, FK ausente em `created_by` do intake sem justificativa escrita.
- Prettier: 84 arquivos fora do padrão (step não-bloqueante no CI).

---

## Verificado e OK (onde se procurou defeito e não se achou)

- **Migrations:** cadeia íntegra com head único (`104_merge_entrada_orquestrador`), merge `6850502` correto (ramos independentes — qualquer ordem de execução é segura), model↔migration coluna a coluna, sem DROP/backfill perigoso, teste de head único no CI.
- **Auth:** rotação/reuso de refresh token fail-secure (cascata de revogação, janela de graça multi-aba, `alterar_senha` revoga tudo antes do novo par); senha forte aplicada em todos os pontos de definição; rate limits presentes.
- **Endpoints novos de hoje** (orquestrador, case_intelligence, matriz_teses, motor_peca, honorários, kit documental, entrada universal, defesas/revisões, raio-x): auth + `verificar_acesso_caso` + papel mínimo + rate limit nas escritas; sem IDOR/mass assignment além dos listados.
- **Agente/tools:** as 9 tools re-verificam acesso ao caso com `case_id` fixado pela request; escrita é HITL one-shot vinculada ao hash dos args; RAG escopado pelo cliente do caso; `apenas_leitura` nega escrita.
- **Uploads:** filepath `uuid+ext` (sem path traversal), validação de conteúdo reusada, ZIP bloqueia caminho absoluto/`..`/aninhado.
- **Frontend:** contratos de `api.ts` batem com os routers (entrada-universal, raio-x, aplicar-extracao, HITL, ações da Central, portal `nao-lidas`, `/ia/status`, `/areas`); CSS deletado era morto de verdade; registry `hidden` mantém rotas ativas; CommandPalette com ARIA correto.
- **Segredos:** nada de credencial no diff; `CITACOES_POLITICA` endureceu para fail-secure.

Passadas adicionais dedicadas cobriram em profundidade os blocos GED/Dossiê/Conhecimento (contratos de entrada universal, documentos, atendimentos, clients e KnowledgeHub — tudo confere; tema escuro sem regressão) e Peças/IA/Defesas (todos os contratos de defesas-revisões, motor-peça, análise bancária, Raio-X, `/ia/status`, ramos/CADE e verificação de citações conferem; a fila de Peças inclusive corrige bug pré-existente de status `versao_final` inexistente).

A passada dedicada de Portal/Financeiro/Navegação também concluiu sem achados (contratos do portal — não-lidas, financeiro como lista, assinaturas/comprovante, middleware de `cliente_externo` —, redirects do registry, deps de useEffect do Financeiro, CommandPalette ARIA e temas conferidos nos dois lados). Com isso, **não resta lacuna de cobertura relevante no frontend**; únicas notas: o cartão de pendências do Portal usa `Promise.allSettled` e pode exibir "em dia" se uma chamada falhar com 5xx (fail-safe deliberado).
