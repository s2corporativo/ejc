# Auditoria — Clientes (módulo e ramificações)

- Data: 2026-10-01 · Base: `40144d6` + relatório da Entrada Jurídica (branch `claude/blissful-darwin-nr2i2v`)
- Método: leitura estática de código. **Nada foi executado** (sem testes, sem banco, sem navegador). Achados são afirmações sobre o código lido; os marcados "a reproduzir" exigem teste antes de qualquer correção.
- Contexto: o módulo já passou por auditorias anteriores (ago/2026, `test_clientes_auditoria_*`). Este relatório não repete achados já corrigidos; procura o que escapou a elas.

## 1. Escopo e mapa

| Camada | Arquivos lidos |
|---|---|
| Routers | `routers/clients.py` (inteiro), `dossie_cliente.py`, `pending_items.py`, `relatorio_cliente.py`, `lgpd_registros.py` (RBAC/ownership), `sociedades_cliente.py` (RBAC/ownership), `sumulas.py` (endpoint de conflito), `portal.py` (inventário de rotas) |
| Core/Models/Schemas | `core/client_ownership.py`, `models/client.py`, `schemas/client.py`, `core/auth_middleware.py` (trecho do portal) |
| Services | `client_anonimizacao.py`, `conflito_service.py`, `conflito_interesses.py`, `pii_crypto.py` |
| Frontend | `pages/Clientes.tsx` (linhas 1–330 e grep do restante), `pages/DossieCliente.tsx` (trechos), `pages/CRMLeads.tsx` (grep), `moduleRegistry.tsx` (rotas `clientes`, `cliente-detalhe`, `crm`, `cadastro-manual`) |
| Testes | apenas o inventário (≈35 arquivos `test_client*`/`test_clientes*`/`test_portal*` etc.) e cabeçalhos de 3 deles |

**Não lidos em profundidade** (lacunas declaradas): corpo de `Clientes.tsx` (linhas 330–1059), `DossieCliente.tsx` (≈1.700 linhas), `CadastroManual.tsx`, `ClienteIaPanel`, `VerificarReceita`/Infosimples (consulta externa de CNPJ), `geracao_documental_cliente.py`, `cobranca_cliente_service.py`, `party_identity_service.py`, `portal.py`/`portal_documentos.py` (só inventário; existe suíte IDOR dedicada), corpo de `sociedades_cliente.py` e `lgpd_registros.py`, migrations/índices de `clients`.

Superfície de API do módulo: `/clients` (CRUD, `resolver`, `verificar-conflito`, `checar-conflito`, `gerar-documentos`, `pecas-geradas`, `ia-analise`, `criar-acesso`, `relatorio-lgpd`, `dados-lgpd.json`, `esquecimento`), `/clients/{id}/dossie`, `/clients/{id}/pending-items`, `/clients/{id}/relatorio-financeiro`, `/empresarial/sociedades`, `/lgpd/registros`, `/portal/*` e — fora do prefixo — `/sumulas/verificar-conflito`.

## 2. Pontos conformes (verificados no código)

- Gate de titularidade canônico (`client_ownership`) usado na listagem, detalhe, escrita, IA, portal-acesso, dossiê, pendências, relatório financeiro e sociedades; 404 uniforme para carteira alheia.
- CPF/CNPJ somente cifrados (Fernet) + HMAC cego; unicidade por índice parcial; resposta comum devolve documento mascarado (`ClientResponse`); decifra resiliente (uma linha ruim não derruba a lista).
- `/checar-conflito` e `/clients/verificar-conflito`: rate limit, máscara de documento, escape de wildcard (`_padrao_like`), piso de 4 caracteres, auditoria.
- Audit WORM sem nome/documento nos eventos de cliente (`CREATE_AUTO`, `PORTAL_ACESSO_CRIADO`, `ANONIMIZAR_LGPD` com vocabulário controlado).
- Exclusão: bloqueio com caso em representação ativa (`forcar` auditado) e desativação do login do portal.
- Anonimização: bloqueio por representação ativa e por documento de admissão consolidado (não sobreponível por `forcar`), justificativa obrigatória no override, `motivo` livre não persistido no WORM.
- Kit de admissão automático respeita piso de advogado, não emite para `lead` (minimização) e degrada sem desfazer o cadastro.
- Portal: `cliente_externo` confinado a `/api/portal/*` pelo `AuthMiddleware`; rotas filtram por `cu.client_id`.
- Relatório LGPD/portabilidade restritos a sócio+ e auditados.

## 3. Achados

Severidade: **A** alta · **M** média · **B** baixa. "Conf." = certeza após a leitura.

