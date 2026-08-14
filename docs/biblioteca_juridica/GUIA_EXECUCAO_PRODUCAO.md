# Guia de Execução em Produção — Ingestão da Biblioteca Jurídica e Verificação de Logs

**Autor:** Manus AI · **Data:** 14/08/2026 · **Script:** `backend/scripts/ingestao_biblioteca_juridica.py` · **PR:** [#1139](https://github.com/s2corporativo/ejc/pull/1139)

## 1. Pré-requisitos na VPS de produção

A execução real do script depende de três condições: o branch `biblioteca-juridica-lote-piloto` mesclado e implantado na VPS, o arquivo `.env` de produção existente (o `DATABASE_URL` e `DATABASE_URL_SYNC` já estão definidos no `backend/app/core/config.py` com valores de produção no `.env` real) e acesso shell ao servidor (usuário com `sudo` e grupo `docker`, se a implantação for via containers). Nenhum parâmetro novo é necessário no `.env`: o script lê as mesmas variáveis do backend (incluindo `EMBEDDINGS_ENABLED=true` e `EMBEDDINGS_PROVIDER=local`, necessárias para a geração dos embeddings de 1024 dimensões).

## 2. Execução passo a passo

```bash
# 1. Acessar a VPS e entrar no diretório do EJC
ssh usuario@vps-ejc
cd /opt/ejc          # ou o diretório onde o repositório está clonado
git pull origin main # garantir a versão com a PR #1139 mesclada
git checkout biblioteca-juridica-lote-piloto  # se a PR ainda não foi mesclada

# 2. Rebuild/reattach do container do backend (se deploy via Docker)
docker compose build backend && docker compose up -d backend

# 3. Validar sem gravar nada (dry-run) — sem banco, pode rodar em qualquer ambiente
python3 backend/scripts/ingestao_biblioteca_juridica.py

# 4. Executar a ingestão real no ambiente do backend (recomendado)
docker compose exec backend \
  python3 backend/scripts/ingestao_biblioteca_juridica.py --execute

# Alternativa sem container (executar diretamente na VPS com as variáveis do .env)
export $(grep -v '^#' .env | xargs)
python3 backend/scripts/ingestao_biblioteca_juridica.py --execute
```

O modo `--execute` insere/atualiza cada documento pelo `upsert_documento`, que já implementa deduplicação por `(client_id, chave_origem, vigente=true)`: a reexecução do script é idempotente e apenas marca os documentos como `[atualizado]` sem criar duplicatas nem reprocessar chunks já embutidos. Os 24 documentos são gravados na base pública do escritório (`client_id=NULL`) com `chave_origem` igual ao `canonical_id` (ex.: `TESE-TRIB-000001`).

## 3. Saída esperada

Cada documento retorna uma linha `[novo | atualizado | inalterado] <canonical_id>`, valores literais do `upsert_documento`. Um lote novo e limpo deve exibir 24 linhas `[novo]`. Falhas de embedding aparecem como erros individuais por documento, mas a ingestão continua nos demais (o fallback de busca ILIKE/trgm permanece funcional pelo gate `emb_disponivel`). As categorias novas `tese_juridica`, `bloco_argumentativo` e `pedido_juridico` não constam do bloqueio de categorias restritas (que exige `client_id` para dados de cliente), portanto a ingestão global `client_id=NULL` é permitida; se o deploy ainda não reconhecer as categorias novas, o script as mapeia para `jurisprudencia_stj` e `modelo_documento_juridico`, categorias já existentes.

## 4. Verificação dos logs do banco de dados

O PostgreSQL em produção é o container `db` do compose (usuário `ejc_user`, banco `ejc_db`). A verificação pode ser feita em três níveis:

### 4.1 Contagem de documentos (confirmar a ingestão)

```bash
docker compose exec db psql -U ejc_user -d ejc_db -c "
SELECT categoria, COUNT(*) AS docs,
       COUNT(*) FILTER (WHERE embedding_ready IS TRUE) AS com_embedding
FROM knowledge_docs WHERE vigente = TRUE
  AND origem_conteudo IN ('fonte_oficial','jurisprudencia_oficial','legislacao')
GROUP BY categoria ORDER BY docs DESC;"
```

Nota: ajuste os nomes de colunas conforme a migração vigente (`knowledge_docs.extra->>'categoria'`, `chunk_status` etc.) — o comando exato pode ser refinado com `\d knowledge_docs` dentro do psql.

### 4.2 Logs de consulta do PostgreSQL (ver o que o RAG buscou)

Ative temporariamente o log de instruções (custo baixo de desempenho para janelas curtas) e leia o log do container:

```bash
# Ativar log_statement para a sessão corrente do backend
docker compose exec db psql -U ejc_user -d ejc_db \
  -c "ALTER SYSTEM SET log_statement = 'all'; SELECT pg_reload_conf();"

# Acompanhar em tempo real
docker compose logs -f db --since 5m | grep -Ei "statement:|duration:"

# Desativar depois da verificação
docker compose exec db psql -U ejc_user -d ejc_db \
  -c "ALTER SYSTEM SET log_statement = 'none'; SELECT pg_reload_conf();"
```

### 4.3 Logs de aplicação do backend (ingestão e embeddings)

```bash
docker compose logs backend --since 10m | grep -Ei "ingest|rag|embedding|knowledge"
```

O backend grava em `LOG_LEVEL=INFO` (padrão do `config.py`); para detalhamento máximo durante a ingestão, defina temporariamente `LOG_LEVEL=DEBUG` no `.env` e faça `docker compose restart backend`.

### 4.4 Confirmação rápida do lote

```bash
docker compose exec db psql -U ejc_user -d ejc_db -c "
SELECT extra->>'canonical_id' AS id, titulo, categoria, revisado
FROM knowledge_docs WHERE vigente = TRUE
  AND extra->>'canonical_id' LIKE '%0000%';"
```

## 5. Riscos e ressalvas operacionais

| Ponto | Mitigação |
|---|---|
| `log_statement='all'` em janela longa degrada desempenho | Usar apenas por 5–10 minutos durante a verificação |
| Embeddings demandam CPU/memória do container backend | Executar fora do horário de pico ou monitorar `docker stats` |
| `client_id=NULL` grava na base pública do escritório | Confirmar que os 24 temas são de domínio público do escritório (são) |
| Reexecução do script | Idempotente por dedup `chave_origem`; sem risco de duplicação |
| Documento MEDIA (Tema 9) | Pode ser mantido fora da base ou marcado `revisado=false` conforme política do painel de governança |
