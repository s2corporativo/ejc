# EJC — Parte 10 — Relatório de execução

**Data:** 30/07/2026  
**Branch:** `fix/parte10-inteligencia-conferencia-assinatura`  
**Base:** `main` em `5a222a73f7dfc41dfa3fe4c71c5175538f395f36`  
**Situação:** alterações isoladas em branch; sem PR, merge, deploy ou mudança direta em produção.

## 1. Resultado executivo

A Parte 10 foi implementada no código com preservação dos gates técnicos e redução da fricção operacional:

1. a peça de IA passa a ser apresentada como **minuta profissional pronta para conferência**;
2. o advogado realiza um único ato afirmativo: **Conferir e assinar**;
3. se não existir validação vigente da versão atual, ela é executada automaticamente nesse ato;
4. score abaixo de 75, veredito bloqueante ou jurisprudência sem validação oficial continuam impedindo a liberação;
5. o PDF da minuta pode ser baixado imediatamente, com marca de minuta de IA enquanto não houver conferência;
6. o PDF final destinado a protocolo continua sujeito aos gates anteriores;
7. o fundamento normativo incorreto do Provimento OAB 205/2021 foi retirado dos prompts centrais e da experiência principal;
8. o fundamento adotado é a responsabilidade profissional pelo ato do advogado, com referência à Lei 8.906/1994, art. 32;
9. o painel `/api/ia/status` foi alinhado ao resolver real do `ai_gateway` e passou a informar o modelo efetivamente configurado para cada tarefa;
10. a duplicidade de duas rotas GET `/api/ia/status` foi eliminada;
11. o script de atualização deixou de forçar `EMBEDDINGS_ENABLED=false` em todo deploy.

## 2. Correção do vínculo `LegalDoc` ↔ `AILog`

A correção estrutural do `ai_log_id` já estava incorporada à `main` pelo PR #544 antes desta branch. A Parte 10 não duplicou essa alteração.

O fluxo novo usa a estrutura já disponível:

- `ai_logs.legal_doc_id`;
- `ai_logs.legal_doc_content_hash`;
- `ai_logs.legal_doc_validation_current`;
- bloqueio `FOR UPDATE` durante a persistência da validação;
- rejeição quando o conteúdo muda durante a validação.

## 3. Fluxo único de conferência

### Endpoint principal

`PATCH /api/legal-docs/{doc_id}/conferir-assinar`

Payload mínimo:

```json
{
  "confirmado": true,
  "observacoes": null
}
```

### Controles preservados

- acesso ao caso e ownership;
- papel de advogado;
- confirmação afirmativa obrigatória;
- validação vinculada à versão corrente;
- score mínimo 75/100;
- bloqueio por veredito impeditivo;
- auditoria de jurisprudência;
- registro de usuário, data, versão e `ai_log_id`;
- `AIStatusHITL.aplicado`;
- `LegalDoc.human_reviewed=true`;
- indexação RAG da peça conferida;
- checklist pré-protocolo quando aplicável.

### Compatibilidade

O antigo `PATCH /api/legal-docs/{doc_id}/aprovar` foi mantido como alias de transição e agora passa pelo ato único. A antiga tela de peças foi preservada em `PecasLegacy.tsx` e permanece disponível como **Ferramentas avançadas**, sem perda de templates, triagem, Visual Law, DOCX ou protocolo.

## 4. PDF imediato

Novo endpoint:

`GET /api/legal-docs/{doc_id}/pdf-minuta`

Regras:

- disponível desde a criação da peça;
- antes da conferência: PDF identificado como minuta gerada por IA;
- após a conferência: PDF sem a marca de minuta;
- o endpoint histórico de PDF final continua com os gates de validação e protocolo.

## 5. Correção normativa

Foram retiradas dos prompts centrais as afirmações de que o Provimento OAB 205/2021 exige revisão humana de peças geradas por IA.

A redação agora distingue:

- saída da IA: minuta profissional;
- ato oficial: responsabilidade do advogado que confere, assina, envia ou protocola;
- fundamento: Lei 8.906/1994, art. 32;
- Resolução CNJ 615/2025: aplicável apenas quando pertinente, especialmente à governança e ao tratamento de dados em plataformas externas, sem ser apresentada como regra geral de HITL para a advocacia privada.

## 6. Status da IA consolidado

### Problema encontrado

Havia duas rotas GET `/api/ia/status` montadas ao mesmo tempo:

- `ai_tools.py`: diagnóstico técnico e modelos;
- `ia_saude.py`: envelope leigo `{disponivel, mensagem}`.

A ordem de registro fazia a primeira rota vencer e o frontend global não encontrava `disponivel`, operando em `fail-open` silencioso.

### Correção

`/api/ia/status` tornou-se fonte única e devolve:

- `disponivel` e `mensagem` para o banner global;
- flags efetivas;
- provedores habilitados/configurados;
- modelos configurados;
- modelo resolvido pelo gateway;
- matriz de modelos por tarefa;
- aviso de minuta e regra de roteamento.

A função leiga histórica foi preservada para compatibilidade de imports e testes, mas não registra uma segunda rota HTTP.

## 7. Embeddings — causa raiz adicional

O arquivo `atualizar-ejc.sh` continha:

```bash
sed -i 's/^EMBEDDINGS_ENABLED=true/EMBEDDINGS_ENABLED=false/' .env
```

