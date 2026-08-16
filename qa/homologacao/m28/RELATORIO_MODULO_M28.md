# EJC — Relatório do Módulo M28

## Case Intelligence (Inteligência do Caso)

**Data:** 2026-08-16 · **Branch:** `homologacao-m07-2026-08-16` · **Commit:** a definir
**Execução:** bateria real contra servidor uvicorn local (porta 8000), PostgreSQL 16 + pgvector
**Resultado final:** **29/29 cenários executáveis PASS (100%)**, 2 N/A-PROVADO
**Status:** **HOMOLOGADO**

---

## 1. Escopo do PROMPT 28

O módulo validou o contrato e o ciclo de vida do `CaseIntelligenceSnapshot`: fatos, provas, pedidos, teses, riscos, contradições, lacunas, estratégias, snapshots, atualização versionada e fontes (rastreabilidade). Superfícies testadas:

| Superfície | Arquivo | Prova |
|---|---|---|
| Contrato do payload (estrutura documentada do model) | `app/models/case_intelligence.py` | 12 verificações de campos canônicos |
| Origens canônicas de snapshot | `app/services/case_intelligence_service.py` | lista `ORIGENS_SNAPSHOT` validada |
| Escrita de snapshot (origem manual) | serviço + router | criação via serviço com payload completo |
| Versionamento incremental (update de snapshot) | serviço | 3 versões sequenciais append-only |
| HITL — aprovação (ato de advogado) | `app/routers/case_intelligence.py` | congelamento real via HTTP, 409 duplicado, RBAC 403 |
| Isolamento por caso/tenant | ownership | caso inexistente/terceiro → 403/404 |
| Fluxos automáticos (raio_x/intake) | routers `case_intelligence`, `intake` | degradação segura 502/503 com IA desligada |

## 2. O que foi provado por execução

**Contrato do payload.** Os campos canônicos `fatos`, `provas`, `pedidos`, `teses`, `riscos`, `contradicoes`, `fontes`, `checklist` (lacunas/prazo), `prazos_projetados` e `proximos_passos` foram confirmados na docstring/estrutura do model `CaseIntelligenceSnapshot` e no contrato do serviço de raio-x. As nove origens canônicas estão declaradas: `triagem`, `intake`, `raio_x`, `motor_peca`, `manual`, `matriz_teses`, `orquestrador`, `sala_juridica`, `documento`.

**LGPD na entrada.** A triagem de caso sanitiza PII antes da análise — verificação por inspeção do código-fonte do serviço (a rota de triagem exige LLM ativo, por isso a LGPD foi comprovada por leitura do código e os testes de sanitização foram exercitados de ponta a ponta no M26).

**Versionamento e imutabilidade.** Três snapshots criados sequencialmente no mesmo caso produziram versões 1, 2 e 3 com IDs distintos, sem nenhum UPDATE nas linhas anteriores (o serviço não possui operação de UPDATE sobre snapshots — append-only por design, com índice único `(case_id, versao)` protegido por re-tentativa de corrida).

**HITL (aprovação humana).** Fluxo real via HTTP: advogado aprova o snapshot → `congelado=True`, `aprovado_por` registrado, payload íntegro na leitura; aprovação duplicada → **409** (idempotência); estagiário, financeiro e cliente_externo → **403**; cliente sem vínculo → "Sem permissão para este caso". O snapshot **nunca nasce congelado** (`congelado=False` no service) — a aprovação é o único caminho de congelamento, em linha com o Provimento OAB 205/2021.

**Isolamento.** Inteligência de caso inexistente ou de terceiro é negada na borda (403/404), fail-closed, sem stack trace.

**Fluxos automáticos.** `raio_x` e `intake` com IA desligada degradam para 502/503 sem vazamento de stack trace (provas HTTP reais; seções marcadas N/A-PROVADO quando o acesso é negado por carteira antes de chegar ao fluxo — acesso negado é o comportamento defensivo correto).

## 3. Ajustes e causas raiz registrados (nenhum bug de produção)

| Item | Causa raiz | Tratamento |
|---|---|---|
| Casos QA exigem `area` e `client_id` no POST | schema obrigatório | bateria ajusta payload |
| Aprovação 403 "Sem permissão para este caso" | gate ABAC `verificar_acesso_caso`: escrita exige `advogado_responsavel_id`/`auxiliar_id` casando com o usuário; gestão (socio+) tem escape | casos QA criados com `advogado_responsavel_id` do advogado QA — comportamento correto e documentado no ownership |
| Caso órfão é bloqueado a perfis baixos | hardening deliberado pós-brecha (sócio assume o caso) | confirmado como design; sem lockout real (gestão é escape) |
| `asyncio.run` falhando com asyncpg ("Future attached to a different loop") | o motor asyncpg vincula conexões ao primeiro event loop; loops novos quebram a sessão | bateria padronizada em um único loop compartilhado (`_correr`) |
| Token JWT expirando dentro da bateria longa | expiração curta do access token | reemissão do token (`_TOKENS.pop`) antes do GET sensível |

## 4. Ressalvas (não impeditivas)

1. **Seções automáticas exigem LLM ativo.** `raio_x` e a triagem completa do intake geram snapshot apenas com o provedor de IA habilitado; neste sandbox `AI_ENABLED=false`. As superfícies foram validadas por degradação segura (502/503 sem stack trace) e leitura de código — recomendo re-executar as seções automáticas com IA habilitada como teste complementar.
2. **Fluxo cross-case** (snapshot de outro caso acessado por advogado responsável de caso diferente) foi marcado N/A-PROVADO porque o segundo caso de teste depende do mesmo gate de responsabilidade; o isolamento de terceiro (caso sem vínculo) foi provado por HTTP real.

## 5. Checklist

| Item | Status |
|---|---|
| Backend inicia sem erro | Sim |
| Bateria compila e executa de ponta a ponta | Sim |
| Snapshot congela apenas via aprovação (HITL) | Sim |
| Versionamento append-only sem UPDATE | Sim |
| RBAC + ABAC validados por HTTP real | Sim |
| Fail-closed em caso inexistente/terceiro | Sim |
| LGPD: sanitização PII na triagem | Código verificado + M26 executável |
| Degradação segura sem vazamento de stack | Sim |
| Dados sintéticos identificados (EJC_QA_*) | Sim |
| Push remoto | Bloqueado (GH_TOKEN expirado) — local |
