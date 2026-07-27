# Auditoria Funcional Módulo-a-Módulo — EJC v3

**Data:** 2026-07-19
**Escopo:** Auditoria funcional item-por-item de todos os módulos do backend (163 routers, 131 services, 4 pacotes de módulo) cruzando **módulo × função × perfil × resultado**, caça a **IDOR/RBAC entre casos/clientes/carteiras**, e inventário de **mocks/placeholders** (substituição por função real ou indicação explícita de indisponibilidade).
**Método:** 9 auditorias estáticas por domínio (orientadas por `graphify`, somente-leitura) + confirmação direta do núcleo RBAC e do `AuthMiddleware` + teste dinâmico com dados fictícios (smoke E2E). Cada achado cita `arquivo:linha`.

---

## 1. Sumário executivo

O EJC está, no geral, **maduro e bem defendido** em segurança de acesso — reflexo das correções de auditorias anteriores (Fase 3A de ownership, `commit 1c7285d` de sigilo de cliente, pente-fino 2026-07). Os invariantes centrais se sustentam:

- **Gate de ownership de caso** (`core/ownership.py::verificar_acesso_caso`) é aplicado de forma consistente na esmagadora maioria dos sub-recursos de caso (prazos, tarefas, provas, peças, documentos, honorários por caso, inteligência, etc.), inclusive revalidando o caso pai em rotas por-id-de-sub-recurso.
- **Isolamento do Portal do Cliente**: o `AuthMiddleware` (auth_middleware.py:128-148) confina `cliente_externo` a uma allowlist EXATA (`/api/portal/`, `/api/auth/`, `/api/health`, `/api/notifications`, `/api/signatures`, `/api/users/me`). **Nenhum dado interno do escritório é alcançável pelo portal**, mesmo com token válido. Isso mitiga, na origem, toda uma classe de achados "cliente_externo alcança X".
- **IA sempre via `ai_gateway`** (nenhum router chama provider direto); sanitização de PII, HITL e citation gate presentes nos fluxos reais.
- **PII de cliente** (CPF/CNPJ) cifrada em repouso (Fernet + HMAC cego).

Os achados residuais concentram-se em **(a) IDOR de leitura/escrita entre carteiras em alguns endpoints de listagem sem escopo**, **(b) pisos de perfil (RBAC) ausentes em endpoints internos** e **(c) um pequeno conjunto de mocks enganosos** que fingem sucesso/dados reais. Não foi encontrado nenhum vazamento crítico ao portal do cliente nem violação de invariante de IA.

**Contagem de achados:** 3 médio-alto · 9 médio · 8 baixo · 4 mocks enganosos · 2 rótulos enganosos. Nenhum crítico não-mitigado.

---

## 2. Perfis (fonte da verdade: `core/security.py:27`)

| Perfil | Nível | Observação |
|---|---|---|
| superadmin | 9 | Acesso total |
| admin | 8 | Administração |
| socio | 7 | Gestão (`is_gestao` ≥ socio) — vê/edita todos os casos |
| **advogado** | **6** | Equipe jurídica |
| advogado_auxiliar | 5 | Equipe jurídica de apoio |
| **financeiro** | **4** | **Abaixo de advogado/auxiliar** — daí gates financeiros usarem *allowlist explícita*, não nível |
| estagiario | 3 | Piso de "staff" (`_is_staff`) |
| secretaria | 2 | Recepção/CRM |
| cliente_externo | 1 | Portal — confinado pelo middleware |

**Semântica de `require_roles(allowed)` (security.py:196):** concede se `role ∈ allowed` **OU** `nível ≥ min(nível dos roles em allowed)`. Consequência: incluir um perfil de nível baixo na lista alarga o acesso a todos os perfis acima daquele mínimo. Os módulos sensíveis (financeiro, clientes) evitam a armadilha usando **checagem por pertencimento exato** de conjunto (`_FINANCEIRO_TOTAL`, `_CLIENTES`).

---

## 3. Matriz módulo × função × perfil × resultado (resumo por domínio)

Legenda: ✓ acesso · ✗ 403 · △ acesso sujeito a ownership do caso (responsável/auxiliar/gestão/órfão) · — bloqueado pelo middleware (cliente_externo).