Essa linha desligava a busca semântica novamente em cada atualização, mesmo que a flag tivesse sido ativada manualmente.

A branch removeu esse comportamento. O script agora:

- preserva o valor explicitamente definido no `.env`;
- adiciona `EMBEDDINGS_ENABLED=true` apenas quando a variável não existe;
- executa ao final a sonda segura `scripts/check_flags_producao.py`;
- não imprime chaves, senhas, tokens ou DSN.

## 8. Procedimento pendente no servidor

Esta etapa não foi executada porque exige SSH à VPS. Deve ser realizada somente após merge/deploy autorizado.

### 8.1 Backup e leitura do estado efetivo

```bash
ssh root@13.140.167.153
cd /opt/ejc
cp .env ".env.bak.parte10_$(date +%Y%m%d_%H%M%S)"
docker exec -i ejc_backend python - < scripts/check_flags_producao.py
```

Não prosseguir se houver incompatibilidade entre `EMBEDDINGS_DIM` e a dimensão da coluna pgvector.

### 8.2 Ativação explícita dos embeddings

```bash
cd /opt/ejc
if grep -q '^EMBEDDINGS_ENABLED=' .env; then
  sed -i 's/^EMBEDDINGS_ENABLED=.*/EMBEDDINGS_ENABLED=true/' .env
else
  echo 'EMBEDDINGS_ENABLED=true' >> .env
fi

docker compose up -d --force-recreate backend
```

### 8.3 Verificação antes de gravar vetores

```bash
docker exec -i ejc_backend python - < scripts/check_flags_producao.py
docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --dry-run
```

### 8.4 Reindexação idempotente

```bash
docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --batch-size 10
```

### 8.5 Prova final

```bash
docker exec -i ejc_backend python - < scripts/check_flags_producao.py
```

Critério mínimo:

- `EMBEDDINGS_ENABLED=true`;
- `modelo_valido=true`;
- `embeddings_disponivel=true`;
- dimensão configurada igual à coluna pgvector;
- `knowledge_chunks_com_embedding` maior que zero e crescente até alcançar os chunks elegíveis.

## 9. Ollama — procedimento pendente no servidor

Antes de habilitar, verificar memória disponível e selecionar o perfil adequado do `.env.example`.

```bash
ssh root@13.140.167.153
cd /opt/ejc
free -h
docker compose --profile ia-local ps
```

Após ajustar `OLLAMA_ENABLED=true`, `OLLAMA_MEM_LIMIT`, `OLLAMA_PULL_MODELS` e os `OLLAMA_MODEL_*` ao hardware:

```bash
bash scripts/subir-ia-local.sh
docker compose --profile ia-local exec ollama ollama list
docker compose up -d --force-recreate backend
```

Não usar `qwen2.5:14b` em VPS sem RAM suficiente. Para 8 GB totais, utilizar o perfil de 3B documentado no `.env.example`; para 16 GB ou mais, avaliar o perfil padrão, observando a memória consumida pelo PostgreSQL, backend e demais contêineres.

## 10. Testes e limitações desta execução

Foi adicionada a suíte:

`backend/tests/test_parte10_conferencia_assinatura.py`

Ela trava por contrato:

- sintaxe dos arquivos Python alterados;
- existência do ato único;
- confirmação afirmativa;
- score mínimo e auditoria de jurisprudência;
- vínculo à validação corrente;
- PDF imediato sem retirada do gate de protocolo;
- compatibilidade das rotas antigas;
- status da IA alinhado ao gateway;
- inexistência de duas rotas GET `/ia/status`;
- correção normativa nos prompts;
- preservação das ferramentas avançadas do frontend.

Os testes não foram executados nesta sessão porque:

1. o repositório privado não está montado no ambiente local;
2. o ambiente local não tem acesso de rede ao GitHub;
3. os workflows disponíveis são associados a pull requests;
4. por orientação do titular, não foi aberta PR nesta etapa apenas para disparar CI.

Portanto, o status correto é: **implementação concluída em branch e revisão estática realizada; CI, build TypeScript e testes de integração ainda pendentes de execução na etapa de PR.**

## 11. Critérios de aceite para a futura PR

Executar, no mínimo:

```bash
cd backend
pytest -q tests/test_parte10_conferencia_assinatura.py
pytest -q tests/test_usabilidade_p0_backend.py
pytest -q tests/test_legal_doc_ai_log_vinculo_dblevel.py

cd ../frontend
npm run lint
npm run test
npm run build
```

Também validar no OpenAPI que existe uma única operação GET `/api/ia/status` e realizar smoke test autenticado:

1. gerar peça de IA;
2. baixar PDF de minuta antes da conferência;
3. confirmar `conferir-assinar` sem observações;
4. confirmar bloqueio com score abaixo de 75;
5. confirmar bloqueio com jurisprudência sem fonte validada;
6. confirmar registro do `ai_log_id`, usuário, versão e data;
7. baixar o PDF após a conferência;
8. confirmar que o protocolo continua exigindo os gates próprios.

## 12. Itens deliberadamente não executados

- PR;
- merge;
- force-push;
- deploy;
- alteração direta no `.env` de produção;
- reindexação dos 47.359 trechos;
- download de modelos Ollama;
- curadoria humana das 29 áreas críticas.
