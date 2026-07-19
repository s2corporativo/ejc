# Adendo à Auditoria Integral do Núcleo de IA e Conhecimento Jurídico

**Data:** 19 de julho de 2026  
**Documento principal:** `AUDITORIA_NUCLEO_IA_CONHECIMENTO_2026-07-19.md`

Este adendo registra achados e decisões consolidados durante a revisão final do diff e dos pull requests concorrentes.

---

## 1. P1 adicional — listagem de metadados do RAG sem escopo

### Situação

O mecanismo de recuperação (`buscar_contexto_rag`) já excluía categorias restritas quando não recebia `scope_client_id`. Entretanto, `GET /rag/docs` listava `KnowledgeDoc` para qualquer usuário autenticado sem filtrar `client_id` ou `case_id`.

Embora a rota não devolvesse chunks, os seguintes metadados podiam revelar informação de cliente:

- título de peça interna;
- categoria;
- fonte;
- tribunal;
- data de criação;
- existência de determinado assunto no acervo.

### Correção

A rota existente foi substituída, antes da inclusão no FastAPI, por callable escopado:

- **sócio/admin/superadmin:** visão integral para gestão e curadoria;
- **demais perfis internos:** conteúdo público e documentos de casos em que sejam responsável, auxiliar ou caso legado ainda sem atribuição;
- **cliente externo, se a rota vier a ser liberada pelo middleware:** apenas conteúdo público e documentos do próprio `client_id`.

O filtro reutiliza a mesma lógica de ownership dos casos. A ausência da rota ou falha ao instalar o gate impede o boot, evitando inicialização em estado inseguro.

### Arquivos

- `backend/app/services/ai_core_hardening_patch.py`
- `backend/tests/test_ai_knowledge_core_hardening.py`

---

## 2. Política final de persistência do AILog

A resposta integral reidratada permanece disponível ao advogado durante a request, mas a persistência usa pseudonimização irreversível.

### Dados sempre protegidos no log

- nomes de cliente, partes, testemunhas e terceiros;
- CPF, CNPJ e RG;
- e-mail, telefone, CEP, cartão e PIX;
- número do processo do próprio cliente;
- demais identificadores estruturais.

### Exceção mínima para o gate antialucinação

O campo `AILog.resposta` também é a fonte determinística usada para recomputar citações antes da aprovação HITL. Por isso, um número CNJ é preservado somente quando a janela local contém cumulativamente:

1. tribunal reconhecível;
2. marcador inequívoco de precedente, acórdão ou julgado;
3. data de julgamento/publicação.

Sem os três elementos, o CNJ é pseudonimizado como qualquer processo de cliente. Essa política preserva a verificação jurídica sem converter o AILog em repositório de processos pessoais.

---

## 3. Coordenação com o PR #317 — Provider Registry, eval comparativo e FTS

A revisão formal foi registrada no PR #317. O parecer separa melhorias válidas de pontos que não devem ser integrados na forma atual.

### Manter

- registro único de provedores;
- guia de curadoria do gold set;
- comparação Anthropic × Maritaca;
- métricas de custo, latência, groundedness e citações;
- testes contra drift das listas de providers.

### Corrigir antes do merge

1. **Fallback sintético:** `_resolver_cadeia` ainda pode criar Groq quando a cadeia elegível fica vazia. O Provider Registry deve incorporar o comportamento fail-closed do PR #322.
2. **FTS ligado sem baseline:** `RAG_FTS_ENABLED=true` não deve ser default antes de gold set jurídico real. A terceira perna lexical pode melhorar recall e simultaneamente reduzir precisão; deve permanecer opt-in até avaliação.
3. **Métrica de fallback:** uma resposta produzida por outro provider não deve compor o agregado do provider solicitado como execução válida. Fallback deve ser separado ou invalidar aquele caso comparativo.
4. **Rebase:** o PR toca `ai_gateway.py` e `provider_policy.py`; deve ser rebaseado após a definição da ordem de integração do hardening.

---

## 4. Ordem recomendada dos PRs

Há três trabalhos concorrentes:

- **#322:** hardening do núcleo e isolamento multi-cliente do conhecimento;
- **#317:** provider registry, eval comparativo e configuração FTS;
- **#318:** alimentação cognitiva DataJud, com migration própria.

Ordem segura:

1. validar e integrar o **#322**;
2. rebasear o **#317**, absorver o fail-closed e manter FTS opt-in;
3. rebasear o **#318**, renomear sua migration para 110 ou número posterior ao head efetivo;
4. confirmar um único head Alembic;
5. executar novamente backend completo, migrations, eval offline e frontend build.

Não é recomendável mesclar os três por merge commits independentes sem rebase, pois há sobreposição em gateway/policy e conflito de migrations baseadas em 108.

---

## 5. Situação consolidada

Após este adendo, os riscos corrigidos no PR #322 abrangem:

1. kill-switch de providers;
2. cache de respostas reidratadas;
3. memória restrita ausente no núcleo;
4. colisão de `chave_origem` entre clientes;
5. PII persistida em resposta/crítica;
6. AILog legado sem campos obrigatórios;
7. precedente de encerramento sem escopo;
8. modelo Groq hardcoded;
9. metadados RAG listados sem ownership.

O PR permanece condicionado à CI completa e não deve ser integrado manualmente enquanto o runner self-hosted não concluir os gates.