# Auditoria Casos + Raio‑X + Sala Jurídica — e o plano de fusão em módulo único

**Data:** 2026‑08‑08 · **Base auditada:** `main` em `05a4a9c` · **Natureza:** somente leitura — nenhuma linha de código foi alterada.

**Pergunta do titular:** *"Faça uma auditoria completa no módulo Casos, Raio‑X, Sala e verifique o fluxo, redundâncias, falhas, obsolescência, travas etc. Viabiliza a necessidade de mesclar em um único módulo? Não altere ainda, só monte o plano perfeito."*

---

## 1. Veredicto

**A fusão é viável, é necessária, e já está meio caminho andada — mas "fundir" aqui não significa reescrever três módulos num arquivo só.** Significa terminar o movimento que o Bloco 3 do plano de lançamento começou (entrada única + caso como espaço de trabalho + quatro estados, aprovado pelo titular em `docs/DESENHO_ENTRADA_UNICA_E_CASO_WORKSPACE.md`):

> **O Caso é o módulo. Sala Jurídica e Raio‑X deixam de ser módulos concorrentes e viram *modos de entrada* do mesmo funil — conversar, analisar documentos, colar o relato — todos desembocando no mesmo serviço de criação de caso, com o mesmo contrato, sem perder dados no caminho.**

A fusão certa é **por contrato, não por tabela**: primeiro um único serviço de conversão e uma única rotina de ingestão de documentos (onde estão os bugs e as triplicações); depois a unificação de navegação/UI; a fusão física de tabelas fica adiada deliberadamente, porque custa caro e não resolve nenhuma dor atual.

O que a auditoria encontrou justifica a urgência: as três "portas" **triplicam** a mesma lógica com divergências que já produziram defeitos reais — caso nascido do Raio‑X que **não pode ser editado** (422 permanente), caso nascido da Sala que **nasce sempre com área "civil"**, conversões que **perdem** partes, pontos fortes/fracos e teses que o próprio `Case` tem coluna para receber.

---

## 2. Método e escopo

- Varredura de código em três frentes paralelas (Casos, Raio‑X, Sala Jurídica), backend + frontend + migrations + testes, com conferência manual dos achados de maior peso (todos os achados citados neste documento com `arquivo:linha` foram confirmados no arquivo).
- Cruzamento com a auditoria externa de produção (`docs/auditoria/`), com o desenho aprovado do Bloco 3 e com os PRs abertos que tocam a área.
- **Fora do escopo:** módulos vizinhos (Peças, Prazos, GED, Financeiro) — entram apenas como fronteiras.

**PRs abertos que tocam esta área (travas de sequenciamento):**

| PR | O que muda | Impacto no plano |
|---|---|---|
| **#786** | Raio‑X assíncrono (Celery, estados `fila`/`em_processamento`/`erro`), fontes unificadas, heartbeat por resultado | O plano **parte do estado pós‑#786**; nenhuma fase deste plano deve mexer em `raio_x.py` antes desse merge |
| **#757** | Allowlist no `PATCH /raio-x/{id}` (mass assignment) | Idem — corrige um P0 de segurança que este plano herda como resolvido |

---

## 3. Radiografia do ecossistema auditado

| Dimensão | Casos | Raio‑X | Sala Jurídica |
|---|---|---|---|
| Routers backend | 12 routers sob `/cases` + satélites, **~46 endpoints** (`cases.py` 1.447 linhas, 20 endpoints) | `raio_x.py` 757 linhas, **17 endpoints** | `legal_chat.py` 443 linhas, **13 endpoints** |
| Services | ~5.600 linhas (13 arquivos; `legal_case_orchestrator.py` 744) | 4 services, ~1.530 linhas | `legal_chat_service.py` 1.169 linhas |
| Frontend | `Casos.tsx` 1.737 · `CasoDetalhe.tsx` 1.230 + 14 abas | `RaioXProcesso.tsx` **1.777** | `SalaJuridica.tsx` **1.572** |
| Tabelas próprias | `cases` + 33 tabelas com FK para `cases.id` | `raio_x_analises`, `raio_x_documentos` | 4 tabelas `legal_chat_*` |
| Endpoints sem consumidor no frontend | **8** (~1.100 linhas servindo ninguém) | 1 (`DELETE /raio-x/{id}`) | 2 (`GET`/`PATCH /estado`) |

