# Auditoria Integral do Núcleo de IA e Conhecimento Jurídico do EJC

**Data:** 19 de julho de 2026  
**Escopo:** backend de IA, RAG/pgvector, ingestão jurídica, agentes, prompts, governança, privacidade, auditoria, testes e migrations.  
**Branch de correção:** `audit/ai-knowledge-core-hardening`  
**Base analisada:** `main` no commit `8bbf33d0e6beffae448becc26385c780c58b512e`.

---

## 1. Conclusão executiva

O EJC possui uma fundação de IA juridicamente madura para o estágio atual: gateway central, política de provedores, sanitização e pseudonimização, RAG híbrido, versionamento do conhecimento, curadoria, validação de citações, agentes declarativos, HITL e suíte de avaliação offline. As auditorias anteriores resolveram fragilidades relevantes de embeddings, grounding, reranking, FIRAC, avaliação e governança.

A revisão integral, porém, identificou quatro riscos estruturais de alta prioridade e dois defeitos operacionais relevantes:

1. **Fallback de provedor não fail-closed:** a ausência de candidatos elegíveis podia gerar fallback sintético ao Groq, contrariando o kill-switch de provedores externos.
2. **Cache incompatível com pseudonimização reversível:** respostas já reidratadas com PII real podiam ser persistidas no Redis; um cache hit posterior não possuía o mapa de reidratação da request original.
3. **Memória restrita ausente no núcleo canônico:** o `ContextBuilder` fazia busca RAG sem `scope_client_id`, excluindo peças, precedentes e comunicações do próprio cliente pelo filtro fail-closed.
4. **Unicidade global de `chave_origem`:** o banco e o upsert não permitiam a mesma chave em clientes diferentes e o write path buscava sem escopo, apesar de a recuperação já ser tenant-aware.
5. **Persistência de resposta reidratada no AILog:** o prompt era sanitizado, mas a resposta e a crítica podiam conter PII real.
6. **Auditoria silenciosamente perdida em writers legados:** algumas rotas instanciavam `AILog` sem `id` ou `modelo` e engoliam a falha do commit.

Os seis pontos foram corrigidos nesta entrega, com testes específicos e migration própria.

**Avaliação após as correções:** arquitetura apta a seguir como núcleo único, desde que a CI completa seja aprovada e a migration seja aplicada de forma coordenada. Ainda existem dívidas de convergência, mas nenhuma delas justifica criar uma segunda IA ou um segundo banco de conhecimento.

---

## 2. Arquitetura efetivamente existente

### 2.1 Execução de IA

Fluxo canônico:

```text
frontend / endpoint interno
        ↓
app.services.ai.core.orchestrator.run
        ↓
classificação de intenção + agente
        ↓
RBAC / ownership / orçamento / sanitização
        ↓
ContextBuilder (caso + documento + processo + RAG)
        ↓
AIProviderPolicy
        ↓
ai_gateway.chat
        ↓
provider elegível
        ↓
ResponseValidator
        ↓
AILog + HITL
```

Fluxos legados ainda ativos:

```text
router/service legado
        ↓
core.ai_brain ou ai_gateway.chat
        ↓
gateway central
        ↓
writer manual de AILog em alguns pontos
```

O gateway é único no transporte, mas o contrato completo de orquestração ainda não é universal. A entrega endurece a primitiva comum para que os fluxos legados não escapem dos gates críticos.

### 2.2 Conhecimento jurídico

```text
fontes oficiais / upload / Drive / documentos internos
        ↓
normalização
        ↓
curadoria e metadados
        ↓
upsert versionado
        ↓
KnowledgeDoc + KnowledgeChunk
        ↓
embeddings pgvector + FTS opcional
        ↓
RRF / reranker opcional
        ↓
gate de aprovação + escopo do cliente
        ↓
contexto dos agentes
```

As versões anteriores são preservadas; o RAG usa apenas a vigente por padrão. Conteúdo público usa `client_id=NULL`. Conteúdo de caso/cliente exige escopo verificável.

---

## 3. Pontos fortes confirmados

### 3.1 Governança e revisão humana

