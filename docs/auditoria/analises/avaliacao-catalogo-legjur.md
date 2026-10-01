# Avaliação do catálogo de referência para o EJC

## Decisão arquitetural

As referências visuais foram tratadas como inventário de necessidades, não como
especificação técnica. O EJC deve manter um único Centro de Inteligência, com
perfis especializados por matéria, gates OAB, RAG interno, trilha de uso e
revisão humana. Não serão criados agentes ou páginas paralelas para cada card.

Esta segunda onda adiciona **52 perfis consolidados**:

| Área | Perfis |
| --- | ---: |
| Estratégia processual | 13 |
| Trabalhista | 12 |
| Previdenciário | 7 |
| Penal | 6 |
| Consumidor | 5 |
| Família e sucessões | 5 |
| Saúde | 2 |
| Provas e segurança | 2 |

Com os 22 perfis da primeira onda, o PR passa a acrescentar 74 fluxos ao
catálogo existente.

## O que foi incorporado

- Consumidor e saúde: negativação, conflito bancário, transporte aéreo,
  superendividamento, juros bancários, negativa e execução de saúde.
- Trabalhista: inicial, defesa, réplica, vínculo, rescisão indireta, recursos,
  execução, liquidação e mapa qualitativo de risco.
- Previdenciário: CNIS, PPP, indeferimento/CRPS, incapacidade, BPC, tempo rural e
  auditoria de atrasados.
- Penal: contraponto defensivo, resposta à acusação, cautelares, habeas corpus,
  inquérito e dosimetria.
- Família e sucessões: divórcio/união estável, partilha, alimentos, execução de
  alimentos e guarda/convivência.
- Estratégia: tutelas, agravo, contradições, prescrição, segurança contra prompt
  injection, precedentes, contrarrazões, embargos, réplica, recursos, raio-X,
  revisão adversarial e pesquisa auditável de dano moral.

## Capacidades reaproveitadas

Os seguintes recursos já existem no EJC e devem continuar como fontes
determinísticas; os novos perfis apenas preparam ou auditam seus insumos:

- liquidação trabalhista e índices oficiais;
- simulador/guia previdenciário;
- estimador de honorários;
- serviço de correção monetária e séries do Banco Central;
- cálculo de prescrição e outras calculadoras já registradas.

## Promessas da referência que não foram copiadas

- Percentual de êxito sem modelo calibrado e amostra governada.
- Valor médio, mínimo ou máximo de dano moral sem dataset oficial identificado,
  critérios de inclusão e data-base.
- Jurisprudência, súmula ou tema afirmados de memória do modelo.
- Peça anunciada como “pronta para protocolo”.
- Tutela, dano moral, repetição em dobro ou efeito suspensivo tratados como
  automáticos.
- Juros mensais fixos para pensão ou qualquer índice aplicado sem conferir
  título, período e tribunal.
- Plano de superendividamento “perfeito” ou aposentadoria “ideal” produzidos por
  texto probabilístico.

## Backlog que exige motor próprio

Estes cards não devem ser simulados por prompt. Antes de disponibilizar cálculo
numérico ao usuário, precisam de especificação, fórmulas versionadas, fontes de
índice, casos-limite e testes de regressão:

1. atualização de pensão por título, período e rito;
2. atrasados previdenciários por regime temporal;
3. liquidação cível por título e natureza da condenação;
4. plano matemático de repactuação por superendividamento;
5. ganho de capital imobiliário e hipóteses fiscais;
6. dosimetria penal e detração;
7. estatística de dano moral com base oficial rastreável.

## Salvaguardas aplicadas

- revisão humana e restrição OAB em todos os novos perfis;
- arquivos tratados como dados não confiáveis, nunca como instruções;
- triagem obrigatória de competência, fase, prazo, legitimidade e prova;
- separação explícita entre alegação, fato documentado, inferência e dado
  ausente;
- fontes oficiais e data de corte obrigatórias;
- cálculo sensível encaminhado a motor determinístico com memória auditável;
- respostas incompletas são interrompidas antes da minuta quando faltam dados
  essenciais.

## Critérios para liberação

- seed idempotente e sem duplicidade;
- áreas exibidas corretamente no filtro do Centro;
- testes unitários das salvaguardas e generalizações corrigidas;
- execução em ambiente de homologação com perfis OAB e não-OAB;
- revisão jurídica amostral por área;
- deploy somente após CI operacional e aprovação explícita.