Total do ecossistema a fundir: **~25.000 linhas**. O módulo fundido, depois da poda, tende a ficar substancialmente menor — a triplicação é grande parte do volume.

---

## 4. Achados

### 4.1 Fluxo real — quatro portas, quatro casos diferentes

Só existem 4 pontos no código que instanciam `Case`:

1. `POST /cases/` — cadastro direto (`cases.py:211`)
2. `POST /entrada/{id}/criar-caso` — Entrada Única (`entrada_service.py:554`)
3. `POST /raio-x/{id}/converter` (`raio_x_service.py:658`)
4. Conversão da Sala Jurídica (`legal_chat_service.py:901`)

A única coisa unificada entre elas é a numeração (`case_numeracao.proximo_numero_interno`, com advisory lock — correto). **Todo o resto diverge:**

| Efeito colateral | `POST /cases/` | Entrada Única | Raio‑X | Sala |
|---|:-:|:-:|:-:|:-:|
| Gate G1 (`proxima_acao` obrigatória) | ✅ | ✅ (default) | **❌** | ✅ (default) |
| Anti‑duplicidade por CNJ (advisory lock) | ✅ | ❌ | ❌ | ❌ |
| `CaseMovimento` de abertura | ✅ | ✅ | ❌ | ❌ |
| Automação (Kanban + checklist) | ✅ | ❌ | ❌ | ❌ |
| Triagem IA | ✅ | ❌ | ❌ | ❌ |
| Kit documental | ✅ | ❌ | ❌ | ❌ |
| `event_bus.emitir_caso_criado` | ✅ (único emissor no repo) | ❌ | ❌ | ❌ |
| `CaseIntelligenceSnapshot` | ❌ | ❌ | ✅ | ✅ |
| Transacional (cliente+caso+vínculos em 1 commit) | — | ✅ | ✅ (banco) | ✅ (banco) |

Ou seja: **um caso "completo" só nasce da porta manual; um caso com memória de IA só nasce das portas de IA.** Nenhuma porta produz as duas coisas. Qualquer assinante do evento `caso.criado` é surdo para 3 das 4 portas.

Nas 3 telas manuais do frontend, cliente e caso são criados por **duas chamadas HTTP sem compensação** (`Casos.tsx:612→625`, `NovoCasoWizard.tsx:208→266`, `CadastroManual.tsx:516→530`) — falha na segunda deixa cliente órfão. A Entrada Única faz certo (transação única).

**Estados:** a migration `126_case_status_quatro_estados` foi aplicada de verdade; `core/status_caso.py` é fonte única com paridade testada contra `frontend/src/types/caseStatus.ts`. Esse é o alicerce bom sobre o qual a fusão se apoia. Porém convivem ainda **5 vocabulários de "onde está o caso"**: o enum (vivo), a jornada de 9 etapas (`jornada_caso.py` — **morta**: `JornadaCaso.tsx` só redireciona), o orquestrador de 16 etapas (`legal_case_orchestrator.py:537` — vivo, via `OrquestradorPanel`), `case_health.ABERTOS/FECHADOS` (reimplementação) e `domain_contracts.CaseLifecycleStatus` (11 valores nunca persistidos).

### 4.2 Redundâncias (o custo da não‑fusão)

