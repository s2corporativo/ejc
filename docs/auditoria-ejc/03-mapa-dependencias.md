# 03 — Mapa de dependências e matriz de impacto (Fase 2/3)

> Base: grafo `graphify` no commit `aa65974` **depurado** (descartadas 10 336 arestas de alvo
> ambíguo, 24,2 % do total — ver `02-relatorio-graphify.md` §2), cruzado com extração direta dos
> 162 arquivos de router e 449 chamadas `api.*` do frontend.

## 1. Camadas e sentido das dependências

```
frontend/src/pages (95)  →  lib/api.ts  ──HTTP──►  main.py (166 APIRouter)
        │                        │                        │
        ├─ config/moduleRegistry ┘                        ├─ routers/ (162 arq., 820 endpoints)
        ├─ components/UI.tsx                              │        ↓
        └─ stores/ (auth, caseContext…)                   ├─ services/ (141 módulos)
                                                          │        ↓
                                                          ├─ core/ (database, security, ownership,
                                                          │         config, rate_limit, middlewares)
                                                          │        ↓
                                                          └─ models/ (62) ─► PostgreSQL 16 + pgvector
                                                                   ↑
                                       alembic/versions (121) ─────┘
```

Fluxo de IA (transversal, **saída única**):

```
router  →  services/ai/core/orchestrator.py  →  sanitizer.py (PII)  →  ai_gateway.py
                                                                             │
                                     ┌───────────────────────────────────────┤
                                     ▼                                       ▼
                        services/providers/*  (ollama → anthropic       citation_gate.py
                        maritaca → groq)                                 (na aprovação HITL)
```

## 2. Nós críticos — matriz de impacto

Classificação de impacto: **local** (só o arquivo) · **modular** (um domínio) · **transversal**
(vários domínios) · **sistêmico** (todo o produto).

| Componente | Depende de | Consumido por | Impacto | Risco | Por quê |
|---|---|---|---|---|---|
| `core/database.py` | `config` | **247** arquivos | sistêmico | alto | `AsyncSession`/`get_db()` — mudança de sessão atinge todo endpoint |
| `models/user.py` | — | **232** | sistêmico | alto | identidade + `role`; base do RBAC |
| `core/security.py` | `models/user` | **207** | sistêmico | **alto** | JWT, `ROLE_LEVEL`, `require_roles` — regressão aqui abre o sistema |
| `core/config.py` | — | **184** | sistêmico | alto | boot falha em produção com chave placeholder (proteção desejada) |
| `core/ownership.py` | `security`, `models` | **99** | sistêmico | **alto** | gate ABAC de caso; **só cobre ESCRITA em sub-recursos** (ver §4) |
| `models/case.py` | — | **98** | sistêmico | alto | entidade central |
| `core/auth_middleware.py` | `security` | 10 | **sistêmico** | **alto** | decide o que é público; normaliza `/api/v1` → `/api` |
| `core/api_version_middleware.py` | — | **1** | **sistêmico** | **alto** | reescreve **todo** path; **causa raiz do P0** |
| `services/ai_gateway.py` | providers, sanitizer | **62** | sistêmico | alto | única saída de IA; custo, kill-switch, fallback |
| `services/sanitizer.py` | — | **41** | transversal | **alto** | barreira de PII antes de provedor externo |
| `services/pii_crypto.py` | `config` | **25** | transversal | **alto** | Fernet + HMAC cego; sem chave o boot falha |
| `services/citation_gate.py` | — | 11 | modular | **alto** | gate antialucinação — aplicado na aprovação, **não na geração** |
| `frontend/lib/api.ts` | axios, `stores/auth` | **137** | sistêmico | **alto** | todo tráfego HTTP; o interceptor do P0 vive aqui |
| `frontend/components/UI.tsx` | — | **118** | transversal | médio | design system |
| `frontend/stores/auth.ts` | `lib/api` | 33 | sistêmico | alto | sessão, bootstrap, refresh |
| `frontend/config/moduleRegistry.tsx` | páginas | 15 | **sistêmico** | médio | rotas + RBAC de navegação (centralidade baixa, criticidade alta) |
| `main.py` | 176 | — | sistêmico | médio | registro de 166 routers; ordem de middleware importa |
| `routers/cases.py` | **42** | — | transversal | médio | router mais acoplado; candidato a extração de service |
| `services/scheduler.py` | 36 | — | transversal | médio | APScheduler; premissa de worker único |