- Respostas jurídicas são tratadas como rascunho.
- Agentes que exigem fontes passam por validação de citações.
- Há detecção de promessa de resultado e alerta ético.
- O agent loop exige confirmação para ferramentas de escrita.
- A aprovação HITL é auditável.
- Corpus fictício e documentos pendentes ficam fora da fundamentação padrão.

### 3.2 Privacidade e sigilo

- Sanitização estrutural de CPF, CNPJ, processo, e-mail, telefone, CEP e outros dados.
- Pseudonimização reversível com mapa mantido somente em memória.
- NER local para nomes residuais em OCR/RAG.
- Provider externo recebe marcadores, não PII real.
- Cofre documental não entra automaticamente no prompt.
- Recuperação de categorias restritas é fail-closed quando não existe escopo de cliente.

### 3.3 Qualidade do RAG

- Embeddings configuráveis e coerentes com o schema pgvector.
- Versionamento auditável de documentos e chunks.
- Gate de confiança e `rag_status`.
- Quarentena para súmulas não reconferidas.
- Busca densa e lexical, com RRF e reranking opcional.
- Exclusão padrão de corpus fictício.
- Fontes oficiais importantes possuem ingestores e telemetria.

### 3.4 Fontes jurídicas

Foram confirmados fluxos para, entre outros:

- Planalto;
- STJ;
- Câmara dos Deputados;
- Senado Federal;
- DJEN/CNJ;
- ANPD;
- Receita Federal;
- TJMG, quando o crawler opt-in estiver validado;
- jurisprudência importada com curadoria;
- documentos e precedentes internos revisados.

A classificação automática não equivale a aprovação jurídica. Fontes externas manuais e do Google Drive ficam pendentes até curadoria.

---

## 4. Achados e correções

## 4.1 P0 — fallback externo podia contrariar o kill-switch

### Situação encontrada

O gateway filtrava candidatos por elegibilidade, mas, quando a cadeia ficava vazia, criava fallback sintético ao Groq. Em determinadas configurações, isso podia tentar provider externo mesmo com `AI_EXTERNAL_PROVIDERS_ALLOWED=false`.

### Correção

Foi instalado um resolver fail-closed na primitiva interna `_resolver_cadeia`. Todos os candidatos finais são novamente submetidos a `_provider_elegivel`. Cadeia vazia permanece vazia e a chamada falha de forma segura, sem tocar em rede externa.

### Arquivos

- `backend/app/services/ai_core_hardening_patch.py`
- `backend/app/services/event_subscribers.py`
- `backend/tests/test_ai_knowledge_core_hardening.py`

### Estado

**Corrigido.** O patch é transitório; o backlog deve unificar definitivamente o registro de provedores entre `AIProviderPolicy` e `ai_gateway`.

---

## 4.2 P0 — cache podia persistir resposta reidratada com PII

### Situação encontrada

Na pseudonimização reversível, o provider recebe marcadores e a resposta é reidratada localmente. O cache gravava a resposta depois da reidratação. Isso implicava:

- PII real no Redis;
- impossibilidade lógica de reidratar corretamente um hit futuro, pois o mapa é efêmero;
- risco de mistura semântica entre requests semelhantes.

### Correção

Tarefas em `EXTERNO_PSEUDONIMIZADO` ou `EXTRACAO_LOCAL` recebem chave `ai:nocache:*`. `obter` e `gravar` tornam-se NO-OP antes de abrir conexão Redis. A decisão é fail-closed: falha ao identificar a política também desabilita cache.

Tarefas estritamente locais ou com mascaramento irreversível continuam tecnicamente cacheáveis, quando a flag geral estiver ativa.

### Arquivos

- `backend/app/services/ai_cache.py`
- `backend/tests/test_ai_cache.py`

### Estado

**Corrigido.** Recomenda-se manter o cache global desligado até haver classificação explícita de quais tarefas locais realmente se beneficiam dele.

---

## 4.3 P0 — chave do RAG era global, apesar do sistema ser multi-cliente

### Situação encontrada

A migration 092 criava índice único parcial apenas em `chave_origem`. O `upsert_documento` também buscava somente pela chave. Logo:

