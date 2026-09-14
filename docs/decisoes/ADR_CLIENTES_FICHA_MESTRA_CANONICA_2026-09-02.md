# ADR — Clientes: Ficha Mestra canônica e fechamento do domínio

**Data:** 02/09/2026  
**Status:** Aceita  
**Escopo:** módulo Clientes do EJC

## Contexto

O domínio Clientes acumulou, ao longo da evolução do EJC, funções distribuídas entre listagem, dossiê, onboarding, pendências, Portal, LGPD, casos, documentos, honorários e IA. A auditoria de 02/09/2026 corrigiu defeitos P0/P1 de RBAC, ownership, PII, anonimização, IA e Portal; a onda seguinte simplifica a superfície sem criar outro subsistema.

O objetivo desta decisão é impedir que futuras implementações voltem a criar uma segunda ficha do cliente, um segundo onboarding, uma segunda saúde cadastral ou atalhos administrativos paralelos.

## Decisão

### 1. Superfícies canônicas

- `/clientes` é a **porta de entrada** do domínio: localizar e cadastrar cliente.
- `/clientes/:clientId` é a **Ficha Mestra do Cliente** e concentra a continuidade operacional.
- O endpoint histórico `/api/clients/{client_id}/dossie` permanece por compatibilidade contratual; o termo “dossiê” pode continuar em nomes internos/rotas legadas, mas não representa uma segunda superfície funcional.

### 2. Responsabilidades da Ficha Mestra

A Ficha Mestra pode compor, sem duplicar a fonte de verdade:

- identificação e contato;
- responsável/carteira;
- casos e prazos;
- documentos e solicitações;
- pendências e próximas ações;
- atendimentos/linha do tempo;
- Portal do Cliente;
- financeiro conforme RBAC;
- IA do cliente conforme RBAC/HITL.

Nenhuma dessas projeções autoriza criar novo cadastro ou persistência paralela quando já existir fonte canônica.

### 3. Onboarding

O onboarding canônico é `backend/app/services/onboarding.py`, exposto por `/api/analytics/onboarding*`.

Regras:

- reutilizar dados reais já existentes;
- não criar segunda tabela ou segundo serviço de onboarding;
- checklist deve ser objetivo e explicável;
- não inventar obrigação jurídica por padrão;
- carregamento em lista deve ocorrer em lote, evitando N+1;
- ownership deve usar os gates canônicos de Clientes.

### 4. Pendências e qualidade cadastral

`client_pending_items` e o painel da Ficha Mestra são o local preferencial para ações pendentes.

Indicadores de qualidade/onboarding devem ser fatos objetivos, por exemplo: documento ausente, contato ausente, procuração ausente, pendência vencida. Não usar score artificial ou classificação de “bom/ruim” sem regra de negócio homologada.

### 5. Conflito de interesses

A checagem de conflito é assistiva e não substitui análise profissional. Sua base ética foi revalidada em 13/09/2026 no texto oficial do Conselho Federal da OAB: **Código de Ética e Disciplina da OAB, aprovado pela Resolução CFOAB nº 02/2015**, especialmente os arts. **19 a 22**. Esses dispositivos tratam de representação de interesses opostos na mesma sociedade, conflito superveniente entre constituintes, dever de sigilo perante ex-cliente/ex-empregador e impedimento decorrente de intervenção anterior. A Resolução CFOAB nº 05/2024 alterou outros dispositivos do Código, sem modificar os arts. 19 a 22.

Fonte oficial de validação: `https://www.oab.org.br/leisnormas/legislacao/resolucoes/02-2015`.

O sistema deve distinguir explicitamente:

- nenhum conflito identificado;
- possível conflito;
- consulta indisponível/não concluída.

Falha técnica nunca pode ser apresentada como ausência de conflito. A resposta automatizada é apenas sinalização de apoio; a decisão sobre aceitação, manutenção ou renúncia de mandato exige análise profissional humana conforme o caso concreto.

### 6. LGPD e segurança

- CPF/CNPJ não devem ser exibidos em claro em listas gerais;
- logs/auditoria devem ser minimizados e sem conteúdo desnecessário;
- nenhuma ampliação de acesso apenas para facilitar UX;
- frontend não substitui RBAC/ownership do backend;
- anonimização e ações de alto impacto permanecem auditáveis e governadas;
- matching de possível duplicidade deve respeitar ownership antes de revelar candidato.

### 7. IA

A IA do cliente é auxiliar e sujeita a revisão humana. A Ficha Mestra é apenas superfície de consumo; não é autorizada a criar um segundo orquestrador, RAG ou memória paralela.

### 8. Deduplicação futura

Deduplicação assistida pode voltar a ser estudada, mas:

- nunca fazer merge automático;
- apresentar somente candidatos permitidos pelo ownership;
- exigir preview dos vínculos;
- definir previamente política de sobrevivência dos campos;
- decisão de consolidação deve ser restrita a papel autorizado e auditada;
- nenhuma exclusão física automática.

## Invariantes arquiteturais

1. Um cliente possui uma única identidade canônica em `clients`.
2. Uma única Ficha Mestra representa a visão 360º operacional.
3. Uma única política de ownership/RBAC governa o domínio.
4. Onboarding deriva dados; não cria verdade paralela.
5. Pendências são explícitas e rastreáveis.
6. IA não executa ação jurídica/financeira/documental definitiva sem os gates existentes.
7. PII é minimizada em UI, logs e auditoria.
8. Nenhuma nova rota/tabela/service de Clientes pode ser criada sem demonstrar que não duplica essas responsabilidades.

## Fechamento do módulo

Após integração da onda de simplificação, o módulo Clientes deve ser considerado **funcionalmente estabilizado** no escopo atual. Itens futuros de deduplicação, qualidade cadastral avançada ou automação de onboarding são roadmap de produto e não pendências necessárias para declarar o módulo operacional.

Pendências transversais do EJC — por exemplo deploy, homologação global, acessibilidade, infraestrutura de CI ou política geral de logs — continuam sendo acompanhadas em suas issues próprias e não reabrem automaticamente o domínio Clientes.

## Rollback

A decisão não exige migration. A onda correspondente pode ser revertida por `git revert` do PR. Nenhum dado é transformado e as rotas históricas permanecem compatíveis.