**Leitura obrigatória desta tabela:** `api_version_middleware.py` tem **um** dependente no grafo e
é o componente de maior raio de dano real. Centralidade de grafo **não** mede criticidade —
middleware, config e registro de rotas são invisíveis à métrica e governam tudo.

## 3. Ordem de segurança para alterações

Derivada da matriz. Mexer num nível exige regressão dos níveis abaixo.

| Nível | Componentes | Exigência antes do merge |
|---|---|---|
| 0 — congelado | `core/security.py`, `core/auth_middleware.py`, `core/api_version_middleware.py`, `core/ownership.py`, `pii_crypto.py`, `sanitizer.py` | teste de regressão específico + `security-auditor` + revisão humana |
| 1 — sistêmico | `core/database.py`, `core/config.py`, `main.py`, `lib/api.ts`, `stores/auth.ts`, `moduleRegistry.tsx` | suíte completa + smoke E2E |
| 2 — transversal | `ai_gateway.py`, `citation_gate.py`, `scheduler.py`, `models/*` centrais | testes do domínio + do consumidor direto |
| 3 — modular | routers/services de um domínio | testes do módulo |
| 4 — local | páginas, componentes de folha | teste do componente |

## 4. Fronteira de autorização — onde o grafo ajuda e onde engana

`core/ownership.py` (99 dependentes) concentra o controle de acesso por caso. Lendo o arquivo
(não o grafo):

- `verificar_acesso_caso()` é descrito no próprio docstring como **"gate de ownership para
  ESCRITAS em sub-recursos de um caso"**;
- gestão (`socio`+, nível ≥ 7) sempre passa;
- equipe passa se for `advogado_responsavel_id` ou `advogado_auxiliar_id`;
- caso **órfão** (sem responsável nem auxiliar) só passa para gestão — *hardening* já aplicado,
  com o comentário registrando que antes qualquer usuário interno entrava.

**Consequência para a auditoria de segurança:** o gate cobre escrita em sub-recurso. **Leitura**
de recurso por ID e recursos-filhos que só herdam escopo pelo pai (`data_room_arquivos`,
`fee_payments`, `bank_transactions`, `document_intake_items`, `case_checklist_items`,
`knowledge_chunks` — 12 tabelas sem coluna de escopo própria) dependem de JOIN explícito em cada
query. Ver `12-seguranca-lgpd.md`.

O banco **não oferece segunda linha de defesa**: zero coluna de tenant, zero RLS, responsáveis
`nullable` (ver `07-banco-de-dados.md` §4). Toda a autorização é decidida em Python.

## 5. Contrato frontend ↔ backend

| Métrica | Valor |
|---|---|
| Endpoints registrados | **820** (162 arquivos, 166 objetos `APIRouter`) |
| Chamadas `api.*` no frontend | 449 |
| Casam com rota real | 422 |
| **Sem rota correspondente** | **27** → **25 pelo bug `/v1`** + 2 artefatos do extrator |
| Sem consumidor localizável no frontend | 393 (48 %) — **limite superior** |
| Routers sem consumidor localizado | 64 de 162 |

### 5.1 Chamadas quebradas — 100 % têm a mesma causa

As 25 chamadas realmente quebradas estão em 8 páginas e todas passam por routers que declaram
`prefix="/v1/..."`. Diagnóstico completo em `08-backend.md` §1 e `00-resumo-executivo.md`.

| Página | Chamadas quebradas | Módulo de negócio atingido |
|---|---|---|
| `pages/Despesas.tsx` | 6 | Financeiro — despesas |
| `pages/OfficeContracts.tsx` | 5 | Contratos do escritório |
| `pages/DossieCliente.tsx` | 4 | Pendências do cliente |
| `pages/Sociedade.tsx` | 3 | Retiradas de sócios |
| `pages/DataJudBusca.tsx` | 2 | Consulta processual DataJud |
| `pages/DespesasRecorrentes.tsx` | 2 | Financeiro — recorrentes |
| `pages/Kanban.tsx` | 2 | Kanban de casos |
| `pages/FinanceiroDashboard.tsx` | 1 | Financeiro — exportação |

### 5.2 Endpoints sem consumidor — por que o número é limite superior

