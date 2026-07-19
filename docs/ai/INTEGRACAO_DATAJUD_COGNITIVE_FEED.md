# DataJud → inteligência nativa do EJC

## Arquitetura

- `Case` e `CaseMovimento` permanecem como dados transacionais;
- DataJud continua como conector externo de metadados;
- cada movimentação gera documento cognitivo restrito por `client_id` e `case_id`;
- cada processo recebe linha do tempo consolidada;
- embeddings, pgvector, RAG e agentes são os já existentes no EJC.

## Segurança jurídica

- DataJud não comprova intimação, publicação ou termo inicial;
- nenhum prazo fatal é criado automaticamente;
- possíveis comunicações exigem conferência no DJEN ou sistema autenticado;
- prazos legados automáticos, ainda pendentes e sem ciência, são cancelados pela migration 110 com histórico preservado.

## Migration

`110_datajud_cognitive_feed` → `109_rag_scope_cliente`.

## Rotas

- `GET /api/casos/{case_id}/andamentos/inteligencia`;
- `POST /api/casos/{case_id}/andamentos/alimentar-ia`;
- `POST /api/casos/inteligencia/datajud/reconstruir-lote`.

Não integrar sem Alembic head único, testes completos e smoke do RAG.
