# Guia Seguro de Produção — Biblioteca Jurídica do EJC

**Revisão:** 14/08/2026  
**Estado:** lote piloto em quarentena; não homologado para fundamentação automática.

Este guia substitui a versão anterior. A sequência abaixo é deliberadamente conservadora: **não ingerir, aprovar ou reativar o lote enquanto a validação fail-closed e a revisão humana não forem concluídas.**

## 1. Pré-condições

Antes de qualquer ação sobre o banco de produção:

1. o hardening do RAG deve estar mesclado e implantado;
2. o código implantado deve ser identificável pelo SHA de produção;
3. os testes do branch devem ter execução real, não apenas `startup_failure` do GitHub Actions;
4. deve existir backup recente e restaurável conforme o procedimento de continuidade do EJC;
5. nenhuma etapa deste guia exige expor ou copiar valores do `.env`.

Enquanto essas condições não forem atendidas, a ação correta é manter o PR sem merge e o lote sem nova ingestão.

## 2. Quarentenar versões do lote que já possam existir no PostgreSQL

O hardening inclui `scripts/quarentenar_biblioteca_juridica_piloto.py` dentro da imagem do backend.

### 2.1 Dry-run obrigatório

```bash
docker exec -i ejc_backend \
  python scripts/quarentenar_biblioteca_juridica_piloto.py
```

O comando apenas lê os 24 `canonical_id` conhecidos e informa quais registros seriam alterados. Não persiste mudanças.

### 2.2 Aplicação

Somente após conferir o dry-run:

```bash
docker exec -i ejc_backend \
  python scripts/quarentenar_biblioteca_juridica_piloto.py --execute
```

Efeito esperado:

- documentos aprovados do lote passam para `rag_status=pendente`;
- `requires_human_review=true`;
- `human_reviewed=false` nos registros que não estejam formalmente recusados;
- recusas humanas permanecem recusadas e sua trilha HITL é preservada;
- `quarantine_active=true` e motivo/data são registrados;
- nenhum documento, chunk, embedding ou versão histórica é apagado.

A operação é idempotente: repetir o script não renova o carimbo da quarentena nem cria novas versões.

## 3. Verificar a quarentena no banco sem expor conteúdo jurídico

Use apenas metadados:

```bash
docker exec -i ejc_db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT
  COALESCE(extra->>'canonical_id', chave_origem) AS canonical_id,
  extra->>'rag_status' AS rag_status,
  extra->>'quarantine_active' AS quarantine_active,
  extra->>'requires_human_review' AS requires_human_review,
  vigente
FROM knowledge_docs
WHERE deleted_at IS NULL
  AND (
    chave_origem LIKE 'TESE-%'
    OR chave_origem LIKE 'JUR-%'
  )
ORDER BY canonical_id;"
```

**Atenção:** os nomes das variáveis no shell dependem do ambiente do administrador. Não imprimir senhas, `DATABASE_URL`, tokens ou o conteúdo integral do JSONB em logs compartilhados.

Para conferir apenas o lote piloto com precisão, prefira consultar os 24 IDs listados no próprio script de quarentena.

## 4. Revalidar o corpus no checkout, fora da base ativa

A validação deve apontar explicitamente para os arquivos versionados:

```bash
python3 backend/scripts/ingestao_biblioteca_juridica.py \
  --dir docs/biblioteca_juridica \
  --graph docs/biblioteca_juridica/grafico_relacoes.yaml
```

Esse comando é dry-run. Ele verifica, entre outros pontos:

- front-matter canônico;
- unicidade de `canonical_id`;
- vocabulário de origem/autoridade/confiança;
- coerência entre camada e autoridade;
- fonte institucional para jurisprudência ALTA;
- ausência de processo/fonte simulada em conteúdo de autoridade;
- proveniência de teses, argumentos e pedidos;
- modelos de IA sem autoridade e com score 0;
- classificação de jurisprudência por tribunal;
- integridade referencial do grafo.

Enquanto qualquer registro falhar, o script encerra com código de erro e **nenhuma ingestão deve ser realizada**.

## 5. Curadoria jurídica individual

Cada documento destinado à base ativa deve passar por revisão humana e possuir, conforme a natureza:

- fonte primária oficial ou precedente verificável;
- identificação correta do tribunal, processo/tema/súmula, relator e datas quando aplicáveis;
- tese efetivamente extraída da decisão, não apenas de resumo de terceiro;
- status de vigência quando normativo;
- jurisprudência favorável e contrária quando o tema for controvertido;
- `distinguishing`, limitações, fatos e provas necessários;
- relação explícita com as fontes utilizadas.

