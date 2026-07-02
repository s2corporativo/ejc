# RELATORIO DE AUDITORIA INCREMENTAL GRAPHIFY EJC - 2026-07-02

Fonte primaria: `graphify-out/GRAPH_REPORT.md`

## 1. Resultado direto

O Graphify foi mantido funcional e regenerado apos os ajustes desta rodada.

- Grafo atualizado: 4.265 nos, 8.216 arestas, 411 comunidades.
- Corpus: 551 arquivos, aproximadamente 352.960 palavras.
- Diagnostico `graphify diagnose multigraph`: 0 endpoints faltantes, 0 dangling endpoints, 0 self loops, 0 duplicatas exatas, 0 arestas colapsadas.
- `graph.html`, `graph.json` e `GRAPH_REPORT.md` foram atualizados em `C:\Users\User\EJC\graphify-out`.

## 2. Correcoes aplicadas nesta rodada

### Rotas quebradas frontend/backend

Corrigidas chamadas do frontend que nao batiam com os routers montados em `backend/app/main.py`:

- `frontend/src/pages/CasoDetalhe.tsx`
  - `/checklists/casos/{caseId}/gerar-ia` -> `/checklists/caso/{caseId}/gerar-ia`
  - `/v1/ia-defensiva/*` -> `/ia-defensiva/*`
- `frontend/src/pages/AgenteIA.tsx`
  - `/v1/ai/status` -> `/ai/status`
  - `/v1/ai/executar` -> `/ai/executar`
- `frontend/src/pages/IA.tsx`
  - `/v1/validador-juridico/validar` -> `/validador-juridico/validar`
- `backend/app/routers/ai_tools.py`
  - comentario de rota atualizado para refletir o contrato real: `/api/ai/*`.

### IDOR / ownership em Processos

`backend/app/routers/processes.py` agora usa `verificar_acesso_caso()` antes de:

- listar processos de um caso;
- criar processo;
- atualizar processo;
- arquivar processo;
- desarquivar processo;
- remover processo.

Isso fecha a lacuna apontada pelo grafo nas comunidades `Backend Routers - Processes` e `Backend Tests - Test Ownership`: antes o router validava existencia do caso/processo, mas nao aplicava o gate canonico de ownership.

### Arquivamento de casos e processos

Foi implementado o fluxo incremental de arquivamento:

- migration `059_archiving_cases_processes`;
- campos `archived_at` e `archive_reason` em `cases` e `processes`;
- endpoints de arquivar/desarquivar;
- filtros `ativos`, `arquivados`, `todos`;
- UI em `Casos.tsx` e `CasoDetalhe.tsx`;
- preservacao de historico, documentos, IA, financeiro e logs.

### IA / RAG / LGPD

Correcoes aplicadas em lacunas objetivas:

- `documento_service.py` passa a sanitizar PII antes de enviar texto ao LLM.
- `legal_base.py` passa a exigir base normativa tambem para `redacao_peca` e `chat_rapido`.
- Mantida a conclusao da auditoria: RAG semantico segue como capacidade parcialmente preparada, nao como runtime plenamente ativo sem validar `EMBEDDINGS_ENABLED`, dependencias e ambiente de execucao.

## 3. Pendencias tecnicas reais

### P1 - Licitacao ainda visivel

O grafo ainda mostra comunidades e arquivos de licitacao:

- `frontend/src/pages/LicitacaoAuditoria.tsx`
- rota `/licitacao-auditoria` em `frontend/src/App.tsx`
- item de menu em `frontend/src/components/Layout.tsx`
- `backend/app/routers/licitacao_auditoria.py`
- `backend/app/core/licitacao_auditor.py`

Pela regra do EJC MVP, isso deve ser removido ou ocultado em uma rodada propria, para nao misturar com arquivamento/IA.

### P1 - Duplicacao arquitetural em IA

O `GRAPH_REPORT.md` continua apontando dispersao de IA/RAG em varias comunidades: `Ai`, `Ai Tools`, `Ai Skills`, `Ia Extra`, `Ia Defensiva`, `Rag`, `Ai Gateway`.

Recomendacao: consolidar entrada publica por contrato, manter `ai_gateway.py` como centro e reduzir routers sobrepostos apenas depois de mapear consumidores frontend.

### P2 - Comunidades finas e nos isolados

O relatorio atual mostra 92 comunidades finas omitidas. Isso nao quebra o sistema, mas indica cauda longa de modulos pequenos, helpers e arquivos pouco conectados. Deve ser tratado por lote, nao como refactor unico.

### P2 - Teste smoke bloqueado por dependencia nativa no Windows

`test_app_monta_com_rotas` falha antes de montar o app porque `documents.py` importa `magic` e o ambiente Windows local nao encontra a DLL `libmagic`, apesar de `python-magic`/`python-magic-bin` existirem no venv.

Impacto: bloqueia smoke local do app completo, mas nao invalida os testes direcionados nem o build frontend.

## 4. Validacoes executadas

### Passou

- `python -m py_compile` nos arquivos backend tocados.
- `npm run build` no frontend: passou.
- `pytest` direcionado: 18 testes passaram.
- Graphify update: passou.
- Graphify diagnose multigraph: passou sem inconsistencias estruturais.

### Falhou / bloqueado

- `backend/tests/test_smoke.py::test_app_monta_com_rotas`
  - causa: `ImportError: failed to find libmagic. Check your installation`.
  - natureza: dependencia nativa local do Windows, disparada ao importar `backend/app/routers/documents.py`.

## 5. Proximo passo recomendado

Rodada unica e focada: remover/ocultar licitacao do MVP EJC e depois rodar novamente `graphify update` + build frontend, porque o grafo ainda confirma esse modulo como referencia ativa.
