# Relatório — Itens do laudo IA/RAG (verificáveis localmente)

**Data:** 2026-06-29 · **Escopo:** 4 achados do laudo que dá pra corrigir e verificar sem deploy/LLM/Docker.
**Regra:** nada executado contra banco; verificado por py_compile + boot + testes.

| # | Achado | Correção | Arquivo |
|---|--------|----------|---------|
| **IA-01** | Análise de documento mandava o **texto bruto** (CPF/CNPJ/nomes/processo) ao Groq sem sanitizar | `sanitizar_pii(texto)` antes da chamada ao LLM; texto bruto preservado para uso local/RAG | `services/documento_service.py` |
| **IA-02** | `ia_especializada` enviava a **pergunta do usuário** ao gateway sem sanitização e sem AILog | sanitização + 2ª barreira `validar_sem_pii` (aborta se sobrar PII) + **AILog** (rastreabilidade) | `routers/ia_especializada.py` |
| **RAG-03** | Súmulas-seed **nunca** chegavam ao `knowledge_chunks`: `upsert_documento` era chamado com `referencia_id` (inexistente) e sem o obrigatório `chave_origem` → `TypeError` silenciado em `debug` | assinatura correta (`chave_origem="sumula:{tribunal}:{id}"`); `except` agora loga `warning` | `services/sumulas_ingestion.py` |
| **RAG-04** | Busca semântica sem **limiar de similaridade** → matches fracos/irrelevantes entravam como "fonte" (risco de alucinação) | `_RAG_MIN_SIM=0.55` → condição `(embedding <=> :vec) <= 0.45` no SQL semântico | `services/ai_service.py` |
| **IA-04** | Base anti-alucinação (`BASE_IDENTIDADE`) só em 3 tarefas; `redacao_peca`/`chat_rapido` (prosa) caíam sem ela | adicionadas ao `_TASKS_COM_BASE` (JSON/resumo seguem fora — design) | `services/legal_base.py` |
| **IA-05** | Verificador de citações (`citation_check`) só via endpoint manual `/qualidade` | acoplado ao fim da `analise_estrategica.analisar_caso` → resposta traz `_citacoes` (súmulas/artigos não confirmados sinalizados) | `services/analise_estrategica.py` |

## Verificação
- ✅ `py_compile` OK; app sobe (465 rotas); `_RAG_MAX_DIST=0.45`.
- ✅ **73 testes passando**, incluindo:
  - `test_documento_service.py` — **prova** que CPF e nº de processo são mascarados no prompt do documento enviado ao LLM.
  - `test_rag_isolation::test_limiar_de_similaridade_rag04` — valida o limiar.
  - `test_legal_base.py` — prosa recebe a base, JSON/resumo não, idempotência.
  - `test_citation_check.py` — extração e marcação de citações não confirmadas.

## Observação (IA-01)
Sanitizar o documento faz a extração de **partes** vir mascarada (placeholders) — o advogado preenche os dados reais (HITL). É o custo de conformidade LGPD (Groq processa nos EUA); a análise jurídica (área/tese/fatos) continua funcionando sobre o texto mascarado.

## Itens do laudo que AINDA faltam
- **IA-03** (fonte única de prompts): a infraestrutura de fonte única JÁ existe (`legal_base.BASE_IDENTIDADE`, aplicada via gateway pelo IA-04). Falta **remover as ~20 cópias inline** das regras espalhadas — refatoração ampla e arriscada de fazer às cegas (muda comportamento de IA em vários fluxos sem como validar). Recomendado fazer **com deploy**.
- Dependem de deploy/Docker/frontend: SEC-02 (XFF→nginx), SEC-03 (JWT→cookie), SEC-04 (container root), DEP-02/04 (dependências), FRT-03 (bypass RoleOnly).
