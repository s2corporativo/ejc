# EJC — Como tirar a preguiça do sistema
## Recomendações para a janela que existe antes da operação começar

**Contexto novo:** o EJC é ferramenta interna, nunca foi usado de ponta a ponta, e a operação começa em breve.
**Sintoma relatado pelo usuário:** *"dá preguiça de levar um caso do início ao fim no sistema."*

---

## 1. Essa preguiça é o diagnóstico mais preciso que recebi

Doze rodadas de auditoria produziram 40 achados técnicos. Nenhum deles me disse o que essa frase disse.

Quando a pessoa que idealizou o sistema sente preguiça de usá-lo, o problema não é falta de funcionalidade — **é excesso de decisões por unidade de trabalho.** E isso não se resolve adicionando nada. Só se resolve tirando.

Vale nomear com precisão: preguiça em software é atrito medível. Não é falta de disciplina do usuário. É o sistema cobrando mais esforço do que o valor que devolve naquele momento.

---

## 2. Por que dá preguiça — a conta real

Contei, a partir dos endpoints que a auditoria mapeou, o que hoje é exigido para levar **um** caso do início ao protocolo:

| # | Ação | Onde |
|---|---|---|
| 1 | Cadastrar cliente | Módulo Clientes |
| 2 | Criar caso — exige título, área, descrição dos fatos e próxima ação | Módulo Casos |
| 3 | Fazer upload dos documentos | Entrada Universal ou GED |
| 4 | Vincular cada documento ao caso | GED (não é automático) |
| 5 | Rodar triagem de IA | Caso |
| 6 | Conversar na Sala Jurídica | Sala Jurídica |
| 7 | Converter a conversa em caso — **perde os fatos** | Sala Jurídica |
| 8 | Redigir a peça com IA | Peças |
| 9 | Validar a peça | Peças |
| 10 | Marcar o log de IA como revisado | Governança de IA |
| 11 | Aprovar a peça | Peças |
| 12 | Exportar o PDF | Peças |
| 13 | Cadastrar o prazo à mão | Prazos |
| 14 | Criar a tarefa de acompanhamento | Tarefas |
| 15 | Lançar o honorário | Financeiro |

**Quinze ações, atravessando oito módulos diferentes.** E três delas estão quebradas (a 7 perde dados, a 10 e a 11 travam por causa do bug do vínculo de validação).

Um advogado com dez casos novos no mês faria isso 150 vezes. Ninguém faz. **A preguiça é a resposta racional a um custo real.**

O alvo que eu perseguiria: **abrir um caso completo em uma tela e menos de dois minutos.** Tudo o mais é consequência disso.

---

## 3. A mudança estrutural — o caso é o sistema, não um módulo

Esta é a recomendação mais importante deste documento.

Hoje o EJC é organizado **por funcionalidade**: existe o módulo de Casos, o de Prazos, o de Documentos, o de Peças, o Financeiro. Para trabalhar um caso, o advogado navega entre eles carregando o contexto na cabeça.

Isso é o padrão de ERP dos anos 2010, e é a origem direta da fadiga. O padrão moderno é **organizar por entidade**: o caso é o espaço de trabalho, e tudo acontece dentro dele.

Na prática, isso significa que a tela do caso deixa de ser uma ficha e passa a ser o lugar onde o trabalho acontece: os documentos aparecem ali e são anexados ali; o prazo é criado ali, a partir da intimação, sem ir ao módulo de Prazos; a peça é redigida, conferida e exportada ali; as horas e despesas são lançadas ali. O advogado nunca "vai ao módulo de Prazos" — ele abre o caso e o prazo está lá.

Os módulos continuam existindo, mas mudam de função: deixam de ser onde se trabalha e viram **visões transversais** — "todos os prazos da semana", "todas as peças aguardando conferência". São relatórios, não estações de trabalho.

Isso sozinho elimina a maior parte das oito travessias de módulo da tabela acima. E é uma mudança de arranjo de interface, não de arquitetura de dados — os endpoints já existem.