1. **Conversão em caso triplicada.** `entrada_service`, `raio_x_service.converter_em_caso` (178 linhas) e `legal_chat_service.converter_em_caso` (136 linhas) reimplementam a mesma sequência (gate de papel → preview de conflito → gates 409 → resolver cliente → numerar → criar → transferir docs → snapshot → congelar). O próprio código admite: `entrada_service.py:441` documenta "paridade com `legal_chat_service.converter_em_caso`". Paridade por cópia é onde nasceram os bugs do §4.3.
2. **Upload/ingestão duplicada por cópia literal.** `raio_x.py:415‑480` ≡ `legal_chat.py:239‑300` — mesmo bloco reescrito, divergindo em incoerências, não decisões: 20 vs 10 arquivos, 8 vs 12 extensões, `enriquecer_rag` True vs False, texto extraído descartado vs retido, falha de extração descarta vs anexa. Ambos importam `_validar_conteudo`, símbolo **privado** de `routers/documents.py`, dentro da função.
3. **Preview de conflito/duplicidade duplicado** entre `raio_x_service` e `legal_chat_service`, com comentários confessando a paridade manual — e o Raio‑X **sem** o rate‑limit que a Sala tem no endpoint equivalente.
4. **Três tabelas de anexo** (`raio_x_documentos`, `legal_chat_attachments`, `documents`) e conversão que **copia fisicamente o arquivo** (`shutil.copy2`) — dois blobs idênticos em disco por documento convertido.
5. **Quatro implementações de linha do tempo** do caso (`/movimentos`, `/linha-do-tempo`, `/timeline`, `/visual-law/.../timeline` — só a última é usada) e **três de score/saúde** (operational-health morto; score‑jurídico e índice‑risco vivos).
6. **Dois caminhos para encerrar e dois para arquivar** com garantias diferentes: `POST /encerrar` exige pós‑mortem e alimenta o RAG; `PATCH {status:"encerrado"}` não exige nada (`cases.py:451` vs `:898`). Idem arquivar (com/sem gate de papel).
7. **Campos narrativos em 6 lugares** (`cases.descricao_fatos/tese_principal/pontos_*`, snapshot payload, `relatorio` do Raio‑X, dossiês, fichas de triagem, intake batches).
8. **Quatro caminhos de export de documento** — o Raio‑X tem pipeline próprio (`fpdf` com `latin‑1`: **acentos viram `?` no PDF**), a Sala outro (WeasyPrint), fora dos serviços canônicos.

### 4.3 Falhas (conferidas no código)

**P0 — quebram o fluxo ou perdem dado de trabalho jurídico**

| # | Falha | Evidência |
|---|---|---|
| 1 | **Caso nascido do Raio‑X fica ineditável.** A conversão cria `Case` `aberto` sem `proxima_acao` (`raio_x_service.py:658‑679` — campo ausente do construtor); o `PATCH /cases/{id}` exige `proxima_acao` para status abertos e devolve **422** (`cases.py:443‑447`). Até "Reabrir caso" (`TabResumo.tsx:234`) quebra. | conferido |
| 2 | **Caso nascido da Sala nasce com área "civil" sempre.** `convArea` inicia fixo `useState("civil")` (`SalaJuridica.tsx:264`) e o wizard nunca aplica `area_sugerida` da sessão (só a exibe, `:898`). | conferido |
| 3 | **Conversão do Raio‑X perde dados que o `Case` tem coluna para receber**: `partes` (nenhum `CaseParte` criado), `pontos_fortes`, `pontos_fracos`, `tese_principal` (snapshot grava `"principal": None`), `decisoes`, `revisao_humana`; e `compactar_payload` descarta cronologia/fatos_provas/provas de análises grandes **silenciosamente** (`raio_x_service.py:574‑615`). |
| 4 | **`prazos_pendentes` é sempre 0** no resumo do caso: `DeadlineStatus(Deadline.status)` chama o construtor do Enum sobre a coluna → `ValueError` sempre → `except` engole (`cases.py:403‑409`). | conferido |
| 5 | **`PATCH /cases/{id}` sem `require_roles` contorna os gates**: qualquer papel com visibilidade arquiva/encerra por PATCH, pulando `_ARQUIVAMENTO_ROLES` e o pós‑mortem obrigatório (`cases.py:425‑456`). Reabertura tampouco limpa `data_encerramento/resultado/licoes` — caso reaberto segue contando como desfecho na jurimetria. |
| 6 | **Purga LGPD de logs de IA vai parar em silêncio**: `legal_chat_messages.ai_log_id` é a única FK do sistema para `ai_logs.id`, **sem `ondelete`** (`models/legal_chat.py:146`); `_purgar_logs_ia` faz `DELETE FROM ai_logs` cru com `except` que só loga (`scheduler.py:1195‑1210`). Na primeira mensagem da Sala com mais de 2 anos, a purga inteira passa a falhar silenciosamente. | conferido |
| 7 | **Sem expurgo de retenção nas duas portas de IA**: `raio_x_analises.retention_until` só bloqueia DELETE — não há job que expurgue; a Sala não tem sequer retenção, e descartar sessão/análise **não remove arquivos físicos**. PII de não‑clientes retida indefinidamente em disco. |

