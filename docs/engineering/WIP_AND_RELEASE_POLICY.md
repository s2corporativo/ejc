# Política de WIP e promoção — EJC

## Objetivo

Reduzir conflitos, branches envelhecidas, correções sobrepostas e regressões decorrentes de várias frentes simultâneas no mesmo núcleo do EJC.

## Limite de trabalho em progresso

No máximo, simultaneamente:

1. **1 frente estrutural** — arquitetura, segurança, banco, CI/CD, RAG core, autenticação ou observabilidade transversal;
2. **1 frente funcional** — um módulo/fluxo de negócio isolado;
3. PRs de dependência automatizada podem existir em paralelo, mas não são promovidos em lote e não contam como justificativa para ultrapassar os limites acima.

Uma terceira frente só começa quando uma das duas anteriores estiver em estado terminal: integrada e homologada, ou encerrada com decisão registrada.

## Ordem de trabalho

1. Issue com problema/objetivo e risco;
2. leitura da `main` atual;
3. branch nova baseada no HEAD atual;
4. implementação coesa;
5. testes locais/CI adequados ao escopo;
6. PR com Definition of Done;
7. gates no HEAD exato;
8. revisão;
9. merge;
10. deploy pelo mecanismo aprovado;
11. health/readiness/smoke;
12. homologação do fluxo alterado;
13. encerramento da Issue e de PRs supersedidos.

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

## Estado recomendado das ondas

1. Estabilização e produção;
2. higiene de PRs/issues/branches;
3. prazos, intimações e fontes processuais;
4. qualidade jurídica da IA e gold set humano;
5. observabilidade e alertas;
6. somente então novas funcionalidades de grande porte.