---

## 4. Entrada única: uma ação no lugar de quinze

O segundo maior ganho, e a boa notícia é que **as peças já existem no sistema, só não estão conectadas.**

O EJC tem `entrada-universal/processar` (extrai texto e classifica documento), `entrevista-inteligente` (triagem por relato livre), `sala-juridica` (conversa estruturada) e triagem automática por IA. São quatro portas de entrada diferentes, nenhuma delas terminando num caso pronto.

O que eu construiria: **uma única entrada** onde o advogado faz uma de duas coisas — cola o relato do cliente, ou arrasta os documentos — e o sistema devolve, em uma tela para confirmação:

> Cliente identificado (ou cadastro novo pré-preenchido) · Área sugerida · Fatos estruturados · Documentos classificados e já vinculados · Prazo detectado, se houver · Próxima ação sugerida

O advogado **confere e confirma**. Um clique, não quinze.

Repare que isso não exige IA nova nem módulo novo. Exige **encadear o que já existe** e consertar a conversão que hoje perde os fatos. É provavelmente a intervenção de maior retorno por esforço do sistema inteiro.

---

## 5. Matar a jornada de nove etapas

O sistema desenha uma jornada de nove passos: Cliente → Triagem → Documentos → Inteligência → Estratégia → Produção → Revisão → Protocolo → Gestão.

Nove etapas é um processo desenhado por quem pensava em completude, não por quem faz o trabalho. Na prática, a maioria dos casos pula metade — e, o que é pior, um processo com nove marcos obrigatórios faz o advogado sentir que está sempre atrasado.

Eu reduziria a **quatro estados** que descrevem o que de fato muda no caso:

**Aberto** (existe, tem cliente, tem fatos) → **Em instrução** (juntando documentos e provas) → **Em produção** (peça sendo redigida e conferida) → **Protocolado** → *Encerrado*

Tudo o que hoje é "etapa" — triagem, inteligência, estratégia — vira **tarefa dentro do estado**, não marco a vencer. A diferença é psicológica e é grande: tarefa opcional não gera culpa, marco não cumprido gera.

---

## 6. A janela rara que vocês têm agora

Isto merece destaque próprio, porque é uma vantagem que quase nenhum sistema tem.

**O EJC nunca foi usado para trabalho real. Isso não é fracasso — é a melhor posição possível para reformar.**

Sistemas em produção há anos não podem mudar modelo de dados, não podem renomear status, não podem cortar módulo, porque há histórico e hábito travando tudo. Vocês podem fazer todas essas mudanças agora, com custo próximo de zero, porque não há dado real para migrar nem rotina consolidada para desaprender.

Essa janela fecha no dia em que o primeiro caso real entrar. **Depois disso, cada mudança custa dez vezes mais.**

Minha recomendação prática: **não comece a operação e conserte depois. Conserte o caminho principal e comece com ele funcionando.** Um mês de atraso agora economiza um ano de retrabalho — e, mais importante, evita que a equipe forme a impressão de que "o sistema é chato", que é uma impressão que não se desfaz.

---

## 7. Checklist de pré-operação — o que fazer antes do primeiro caso real

Coisas de cadastro e configuração que não são desenvolvimento, mas que, se não forem feitas antes, contaminam a operação desde o primeiro dia:

**Identidade e captura de prazo.** Cadastrar `djen_oab_numero` e `djen_oab_uf` dos três advogados (hoje só existe uma inscrição, numa conta administrativa). Sem isso, o sistema não captura intimação de ninguém. Preencher também o `oab_number` no perfil de cada um.

**Limpeza.** Excluir definitivamente os dados de teste — os 37 casos na lixeira, as peças órfãs, a conta `homolog.qa` com perfil superadmin, e a conta fictícia de portal. Começar com base limpa evita que ninguém saiba mais o que é real.

**Financeiro.** Carregar a tabela de honorários da OAB/MG (hoje `disponivel: false`), cadastrar os sócios e seus percentuais (hoje vazio), e definir as categorias de despesa que o escritório usa.