**P1 — arquitetura e segurança**

8. **HITL e citações descartados pela UI da Sala**: o backend devolve `is_rascunho`, `aviso_hitl`, `critica_adversarial` e persiste `citacoes`; o frontend joga a resposta fora (`SalaJuridica.tsx:438‑441`) e o tipo `Mensagem` nem tem o campo `citacoes`. O gate existe e o advogado não o vê.
9. **Análise de anexos não passa pelo orchestrator** (RAG/citação/crítica): `documento_service.extrair_e_analisar` vai direto ao `ai_gateway.chat` — conforme à regra crítica do gateway (nenhuma chamada de provider direta foi encontrada nos três módulos), mas contradiz o docstring "toda IA passa pelo núcleo único".
10. **`POST /raio-x/{id}/reanalisar?reprocessar=true` sem rate‑limit** — refaz OCR+LLM de todos os documentos; bypass direto do teto de custo do upload. Também sem limite: exports (PDF síncrono na request), previews com `ILIKE '%…%'`.
11. **RBAC desigual**: a Sala protege 100% dos endpoints com `exigir_equipe_juridica`; o Raio‑X aplica `_permitido` em só 3 de 17; em Casos, `GET /cases/`, `PATCH`, `/movimentos` e dois endpoints que chamam LLM ficam em `get_current_user` puro (sem piso de papel, sem rate‑limit). `atualizar_sessao` da Sala aceita `advogado_responsavel_id` sem validar existência/papel.
12. **Gravações em duas sessões**: kit documental comita `LegalDoc` numa sessão própria e o `AuditLog` na do router (`cases.py:698‑732` + `documental.py:362`) — ato jurídico pode ficar sem rastro; uploads gravam arquivo em disco antes do commit sem compensação; cópias físicas da conversão podem órfã‑se se o commit do router falhar.
13. **Herança de visibilidade pós‑exclusão só existe para peças**: `filtrar_pecas_visiveis` tem um único consumidor; prazos, documentos, tarefas e honorários de caso excluído continuam aparecendo — prazo de caso excluído segue alertando.
14. **N+1**: `ranking_saude` até ~2.500 queries/request; `/resumo` 12+ COUNTs sequenciais; filtro de tipo em `Casos.tsx` aplicado client‑side sobre página de 50 (resultado silenciosamente incompleto).
15. **A correção da conversão Sala→Caso (`descricao_fatos`) está sem teste de regressão**, e o fallback quebra com `resumo === ""` (o `??` não cobre string vazia — `SalaJuridica.tsx:494`).

**P2 — inconsistências menores** (vocabulário de `resultado` divergente entre schema e model; `area` texto‑livre sem validação em `caso_areas.py`; `date.today()` na numeração; mensagem "Caso criado em triagem" pós‑migration 126; import redundante de Pydantic; `dry_run` aceito duas vezes).

### 4.4 Obsolescência (poda segura, zero consumidores)

