# 11 — Auditoria módulo por módulo (Fase 11)

> Os 38 módulos obrigatórios do escopo. Classificação com base em: existência do código, registro
> da rota, consumidor no frontend, cobertura de teste e achados das fases 6-12.
> **Limitação:** sem stack de pé, "funcional" significa *"o caminho existe e está íntegro no
> código"*, não *"exercitado em runtime"*. As exceções (provadas em runtime) estão marcadas ✅.

## Legenda

`FUNCIONAL` · `FUNC. C/ RESSALVAS` · `PARCIAL` · `DESCONECTADA` (existe, sem consumidor) ·
`DUPLICADA` · `OBSOLETA` · `QUEBRADA` · `NÃO TESTÁVEL` (sem ambiente)

## Quadro geral

| # | Módulo | Rotas / arquivos | Teste? | Classificação | Achado principal |
|---|---|---|---|---|---|
| 1 | **Dashboard** | `DashboardModern.tsx`, `/dashboard` | sim | **PARCIAL** | `Promise.allSettled` descarta rejeições — widget que falha vira "sem dados" (P2) |
| 2 | **Atendimentos** | `atendimentos.py` (1 060 l., 22 queries), `Central` | parcial | **FUNC. C/ RESSALVAS** | regra de negócio no router; 1 import de service |
| 3 | **Clientes** | `clients.py`, `Clientes`, `DossieCliente` | **sim, denso** | **FUNC. C/ RESSALVAS** | CPF cifrado + 404 que não vaza. Ressalva: bloco de pendências **QUEBRADO** (P0 `/v1`) |
| 4 | **Casos** | `cases.py` (42 deps, router mais acoplado), `Casos` | **sim (persistência + IDOR)** | **FUNCIONAL** | `_filtro_visibilidade` correto; DELETE soft com 422 protetivo |
| 5 | **Processos** | `processes.py`, `TabProcessos` | parcial | **FUNC. C/ RESSALVAS** | `numero_cnj` **sem UNIQUE nem índice** (P2) — duplicata entra sem barreira |
| 6 | **Visão do caso** | `CasoDetalhe` + 8 abas | parcial | **PARCIAL** | **6 abas com `.catch(() => {})`** — falha indistinguível de vazio (P2) |
| 7 | **Documentos** | `documents.py`, `GestaoDocumental` | **sim (LGPD + ownership)** | **FUNCIONAL** | magic bytes + UUID + fora do webroot. Sem antivírus (P3) |
| 8 | **OCR** | `ocr_service.py`, `entrada_universal_service` | 2 testes (skip local) | **FUNC. C/ RESSALVAS** | **fora do pipeline RAG** — documento OCRizado não vira chunk automaticamente |
| 9 | **Produção jurídica** | `peca_service` (1 365 l.), `motor_peca`, `Pecas` | **`peca_geracao_router` SEM teste** | **FUNC. C/ RESSALVAS** | citation gate **não roda na geração** (P1); `document-templates/generate` sem gate de advogado (P1) |
| 10 | **Estratégia** | `raio_x`, `dossie`, `legal_case_orchestrator` | parcial | **FUNC. C/ RESSALVAS** | depende do RAG; degradação silenciosa se embeddings off |
| 11 | **Prazos** | `deadlines.py`, `deadline_calculator` | **sim (função pura + job real)** | **FUNCIONAL** | Páscoa/Corpus Christi/dias úteis testados com datas concretas |
| 12 | **Agenda** | `agenda_eventos.py`, `calendar_feed.py`, `Central` | parcial | **FUNCIONAL** | feed `.ics` com HMAC + `compare_digest` |
| 13 | **Audiências** | `preparar-audiencia` (`ai.py:451`), `resumidor` | não | **PARCIAL** | endpoint de IA **sem rate limit** (P1) |
| 14 | **Tarefas** | `tasks.py`, `Central`, `/legado/tarefas` | parcial | **FUNC. C/ RESSALVAS** | `/legado/tarefas` roteada **sem nenhum link** (P3) |
| 15 | **Andamentos** | `andamentos.py`, `datajud_intelligence` | não | **PARCIAL** | sem consumidor localizado; DataJud **QUEBRADO** (P0) |
| 16 | **Pesquisa jurídica** | `RAGResearchAgent`, `rag.py`, `jurisprudencia_*` | sim (RAG) | **FUNC. C/ RESSALVAS** | agente **sem prompt próprio** — usa o genérico do `CaseAgent` (P2) |
| 17 | **Banco de teses** | `teses.py`, `teses_v4` (deprecated), `matriz_teses` | parcial | **DUPLICADA** | `teses_v4` já `deprecated=True` e delegando — pronto para remoção (P3) |
| 18 | **Base de conhecimento** | `knowledge_docs`, `rag_governance`, `KnowledgeGovernancePanel` | sim | **QUEBRADA** | **`GET /rag/docs` retorna 500 sempre** ✅ (P0) |
| 19 | **RAG** | `ai_service.py` (1 110 l.), `ingestion_service`, pgvector | **sim, 2 níveis** | **FUNC. C/ RESSALVAS** | isolamento **confirmado fail-closed**; sem embeddings vira `ILIKE` sem alarme (P1) |
| 20 | **Agentes** | 37 em `agent_registry.py`, `orchestrator` | estrutural (8 sem comportamental) | **FUNC. C/ RESSALVAS** | HITL universal; 12 ramos sem skill nativa (P2) |
| 21 | **Skills** | 4 superfícies paralelas | parcial | **DUPLICADA** | 16 de 17 handlers **nunca invocados** (P2); `SkillRouter` concorrente (P2) |
| 22 | **Jurimetria** | `jurimetria.py`, `JurimetryAgent` | parcial | **FUNC. C/ RESSALVAS** | `.catch(() => {})` em `Jurimetria.tsx:114,133` |
| 23 | **Contratos** | `office_contracts.py`, `OfficeContracts.tsx` | não | **QUEBRADA** | **página inteira morta** — 5 chamadas em 404 ✅ (P0) |
| 24 | **Honorários** | `fees.py`, `honorarios_oab`, `honorarios_calc` | **parcial — sem teste de cálculo** | **PARCIAL** | `_req_financeiro_mutacao` é conjunto explícito (bom); **zero teste de valor/persistência** (P1) |
| 25 | **Financeiro** | `financeiro_consolidado`, `despesas`, `centro_custos` | **sem teste de cálculo** | **QUEBRADA (parcial)** | `Despesas` + `DespesasRecorrentes` + export CSV em 404 ✅ (P0) |
| 26 | **Comunicações** | `portal_mensagens`, `notifications`, `whatsapp` | parcial | **PARCIAL** | `whatsapp` atrás do prefixo `/v1` (P0); `PortalCasoDetalhe.tsx:17` falha em silêncio |
| 27 | **Portal do cliente** | `portal.py`, `portal_documentos.py`, 6 páginas | **sim — 2 camadas + row-level** | **FUNCIONAL** | **melhor cobertura de segurança do repo**; isolamento comprovado em 3 camadas |
| 28 | **Usuários** | `users.py`, `Usuarios` | sim | **FUNCIONAL** | `require_admin` |
| 29 | **Perfis** | `ROLE_LEVEL` (`security.py:27-37`) | sim (matriz por papel) | **FUNC. C/ RESSALVAS** | `require_roles()` hierárquico é footgun (P3) |
| 30 | **Permissões** | `require_roles`, `ownership.py`, `canRoleAccessPath` | **sim, denso** | **FUNC. C/ RESSALVAS** | `/prompts` protegido **só no frontend** (P1); peça sem `case_id` sem gate (P2) |
| 31 | **Credenciais** | `credential_vault.py`, `api_keys.py` | **`api_keys` SEM teste** | **FUNC. C/ RESSALVAS** | cofre guarda só hash + prefixo, comparação constant-time, piso superadmin |
| 32 | **Integrações** | DataJud, Infosimples, NFSe, WhatsApp, DJEN, Drive | parcial | **PARCIAL** | padrão opt-in/default-OFF respeitado; **SSRF por DNS rebinding** em `document_url_import_service` (P2) |
| 33 | **Relatórios** | `analytics.py`, `export.py`, `produtividade.py` | não | **PARCIAL** | `/produtividade`: registry sem `roles` vs backend sócio+ (P2) |
| 34 | **Auditoria** | `audit_logs`, `audit.py`, `Auditoria` | sim | **FUNC. C/ RESSALVAS** | **"imutável" só por comentário — sem WORM** (P2); leitura de dado sigiloso não gera trilha (P3) |
| 35 | **Administração** | `system_modules`, `diagnostico`, `MapaModulos` | parcial | **FUNC. C/ RESSALVAS** | `/system-modules/mapa` subdetecta rotas (pista conhecida, não reauditada) |
| 36 | **Backups** | `backup_service.py` (690 l.), `backup_admin.py` | sem teste do router | **PARCIAL** | `subprocess` seguro (lista, sem `shell=True`); sem consumidor no frontend |
| 37 | **DataJud** | `datajud.py`, `datajud_intelligence`, `DataJudBusca` | não | **QUEBRADA** | **página inteira morta** ✅ (P0) |
| 38 | **Data Room** | `data_room.py` (726 l.), `data_room_v4` (deprecated) | **sim (ownership)** | **DUPLICADA** | `_gate_room` correto com 404 uniforme; `v4` pronto para remoção (P3) |