| # | Sev | Conf. | Achado | Evidência |
|---|---|---|---|---|
| C1 | A | Alta (a reproduzir) | **`POST /sumulas/verificar-conflito` vaza CPF/CNPJ em claro de qualquer cliente, para qualquer usuário autenticado.** O endpoint exige só `get_current_user` (sem `_req_clientes`, sem rate limit, sem gate de carteira) e delega a `conflito_interesses.verificar_conflito`, que devolve `documento` = `documento_plain` dos clientes casados por nome (ILIKE, 4+ caracteres) ou documento. É exatamente a superfície que `/clients/verificar-conflito` e `/checar-conflito` já mascaram e limitam (Achado 3 da auditoria de ago/2026), mas esta cópia ficou de fora. Permite reconstruir a base de documentos por consultas de nome, inclusive de carteiras alheias e por perfis sem acesso ao CRM (estagiário, financeiro). Sem consumidor no frontend (nenhuma chamada em `frontend/src`). | `sumulas.py` l.103-117; `conflito_interesses.py` l.51-69, 71-83; `clients.py` l.178-226 (versão protegida) |
| C2 | A | Alta (a reproduzir) | **Dossiê de cliente PJ sem nome.** `GET /clients/{id}/dossie` seleciona só `nome` (nulo em PJ, que usa `razao_social` — vide `resolver` e `criar`), e `DossieCliente.tsx` usa `cliente.nome` no título, nas mensagens de WhatsApp/e-mail/ligação e no aviso de acesso; o formulário de edição exige `nome` preenchido, bloqueando a edição de contatos de PJ. | `dossie_cliente.py` l.99-103; `DossieCliente.tsx` l.692-739, 1042-1059, 1295 |
| C3 | A | Alta | **Anonimização não anonimiza o usuário do Portal.** Para `User.client_id == cliente`, apenas `is_active=False`; `email` e `full_name` (nome do cliente, copiado de `c.nome`) permanecem em `users`. O docstring afirma que a PII "NÃO é recuperável". Direito ao esquecimento (LGPD art. 18, VI) fica incompleto. | `client_anonimizacao.py` l.223-229, 8-10; `clients.py` l.999 |
| C4 | M | Alta | **Cliente anonimizado pode ter a PII recadastrada.** `anonimizado_em` não é consultado em `PATCH /clients/{id}`, `criar-acesso`, `gerar-documentos` nem no detalhe; um PATCH repõe nome, e-mail, CPF e gera novo hash, desfazendo a anonimização sem trilha de "reidentificação". | `clients.py` l.816-900; `client_anonimizacao.py` |
| C5 | M | Alta | **Texto livre com dados do titular sobrevive à anonimização:** `Case.titulo`/`descricao_fatos`, títulos e `ocr_text` de documentos, `client_pending_items` (title/description, sem FK), `fees.descricao`, interações/atendimentos, `parte_contraria` de outros casos. A retenção do caso é legítima (LGPD art. 16, II), mas o sistema não distingue o que fica por obrigação legal do que deveria ser redigido, e a mensagem de sucesso não declara a limitação. Exige decisão do titular. | `client_anonimizacao.py` l.156-229; `pending_items.py` |
| C6 | M | Alta | **RBAC divergente entre o router e as ramificações.** `/clients/*` aplica a matriz `_CLIENTES` (estagiário, advogado_auxiliar e financeiro recebem 403), mas `dossie`, `pending-items`, `sociedades` (leitura) e `lgpd/registros` aceitam qualquer usuário interno com vínculo à carteira (`get_current_user`/`cliente_externo` excluído). Um estagiário vinculado a um caso lê o dossiê (inclui honorários e prazos) e edita pendências de um cliente cuja ficha o próprio `/clients/` lhe nega. O teste `test_clientes_rbac_matrix_20260902` cobre só o CRUD e o relatório financeiro. | `dossie_cliente.py` l.89-93; `pending_items.py` l.168-175; `sociedades_cliente.py` l.59-67; `lgpd_registros.py` l.81-86; `clients.py` l.38-51 |
| C7 | M | Média | **Dossiê consolida por cliente e ignora os gates por caso e por documento.** Lista todos os casos do cliente (inclusive de outro advogado) sem `pode_ver_caso_resumido` e os 10 documentos mais recentes sem `confidencialidades_visiveis` (política do cofre). Hoje a decisão ("visão consolidada por CLIENTE") é documentada, mas coexiste com filtros por caso/confidencialidade em outros fluxos (Entrada, dossiê jurídico). Títulos de documentos sigilosos podem aparecer a quem não os acessa. | `dossie_cliente.py` l.32-72, 106-113 |
| C8 | M | Alta | **Quatro implementações de conflito com cobertura divergente.** `detectar_conflito` (usada em `/clients/verificar-conflito`, `criar`, conversão de caso), `/checar-conflito` (lógica inline + `case_partes`), `conflito_interesses.verificar_conflito` (rota `sumulas`) e `entrada_service.analisar_conflito`. Só `/checar-conflito` consulta `case_partes`; as demais cruzam apenas `Case.parte_contraria` (texto livre). O casamento por nome é `ILIKE %nome%` sem normalização de acentos/caixa/ordem ("José"≠"Jose", "Silva, Maria"≠"Maria Silva"), com `limit` sem `ORDER BY`: falso-negativo possível numa checagem ética (EOAB 34-35). Docstring diz "clientes ATIVOS", mas o filtro inclui lead/inativo/arquivado (o comportamento é o correto; o texto é que está errado). | `conflito_service.py` l.37-113; `clients.py` l.323-392; `entrada_service.py` l.370-434 |
| C9 | M | Alta | **Cadastro de cliente não exige reconhecimento de conflito.** A tela chama `/checar-conflito` em `onBlur` (assistivo) e `POST /clients/` descarta o resultado de `detectar_conflito` (só grava em audit); o conflito crítico não bloqueia nem pede confirmação, enquanto a Entrada Única exige `conflict_confirmed` no servidor. A própria orientação do sistema diz que conflito grave "só prossegue com aprovação de sócio", sem mecanismo que a registre. | `clients.py` l.487-526; `Clientes.tsx` l.588, 617, 738, 755-808; `entrada_service.py` l.961-971 |
| C10 | M | Média | **`POST /clients/resolver` diverge de `criar`:** não valida dígito verificador, trunca CPF a `[:11]` e CNPJ a `[:14]` sem rejeitar excesso, não roda `detectar_conflito`, cria PF sem nome. Para documento de carteira alheia responde 404 (e não cria), enquanto `criar` responde 409 "CPF/CNPJ já cadastrado" — oráculo de existência de documento entre carteiras. | `clients.py` l.100-171, 527-531 |
| C11 | M | Média | **Acesso ao Portal por senha definida pelo operador.** `criar-acesso` recebe `senha_inicial` digitada pelo advogado (conhecida do operador até a troca, que é forçada), sem convite por token/link de uso único. Resposta 409 "E-mail já cadastrado no sistema" enumera e-mails de usuários internos; a checagem é não atômica (corrida → `IntegrityError` não tratado, a verificar se há UNIQUE em `users.email`). Não impede acesso para lead/anonimizado. | `clients.py` l.961-1015 |
| C12 | M | Alta | **Chave de PII sem rotação.** `pii_crypto` usa um único `Fernet` (`PII_ENCRYPTION_KEY`) e um único HMAC (`PII_HASH_KEY`); `vault_crypto` já usa `MultiFernet.rotate`, mas `pii_crypto` não. Troca de chave transforma toda a base em `[documento indisponível]` e quebra dedup/conflito; não há runbook/script de rotação. | `pii_crypto.py` l.42-87; `vault_crypto.py` l.24-68 |
| C13 | M | Alta | **Exclusão (soft delete) retém PII para sempre.** `DELETE /clients/{id}` só preenche `deleted_at`; `cpf_enc`, nome, e-mail etc. permanecem sem prazo de retenção/expurgo nem caminho automático para anonimizar. | `clients.py` l.903-950; `models/client.py` |
| C14 | M | Média | **Portabilidade (art. 18, V) incompleta.** `dados-lgpd.json` e o PDF cobrem casos, documentos (só título/data) e honorários; omitem partes estruturadas, pendências, sociedades, registros ROPA, atendimentos/interações, assinaturas, usuário do portal e registros de IA. | `clients.py` l.1018-1142 |
| C15 | B | Média | **RIPD: download sem vínculo ao cliente/usuário.** Qualquer usuário interno que obtenha o UUID baixa o PDF (que nomeia o cliente); a limpeza TTL só roda ao gerar novo RIPD; mensagem 503 ecoa `{exc}`. | `lgpd_registros.py` l.374-430 |
| C16 | B | Alta | **Custo desnecessário na listagem:** cada linha decifra CPF/CNPJ só para mascarar (até 500 linhas; `CRMLeads` pede `page_size=500`); `search` usa `ILIKE %…%` sem escape de `%`/`_` e sem limite de tamanho. | `schemas/client.py` ClientResponse; `clients.py` l.423-441; `CRMLeads.tsx` l.111 |
| C17 | B | Alta (a reproduzir) | **CRM de leads:** limite silencioso de 500; após converter, o card sai da lista (`status=ativo`) e o KPI "convertidos/taxa" é calculado só sobre o que sobrou (tende a zero após recarregar); `etapa_funil` e `status` não têm coerência imposta no servidor (ex.: `status=ativo` com etapa `lead`). | `CRMLeads.tsx` l.111, 155-161, 180-184; `schemas/client.py` |
| C18 | B | Alta | **Schemas sem limites de tamanho** (`observacoes` Text, `nome`, `profissao`, `numero`, etc.); `estado` sem validação de 2 letras; PF aceita CNPJ e vice-versa; DataError vira 422 genérico (mensagem pouco útil). | `schemas/client.py` |
| C19 | B | Alta | **Pendências do cliente:** `SELECT *` sem paginação, `description` sem `max_length`, `client_id` sem FK (já reconhecido no código), sem gate de papel. | `pending_items.py` l.184-198, 59-63 |
| C20 | B | Média | **`/checar-conflito` expõe `client_id`, `case_id` e título do caso de carteiras alheias** (a justificativa documentada cobre o nome, não o título do caso, que costuma conter nomes); auditoria é "fail-safe" (engolida) aqui e obrigatória (500) em `/verificar-conflito`. | `clients.py` l.285-392, 394-402 |