| Alvo | Tamanho | Evidência |
|---|---|---|
| Jornada de 9 etapas inteira: `jornada_caso.py` + `schemas/jornada_caso.py` + `JornadaCaso.tsx` (só redireciona) + entrada `caso-jornada` do registry | ~500 linhas | endpoint sem nenhum caller; UI usa o orquestrador de 16 etapas |
| Endpoints órfãos de Casos: `/resumo`, `/assistente-estrategico`, `/movimentos/{id}/traduzir`, `/linha-do-tempo`, `/timeline` + `case_timeline_service.py`, `/operational-health`, `case_intelligence.py` (3 rotas) | ~1.100 linhas | grep no frontend negativo |
| `DELETE /raio-x/{id}` (órfão); colunas mortas `origem_contextual_case_id` (nunca escrita — e por isso o modo contextual do Raio‑X nunca registra nada), `dados_extraidos` (write‑only), `paginas` (sempre null); `RaioXAcaoRequest`; status `nao_convertido` | — | grep |
| Sala: `GET/PATCH /estado` sem UI (a tela **instrui o usuário a chamar a API na mão** — `SalaJuridica.tsx:1241`), params mortos (`status`, `favorita`, `incluir_workspace`, `usar_rag`, `transferir_anexos`, ações `descartar`/`encerrar_consulta`) | — | grep |
| Vocabulários legados: `LEGACY_CASE_STATUS_TO_CANONICAL`, `CaseLifecycleStatus`, `CasePendencia*`, mapeamentos `triagem`/`ativo` em `UI.tsx`, deep‑links inertes (`/casos?status=ativo` do Dashboard é ignorado pela tela) | — | conferido |
| `backendPrefixes` desatualizados no registry: Sala declara `/api/ai` (não usa), Raio‑X declara `/api/documentos-ia` (não usa) | — | grep |

**Apontamento sobre a documentação:** a armadilha "backend usa `triagem`/`arquivado`; a interface oferece `ativo`/`all`" registrada no `CLAUDE.md` está **desatualizada** — a migration 126 + paridade testada resolveram o núcleo; restam só os resíduos listados acima. Corrigir o texto quando a poda passar por lá.

### 4.5 Travas reais para a fusão

1. **O dict `relatorio` v2 do Raio‑X não tem schema.** ~24 chaves lidas por 7 consumidores (2 exports, tela de 1.777 linhas, prompt do agente, snapshot, preview, `_aplicar_identificacao`). Renomear uma chave quebra tudo simultaneamente. **Tipar em Pydantic é pré‑requisito de qualquer unificação.**
2. **`jornada_caso.py:353‑377` conta `RaioXAnalise` e `LegalChatSession` por FK** para decidir a etapa "triagem" — único vínculo estrutural externo às tabelas dos dois módulos. (Mitigação natural: é código morto — a poda remove a trava.)
3. **33 modelos têm FK para `cases.id`** — qualquer fusão física de tabelas é migration de 33 FKs. Motivo central para fundir por contrato e adiar a fusão de dados.
4. **Superfície dupla `/api` + `/api/v1`** — todo remapeamento de rota precisa cobrir as duas e manter redirects.
5. **Portal do cliente** lê `cases` diretamente — identidade do caso é intocável.
6. **Contratos sem `response_model`**: a Sala serializa dict cru à mão (409 com objeto no `detail`, tratado pelo frontend); qualquer unificação precisa congelar esses formatos antes de mexer.
7. **PRs #786 e #757 abertos** sobre `raio_x.py` — sequenciamento obrigatório (nada de tocar nos mesmos arquivos antes do merge).
8. Três regimes de ciclo de vida pré‑caso (status texto‑livre do Raio‑X ≠ congelamento da Sala ≠ enum do Caso) — a unificação é desejável, mas é migration de comportamento, não de renomeação.

---

## 5. Viabilidade — por que fundir, e em que sentido

**A favor (peso decisivo):**
- As três portas respondem à mesma pergunta de produto ("como um problema vira um caso?") com três códigos que já divergiram em bugs reais (§4.3‑1/2/3). Cada correção hoje precisa ser feita três vezes — e a história recente mostra que não é (paridade por comentário).
- A auditoria externa e o parecer arquitetural pedem exatamente isso: 15 ações/8 módulos → entrada única + caso‑workspace; "reduzir de 34 para ~10 módulos".
- O alicerce já existe e está bom: 4 estados com paridade testada, Entrada Única transacional e com gates, `CaseIntelligenceSnapshot` como ponto de convergência com campo `origem` já contemplando `raio_x` e `sala_juridica`.
- Nenhuma FK externa aponta para as tabelas da Sala; só uma (em código morto) consome as do Raio‑X por fora. O custo estrutural da reorganização é baixo.
- A janela pré‑operação segue aberta (nenhum caso real; mudança barata agora, cara depois).

