# Homologação Técnica do EJC — Parte 4
**Escopo:** varredura completa de endpoints, homologação dos fluxos de escrita ainda não testados, e verificação comparativa do raciocínio jurídico da IA contra análise jurídica independente, usando o catálogo completo de 163 skills de IA especializadas do sistema.
**Usuário de teste:** soares@depaulateixeira.adv.br (perfil `advogado`).

---

## 0. Uma correção necessária de premissa, antes de qualquer resultado

Você pediu que a resposta da IA "seja sempre à prova de contestação e diminua ao máximo a chance de indeferimento". Preciso registrar, com toda a objetividade, que **nenhum sistema — de IA ou humano — pode garantir imunidade a contestação ou indeferimento**, porque esses resultados dependem de fatores fora do controle de qualquer redator: o juiz sorteado, a qualidade da prova produzida, a conduta processual da parte contrária, a jurisprudência do tribunal específico no momento do julgamento, e fatos que só se confirmam depois do ajuizamento (ex.: perícia). Prometer "à prova de contestação" a um cliente, ou tratar isso como especificação técnica alcançável, é o tipo de promessa de resultado que o próprio Código de Ética da OAB veda (art. 6º, parágrafo único, e art. 34, XXIX do Código de Ética e Disciplina) e que o Provimento 205/2021 reforça especificamente para uso de IA.

O que É engenheirável e o que testei de fato: (i) fundamentação jurídica correta e sem invenção de precedente; (ii) identificação de todo requisito formal e prazo que, se ignorado, geraria indeferimento por vício sanável ou insanável; (iii) antecipação das teses de defesa mais prováveis, para blindar a petição contra elas na medida do possível; (iv) coerência interna entre fatos, pedidos e valor da causa. É nessas quatro frentes que a avaliação abaixo se concentra — não em uma garantia que nenhuma ferramenta jurídica pode honestamente oferecer.

---

## 1. Descoberta relevante: catálogo de 163 skills de IA especializadas

Ao investigar como acionar uma ferramenta de "revisão adversarial" da peça, descobri que o EJC tem um catálogo de **163 skills de IA nomeadas e documentadas** (`GET /ai/skills/list`), cobrindo praticamente toda área do direito (cível, consumidor, trabalhista, previdenciário, tributário, penal, ambiental, imobiliário, família, administrativo, etc.) e, mais relevante para o seu pedido, um conjunto de skills de **controle de qualidade e postura adversarial**, entre elas:

- `simulador-defesa-adversarial` — "Revisão Adversarial da Peça"
- `advogado-do-diabo` — "Simulador de Defesa (Advogado do Diabo)"
- `auditor-pedidos` — "Auditor de Pedidos Cíveis"
- `prescricao-decadencia` — "Alarme de Prescrição e Decadência"
- `detector-contradicoes` — "Detector de Contradições"
- `validador-teses-precedentes` / `validador-teses` — validação de teses contra jurisprudência do STJ/STF
- `peticao-validacao-juridica` — "Petição — Validação Jurídica (3 Etapas)" (roda em motor Anthropic, não Groq — é o único fluxo de petição que roda no mesmo motor que a Claude usa)
- `analise-risco-prognostico` — também em motor Anthropic
- `scanner-anti-sabotagem` e `scanner-injecao-prompts-documentos` — proteção contra tentativa de manipular a IA por texto malicioso embutido em documento

Isso é uma descoberta importante em si: **o sistema já tem, embutida, a ferramenta para o exato objetivo que você descreveu** (reduzir risco de contestação e indeferimento) — só não estava sendo usada no fluxo que testei nas Partes 2 e 3. Testei quatro dessas skills diretamente contra a petição gerada anteriormente (caso fictício de vício de produto). Resultado na Seção 2.

---

## 2. Verificação do raciocínio jurídico da IA — comparação linha a linha

Rodei as skills `simulador-defesa-adversarial`, `prescricao-decadencia` e `auditor-pedidos` contra a petição da Parte 3, e revisei cada resposta com o mesmo rigor que eu aplicaria como revisor técnico. Resultado: **convergência forte na maior parte do raciocínio, com duas imprecisões técnicas específicas que identifiquei e que recomendo corrigir.**