A aprovação deve ocorrer pelo fluxo de governança do EJC. **Não editar o JSONB diretamente para transformar `pendente` em `aprovado`.**

## 6. Preparar um lote saneado para ingestão

Somente depois de todos os documentos do lote selecionado passarem pelo dry-run e pela revisão humana documental.

Como o diretório `docs/` não é copiado para a imagem do backend, materialize o lote validado temporariamente no contêiner, sem alterar volumes persistentes:

```bash
docker exec ejc_backend rm -rf /tmp/biblioteca_juridica_validada
docker cp docs/biblioteca_juridica/. \
  ejc_backend:/tmp/biblioteca_juridica_validada/
```

Primeiro execute novo dry-run dentro da mesma imagem que fará a ingestão:

```bash
docker exec -i ejc_backend \
  python scripts/ingestao_biblioteca_juridica.py \
  --dir /tmp/biblioteca_juridica_validada \
  --graph /tmp/biblioteca_juridica_validada/grafico_relacoes.yaml
```

Apenas com retorno zero e evidência de curadoria, a ingestão poderá ser feita:

```bash
docker exec -i ejc_backend \
  python scripts/ingestao_biblioteca_juridica.py \
  --execute \
  --dir /tmp/biblioteca_juridica_validada \
  --graph /tmp/biblioteca_juridica_validada/grafico_relacoes.yaml
```

Mesmo nesse modo, os registros são inseridos como `rag_status=pendente`. A ingestão não substitui a aprovação humana.

Após o procedimento:

```bash
docker exec ejc_backend rm -rf /tmp/biblioteca_juridica_validada
```

## 7. Verificação pós-ingestão

Verifique apenas estado e indexação:

```bash
docker exec -i ejc_db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT
  COALESCE(extra->>'canonical_id', chave_origem) AS canonical_id,
  categoria,
  status_indexacao,
  extra->>'rag_status' AS rag_status,
  extra->>'confidence_level' AS confidence_level,
  vigente
FROM knowledge_docs
WHERE deleted_at IS NULL
  AND extra ? 'canonical_id'
ORDER BY canonical_id;"
```

Não existe coluna `embedding_ready` em `knowledge_docs`. A vetorização é controlada por `status_indexacao`, enquanto os vetores residem nos `knowledge_chunks`.

Para conferir cobertura dos chunks:

```bash
docker exec -i ejc_db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
SELECT
  kd.id,
  COALESCE(kd.extra->>'canonical_id', kd.chave_origem) AS canonical_id,
  COUNT(kc.id) AS chunks,
  COUNT(kc.embedding) AS chunks_com_embedding
FROM knowledge_docs kd
LEFT JOIN knowledge_chunks kc ON kc.doc_id = kd.id
WHERE kd.deleted_at IS NULL
  AND kd.extra ? 'canonical_id'
GROUP BY kd.id, canonical_id
ORDER BY canonical_id;"
```

## 8. O que não fazer

- Não executar `ALTER SYSTEM SET log_statement='all'` apenas para acompanhar a ingestão; isso pode registrar conteúdo sensível e aumentar carga/volume de logs.
- Não usar `export $(grep .env ...)`; essa técnica é frágil para valores com espaços/caracteres especiais e aumenta o risco de exposição acidental de segredos.
- Não usar `--execute` apenas porque o arquivo declara `nivel_confiaca: ALTA`.
- Não aprovar por SQL direto.
- Não tratar modelo ou texto de IA como jurisprudência.
- Não reativar `CITACOES_MODO_ESTRITO` apenas para mascarar lacunas de curadoria; primeiro medir cobertura e corrigir a base.

## 9. Critério de conclusão

O hardening técnico pode ser considerado implantado quando:

1. CI/testes do commit realmente executarem e passarem;
2. produção estiver no SHA aprovado;
3. dry-run da quarentena for revisado e a quarentena aplicada;
4. a consulta de metadados comprovar que o lote antigo não está ativo;
5. cada documento revalidado passar pelo dry-run fail-closed;
6. a aprovação humana ocorrer pelo fluxo de governança;
7. uma consulta RAG controlada comprovar que documento `pendente`, `recusado`, revogado ou não validado não aparece como fonte de fundamentação.

Até esse ponto, a política correta é **falhar para o lado seguro**.