**Contra (delimitam o *como*, não o *se*):**
- Fusão física de tabelas: 33 FKs, portal, contratos crus — custo alto, ganho imediato nulo. **Adiar.**
- `relatorio` sem tipo e telas de 1.500‑1.800 linhas: fusão de UI sem antes extrair componentes repetiria o erro que o desenho do Bloco 3 já alertou para o `CasoDetalhe`.
- Dois PRs abertos na área.

**Conclusão:** fundir **em três camadas, nesta ordem** — (1) serviço/contrato, (2) produto/navegação, (3) dados (opcional, depois da operação). É a ordem que entrega valor a cada fase e nunca deixa o sistema pior do que estava.

---

## 6. O plano

Cada fase é uma Issue + um PR (draft), com critérios de aceite objetivos. Fases F1a/F1b/F2 são pré‑lançamento (corrigem perda de dados no caminho crítico); F3/F4 idealmente pré‑lançamento (janela de navegação); F5 é pós‑operação. **Nenhuma fase começa antes do merge dos PRs #786 e #757.**

### F0 — Alicerces (sem mudança de comportamento)

1. Tipar o `relatorio` v2 do Raio‑X em Pydantic (`schemas/raio_x_relatorio.py`), adotado pelos 7 consumidores — congela o contrato antes de qualquer mexida.
2. Testes de regressão que hoje faltam no caminho crítico: conversão Sala→Caso (payload `descricao` → `descricao_fatos`, inclusive `resumo === ""`), conversão Raio‑X→Caso (campos transportados, snapshot), upload do Raio‑X (nenhum teste cobre `analisar_documentos` hoje; o teste de conversão só roda com `RUN_DB_TESTS=1` — avaliar promover ao CI).
3. Promover `_validar_conteudo` de `routers/documents.py` a serviço público (`services/upload_validacao.py`) — desfaz o import router→router privado em 2 lugares.

*Critério de aceite:* suíte verde; snapshot OpenAPI inalterado; zero mudança de comportamento.

### F1a — Correções P0 independentes da fusão (PRs pequenos, um por bug)

1. Conversão Raio‑X grava `proxima_acao` (derivada de `proximos_passos` do relatório, ou default como as demais portas) — desbloqueia o PATCH (§4.3‑1).
2. Wizard da Sala pré‑seleciona `area_sugerida`; fallback de fatos cobre string vazia (§4.3‑2/15).
3. `prazos_pendentes`: `Deadline.status == DeadlineStatus.pendente` + teste (§4.3‑4).
4. `PATCH /cases/{id}`: transição para `arquivado`/`encerrado` via PATCH passa a exigir os mesmos gates dos endpoints dedicados (ou é rejeitada com apontamento para eles); reabertura limpa os campos de desfecho (§4.3‑5).
5. Migration: `ondelete` (SET NULL) em `legal_chat_messages.ai_log_id`; purga de logs passa a **aferir resultado** (alerta quando 0 purgados com candidatos existentes) (§4.3‑6). *Reservar número em `MIGRATION_RESERVATIONS.md`; conferir `alembic heads` na hora.*
6. Rate‑limit em `reanalisar`, exports e previews do Raio‑X (paridade com a Sala) (§4.3‑10).
7. UI da Sala exibe `aviso_hitl`, `critica_adversarial` e `citacoes` (§4.3‑8) — HITL visível é regra de governança, não estética.

*Cada item com teste de regressão. `security-auditor` obrigatório nos itens 4‑6.*

### F1b — Um único serviço de criação de caso

Criar `services/caso_factory.py` (nome sugerido: `criar_caso_completo(db, user, origem, payload)`) com payload canônico, e **as quatro portas passam a chamá‑lo**:

- Efeitos garantidos em toda porta: G1 (`proxima_acao`), guarda anti‑duplicidade CNJ, `CaseMovimento` de abertura, `event_bus.emitir_caso_criado`, automação/triagem/kit (parametrizáveis), `CaseIntelligenceSnapshot` **sempre** (origem `manual` incluída), `AuditLog`, transação única (padrão da Entrada Única).
- Correção das perdas na conversão: `partes` → `CaseParte`; `pontos_fortes`/`pontos_fracos`/`tese_principal` → colunas do `Case`; `compactar_payload` deixa de descartar em silêncio (aviso explícito no snapshot).
- Telas manuais migram para transação única (fim do cliente órfão).
- Unificar o preview de conflito/duplicidade num serviço só, com o mesmo rate‑limit, e a mesma entrada no preview e na conversão (fim do 409 sobre alerta que o usuário nunca viu).

*Critério de aceite:* teste ponta a ponta por porta comparando o caso resultante — **as quatro portas produzem casos estruturalmente equivalentes** (mesmos efeitos colaterais, dados de origem preservados no snapshot). Zero mudança de contrato HTTP externo.

### F2 — Ingestão única de documentos

Extrair `services/documento_intake.py` (validação de extensão/tamanho/conteúdo, sha256, gravação em disco, chamada ao `extrair_e_analisar`, shape de retorno) e usar em Sala, Raio‑X e Entrada Única. Decidir **uma** política para as divergências hoje acidentais (nº máximo de arquivos, extensões, `enriquecer_rag`, retenção do texto extraído, tratamento de falha de extração) — proposta: o superset das extensões, `enriquecer_rag=True`, texto retido, falha anexa com aviso (comportamento da Sala, que degrada melhor).

*Critério de aceite:* os dois blocos duplicados somem; upload dos três fluxos passa pelos mesmos testes; comportamento divergente só onde documentado.

### F3 — Fusão de produto: o módulo único "Caso"

É a fusão que o titular pediu, na camada onde ela é visível:

1. **Navegação**: um único grupo/porta — `/entrada` ganha três modos: **Relatar** (colar relato/arrastar docs — atual), **Conversar** (a Sala Jurídica, embutida como modo), **Analisar autos** (o Raio‑X, embutido como modo). `sala-juridica` e `raio-x-processo` saem do menu como módulos independentes; `/sala-juridica` e `/raio-x` viram redirects (padrão já usado em `/sala-analise`). Depois da conversão, as mesmas ferramentas ficam acessíveis **de dentro do caso** (aba/ação no `CasoDetalhe`), fechando o modo contextual do Raio‑X do jeito certo.
2. **Vocabulário único de progresso**: os 4 estados são a única linha de estado; o orquestrador de 16 etapas vira checklist informativo derivado (ou é podado — decisão do titular, §8). A jornada de 9 etapas morre.
3. **Poda** (aproveitando a janela): jornada 9 etapas (~500 linhas), endpoints órfãos (~1.100 linhas), params/colunas/schemas mortos (§4.4), `backendPrefixes` corrigidos, timelines e scores reduzidos aos consumidos. Colunas mortas caem em migration própria (numeração reservada). Endpoints órfãos que o titular queira preservar "para o futuro" saem da OpenAPI e ganham Issue própria em vez de ficar.
4. **Pré‑requisito de engenharia**: antes de embutir modos, extrair componentes das três telas grandes (`SalaJuridica.tsx`, `RaioXProcesso.tsx` — mesma regra que o desenho do Bloco 3 impôs ao `CasoDetalhe`). Embutir 1.700 linhas dentro de outra página não é fusão, é empilhamento.

*Critério de aceite:* o critério do lançamento — um advogado abre o sistema e existe **uma** porta de entrada e **um** lugar onde o caso acontece; redirects preservam todo link antigo; testes de integridade de rotas do registry verdes.

### F4 — Ciclo de vida e LGPD unificados

1. Vocabulário único de estados pré‑caso para Sala e Raio‑X (`rascunho → em_analise → aguardando_conferencia → convertido | descartado | arquivado`), alinhado aos estados assíncronos do PR #786.
2. Job de expurgo por `retention_until` cobrindo `raio_x_analises` **e** `legal_chat_sessions` (que ganha retenção), removendo arquivos físicos no descarte/expurgo, com monitoramento **por resultado** (regra da casa).
3. Transferência de anexo por **move/hardlink** em vez de cópia dupla, com varredura de órfãos.