Detectar consumo por análise estática subestima o uso quando a URL é **dado**, não literal.
Exemplo confirmado: o router `ramos` (82 endpoints) aparecia como 100 % órfão, mas
`frontend/src/pages/ramos/ramosConfig.ts` declara **72 endpoints como dado**
(`endpoint: "/empresarial/ferramentas/prazos-rj"` etc.), consumidos em
`pages/ramos/RamoBase.tsx:201,1017,1063` via `api.get(cfg.endpoint)`.

Após incorporar os endpoints declarados em configuração, o número caiu de 496 para **393**.
O resíduo ainda contém falsos positivos (URLs montadas em variável, chamadas encadeadas).

**Os 64 routers sem consumidor localizado, classificados:**

*Legítimos — consumo fora do frontend (webhook, cron, admin, integração):*
`evolution_webhook`, `backup_admin`, `api_keys`, `audit`, `observabilidade`, `radar_legislativo`,
`whatsapp`, `datajud`, `datajud_intelligence`, `regulatorio`, `google_drive_knowledge`,
`rag_public`, `export`.

*Atingidos pelo bug `/v1` (o consumidor existe, a rota é que não responde):*
`despesas`, `office_contracts`, `partner_withdrawals`, `pending_items`, `kanban`, `datajud`,
`regulatorio`, `whatsapp`.

*Merecem decisão de produto (funcionalidade construída e não exposta):*
`cerebro` (4), `diplomacia_v3` (1), `intelligence_v3` (2), `victory_vault_router` (4),
`curadoria_renomada` (3), `matriz_teses` (4), `jurisprudencia_externa` (6),
`jurisprudencia_interna` (6), `contratos_societarios` (6), `centro_custos` (6),
`calculadoras` (8), `module_help` (7), `novos_modulos` (14), `ai_core` (9), `teses_v4` (3),
`sumulas` (3), `procuracoes` (4), `qualidade` (3), `prompts` (3), `search` (2),
`solicitacoes_documentos` (2), `transparencia` (2), `produtividade` (2), `compliance` (2),
`consumidor_monitor` (4), `case_intelligence` (3), `anexos` (3), `architecture` (3),
`data_room_v4` (2), `honorarios_calc` (2), `ia_adversarial` (1), `ia_agente` (1),
`ia_citacoes` (1), `jornada_caso` (1), `kit_documental` (1), `precedentes_jurisprudencia` (1),
`triagem_entrevista` (1), `veredito_ia_router` (1), `advogado_estilo` (1), `areas` (1),
`dossie_cliente` (1), `andamentos` (2), `ai_tools` (2), `car` (2), `conteudo` (2),
`peca_geracao_router` (2), `backup_admin` (2).

Este é o dado quantitativo por trás do diagnóstico de excesso de superfície do
`docs/auditoria/parecer-arquitetural.md`: **cerca de metade da API construída não tem tela que a
consuma.**

## 6. Registro de rotas — fragilidade estrutural

162 routers, mas **dois mecanismos de registro**:

1. **Explícito** em `main.py` — 157 routers, `app.include_router(x.router, prefix=API)`.
2. **Aninhado por efeito colateral de import** em `backend/app/routers/__init__.py:24-30` —
   5 routers (`entrada_universal`, `entrada_universal_vinculo`, `defesas_revisoes`,
   `defesas_revisoes_pacote_seguro`, `defesas_revisoes_avancado`) são anexados a
   `novos_modulos.router`.

O próprio `main.py:428-433` documenta que **cinco outros grupos foram retirados desse padrão**
justamente porque "tornava as rotas dependentes da ORDEM de import e invisíveis aqui", e travou a
paridade com `tests/test_rotas_registro_explicito.py`. **O padrão permanece para os 5 acima.**

Nenhum router está órfão hoje — mas a superfície real da API não é legível num só lugar, e foi a
causa de dois falsos positivos na minha própria análise (registrados em
`02-relatorio-graphify.md` §6).

## 7. Dependências circulares

Não foram encontradas circularidades ativas. `core/ownership.py` **existe para evitá-las** — o
cabeçalho do arquivo declara: *"Módulo dedicado (não em security.py/cases.py) p/ evitar import
circular: sub-recursos importam daqui, e este só importa models + ROLE_LEVEL."*

O padrão de **743 imports tardios** (dentro de função) em 169 arquivos é, em parte, mitigação de
ciclo — e é também o que torna o grafo cego a um terço das dependências do backend.