- cliente A e cliente B não podiam manter a mesma chave externa;
- um upsert podia reutilizar ou desativar a versão de outro cliente;
- a API pública já tentava consultar por chave + cliente, divergindo do banco;
- o filtro de leitura não corrigia o risco do write path.

### Correção

A identidade vigente passa a ser:

```text
(COALESCE(client_id, ''), chave_origem)
```

Efeitos:

- documentos públicos (`client_id=NULL`) continuam globalmente únicos;
- a mesma chave pode existir em clientes diferentes;
- versionamento de um cliente não altera o outro;
- o upsert procura e atualiza apenas dentro do escopo correto;
- categorias restritas sem `client_id` são bloqueadas no write path.

### Migration

- `109_rag_scope_cliente`

### Arquivos

- `backend/app/services/ingestion_service.py`
- `backend/alembic/versions/109_rag_chave_origem_por_cliente.py`
- `backend/tests/test_rag_scope_cliente_dblevel.py`
- `backend/tests/test_alembic_single_head.py`

### Estado

**Corrigido no branch.** Exige PostgreSQL real e `alembic upgrade head` na CI.

---

## 4.4 P1 — o núcleo canônico não recuperava memória restrita do próprio cliente

### Situação encontrada

O filtro do RAG é corretamente fail-closed: categoria restrita só aparece se `kd.client_id = scope_client_id`. Porém o `ContextBuilder` chamava `buscar_contexto_rag` sem esse escopo. Consequência: o agente autorizado via o dossiê do caso, mas não recuperava precedentes internos, peças revisadas ou comunicações do mesmo cliente.

### Correção

Após montar o dossiê do caso autorizado, o backend resolve o cliente por `case_id`, sem aceitar `client_id` enviado pelo frontend, e repassa o escopo ao RAG.

### Arquivos

- `backend/app/services/ai/core/context_builder.py`
- `backend/tests/test_ai_knowledge_core_hardening.py`

### Estado

**Corrigido.** A memória interna volta a participar do núcleo único sem enfraquecer o isolamento.

---

## 4.5 P1 — resposta e crítica do AILog podiam conter PII real

### Situação encontrada

O prompt persistido era sanitizado, mas a resposta do gateway podia ter sido reidratada com nomes, CPF e outros dados. Vários writers instanciam `AILog` diretamente.

### Correção

O modelo ORM agora pseudonimiza `resposta` e `critica_adversarial` no write path. O mapa é descartado, tornando a persistência irreversível. Se o NER falhar, o sistema degrada para mascaramento estrutural, não para texto bruto.

### Arquivos

- `backend/app/models/ai_log.py`
- `backend/tests/test_ai_knowledge_core_hardening.py`

### Estado

**Corrigido.** O texto integral continua disponível ao usuário na request, mas o log guarda somente versão protegida.

---

## 4.6 P1 — writers legados podiam perder o AILog por ausência de campos

### Situação encontrada

Algumas rotas instanciavam `AILog` sem `id` e/ou `modelo`. Como as colunas eram obrigatórias e certos handlers engoliam a exceção do commit, a auditoria podia não existir apesar do código aparentar registrá-la.

### Correção

- `id` recebe UUID no default Python;
- `modelo` recebe `nao_informado` quando o writer não tem telemetria;
- modelo real continua prevalecendo quando informado;
- normalização de nomes de modelo foi preservada.

### Estado

**Corrigido.** O valor `nao_informado` é deliberadamente honesto; não inventa provider ou modelo.

---

## 4.7 P1 — precedente de encerramento não informava escopo ao RAG

### Situação encontrada

`cases.encerrar_caso` criava `precedente_interno` com chave `caso:<id>`, mas sem `client_id` e `case_id`. O novo gate corretamente o bloquearia.

### Correção de compatibilidade

O startup hardening reconhece exclusivamente o padrão canônico `caso:<id>`, carrega o caso no banco e deriva `client_id`/`case_id` do servidor. Nenhuma identificação de cliente do frontend é aceita. Outras chaves restritas sem escopo continuam bloqueadas.

### Estado

**Corrigido.** Recomenda-se, em refatoração posterior, passar os campos explicitamente no próprio endpoint e remover o adapter.

---

## 4.8 P1 — Google Drive podia classificar peça de cliente sem vínculo verificável