## 4. Plano de melhoria, correção e consolidação

Premissas: PRs pequenos por frente; correção de bug entra com teste de regressão (CLAUDE.md §7); mudança em auth/permissões/uploads/config passa por `security-auditor` antes de finalizar (§8); migration só quando indicado, com reserva em `MIGRATION_RESERVATIONS.md` e `alembic upgrade head` do zero; rota removida/alterada atualiza `test_rotas_registro_explicito.py` e o ledger (`backend/scripts/ledger_rotas.py --verificar`). Nada enfraquece HITL, RBAC, sanitização de PII ou kill-switch.

### Fase 0 — Reproduzir e decidir (sem código de produção, ≈1 dia)
1. Reproduzir **C1** (usuário `estagiario` chama `/sumulas/verificar-conflito` e recebe documento em claro de cliente de outra carteira), **C2** (dossiê de PJ) e **C3** (e-mail/nome do usuário do portal após `esquecimento`).
2. Confirmar `users.email` UNIQUE (C11) e a tabela real de `client_pending_items`/`atendimentos` para o inventário de C5/C14.
3. Decisões do titular (bloqueiam fases posteriores): política de retenção/redação de texto livre (C5/C13, LGPD art. 16); dossiê por cliente vs por caso/confidencialidade (C7); conflito crítico exige confirmação/aprovação de sócio no cadastro (C9); fluxo de convite do portal (C11).

