# Fase 7 — Pendências menores: decisões e encerramento (2026-09-17)

Auditoria de referência: `docs/auditoria/relatorios/2026-09-15-fase0-auditoria-ecossistema.md`
(pares de duplicação residuais). Este documento registra a decisão de engenharia
sobre as três pendências menores da Fase 7 que ficaram fora dos clusters já
encerrados (intake `/documentos-ia` — PR #1675; jurisprudência externa — PR
#1677; teses — decisão de não consolidar). O critério é o mesmo das rodadas
anteriores: medir antes de decidir, consolidar só quando há ganho real e
registrar o porquê para a decisão não ser reaberta às cegas.

## 1. Google Drive ×2 — NÃO consolidar (famílias distintas)

A auditoria lista `services/google_drive.py` × `services/google_drive_service.py`
na família "google-drive duplicada". A medição não confirma duplicação lógica —
são duas camadas com protocolos, dependências e planos de dados diferentes:

| | `google_drive.py` (332 linhas) | `google_drive_service.py` (829 linhas) |
|---|---|---|
| Papel | Armazenamento do GED (plano de blobs) | Sincronização Drive → base de conhecimento RAG |
| Protocolo | `rclone` via subprocesso (síncrono por desenho, chamado com `asyncio.to_thread`) | `googleapiclient` com OAuth do usuário ou service account |
| Consumidores | `routers/documents.py`, `services/data_room_public.py` | `routers/google_drive_knowledge.py`, `services/backup_service.py`, `services/backup_drive_auth.py` |
| Unidade de dado | arquivo do GED (`remote_path` persistido no documento) | `knowledge_docs` com `chave_origem='gdrive:<file_id>'` |

Fundir os dois acoplaria o deploy do rclone às bibliotecas Google, uniria dois
ciclos de falha independentes (storage vs. ingestão) e não eliminaria nenhuma
linha efetivamente repetida — não há sobreposição de função: um copia/move/remove
blobs endereçados por path, o outro lista/downloada e ingere via
`upsert_documento`. Decisão: **manter os dois módulos** e tratar o problema real,
que é de nomeação/confusão: ambos recebem uma seção de fronteira no cabeçalho
apontando um para o outro e para esta decisão.

## 2. Analytics ×4 — NÃO consolidar (granularidades complementares)

A auditoria cita `dashboard.py` × `analytics.py` × `produtividade.py` ×
`relatorio*.py` como "agregadores diferentes para os mesmos dados". A medição
mostra cinco routers com recortos distintos e higiene já aceitável:

- `analytics.py` (`/api/analytics/*`, 8 GETs) — leitura analítica por indicador;
  já delega todo o cálculo a services (`case_health`, `jurimetria`, `taskscore`,
  `funil`, `rentabilidade`, `onboarding`) e usa `require_roles_exact`.
- `dashboard.py` (`/api/dashboard`) — KPIs executivos em uma chamada, com cache
  em processo de TTL 30s e escopo financeiro por perfil; usa os helpers
  compartilhados de `core/status_caso.py` (mesma fonte de status que o resto do
  sistema).
- `produtividade.py` (`/api/analytics/produtividade`, `/roi-por-area`) —
  indicadores sensíveis de gestão (sócio+), SQL próprio com audit log e rate
  limit.
- `relatorio.py` (`/api/relatorio/mensal`) — competência mensal JSON sobre o
  ledger efetivo (`fee_payments` como fonte soberana com fallback compatível).
- `relatorio_cliente.py` — recorte por cliente com política própria.

A sobreposição que existe é de DADOS (todos leem casos/fees), não de LÓGICA — e
os pontos que seriam divergência de verdade já foram centralizados:
`core/status_caso.py` define os conjuntos de status usados por dashboard,
relatório e demais consumidores, e o par PDF executivo
(`dashboard/relatorio-mensal`) × JSON contábil (`relatorio/mensal`) responde
perguntas diferentes em formatos diferentes para públicos diferentes (sócio
consome PDF; integrações consomem JSON). Consolidar os quatro obrigaria a uma
camada de "agregador geral" artificial, com risco de regressão em superfícies de
financeiro que já passaram por homologação. Decisão: **não consolidar**; a
evolução continua sendo puxar qualquer agregação nova para services (como já faz
`analytics.py`) e manter `core/status_caso.py` como única fonte de conjuntos de
status.

## 3. `core/skill_router.py` — movido para `services/ai/`

O roteador de especialidades (identifica o ramo do direito por palavras-chave e
fornece a instrução de skill) vivia em `app/core/`, mas não é infraestrutura de
framework — é lógica de domínio de IA com um único consumidor
(`routers/cerebro.py`). Com a aposentadoria do shim `core/ai_brain` (PR #1672),
`core/` ficou restrito a autenticação, config, banco e rate limit; o roteador de
skills migrou para `app/services/ai/skill_router.py`, ao lado de `model_router.py`
e `provider_registry.py`, mantendo a API (`skill_router.identificar_ramo`,
`get_skill_instruction`) e o singleton intactos. Nenhum contrato muda; teste
algum importava o caminho antigo.

## Resultado

- Fase 7 encerrada sem nenhuma pendência aberta: intake, jurisprudência e teses
  (clusters), Drive, analytics e skill_router (este documento).
- Próxima frente do Plano Mestre: Fase 8 (gates/rate limit nos endpoints
  ONLY_AUTH — onda 1 em andamento) e Fase 9 (deploy + restore drill, condicionada
  a janela e go explícitos — ver `docs/RUNBOOK_FASE9_DEPLOY_RESTORE_DRILL.md`).