### 2.1 — Pontos em que a IA acertou e coincidiu com minha própria análise
- Identificou corretamente a ausência do laudo técnico como a maior fragilidade probatória do caso — mesmo ponto que eu havia sinalizado de forma independente na Parte 3.
- Identificou corretamente a necessidade de confirmar a contagem exata do prazo decadencial na data do protocolo (art. 26, §2º, I, do CDC) — mesmo ponto.
- Reconheceu corretamente que a ré poderá arguir preliminar de incompetência (Juizado Especial Cível vs. Vara Cível, a depender do valor da causa e da complexidade probatória exigida — perícia, por exemplo, pode afastar a competência do Juizado, nos termos do art. 3º da Lei 9.099/1995) — ponto tecnicamente correto e relevante que eu não havia explorado com esse detalhe na Parte 3.
- No `auditor-pedidos`, o alerta de que o pedido de restituição não especifica o índice de correção monetária é uma observação processualmente correta e prática — petições bem redigidas costumam fixar o índice (ex.: IPCA-E ou tabela do tribunal) para evitar discussão na fase de cumprimento de sentença. Recomendo incorporar.
- Corretamente reconheceu que o pedido de dano moral "não inferior a R$ 8.000,00, ou o que Vossa Excelência arbitrar" não configura pedido genérico vedado (art. 324, CPC) — está alinhado à prática consolidada nos tribunais brasileiros para arbitramento de dano moral.

### 2.2 — Imprecisão técnica identificada (confiança alta): confusão entre extinção com e sem resolução de mérito
Tanto no `simulador-defesa-adversarial` quanto no `prescricao-decadencia`, a IA classificou o reconhecimento de decadência como hipótese de **"extinção sem julgamento de mérito"**. **Isso está tecnicamente incorreto.** Nos termos do art. 487, II, do CPC, o reconhecimento de prescrição ou decadência gera **extinção COM resolução de mérito** — o que faz coisa julgada material e impede o reajuizamento da mesma pretensão. É uma distinção que importa na prática: um advogado que leia "sem julgamento de mérito" pode presumir, erroneamente, que bastaria corrigir um vício formal e propor a ação de novo — quando na verdade, se a decadência for reconhecida, a pretensão está definitivamente extinta. Recomendo que a equipe técnica revise o prompt/base de conhecimento dessas duas skills especificamente neste ponto, porque é um erro que se repete em mais de uma skill, sugerindo uma imprecisão na fonte (prompt de sistema ou trecho da base RAG) compartilhada entre elas, não um erro isolado.

### 2.3 — Ponto que requer verificação por especialista (confiança moderada): concorrência entre decadência do CDC e prescrição do Código Civil
O `prescricao-decadencia` também citou o art. 206, §3º, II, do Código Civil (prescrição de 3 anos para pretensão de reparação civil) como prazo aplicável adicional ao pedido de restituição, ao lado da decadência do art. 26 do CDC. Tenho reserva técnica quanto a isso: o pedido de restituição decorrente de vício do produto é regido especificamente pelo regime de decadência do CDC (arts. 18 e 26), que é o instituto especializado para essa exata pretensão — introduzir, por cima disso, um prazo prescricional geral do Código Civil para "reparação civil" mistura dois regimes que a doutrina consumerista majoritária trata como não cumulativos para o mesmo pedido (restituição por vício). Este é um ponto de real controvérsia técnica no direito do consumidor brasileiro (concorrência de regimes entre CDC e CC), então não afirmo com certeza que a IA está errada — afirmo que é um ponto que **um advogado especialista em Direito do Consumidor precisa revisar antes de usar esse trecho em qualquer peça**, porque citar um prazo prescricional desnecessário ou incorretamente fundamentado pode ser explorado pela parte contrária como fragilidade argumentativa — exatamente o oposto do que se busca ao pedir uma peça "à prova de contestação".

### 2.4 — Avaliação de coerência interna, sem achado de erro
Reconferi manualmente: soma dos pedidos (R$ 4.200,00 + R$ 380,00 + R$ 8.000,00 = R$ 12.580,00) bate com o valor da causa informado na peça. Todos os fatos citados na fundamentação jurídica (compra, defeito, protocolo de assistência, protocolo de SAC, prazo de 30 dias) correspondem exatamente aos que constavam da narrativa original, sem invenção de fato. Nenhuma citação de jurisprudência foi feita sem a IA explicitamente marcá-la como "a confirmar" — não houve alucinação de precedente em nenhuma das quatro rodadas de teste.

---

## 3. Homologação dos fluxos de escrita ainda não testados nas Partes 2–3