### Fase 1 — Correções urgentes (alta severidade)
| Item | Ação | Teste de regressão |
|---|---|---|
| C1 | Preferência: **remover** `/sumulas/verificar-conflito` (sem consumidor no frontend; atualizar baseline de rotas e ledger) e mover o chamador legítimo, se existir, para `/clients/verificar-conflito`. Alternativa: manter com `_req_clientes`, rate limit, máscara e `criar_audit_log` sem nome/documento. Em qualquer caso, substituir o `INSERT` cru em `audit_logs` (que grava nome e CPF/CNPJ da parte contrária no WORM, sem `user_role`/`ip`) por `criar_audit_log` com vocabulário controlado. | role sem acesso → 403/404; documento nunca em claro; `detalhes` sem PII |
| C2 | Incluir `razao_social`/`nome_fantasia` no SELECT do dossiê e devolver `nome_exibicao`; `DossieCliente.tsx` e o formulário de edição passam a usar o nome de exibição e a editar `razao_social` para PJ. | dossiê PJ devolve nome; edição de contato de PJ salva |
| C3 | Anonimizar o usuário do portal na mesma transação: `email` → placeholder único, `full_name` → marcador, credencial invalidada, sessões/refresh revogados; corrigir o docstring. | `users` sem PII após `esquecimento` |

