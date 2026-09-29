# Integração contextual de IA nos módulos existentes

## Decisão de produto

As capacidades inspiradas no catálogo analisado foram incorporadas como ações dos módulos já existentes do EJC. Não foi criado novo item de menu, nova entidade de negócio ou módulo paralelo.

- `CasoDetalhe` continua sendo o centro operacional do caso.
- `Ferramentas de IA` continua sendo o catálogo completo e a área de uso avulso.
- Cada aba do caso recebe um painel compacto e recolhido de ações contextuais.
- O backend continua usando o catálogo `EjcSkill`, os logs de IA e os endpoints de casos e agenda existentes.

## Fluxo implementado

1. O frontend informa ao backend o caso e a superfície atual, como documentos, provas, prazos, audiências, teses, contratos ou financeiro.
2. O backend usa área, fase e superfície para ranquear até cinco skills já cadastradas.
3. Quando há arquivo, uma classificação determinística local identifica o tipo documental antes da escolha do fluxo.
4. A skill selecionada produz apenas um rascunho interno e auditável.
5. O usuário revisa o resultado e confirma a responsabilidade profissional.
6. Somente após confirmação explícita o resultado pode virar nota do caso ou evento de agenda.
7. Próximas ações são sugeridas, mas nunca executadas automaticamente.

## Encaixe por módulos existentes

| Superfície existente | Ações priorizadas |
| --- | --- |
| Documentos | síntese, classificação, contratos, CNIS/PPP, laudos e peças |
| Provas | detector de contradições, casador de fatos, prints e laudos |
| Prazos | prazo seguro, intimações, prescrição e decadência |
| Audiências | roteiro, transcrição e preparação de perguntas |
| Teses e jurisprudência | validação, distinguishing e pesquisa semântica |
| Financeiro e acordo | honorários, proposta, minuta e cálculos aplicáveis |
| Estratégia defensiva | raio-X, advogado do diabo, réplica, recursos e contrarrazões |

O ranqueamento é explicável e limitado. O catálogo completo não é despejado em todas as telas.

## Metadados e auditoria

Cada execução devolve, quando aplicável:

- identificador do log de IA;
- nome técnico e nome de exibição da skill;
- superfície de origem;
- tipo de entrada;
- indicação de uso do RAG do cliente;
- classificação documental e confiança;
- próximas ações permitidas.

O conteúdo integral permanece no log de IA existente. A classificação local registra apenas tipo, confiança e sinais abstratos, sem criar uma segunda cópia do documento.

## Segurança e responsabilidade

- A execução é apresentada como rascunho interno.
- A aplicação exige revisão humana marcada pelo usuário.
- Nota e agenda exigem confirmação adicional do navegador.
- O gate de citações do fluxo HITL continua ativo.
- Feedback útil/não útil utiliza o endpoint de feedback já existente.
- Skills restritas continuam respeitando permissões, caso vinculado e RAG isolado por tenant.
- Não há protocolo, envio externo ou alteração de peça automática.

## Compatibilidade e rollback

As alterações são aditivas:

- campos novos de resposta são opcionais;
- `skill_name` segue obrigatório no fluxo textual e passa a aceitar seleção automática somente no upload documental;
- clientes anteriores continuam podendo escolher uma skill explicitamente;
- não há migration nova;
- remover o componente contextual do `CasoDetalhe` restaura a experiência anterior sem perda de dados.

## Critérios de aceite

- Nenhum novo menu ou módulo de negócio.
- Recomendações limitadas e aderentes à aba/área.
- Documento classificado antes da escolha automática da skill.
- Resultado contém log e metadados de auditoria.
- Nenhuma mutação no caso sem confirmação humana.
- Encadeamento sempre manual e revisável.
- Testes determinísticos cobrem classificação, ranking, restrição por caso e próximas ações.