**Base de conhecimento.** Não tente cobrir 25 áreas. Escolha **as duas ou três que o escritório realmente pratica** — pelos casos existentes, consumidor e civil — e carregue súmulas, jurisprudência e modelos só delas. Uma área bem servida vale mais que 25 vazias.

**Ambiente.** Separar homologação de produção antes de começar. Hoje há rotina automatizada de teste rodando contra o banco real; a partir do momento em que houver dado de cliente, isso deixa de ser desleixo e passa a ser risco de sigilo.

**Modelos do escritório.** Carregar as peças-padrão que vocês já usam. A IA redige muito melhor com exemplos da casa do que sem.

---

## 8. O método do primeiro caso real

Em vez de tentar consertar tudo em abstrato, sugiro um método que costuma ser mais eficiente:

Escolha **um caso real, de complexidade média**, e leve-o do início ao fim dentro do sistema — com um advogado usando de verdade, e alguém anotando. Cada ponto de atrito vira um item de correção, e a ordem em que os problemas aparecem **já é a ordem de prioridade**, porque reflete o caminho real.

Duas regras para funcionar: não conserte nada durante a passagem (anote e siga, senão vira sessão de depuração e não de observação); e anote também o que causou **hesitação**, não só o que causou erro — "não sei onde clicar" é achado tão válido quanto uma mensagem de falha.

Minha aposta é que esse exercício vai render entre 15 e 25 itens, dos quais talvez seis expliquem 80% da preguiça. E vai render em uma tarde o que a auditoria levou doze rodadas para inferir de fora.

---

## 9. O que eu deixaria quebrado de propósito

Consultor honesto também diz o que **não** consertar agora. Com a operação começando, o tempo é o recurso escasso:

**Portal do Cliente** — não há cliente usando. Pode esperar até haver operação estabilizada. (Com uma exceção não negociável: confirmar que a métrica de "chance de êxito" não é exposta lá. Isso é rápido e é risco ético.)

**Acessibilidade** — importante, real, e não bloqueia a operação de três advogados sem necessidade específica. Entra depois.

**Paleta de cores e design tokens** — pura estética enquanto os números da tela não baterem. Beleza sobre dado errado não convence ninguém.

**As 211 rotas órfãs** — não removê-las agora. Remover código dá trabalho e risco. Basta tirá-las da navegação; some da vista, para de confundir, e a remoção física fica para uma faxina futura.

**Jurimetria, Victory Vault, radar regulatório** — tirar do menu hoje, decidir o destino depois. Não gastar um minuto neles.

---

## 10. Se eu pudesse fazer só três coisas

Se o tempo até o início da operação for curto e for preciso escolher:

**Primeiro, a entrada única** (Seção 4). Transforma quinze ações em uma e ataca a preguiça na raiz.

**Segundo, o caso como espaço de trabalho** (Seção 3). Elimina as travessias entre oito módulos.

**Terceiro, fazer os números baterem** (contadores e filtros, Fase 1 do plano de correção). Sem isso, a equipe não confia no que a tela mostra — e um sistema em que não se confia não é usado, por melhor que seja.

Essas três, com o desbloqueio do pipeline de peças, entregam um sistema que **um advogado usa por vontade própria**. É o único teste que importa.

---

## 11. Uma observação final, sobre o que já está certo

O instinto de cortar não deve virar autodepreciação. O EJC tem coisas que sistemas comerciais caros não têm: a crítica adversarial que ataca a própria peça, o validador que bloqueia citação inventada, a degradação segura da extração de documentos, a trilha de auditoria de IA.

O problema nunca foi capacidade. Foi ordem de construção. Vocês construíram o segundo andar antes da escada — e a boa notícia é que o segundo andar está bom. Falta a escada, e ela é a parte mais barata da obra.

---

*Recomendações de produto e processo. As correções técnicas correspondentes estão no plano de correção v2 e nos prompts por fase.*