### D1 — Auth / Users / Portal / Notificações / Cofre / API-keys
| Função | super | admin | socio | fin | adv | aux | est | sec | cli_ext |
|---|--|--|--|--|--|--|--|--|--|
| /auth/*, /users/me, /notifications | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| /users CRUD, /api-keys | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — |
| /cofre-credenciais/** (superadmin + step-up) | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — |
| /portal/** (casos/docs/mensagens) | — | — | — | — | — | — | — | — | ✓ (só do próprio client_id) |
**Resultado:** SÓLIDO. Isolamento por `client_id` fecha IDOR de portal. Sem mocks. Achado baixo: `GET /users/{id}/avatar` legível por qualquer interno.

### D2 — Clientes / Intake / CRM / Societário-cliente
| Função | super | admin | socio | fin | adv | aux | est | sec | cli_ext |
|---|--|--|--|--|--|--|--|--|--|
| GET/POST /clients (matriz `_CLIENTES`) | ✓ | ✓ | ✓ | ✗ | ✓ (carteira) | ✗ | ✗ | ✓ | — |
| **PATCH /clients/{id}** | ✓ | ✓ | ✓ | ✗ | ✓ **(sem ownership → IDOR)** | ✗ | ✗ | ✓ **(idem)** | — |
| DELETE /clients/{id} | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | — |
| /contratos-societarios/* | ✓ | ✓ | ✓ | ✗ | ✓ **(sem escopo → IDOR)** | ✗ | ✗ | ✗ | — |
| /triagem, /intake, /conversao, /entrada-universal | ✓ | ✓ | ✓ | △ | △ | △ | △ | ✗ | — |
**Resultado:** núcleo `clients` blindado na LEITURA; lacuna residual na ESCRITA (ver §4-A1). Sem mocks.

### D3 — Casos / Sub-recursos / Jornada / Sala-de-guerra / Ramos
Base: `verificar_acesso_caso` → super/admin/socio ✓; equipe △; cliente_ext —. Sub-recursos (provas, partes, etiquetas, processos, movimentos, inteligência) todos gateados. **Sem IDOR explorável em rota registrada.** Achado latente: router morto `modules/case_partes/router.py` sem gate; achado baixo: `indice_risco/recalcular` sem piso de role.

### D4 — Prazos / Agenda / Tarefas / Intimações / Checklists / Workflow / Timesheet
Maioria com ownership (agenda_eventos, atividades, tasks, intimacoes, checklists, workflow, timesheet). **Achados:** `GET /deadlines` e `/deadlines/export.csv` **sem escopo de caso** (IDOR de leitura); `DELETE /deadlines/{id}` com lockout de superadmin; `calendar_feed` token permanente não-revogável.

### D5 — Documentos / DataRoom / Assinaturas / Peças / Templates
GED e Peças bem defendidos (`_verificar_acesso_documento` + cofre + `verificar_acesso_caso`). Assinaturas isoladas por `client_id`. **Achado:** `data_room.py` operações de SALA sem gate de ownership (metadados/links de outra carteira). `data_room_v4` é stub.

### D6 — IA / RAG / Governança / Prompts / Busca
Invariante de gateway respeitado; ownership presente. **Achados (mocks):** `curadoria_renomada.py` (router inteiro fake), `cerebro.py::/jurisprudencia/pesquisa` (retorna vazio "simulado"). Comentários "simulado" enganosos em `teses_v4.py`/`search.py` sobre código real.

### D7 — Financeiro
Allowlist explícita `_FINANCEIRO_TOTAL` correta. **Achados:** `centro_custos` lista custos de todos os casos quando `case_id` omitido (IDOR); `partner_withdrawals` permite auto-aprovação de saque (SoD); `pix/cobranca` sem piso de perfil. Cálculos (CET, rentabilidade) são REAIS.

### D8 — Integrações externas
Webhook (`evolution`) valida segredo; integrações pagas gateadas + rate-limit. **Achados:** `consumidor_monitor` (mock "dados SENACON"); `environmental` lista todos sem escopo; `whatsapp` qrcode/chats/messages sem piso; `datajud` process lookup sem rate-limit.

### D9 — Admin/Governança + Conhecimento/Jurimetria/Ramos-cálculo
Sensíveis (audit/backup/lgpd/cofre) restritos corretamente. **Achados (staff amplo):** `dashboard` agregações não escopadas; `wiki`/`teses-v4` editáveis por qualquer staff; `trabalhista`/`tributario` sem gate jurídico. **Mock:** `ramos.py:290` valor CADE hardcoded. Motores de cálculo são REAIS e honestos (retornam `null`+observação quando falta dado).

---

## 4. Achados IDOR/RBAC consolidados (ranqueados)

| # | Sev | Arquivo:linha | Achado | Correção |
|---|---|---|---|---|
| A1 | **Médio/Alto** | clients.py:595 | PATCH `/clients/{id}` sem `_pode_ver_cliente` → advogado edita (regrava CPF/CNPJ) cliente fora da carteira | add gate `_pode_ver_cliente` (404) |
| A2 | **Médio/Alto** | centro_custos.py:92 | `GET /centro-custos` sem `case_id` não filtra escopo → custos de todos os casos | escopar por casos visíveis |
| A3 | **Médio** | deadlines.py:73-77,102 | `GET /deadlines` e `/export.csv` sem escopo de caso → prazos de todos os casos | filtro de ownership por default |
| A4 | **Médio** | data_room.py:139,190,247+ | operações de SALA sem gate de ownership → metadados/links de outra carteira | gate de ownership de sala |
| A5 | **Médio** | contratos_societarios.py:95+ | sem escopo por cliente/caso → qualquer advogado edita contrato de qualquer cliente | filtro por titularidade ou socio+ |
| A6 | **Médio** | partner_withdrawals.py:94-163 | socio aprova/paga a própria retirada (sem SoD) | bloquear `approved_by == partner_id` |
| A7 | **Médio** | whatsapp.py:66,106,123 | qrcode/chats/messages sem piso → estagiário controla sessão/lê conversas | piso admin/socio (qrcode) + staff |
| A8 | **Médio** | environmental.py:57 | listagem sem piso nem ownership → todos os autos a qualquer staff | piso advogado + filtro ownership |
| A9 | **Médio (latente)** | modules/case_partes/router.py | router morto duplicado sem `verificar_acesso_caso` (PII) | remover dead code |
| B1 | Baixo | deadlines.py:310 | `DELETE /deadlines` tupla literal exclui superadmin/financeiro (lockout) | usar `requer_advogado` |
| B2 | Baixo | indice_risco.py:48 | `POST /recalcular` sem piso de role (irmãos usam `_ADV`) | alinhar a `_req_adv` |
| B3 | Baixo | pix.py:49 | `POST /pix/cobranca` sem piso → qualquer interno gera PIX do escritório | piso `_FINANCEIRO_TOTAL`/advogado+ |
| B4 | Baixo | datajud.py:19 | `GET /process/{cnj}` sem rate-limit nem piso | rate-limit + piso advogado |
| B5 | Baixo | wiki.py:59,69 / teses_v4.py:60,77 | escrita/leitura sem piso staff (só DELETE gateado) | piso `_is_staff` |
| B6 | Baixo | trabalhista_liquidacao.py:136 / tributario_fiscal.py:103 | ferramentas de ramo sem gate jurídico | `JURIDICO_ROLES`/`_EQUIPE` |
| B7 | Baixo | dashboard.py:37 | agregações office-wide sem piso staff | piso `estagiario` |
| B8 | Baixo | calendar_feed.py | token permanente não-revogável | salt/versão por usuário |
| B9 | Baixo | evolution_webhook.py:25 | segredo aceito via query string (log leak) | preferir header |

---

## 5. Inventário de mocks/placeholders e disposição

| Arquivo:linha | Natureza | Disposição |
|---|---|---|
| curadoria_renomada.py:22-41 | **Mock enganoso** — `/teses`→[], `/sincronizar`→fake "sucesso", `/analise-vencedora`→string fixa | → 503 indisponível explícito |
| cerebro.py:70-73 | **Mock enganoso** — `/jurisprudencia/pesquisa` retorna vazio "simulado" | → 503 indisponível explícito |
| consumidor_monitor.py:33-129 | **Mock enganoso** — dict hardcoded rotulado "dados públicos SENACON"; httpx morto | → rotular constantes internas + remover imports mortos |
| ramos.py:290 | **Rótulo enganoso** — "R$ 85.000 (tabela CADE 2026)" hardcoded | → rotular "estimativa a confirmar" |
| teses_v4.py:94 | **Rótulo enganoso** — comentário "simulado" sobre código real | → corrigir comentário |
| motor_peca.py:337 | Marcador HITL `[VERIFICAR]` intencional | Manter |
| data_room_v4.py:18-71 | Stub incompleto (sem download/token) | Concluir ou remover do registro |
| Degradação graciosa (datajud/pncp/infosimples/car/nfse/whatsapp/radar/noticias) | Opt-in flag OFF → 503/[] honesto | Manter (padrão do repo) |
| calc/cet.py, rentabilidade.py, previdenciario_beneficio.py, liquidacao_trabalhista.py, jurimetria.py | Cálculo REAL (não-mock) | Manter |

---

## 6. Teste dinâmico com dados fictícios

Stack mínima **de pé de verdade**: Postgres 16 + pgvector local (Docker Hub bloqueado por egress → contorno com cluster local, no espírito de `scripts/ci-local.sh`) + backend FastAPI (`uvicorn --workers 1`, `alembic upgrade head` OK, `/api/health` 200, admin semeado). O smoke oficial `qa/e2e/run_fictitious_smoke.py` rodou contra a API real.

**Resultado: 42 passos — 41 PASS, 1 FALHA dura.** Fluxos de escrita reais exercitados: criar cliente (201), criar caso, upload+classificar documento (201/200), movimento/patch de caso, `/users/me`, mapa de módulos, diagnóstico.

**Bug funcional REAL encontrado (corrigido neste PR):**
- `PATCH /api/cases/{id}` com `fase` fora do enum `casefase` retornava **HTTP 500** (`asyncpg.InvalidTextRepresentationError`) em vez de 422 — o schema `CaseUpdate.fase` era `Optional[str]` solto e a string crua chegava ao Postgres. Fix: `field_validator` valida `fase` contra `CaseFase` → 422 (schemas/case.py). **Risco similar** (não corrigido, backlog): `status`/`prioridade`/`risco` no mesmo schema também são strings soltas mapeando a enums.

**Defeitos do DADO de teste (corrigidos):** `qa/e2e/fictitious_matrix.json` usava `numero_processo` com dígito verificador CNJ inválido (`5000000-00…`, o backend corretamente rejeita com 422) e `fase="instrucao"` (inexistente). Corrigidos para CNJ válido (`5000000-83…`) e `fase="conhecimento"`.

**Cobertura / limites honestos:** suíte é 100% HTTP/API (sem UI/Playwright); o smoke por-módulo faz **só GET** e tolera 404 (`expected:[200,404]`) — logo NÃO comprova funcionamento de financeiro/IA/RAG/jurimetria, apenas que a rota existe/não estoura. Sem cenários negativos de segurança (não testa acesso indevido de `cliente_externo`). Embeddings/IA externa degradaram graciosamente (403 do proxy / sem chave), sem derrubar o app — comportamento esperado.

---

## 7. Correções aplicadas neste PR

### 7.1 Mocks/placeholders → função real ou indisponibilidade explícita
- `curadoria_renomada.py` — os 3 endpoints (lista vazia / "sucesso" fabricado / string fixa) passam a responder **503** honesto apontando para `/api/search` e `/api/rag`; corrigido `caso_id: int` → `str` e documentado o gate de ownership necessário ao ligar a lógica real.
- `cerebro.py::/jurisprudencia/pesquisa` — deixa de fingir `resultados: []` "simulado"; responde **503** apontando a busca real.
- `consumidor_monitor.py` — rótulos "dados públicos SENACON/Consumidor.gov.br" corrigidos para **estimativas internas de referência**; removidos `httpx`/`TIMEOUT`/`HEADERS` mortos. Funcionalidade (com aviso HITL) preservada.
- `ramos.py:290` — `taxa_cade_estimada` deixa de afirmar "tabela CADE 2026"; rotulado como estimativa de referência a confirmar.
- `teses_v4.py:94` — comentário "simulado" corrigido (o código faz listagem real no DB, não RAG).

### 7.2 IDOR / RBAC / correção
- **A1** `clients.py::atualizar (PATCH /clients/{id})` — adicionado gate `_pode_ver_cliente` (404), fechando write-IDOR de PII entre carteiras (a leitura já era gateada; a escrita não).
- **A2** `centro_custos.py::listar_lancamentos` — sem `case_id`, a equipe não-gestão passa a ver só custos dos próprios casos (subquery espelhando `fees._filtro_fees_lista`); antes listava todos os casos.
- **A9** removido o router morto duplicado `modules/case_partes/router.py` (manipulava PII sem `verificar_acesso_caso`; não registrado — o canônico é `routers/case_partes.py`).

### 7.3 Bug funcional (achado do smoke dinâmico)
- `schemas/case.py::CaseUpdate.fase` — `field_validator` valida contra `CaseFase`, transformando o **500** (asyncpg) em **422** claro. Dados de teste da matriz fictícia corrigidos (CNJ válido + `fase` válida).

### 7.4 Hardening RBAC/IDOR — lote 1 (commit `hardening RBAC/IDOR (lote 1)`)
- **A3** `deadlines.py` — `GET /deadlines` e `/export.csv` escopam por casos do usuário (não-gestão) por default; `_filtro_escopo_prazos` (gestão vê tudo).
- **B1** `deadlines.py` — `DELETE /deadlines/{id}` usa `requer_advogado`, eliminando o lockout de superadmin.
- **A4** `data_room.py` — `_gate_room` (case_id→`verificar_acesso_caso`, client_id→`_pode_ver_cliente`) em obter/adicionar_arquivo/gerar_link/revogar_link/remover_arquivo.
- **A5** `contratos_societarios.py` — escopo por titularidade na listagem + gates row-level em obter/atualizar/transição; `criar` valida titularidade de case_id/client_id.
- **A6** `partner_withdrawals.py` — approve/pay recusam auto-aprovação (`partner_id == cu.id`).
- **A7** `whatsapp.py` — `/qrcode` exige gestão; `/status,/chats,/messages` exigem o conjunto do `/send`.
- **A8** `environmental.py` — `listar` com piso advogado + filtro de ownership.
- **B2** `indice_risco.py` — `POST /recalcular` exige advogado.
- **B3** `pix.py` — `POST /cobranca` restrito a `_FINANCEIRO_TOTAL`.
- **B4** `datajud.py` — `GET /process/{cnj}` com rate-limit + piso advogado.
- Testes (lote 1): **179 passed, 16 skipped, 0 failed**.

### 7.5 Hardening RBAC/escopo — lote 2 (commit `hardening RBAC/IDOR (lote 2)`)
- **B5** `wiki.py` (leitura staff / escrita gestão) e `teses_v4.py` (GET e sugestao-ia com piso staff).
- **B6** `trabalhista_liquidacao.py` e `tributario_fiscal.py` — piso de equipe jurídica.
- **B7** `dashboard.py` — piso de staff (estagiário+), preservando o escopo financeiro por uid.
- **D9a** `qualidade.py` (piso staff nos endpoints de IA), `novos_modulos.py` (due-diligence: leitura staff / escrita socio+), `atendimentos.py` (segregação de carteira na listagem + gate row-level em obter/histórico, espelhando `clients._filtro_visibilidade_cliente`).
- **D1** `users.py` — `GET /users/{id}/avatar` de terceiros restrito a staff (self sempre; 404 para os demais).
- **D4** `tasks.py` — `criar` valida existência de `responsavel_id`.
- Extensão da validação de enum em `schemas/case.py`: `status` e `prioridade` (além de `fase`) → 422 em vez de 500.

---

## 8. Recomendações não implementadas (backlog priorizado)

Itens que exigem mais que um *point-fix* (migração de banco, coordenação com integração externa ou feature de frontend) ficam registrados aqui, com o motivo. Nenhum é bloqueador isolado.

- **B8 — `calendar_feed` token permanente não-revogável.** Correção adequada = coluna `users.calendar_token_version` (migração Alembic) incluída no HMAC + botão "regenerar link" no frontend. É uma feature, não um point-fix; fora do escopo desta PR de segurança para não introduzir migração destrutiva/coordenada. Mitigado hoje por token de 128 bits, tempo-constante e escopo por `user_id`.
- **B9 — `evolution_webhook` aceita segredo via query string (`?token=`).** Migrar para header-only pode quebrar a config atual da Evolution API em produção; exige coordenação operacional. Recomendado: garantir que o segredo não seja logado (nginx/uvicorn) e migrar para header em janela combinada.
- **D8 — `infosimples/receita/cpf` sem vínculo a caso/finalidade no audit.** Minimização LGPD: registrar finalidade/caso na trilha. Melhoria de auditoria (não é gate de acesso).
- **D2 — Dossiê do Cliente (divergência frontend/backend).** `moduleRegistry` roteia `/clientes/:clientId` sob `ROLES.clientes` (inclui advogado/secretaria), mas o backend exige `is_gestao`. Backend mais restrito (seguro); ajuste é de UX (alinhar a rota a socio+ no registry).
- **Similar-risk enum 500 fora de `cases`.** Outros routers podem ter o mesmo padrão de string-solta → coluna SAEnum. Varredura recomendada como higiene (não confirmado nesta auditoria fora de `cases`).

Os achados A1–A9 e B1–B7 da §4 foram **corrigidos** nesta PR (§7). O restante acima é backlog priorizado.