### Situação encontrada

A taxonomia do Drive detecta sinais de peça de cliente e classifica como `peca_interna`, mas o sincronizador da pasta geral não possui mapeamento confiável de arquivo → caso/cliente.

### Efeito da correção

O write gate passa a recusar esses itens individualmente. O sincronizador já isola falhas por arquivo, registra o motivo e continua com legislação, jurisprudência e doutrina. Isso é preferível a inserir conteúdo sigiloso em escopo global.

### Próximo passo

Criar fluxo explícito de vinculação:

```text
arquivo Drive classificado como restrito
        ↓
quarentena
        ↓
seleção/identificação do caso
        ↓
validação de ownership
        ↓
ingestão com client_id + case_id
```

### Estado

**Risco contido; funcionalidade de vinculação ainda pendente.**

---

## 4.9 P2 — modelo Groq estava duplicado e fixo no router de tarefas

### Situação encontrada

`system_prompts/router.py` usava nome de modelo Groq hardcoded, enquanto o gateway e Settings já possuíam `GROQ_MODEL` configurável.

### Correção

O router passa a usar `Settings.GROQ_MODEL`; modelos Anthropic também continuam vindos de Settings.

### Estado

**Corrigido.** A seleção final segue sujeita à política de elegibilidade e aos fallbacks do gateway.

---

## 5. Dívidas técnicas remanescentes

As pendências abaixo não são motivo para criar novo núcleo; devem ser tratadas por convergência incremental.

### 5.1 Unificar registro e resolução de provedores

Hoje há regras em:

- `AIProviderPolicy`;
- `ai_gateway`;
- `system_prompts/router.py`;
- configurações do cofre/.env;
- patches de compatibilidade.

Objetivo futuro: um único `ProviderRegistry` produzir a cadeia elegível, com provider, modelo, modo de sanitização, custo, disponibilidade e justificativa auditável.

### 5.2 Migrar callers diretos para o orquestrador

Existem muitos usos legítimos de `ai_gateway.chat`, mas parte deles não passa pelo `ResponseValidator` nem pelo logger canônico. A migração deve ser por domínio, com testes de contrato, evitando substituição em massa.

Prioridade sugerida:

1. geração de peça;
2. análise estratégica;
3. crítica adversarial;
4. pesquisa jurídica;
5. resumos operacionais;
6. tarefas administrativas.

### 5.3 Consolidar prompts e configuração de tarefa

Ainda existem prompts em serviços específicos, templates, registry e módulos legados. Criar inventário canônico com:

- chave única;
- versão;
- tarefa/agente;
- exige fonte;
- formato de saída;
- política HITL;
- testes de invariantes;
- hash do prompt utilizado no AILog.

### 5.4 Melhorar metadados recuperados pelo RAG

A saída atual deve evoluir para incluir, de modo uniforme:

- URL oficial;
- data do documento/julgamento/publicação;
- tribunal e órgão;
- vigência/atualidade;
- versão;
- `client_id`/`case_id` apenas na camada interna;
- tipo de fonte;
- status de conferência;
- razão de relevância.

### 5.5 Diferenciar memória por caso e memória por cliente

A unicidade adotada é por cliente + chave. Para determinadas categorias, especialmente comunicação processual e andamento, a recuperação deve poder exigir também `case_id`, evitando que comunicação de um caso apareça em outro caso do mesmo cliente quando não for pertinente.

### 5.6 Atualidade das fontes

Criar SLA por fonte:

- legislação: data da última conferência e revogação;
- jurisprudência: data de julgamento/publicação;
- súmulas: situação vigente/cancelada;
- crawlers: último sucesso e alterações de layout;
- DJEN: janela e continuidade da captura;
- documentos internos: versão e responsável pela revisão.

### 5.7 Calibração de busca

FTS, HyDE e reranker devem ser ativados somente após avaliação com conjunto jurídico real. O objetivo não é maximizar quantidade de fontes, mas precisão, diversidade e ausência de falso grounding.

---

## 6. Matriz de risco após a correção

