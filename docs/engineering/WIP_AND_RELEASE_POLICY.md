# Política de WIP e promoção — EJC

## Objetivo

Reduzir conflitos, branches envelhecidas, correções sobrepostas e regressões decorrentes de várias frentes simultâneas no mesmo núcleo do EJC, sem transformar segurança e governança em gargalo operacional.

A regra central do EJC passa a ser: **encurtar o ciclo código → teste dirigido → correção → CI → merge**, mantendo mudanças pequenas, reversíveis e rastreáveis.

## Limite de trabalho em progresso

No máximo, simultaneamente:

1. **1 frente estrutural** — arquitetura, segurança, banco, CI/CD, RAG core, autenticação ou observabilidade transversal;
2. **1 frente funcional** — um módulo/fluxo de negócio isolado;
3. PRs de dependência automatizada podem existir em paralelo, mas não são promovidos em lote e não contam como justificativa para ultrapassar os limites acima.

Uma terceira frente só começa quando uma das duas anteriores estiver em estado terminal: integrada e homologada, ou encerrada com decisão registrada.

## Entrega rápida segura

Quando uma demanda ampla puder ser decomposta sem quebrar contrato transacional ou de domínio, ela deve ser dividida em PRs menores e independentes.

Ordem preferencial de decomposição:

1. **estabilização / correção P0-P1**;
2. **schema expand-only e infraestrutura de compatibilidade**;
3. **backend/regra de negócio**;
4. **workers/IA/RAG/processamento assíncrono**;
5. **frontend/UX**;
6. **remoção de legado ou contração de schema**, somente depois de homologação.

Não fragmentar artificialmente uma alteração que dependa da mesma atomicidade para permanecer segura. Exemplo: criação de registro jurídico + audit log obrigatório pertencem à mesma unidade de mudança quando a separação permitir estado sem trilha.

## PRs empilhados (stacked PRs)

É permitido desenvolver uma frente dependente enquanto o PR anterior ainda está em CI, desde que:

- o PR filho tenha como base a branch do PR pai;
- a dependência esteja explícita no corpo do PR;
- o PR filho não seja mergeado antes do pai;
- qualquer alteração no contrato do pai seja reconciliada antes da promoção do filho;
- depois do merge do pai, o filho seja rebaseado/retargeted para a `main` e rode novamente os gates no novo HEAD.

Use stacked PR quando isso reduzir tempo ocioso sem criar duas implementações concorrentes do mesmo contrato.

## Tamanho e coesão do PR

Preferir PR que possa ser entendido e revertido como uma única decisão técnica.

Sinais de que a frente deve ser separada:

- migration + redesign visual não relacionados pela mesma atomicidade;
- segurança/lifecycle misturados com refatoração estética;
- backend estável bloqueado por trabalho de frontend ainda incompleto;
- mudança de RAG/IA que possa ficar atrás de flag independente;
- arquivos alterados em vários módulos sem dependência funcional clara.

Não usar número rígido de linhas como único critério. O critério é **coesão, reversibilidade e superfície de risco**.

## Flags e ativação gradual

Integrações sensíveis ou dependentes de infraestrutura devem preferir ativação gradual quando isso não enfraquecer a segurança do caminho ativo.

Exemplos:

- antimalware;
- IA pós-upload;
- indexação automática no RAG;
- novos workers/filas;
- integrações externas;
- novos mecanismos de busca/indexação.

Regras:

- flag desligada deve preservar comportamento seguro e conhecido;
- flag ligada deve falhar de modo seguro quando a funcionalidade for um gate de segurança (ex.: scanner antimalware obrigatório);
- nunca usar flag para desabilitar autenticação, RBAC, auditoria, sanitização LGPD ou validação crítica;
- ativação em produção ocorre somente após CI + homologação da infraestrutura correspondente.

## Estratégia de testes para reduzir ciclo

A ordem padrão é:

1. **teste dirigido do módulo alterado**;
2. **teste de contrato/RBAC/Alembic quando aplicável**;
3. **build/checagem do frontend quando houver mudança TS/React**;
4. **suíte completa e gates de CI**.

Falha em teste dirigido deve ser corrigida antes de gastar ciclo com a suíte inteira.

Nenhum teste pode ser marcado como executado sem evidência real do comando/run correspondente.

## Migration rápida e segura

Para evoluções de schema, preferir:

1. migration **expand-only**;
2. aplicação em homologação;
3. código compatível com estado antigo/novo quando necessário;
4. backfill controlado;
5. validação de dados;
6. somente em PR posterior remover coluna/constraint/legado antigo.

Antes de migration:

- confirmar head Alembic atual;
- confirmar que tabela/campo não existe;
- atualizar o teste de single head;
- documentar upgrade/downgrade;
- evitar `DROP` no mesmo passo de introdução do substituto.

## Ordem de trabalho

1. Issue com problema/objetivo e risco;
2. leitura da `main` atual;
3. branch nova baseada no HEAD atual ou no PR pai explicitamente declarado;
4. implementação coesa;
5. testes dirigidos adequados ao escopo;
6. correção das falhas dirigidas;
7. PR com Definition of Done;
8. suíte completa/gates no HEAD exato;
9. revisão;
10. merge na ordem das dependências;
11. deploy pelo mecanismo aprovado;
12. health/readiness/smoke;
13. homologação do fluxo alterado;
14. encerramento da Issue e de PRs supersedidos.

## Regra de CI

`mergeable=true` não significa pronto para merge.

Um PR só é elegível para promoção quando os checks obrigatórios executaram passos reais no HEAD exato e ficaram verdes. Status ausente, `pending` indefinido, workflow que falhou antes do primeiro step ou check meramente decorativo não satisfaz o gate.

Quando um CI falhar:

1. corrigir primeiro a causa concreta apontada;
2. rerodar no novo SHA;
3. não ampliar o escopo do PR enquanto existir regressão básica sem relação com a ampliação;
4. somente depois continuar a próxima camada do stack.

## Regras para PRs antigos ou divergentes

- não fazer merge apenas porque o PR possui correções aparentemente úteis;
- comparar com a `main` atual;
- identificar quais mudanças ainda não existem;
- extrair somente as mudanças necessárias para branch limpa baseada na `main` atual;
- executar novamente CI e revisão;
- encerrar o PR antigo como supersedido somente após existir vínculo para a frente limpa ou comprovação de que seu conteúdo já entrou na `main`.

## Regras para dependências

- upgrades major são avaliados individualmente;
- não usar “merge all” de Dependabot;
- alteração de framework, ORM, build, estado ou biblioteca de segurança exige teste de regressão compatível;
- atualização que alterar API pública exige plano de compatibilidade.

## Promoção para produção

Produção só recebe commit que:

- está na `main` por fluxo protegido;
- passou pelos gates aplicáveis no SHA correto;
- usa o workflow de deploy aprovado do repositório;
- executa backup pré-deploy quando exigido;
- preserva rollback;
- passa por health/readiness e smoke pós-deploy.

Nenhum atalho manual substitui o fluxo acima salvo incidente crítico, quando o ato emergencial deve ser documentado e reconciliado imediatamente no GitHub.

## Regra de interrupção

Ao surgir defeito P0/P1 durante uma frente, a prioridade muda para estabilização. Novas funcionalidades ficam congeladas até:

- causa raiz identificada;
- correção validada;
- rollback conhecido;
- incidente registrado.

Em stacked PRs, isso significa congelar a promoção dos filhos; desenvolvimento que não interfira na causa raiz pode continuar apenas em branch isolada e não deve mascarar o gate vermelho do pai.

## Estado recomendado das ondas

1. Estabilização e produção;
2. higiene de PRs/issues/branches;
3. prazos, intimações e fontes processuais;
4. qualidade jurídica da IA e gold set humano;
5. observabilidade e alertas;
6. somente então novas funcionalidades de grande porte.