## Síntese quantitativa

| Classificação | Módulos | % |
|---|---|---|
| FUNCIONAL | 8 | 21 % |
| FUNC. C/ RESSALVAS | 14 | 37 % |
| PARCIAL | 8 | 21 % |
| **QUEBRADA (total ou parcial)** | **5** | **13 %** |
| DUPLICADA | 3 | 8 % |
| DESCONECTADA / OBSOLETA / NÃO LOCALIZADA | 0 | 0 % |

**Nenhum módulo obrigatório está ausente.** Nenhum é simulado — não há mock exibido como real em
nenhuma tela (`09-frontend.md` §3). Os 5 quebrados têm **causa única**: o prefixo `/v1`
(módulos 23, 25, 37 e partes de 3, 15, 26) e o monkeypatch do RAG (módulo 18).

## Módulos liberados para uso

Íntegros no código, com cobertura de teste e sem achado P0/P1 próprio:

**Casos · Clientes (menos pendências) · Prazos · Agenda · Documentos · Portal do cliente ·
Usuários · Tarefas**

## Módulos que devem permanecer bloqueados

| Módulo | Motivo | Desbloqueia com |
|---|---|---|
| **Contratos do escritório** | página inteira em 404 | correção P0-1 |
| **DataJud** | página inteira em 404 | correção P0-1 |
| **Financeiro — despesas** | listar/criar/editar/excluir/exportar em 404 | correção P0-1 |
| **Base de conhecimento / governança RAG** | `GET /rag/docs` 500 sempre | correção P0-3 |
| **Produção jurídica → protocolo** | gate de citações sobre base possivelmente vazia; router sem teste | P1-3 + T-P0-1 + curadoria da base |
| **Honorários / financeiro consolidado** | sem teste de cálculo nem de persistência | T-P1-2 |

## Observação de produto

O `docs/auditoria/parecer-arquitetural.md` recomenda cortar módulos. Esta auditoria fornece o dado
quantitativo que faltava: **393 dos 820 endpoints (48 %, limite superior) não têm consumidor
localizável no frontend, e 64 dos 162 routers não têm nenhum** (`03-mapa-dependencias.md` §5.2).

Parte é legítima (webhook, cron, admin). Mas a lista de "funcionalidade construída e não exposta"
— `cerebro`, `diplomacia_v3`, `intelligence_v3`, `victory_vault`, `curadoria_renomada`,
`matriz_teses`, `jurisprudencia_externa/interna`, `contratos_societarios`, `calculadoras`,
`module_help`, `novos_modulos` — **é grande o bastante para ser decisão de produto, não dívida
técnica.** Não recomendo remoção nesta auditoria: recomendo que o titular decida, módulo a módulo,
entre **expor**, **arquivar** ou **remover** — com o dado de uso real (`route_usage_metrics`, que
já existe) como critério.
