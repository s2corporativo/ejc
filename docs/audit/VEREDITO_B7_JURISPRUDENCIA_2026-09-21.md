# Veredito da investigação B7 — Jurisprudência: duas fontes?

**Data**: 2026-09-21 · **Onda**: W6 (Conhecimento/Teses/Jurimetria) · **Ref**:
Auditoria Real 2026-09-20 §B7 (linha 180) e CSV BE-15 — ação INVESTIGAR.

## Pergunta

`jurisprudencias_internas` (tabela + router `/api/jurisprudencias`) e
`knowledge_docs.categoria="jurisprudencia"` (base RAG) são a mesma entidade em
dois lugares? Qual é o canônico?

## Evidência coletada no código (2026-09-21, main `3b5b05cb9`)

**Escrita/ingestão**:
- `knowledge_docs` recebe a jurisprudência viva: ingestores `stj.py`, `tjmg.py`
  (e semanais do scheduler) gravam com `categoria="jurisprudencia"`;
  `juris_import.py` (importação manual por OAB/tribunal) também alimenta o RAG.
- `jurisprudencias_internas` só é escrita pelo router manual `POST /jurisprudencias`
  (registro manual sem formulário no frontend).

**Leitura/consumo**:
- Frontend lê jurisprudência EXCLUSIVAMENTE via `/rag/buscar` (RAG): busca
  semântica da Base de Conhecimento, indicadores do caso
  (`TabIndicadoresJuridicos.tsx`), `MotorTeses`, `ContextualAIAssistant`,
  `KnowledgeGovernancePanel` e `rag_coverage.py` no backend.
- `GET /jurisprudencias` (router `jurisprudencia_interna.py`): **0 consumidores
  no frontend** (grep por `/jurisprudencias` em `frontend/src` = vazio).

## Veredito

**Canônico: `knowledge_docs` (categoria `jurisprudencia`)** — única fonte com
ingestão ativa, busca vetorial e consumidores reais (frontend + IA + cobertura).
`jurisprudencias_internas` é um registro manual SEM superfície de uso — store
órfã de fato, não duplicação viva.

## Ação decorrente

- NÃO unificar agora: não há segunda escrita ativa competindo — não existe o
  risco de "dupla escrita não controlada" (G6) nesta dupla.
- `router jurisprudencia_interna.py` + `models/jurisprudencia_interna.py` seguem
  para a **W10 (dead code comprovado)** com o critério da auditoria
  ("nenhuma tela viva referencia" — provado acima por grep).
- Antes de qualquer DROP físico (W12): dump + telemetria de rotas
  (`route_usage`), conforme §12.3 e regra de expurgo da auditoria.
- Runbook de deduplicação (`docs/RUNBOOK_DEDUPLICACAO_BASE_CONHECIMENTO.md`)
  permanece a ferramenta de higiene da base canônica (rebaixa `vigente=false`,
  nunca apaga).