### F5 — Convergência de dados (adiada de propósito)

Fundir `raio_x_analises` + `legal_chat_sessions` numa tabela `pre_casos` (com `tipo`) e os anexos em `documents` com estágio: **só depois da operação estabilizada**. Depois de F1‑F4, essas tabelas são detalhe interno atrás de um contrato único — o ganho de fundi‑las é estético, e o risco (migração de dados + 4 telas + exports) é o maior do plano. Registrar como Issue de faxina futura, sem prazo.

### Sequenciamento e dependências

```
merge #786 e #757 ─→ F0 ─→ F1a (paralelo por item) ─→ F1b ─→ F2 ─→ F3 ─→ F4 ─→ (operação) ─→ F5?
```

F1a pode andar em paralelo com F0 (arquivos distintos por item). F3 é o único bloco de redesenho visível — os anteriores são invisíveis ao usuário e reversíveis um a um.

---

## 7. O que este plano deliberadamente NÃO faz

- **Não funde tabelas agora** (§6‑F5) — fundir por contrato primeiro.
- **Não reescreve as telas do zero** — extrai componentes e re‑hospeda.
- **Não remove a capacidade** de conversar (Sala) nem de análise preliminar (Raio‑X) — muda onde moram.
- **Não toca** em Peças, Prazos, GED, Financeiro além das fronteiras citadas.
- **Não mexe em `raio_x.py`** enquanto #786/#757 estiverem abertos.

## 8. Decisões que só o titular pode tomar

1. **Sala e Raio‑X como modos da entrada única** (recomendado) ou mantidos como itens de menu visíveis apontando para a mesma engine?
2. **Orquestrador de 16 etapas**: vira checklist derivado dentro do caso, ou é podado junto com a jornada de 9?
3. **Endpoints órfãos** (~1.100 linhas): podar agora (recomendado — janela aberta) ou só tirar da OpenAPI?
4. **Export do Raio‑X**: unificar no pipeline canônico de documentos (corrige acentuação e timbre) ou congelar como está até F5?
5. **RBAC do acervo**: `financeiro`/`secretaria` devem mesmo listar casos (`GET /cases/` hoje aceita qualquer papel interno)? A allowlist `EQUIPE_JURIDICA` existe e não é usada ali.
6. **F5** (fusão física de tabelas): manter como Issue futura sem prazo, ou descartar de vez?

## 9. Governança da execução

- Uma Issue por fase (F0, F1a‑item, F1b, F2, F3, F4), PR draft vinculado com `Closes #NNN`, correções de review no mesmo PR.
- Toda migration com número reservado em `backend/alembic/MIGRATION_RESERVATIONS.md` após conferir `python -m alembic heads`.
- `security-auditor` obrigatório em F1a‑4/5/6, F1b (gates de conversão) e F3 (mudança de rotas).
- Toda correção com teste de regressão; F1b com teste de equivalência entre portas; F3 com testes de integridade de rotas.
- Nenhum arquivo de PR ativo é tocado por outra fase; conflito de sequenciamento resolve‑se esperando o merge, nunca duplicando correção.

## 10. Achados fora do escopo da fusão (viram Issues próprias)

1. FK `ai_log_id` × purga LGPD (F1a‑5 já cobre, mas o padrão "purga sem aferir resultado" merece varredura nas demais purgas).
2. Herança de visibilidade pós‑exclusão limitada a peças (§4.3‑13) — prazo de caso excluído continua alertando.
3. N+1 em `ranking_saude` e `/resumo` (§4.3‑14).
4. Kit documental em duas sessões sem atomicidade com o `AuditLog` (§4.3‑12).
5. Vocabulário de `resultado` divergente entre schema e model (§4.3‑P2).
6. Texto desatualizado no `CLAUDE.md` sobre `ativo`/`all` (§4.4).
7. `GET /system-modules/mapa` e afins não foram reauditados aqui (armadilha conhecida — fica como está).