| Área | Antes | Depois do branch | Observação |
|---|---:|---:|---|
| Kill-switch externo | Alto | Baixo | Cadeia vazia não sintetiza provider |
| PII no cache | Alto | Baixo | Tarefas reversíveis são no-cache |
| PII no AILog | Alto | Baixo | Pseudonimização no ORM |
| Colisão RAG cross-tenant | Crítico | Baixo | Índice e upsert por cliente |
| Memória interna no núcleo | Médio | Baixo | Escopo derivado do caso |
| Drive restrito sem vínculo | Alto | Médio | Bloqueado/quarentenado, falta UX de vínculo |
| Chamadas fora do orquestrador | Médio | Médio | Gateway endurecido; convergência pendente |
| Duplicação de provider policy | Médio | Médio | Adapter transitório |
| Atualidade de fontes | Médio | Médio | Telemetria existe; SLA uniforme pendente |

---

## 7. Testes adicionados/alterados

- kill-switch sem qualquer chamada de provider;
- pseudonimização de resposta e crítica no AILog;
- defaults de auditoria para writer legado;
- escopo de cliente repassado pelo ContextBuilder;
- categoria restrita sem cliente bloqueada;
- tarefas reidratáveis sem acesso ao Redis;
- cache permitido apenas em modo compatível;
- duas chaves idênticas em clientes distintos;
- versionamento independente entre clientes;
- head único do Alembic atualizado.

A validação definitiva exige:

```bash
python -m alembic upgrade head
RUN_DB_TESTS=1 python -m pytest tests -v
npm ci
npm run build
python -m app.eval.run_eval --smoke
python -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0
```

---

## 8. Implantação e rollback

### Ordem recomendada

1. backup lógico do PostgreSQL;
2. executar CI completa em Postgres pgvector;
3. revisar contagem de duplicidades por escopo;
4. aplicar `alembic upgrade head`;
5. reiniciar backend/scheduler;
6. validar health, provider policy, RAG e AILog;
7. executar consultas de smoke por caso de dois clientes diferentes;
8. monitorar logs e métricas por 24 horas.

### Verificações pós-deploy

- nenhum provider externo chamado com kill-switch desligado;
- nenhuma chave `ai:nocache:*` gravada no Redis;
- `ai_logs.resposta` sem CPF/CNPJ/nome contextual em claro;
- mesma `chave_origem` possível em clientes distintos;
- busca sem `scope_client_id` não retorna conteúdo restrito;
- busca de caso autorizado recupera memória do próprio cliente;
- Google Drive marca peça sem vínculo como erro/quarentena, não como global.

### Rollback

A migration preserva documentos; o downgrade rebaixa versões concorrentes antes de restaurar a unicidade global. Isso evita exclusão física, mas pode tornar não vigente uma das chaves duplicadas entre clientes. Portanto, rollback após uso efetivo do novo índice deve ser excepcional e precedido de exportação dos documentos afetados.

---

## 9. Dependência com o PR DataJud

Há um PR DataJud aberto que também parte da migration 108 e utiliza número 109. Os dois PRs não podem ser integrados nessa forma sem criar múltiplos heads.

Ordem recomendada:

1. integrar primeiro este hardening do núcleo;
2. rebasear o PR DataJud sobre a nova `main`;
3. renomear a migration DataJud para 110 e definir `down_revision = "109_rag_scope_cliente"`;
4. atualizar o teste de head canônico;
5. executar novamente a CI completa.

A integração inversa também é tecnicamente possível, mas exigiria renumerar esta migration. O requisito essencial é manter **um único head Alembic**.

---

## 10. Parecer final

O EJC não precisa de outra IA nem de outro banco de conhecimento. Precisa concluir a convergência para que todos os fluxos usem o mesmo contrato de segurança, contexto, validação e auditoria.

Após as correções desta entrega, o núcleo passa a ter:

- provider routing fail-closed;
- cache compatível com a política de PII;
- auditoria protegida;
- memória jurídica restrita realmente utilizável;
- write path multi-cliente coerente com o read path;
- migration e testes de isolamento;
- bloqueio seguro de documentos restritos sem vínculo.

**Parecer:** tecnicamente recomendável para merge somente após CI verde, revisão da migration em PostgreSQL real e coordenação com o PR DataJud. Não se recomenda merge manual contornando os gates.