### Fase 2 — Integridade de acesso e ciclo de vida
- **C4:** `409` em PATCH/`criar-acesso`/`gerar-documentos` quando `anonimizado_em` está preenchido; reabertura só por ato explícito de gestão, auditado.
- **C6:** criar dependência única (`requer_clientes_leitura`, hoje duplicada em `clients.py`) e aplicar a `dossie`, `pending-items`, `sociedades` (leitura) e `lgpd/registros`; estender `test_clientes_rbac_matrix` a essas rotas. Decisão registrada: estagiário/auxiliar com vínculo a caso continuam vendo o cliente **pelo caso**, não pela ficha do CRM.
- **C7:** conforme decisão da Fase 0, aplicar `confidencialidades_visiveis` aos documentos do dossiê e `pode_ver_caso_resumido` aos casos (ou rotular explicitamente "visão do cliente").
- **C9:** `POST /clients/` aceitar `conflict_confirmed` e responder 409 com os achados quando houver conflito crítico sem confirmação (paridade com a Entrada Única); registrar quem confirmou.
- **C10:** `resolver` passa a reutilizar a validação e o `detectar_conflito` de `criar`; unificar 404/409 para não ser oráculo de documento.
- **C11:** trocar senha digitada por convite de uso único (link com token e expiração) ou, no mínimo, gerar a senha no servidor e exibi-la uma única vez; tratar `IntegrityError` (409 genérico); bloquear para lead/anonimizado.

### Fase 3 — Consolidação do conflito de interesses (C8, C20)
- Uma única implementação em `conflito_service` (documento por HMAC, nome normalizado sem acento/caixa e tokenizado, `case_partes` + `Case.parte_contraria`, `ORDER BY` determinístico, mesmo critério de gravidade) com **formatadores** por consumidor; as quatro entradas atuais passam a delegar.
- Se for adotado `unaccent`/índice trigram: migration própria (reservar número), revisão manual do autogenerate, `alembic upgrade head` do zero em PostgreSQL 16.
- Alinhar o contrato de PII dos achados: nome sim, documento sempre mascarado; decidir se título de caso de carteira alheia sai (C20). Tornar a auditoria obrigatória e uniforme.
- Testes: casos com acento, ordem invertida, homônimos, `case_partes` sem `parte_contraria`, falso-negativo histórico.

### Fase 4 — Ciclo de vida de dados e chaves (C5, C12–C15)
- **C12:** migrar `pii_crypto` para `MultiFernet` (chave primária + legadas), script de recifragem em lote e runbook; plano de rotação do HMAC (dupla escrita de hash durante a transição).
- **C13/C5:** com a decisão do titular, política de retenção para `deleted_at` (anonimizar ou expurgar após prazo) e redação de texto livre sob retenção legal; mensagem de sucesso da anonimização declara o que foi mantido e a base legal.
- **C14:** completar o JSON/PDF de portabilidade (partes, pendências, sociedades, ROPA, atendimentos, assinaturas, usuário do portal, registros de IA).
- **C15:** vincular o download do RIPD ao usuário/cliente que o gerou e mover a limpeza TTL para job.

### Fase 5 — Desempenho e qualidade (C16–C19)
- Mascarar a partir de coluna derivada/`last4` ou calcular a máscara sob demanda em vez de decifrar toda linha; `escape` e limite de tamanho no `search`.
- CRM: paginação/cursor, KPI de conversão baseado em contagem do servidor, coerência `status`↔`etapa_funil` no schema.
- `max_length` e validações PF/PJ/UF nos schemas; paginação e limites nas pendências.

### Fase 6 — Lacunas desta auditoria (próxima rodada)
`Clientes.tsx` (restante), `DossieCliente.tsx`, `CadastroManual`, `VerificarReceita`/Infosimples (consulta externa de CNPJ: egress de PII, flag/degradação), `geracao_documental_cliente`, `cobranca_cliente_service`, `party_identity_service`, corpo de `portal*`, `sociedades`, `lgpd_registros`, e cobertura real da suíte `test_client*`. Acionar `security-auditor` antes de fechar as Fases 1, 2 e 3.

### Portões de verificação
- Backend (Fases 1–5): `ruff check app` + pytest da área + suíte completa uma vez antes do push; testes de banco com `RUN_DB_TESTS=1`; migration → `alembic upgrade head` do zero em PostgreSQL 16 + pgvector.
- Frontend (C2, C9, C17): `npm run lint && npm test && npm run build`.
- Remoção/alteração de rota (C1): `backend/scripts/ledger_rotas.py --verificar` e atualização do baseline em `test_rotas_registro_explicito.py`.
- Deploy: somente pela esteira / `RUNBOOK_DEPLOY_MANUAL.md` (CLAUDE.md, regra 9).

## 5. Limitações
Análise estática; sem execução, sem acesso a produção e com as lacunas da seção 1. C1, C2, C3 e C17 devem ser reproduzidos antes da correção; C11 depende de confirmar a constraint de `users.email`; C5, C7, C9 e C13 dependem de decisão do titular (regras de negócio e retenção), não de simples correção técnica.
