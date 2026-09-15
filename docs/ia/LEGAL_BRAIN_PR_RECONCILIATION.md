# Legal Brain — reconciliação de PRs

Data-base: 13/09/2026. Base da branch: `main@e247ed90dac220dc243d3984d07fb290a1a7bb2b`.

Este documento registra dependências para impedir merge por número ou por
`mergeable=true` sem considerar contrato e ancestry.

## P0 antes do rollout do Legal Brain

- `#1646` — integridade/LGPD de CPF. Merge somente com CI do HEAD verde.
- `#1635` — ownership de tarefas e caminho Atendimento -> Task.
- `#1644` — ownership da memória institucional case-scoped.
- `#1638` — DataJud não pode materializar Deadline automaticamente.
- `#1637` — encerramento do caso não depende do sucesso de memória/RAG acessório.

## Continuidade e documentos

- `#1572` — persistência de backup cifrado recuperável. Antes de nova migration
  do Legal Brain, exige CI verde e restore drill controlado.
- `#1606` — upload GED pelo pipeline streaming canônico. Deve ser reconciliado
  com a main vigente antes da promoção.

## Conhecimento e avaliação

- `#1483` — política: fonte oficial e vigência conferida são dimensões distintas.
- `#1647` — distingue vigência pendente de versão histórica/superada sem abrir o
  gate de recuperação.
- `#1498` — coletor fail-safe para fontes do gold set; reconstruir sobre main.
- `#1502` — correção DB-level da ferramenta de deduplicação; integrar ferramenta
  não significa executar deduplicação em produção.
- `#1496` — atestação humana externa do gold set; só ganha valor depois da
  curadoria material do benchmark.

## Inteligência e interface

- `#1645` — Dashboard IA-first, Sala Jurídica, dossiê estruturado e alertas. É
  veículo canônico; não criar implementação concorrente.
- `#1610` — EvidenceAgent/JudicialReviewAgent. Reaplicar sobre o núcleo vigente
  depois da consolidação do #1645, em vez de mesclar ancestry antigo cegamente.
- `#1528` — jurimetria externa; sinal descritivo, nunca probabilidade de êxito.
- `#1252` — piloto TJMG Betim/Contagem; migrar dados úteis para a governança
  atual e preservar quarentena.

## Não mesclar no estado atual

- `#1412` — a própria PR declara bloqueio de migration/topologia. Extrair apenas
  invariantes úteis e reconstruir sobre o ledger real.
- `#1545` — limpeza ampla e antiga; portar apenas guardas comprovadamente ainda
  ausentes após a consolidação atual.
- `#1538` — fundação visual concorrente com a direção mais recente do Dashboard;
  reavaliar depois do #1645.
- `#1307` — auditar residual; grande parte do comportamento fail-closed já está
  na main e não deve ser duplicada.
- `#1251` — fechado sem merge e arquiteturalmente paralelo; não ressuscitar.

## Regra de merge

Para qualquer PR acima:

1. conferir HEAD exato;
2. CodeRabbit/revisão sem P0/P1;
3. Woodpecker verde no HEAD exato;
4. comparar diff com a main vigente;
5. validar ownership/RBAC, LGPD e HITL quando aplicáveis;
6. Alembic single-head + upgrade/downgrade/re-upgrade quando houver migration;
7. rollback explícito;
8. somente então promover.