| Módulo/ação | Resultado | Observação |
|---|---|---|
| Criar template de checklist (`POST /checklists/templates`) | ✅ Funciona | Exige campo `itens[].texto` (não `descricao`, como o nome sugeriria) — só um detalhe de nomenclatura de API a documentar para quem integrar via automação. |
| Criar prompt jurídico (`POST /prompts-juridicos`) | ✅ Funciona | Exige `conteudo` com no mínimo 20 caracteres. **Achado relevante:** o prompt criado nasce com `"publico": true` por padrão — qualquer prompt que um advogado criar fica visível a todo o escritório automaticamente, sem opção explícita de marcá-lo como privado no payload testado. |
| Criar etiqueta (`POST /etiquetas`) | ✅ Funciona | Sem restrição de perfil. |
| Excluir template de checklist criado (`DELETE /checklists/templates/{id}`) | ❌ Bloqueado (403 `"Forbidden"`) | Advogado pode criar mas não excluir — mesmo padrão de assimetria já visto em Casos/Clientes. A mensagem de erro, novamente, veio em inglês e sem explicação ("Forbidden" puro) — já é o **segundo** endpoint com esse mesmo padrão de mensagem não localizada (o primeiro foi `/sociedade/distribuicao` na Parte 3), o que sugere uma dependência de permissão compartilhada no backend que não passou pelo mesmo tratamento de mensagens do restante do sistema. |
| Excluir prompt jurídico criado (`DELETE /prompts-juridicos/{id}`) | ❌ Bloqueado (403 "Apenas sócios podem remover prompts") | Assimetria mais chamativa aqui: o advogado pode publicar um prompt **visível a todo o escritório** mas não pode desfazer a própria publicação sem acionar um sócio. Recomendo permitir que o autor exclua o próprio prompt, restringindo a sócio apenas a exclusão de prompts de terceiros. |
| Criar prazo, tarefa, cliente, caso (via conversão Sala Jurídica) | ✅ Confirmado novamente | Replica o resultado da Parte 3. |
| Criar honorário (`POST /fees/`) | ❌ Bloqueado (403, esperado) | Confirma novamente a segregação de função financeira já documentada. |

---

## 4. Dados de teste criados nesta rodada (pendentes de exclusão definitiva por um sócio/admin)

| Item | ID | Estado atual |
|---|---|---|
| Etiqueta `[TESTE AUDITORIA - EXCLUIR]` | `d2c8e68e-969e-47a4-93e7-8eb0cd5a6aaf` | Ativa, não vinculada a nenhum caso. |
| Template de checklist `[TESTE AUDITORIA - EXCLUIR] Checklist vicio produto` | `add3df98-1666-44bb-8151-9de50ab29a2d` | Ativo, não posso excluir com perfil advogado. |
| Prompt jurídico `[TESTE AUDITORIA - EXCLUIR] Prompt teste` | `20bc97b2-03da-4faf-a3d2-66f39bc31a14` | Ativo e **público** (visível a todo o escritório), não posso excluir com perfil advogado. |

Somados aos pendências já registradas na Parte 3 (caso, cliente e prazo arquivados/inativados, IDs já informados anteriormente), recomendo que um sócio/admin faça uma limpeza única de tudo prefixado `[TESTE AUDITORIA - EXCLUIR]` antes de o sistema entrar em uso real pela equipe, para que ninguém confunda esses registros com dados reais — em especial o prompt jurídico, que já está visível publicamente para qualquer advogado do escritório que abrir o módulo Prompts.

---

## 5. Conclusão da homologação

**O que está pronto para uso:** o núcleo funcional do EJC — autenticação, criação de cliente/caso/prazo/tarefa, geração de peça por IA, e as skills de auditoria adversarial e de pedidos — funciona de ponta a ponta e produz resultado juridicamente consistente na grande maioria dos pontos verificados, com fundamentação real e sem alucinação de jurisprudência nas oito execuções de IA testadas ao longo desta auditoria (Partes 3 e 4).

**O que precisa de correção antes de confiar cegamente no resultado da IA:** a imprecisão sobre extinção com/sem resolução de mérito (Seção 2.2) deve ser corrigida na base de conhecimento das skills `simulador-defesa-adversarial` e `prescricao-decadencia`, porque é factualmente errada e se repetiu nas duas execuções — não é uma opinião divergente, é uma citação incorreta de dispositivo processual.

**O que precisa de decisão do escritório, não do sistema:** nenhuma ferramenta pode entregar uma peça "à prova de contestação" — o que o EJC entrega, de forma consistente nos testes, é uma minuta bem fundamentada com os riscos relevantes já sinalizados, para que o advogado feche as lacunas que só ele pode fechar (fatos confirmados com o cliente, prova reunida, estratégia processual). Recomendo formalizar essa expectativa na rotina interna do escritório — por exemplo, exigindo que toda peça gerada por IA passe pela skill `simulador-defesa-adversarial` antes da revisão final do advogado responsável, como uma segunda camada de checagem antes do protocolo. Isso é operacionalizável hoje, com o que já existe no sistema — só não está sendo usado como etapa obrigatória do fluxo.
