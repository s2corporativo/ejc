# Runbook — Ativação da Busca Semântica (Embeddings) e Validação RAG

Este runbook ativa a **busca semântica local** (pgvector + intfloat/multilingual-e5-base) no EJC
e valida o pipeline RAG em produção. Soberania de dados preservada: o modelo de
embeddings roda **localmente na VPS**, nenhum dado sai da infraestrutura.

> Pré-condição: backend já em produção, migrations aplicadas (`alembic upgrade head`),
> `seeds/seed_all.py` executado ao menos uma vez (admin + feriados).

---

## Contexto técnico

| Item | Valor |
|------|-------|
| Modelo de embedding | `sentence-transformers/intfloat/multilingual-e5-base` (~90 MB, CPU) |
| Dimensão do vetor | 768 (coluna `knowledge_chunks.embedding`) |
| Índice | HNSW `vector_cosine_ops` (migrations 001/002) |
| Operador de distância | `<=>` (cosseno) — usado em `buscar_contexto_rag` |
| Flag de ativação | `EMBEDDINGS_ENABLED` (default `false`) |

Com a flag desligada, o sistema funciona normalmente em **busca textual** (ILIKE).
Ligar a flag ativa a "Tentativa 0" vetorial, com fallback textual automático.

---

## Passo a passo

### 1. Confirmar a extensão pgvector no banco
```bash
docker compose exec db psql -U ejc -d ejc -c "SELECT extname FROM pg_extension WHERE extname='vector';"
```
Se não retornar `vector`, a migration 001 não criou a extensão. Crie manualmente:
```bash
docker compose exec db psql -U ejc -d ejc -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Usar o serviço interno de embeddings
```bash
docker compose build embeddings && docker compose up -d embeddings
```
> Adiciona `sentence-transformers==3.0.1`. O download do modelo (~90 MB) ocorre no
> primeiro uso (lazy-load), não na instalação.

### 3. Ligar a flag no ambiente
No `.env` (ou variáveis do compose):
```env
EMBEDDINGS_ENABLED=true
```
Reinicie o backend:
```bash
docker compose restart backend
```

### 4. Backfill — gerar embeddings dos documentos já existentes
Os documentos ingeridos antes da ativação têm `embedding = NULL`. Gere os vetores:
```bash
docker compose exec backend python seeds/gerar_embeddings.py
```
Saída esperada: `Chunks sem embedding: N` → progresso em lotes de 32 → `✅ Backfill concluído`.

> Reexecutável com segurança: processa apenas chunks com `embedding IS NULL`.

### 5. Smoke test — validar o pipeline em produção
```bash
docker compose exec backend python seeds/smoke_rag_producao.py
```
Verifica: extensão pgvector, contagem da base, busca textual com filtro de categoria
(`ILIKE` + `ANY`), busca semântica (`<=>`), e recuperação de precedentes internos.
Código de saída `0` = tudo OK; `!= 0` = há falha a investigar. **Não escreve dados.**

---

## Rollback

Se a busca semântica apresentar qualquer problema, desligue sem perder nada:
```env
EMBEDDINGS_ENABLED=false
```
```bash
docker compose restart backend
```
O sistema volta imediatamente à busca textual. Os vetores permanecem no banco
(não são apagados) e voltam a ser usados assim que a flag for religada.

---

## Verificação rápida (manual)

Quantos chunks já têm vetor:
```bash
docker compose exec db psql -U ejc -d ejc -c \
  "SELECT COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS com_vetor, COUNT(*) AS total FROM knowledge_chunks;"
```

Testar uma busca semântica pela API (autenticado):
```bash
curl -s -H "Authorization: Bearer <TOKEN>" \
  "https://<dominio>/api/ai/analisar-caso" -X POST \
  -H "Content-Type: application/json" \
  -d '{"descricao_fatos":"<fatos com mais de 30 caracteres>","area":"civil"}'
```
Com embeddings ligados, os resultados RAG passam a trazer `score` (similaridade de cosseno).

---

## Observações de conformidade

- **Soberania de dados:** o modelo roda na VPS; nenhum texto é enviado a serviço externo
  para gerar embeddings.
- **HITL inalterado:** a busca semântica melhora a *recuperação* de fontes; toda saída
  da IA continua sendo minuta sujeita a revisão humana obrigatória.
- **LGPD:** os textos ingeridos no RAG já passam por sanitização na origem (precedentes
  internos e pós-mortem). Os embeddings são derivados desses textos já sanitizados.
