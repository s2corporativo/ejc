# EJC — Crítica arquitetural e visão de produto
## Parecer de quem foi contratado para tornar o sistema moderno, funcional e bonito

**Autor:** consultoria de arquitetura de sistemas jurídicos / ERP
**Base:** 12 rodadas de auditoria técnica sobre o ambiente de produção
**Natureza deste documento:** não é auditoria. É opinião técnica, com recomendações que envolvem cortar coisas. Foi pedida honestidade; ela está aqui.

---

## 1. O diagnóstico, em uma frase

**O EJC é um sistema com ambição de produto de mercado sendo usado como ferramenta interna de três advogados — e essa incompatibilidade, não a falta de qualidade técnica, é a causa da maior parte dos problemas que a auditoria encontrou.**

---

## 2. O fato que resume tudo

Deixo de lado, por um momento, os 40 achados da auditoria. Um único número diz mais que todos eles:

> **Nenhum caso, em toda a história do sistema, completou a jornada. Nenhuma peça foi protocolada. Nenhum prazo foi capturado automaticamente. Nenhum registro financeiro foi lançado.**

Os oito casos ativos estão todos parados em `triagem`, a primeira das nove etapas que o próprio sistema desenha. As 23 peças estão todas em `rascunho`. O único prazo cadastrado foi digitado à mão. O módulo financeiro está zerado.

E, ao mesmo tempo, o sistema tem **34 módulos, 453 rotas, 163 skills de IA, 37 agentes**, jurimetria com predição de êxito, cofre de credenciais, portal do cliente, radar regulatório, victory vault, análise de magistrado, módulos de direito eleitoral, agrário, agronegócio e internacional.

Essa desproporção é o problema central. Não é que o sistema seja ruim — **é que ele cresceu em largura antes de fechar uma única linha de ponta a ponta.** Construiu-se a catedral inteira antes de testar se a porta abre.

Um sistema jurídico se justifica por uma coisa: **fazer o advogado chegar do cliente ao protocolo com menos atrito e menos risco.** Hoje o EJC não faz isso nenhuma vez. Todo o resto é acessório.

---

## 3. O que eu cortaria — e por quê

Esta é a parte impopular. Corto por três razões concretas, não por gosto: cada módulo não usado é superfície de ataque, é custo de manutenção, e é carga cognitiva para o advogado que abre o menu e vê 34 opções sem saber qual importa.

A auditoria mediu isso: **211 das 453 rotas nunca são chamadas por nenhuma tela.** Quase metade do sistema é peso morto.

### 3.1 Cortaria sem hesitar

**Jurimetria e predição de êxito.** Não é só que estão vazios (`total_vinculos: 0`, todas as consultas retornando `[]`). É que **jurimetria com 8 casos não é jurimetria, é anedota**. Predição estatística exige centenas de desfechos. O escritório tem zero. Manter o módulo é manter a promessa de uma capacidade que não existe — e, no dia em que houver dados, ele reaparece com o problema ético do item 4.2 da auditoria. Corte agora, reconstrua quando houver 300 casos encerrados.

**"Diplomacia-v3" — análise de magistrado e "dossiê de pressão".** Encontrei os endpoints `/diplomacia-v3/analisar-magistrado` e `/diplomacia-v3/dossie-pressao`. Vou ser franco: um módulo com esse nome, num sistema de escritório de advocacia, é um risco reputacional e disciplinar que eu não correria por nenhum benefício operacional. "Dossiê de pressão" sobre magistrado é o tipo de coisa que, exposta numa perícia ou numa representação, é indefensável — independentemente do que o código realmente faça. Remova.

**Victory Vault.** Vazio (`/teses/ranking` → `[]`). O conceito — banco de teses vencedoras reaproveitáveis — é bom, mas ele só tem valor com histórico. Hoje é uma casca. Vire uma pasta de modelos até que haja acervo.

**Áreas de atuação que o escritório não pratica.** O backend aceita 25 áreas canônicas, incluindo eleitoral, agrário, agronegócio e internacional. Os casos reais estão em **consumidor (7) e civil (2)**. Manter 25 áreas significa manter 25 taxonomias, 25 conjuntos de skills, 25 lacunas de RAG a preencher. Reduza para as áreas efetivamente praticadas e adicione conforme a prática exigir.

**A maior parte das 163 skills de IA.** Ninguém navega 163 opções. Na prática, o advogado usa cinco ou seis. As 163 existem porque foram geradas por combinação (área × módulo), não porque alguém precisou delas. Mantenha as que têm uso registrado nos logs; arquive o resto. O catálogo grande impressiona numa demonstração e atrapalha no dia a dia.

**Radar regulatório e notícias.** `/noticias` puxa ConJur e JOTA. É agradável, não é ERP. O advogado já lê ConJur. Isso não deveria consumir manutenção enquanto o protocolo não funciona.

**Módulo de sociedade / retiradas de sócio.** `GET /sociedade/socios` retorna vazio. Enquanto não houver estrutura societária cadastrada, o módulo só produz telas que não abrem.

### 3.2 O que ganho com o corte

Estimando por baixo: sai de 34 para **10 ou 12 módulos**. A superfície de ataque cai pela metade. O menu passa a caber numa tela. E — o mais importante — o esforço de manutenção que hoje se espalha por 453 rotas se concentra nas 40 ou 50 que o escritório realmente usa, que é onde os bugs doem.

---

## 4. O que eu consertaria na arquitetura

### 4.1 Há uma classe de defeito, não uma lista de bugs

A auditoria encontrou cinco falhas aparentemente independentes: a validação que não vincula ao documento, a chance de êxito que fica no log e não no caso, a conversão da Sala Jurídica que perde os fatos, a exclusão de caso que não cascateia para as peças, o campo de OAB duplicado e inconsistente.

**Não são cinco bugs. É um só, repetido: o sistema grava em dois lugares e não garante que os dois aconteçam.**

A correção certa não é remendar os cinco. É estabelecer uma **fronteira de agregado em torno do Caso** — Caso, suas peças, seus documentos, seus prazos e seus logs mudam juntos, dentro de uma transação, ou não mudam. E adotar eventos de domínio para o que atravessa a fronteira. Enquanto isso não existir, cada nova funcionalidade vai reintroduzir o mesmo defeito, porque o padrão que o produz continua sendo o padrão da casa.

### 4.2 Observabilidade que mede resultado, não execução

O DJEN nunca capturou um único documento e o painel dizia "ok" todos os dias, porque o monitoramento pergunta *"o job rodou?"* em vez de *"o job entregou?"*.

Isso é uma decisão de arquitetura, não um bug pontual. Todo job, toda integração, todo pipeline deve declarar **o que significa sucesso em termos de saída**, e o monitor deve aferir isso. Um pipeline que roda pontualmente e entrega zero por 30 dias precisa gritar.

Custo: baixo. Impacto: é a diferença entre descobrir uma falha em um dia ou em um mês. No caso do DJEN, a diferença entre perceber e perder um prazo.

### 4.3 Uma fonte de verdade por fato

Hoje há três painéis dizendo três coisas diferentes sobre quais provedores de IA estão configurados, e dois dizendo coisas opostas sobre se o backup está ligado. Isso corrói a confiança em tudo o mais: se o painel erra sobre backup, por que eu acreditaria nele sobre prazos?

Um fato, uma fonte, e os painéis leem dela.

### 4.4 Sobre o modelo de dados de status

`triagem`, `arquivado`, `ativo`, `all` — quatro vocabulários que não conversam, produzindo uma tela que mostra "nenhum caso" com oito casos cadastrados. Enum compartilhado entre frontend e backend, gerado de uma definição só. É trabalho de um dia e elimina uma classe inteira de confusão.

---

## 5. O que eu construiria que não existe

Aqui está o que mais me incomoda como especialista em ERP jurídico: **o sistema tem análise de magistrado e não tem apontamento de horas.**

### 5.1 O ciclo financeiro real

O módulo financeiro está zerado — receitas, despesas, honorários, tudo em zero. Isso significa que **o escritório fatura fora do sistema**. Um ERP jurídico que não captura a hora trabalhada e não fecha o ciclo até o recebimento não é um ERP; é um gestor de documentos com IA.

O que falta, em ordem de importância: apontamento de horas vinculado ao caso; despesas reembolsáveis por caso (custas, diligências, cópias); geração de fatura a partir do apontado; e conciliação do recebido. Sem isso, o sistema nunca vai responder a pergunta que todo sócio faz — **"esse cliente dá lucro?"**.

A tabela de honorários da OAB/MG, aliás, não está carregada (`{"disponivel": false}`), então nem a verificação de piso ético funciona.

### 5.2 Protocolo de verdade

Não há integração de peticionamento. O fluxo termina em "exportar PDF" — e nem isso funciona hoje. Enquanto o advogado tiver que baixar o PDF e subir manualmente no PJe, o sistema é um processador de texto caro.

Integração com PJe/eproc/Projudi é trabalhosa e é exatamente o tipo de coisa que justifica um ERP. É o que eu construiria antes de qualquer skill nova de IA.

### 5.3 Agenda e audiências

Existe `/agenda-eventos`, mas o módulo de audiências — preparação, controle de comparecimento, vinculação ao caso — não aparece na prática. Para advocacia contenciosa, audiência é evento estruturante. Deveria ser cidadão de primeira classe.

### 5.4 Uma tela de "o que eu faço hoje"

Não existe. O advogado abre o sistema e vê 34 módulos e 281 alertas não lidos. Deveria ver **cinco linhas**: os prazos de hoje e amanhã, as peças esperando sua conferência, os casos parados há mais de X dias, as intimações novas, e o que precisa de decisão dele.

Isso é, na minha opinião, a funcionalidade de maior retorno que se pode construir neste sistema — e provavelmente leva uma semana.

---

## 6. O que é genuinamente bom e deve ser amplificado

Seria desonesto só criticar. Há coisas aqui que são melhores do que se vê na maioria dos sistemas jurídicos comerciais:

**A crítica adversarial (`/ia/critica-adversarial`) é excelente.** Testei com uma tese propositalmente absurda e ela identificou a incoerência interna, listou cinco teses defensivas prováveis em ordem de risco, apontou as lacunas probatórias e recusou-se a inventar precedente — recomendando verificar as fontes. Ela teve desempenho **superior ao da própria geração de peças**. Isso deveria ser etapa obrigatória de revisão, e é o tipo de coisa que diferencia o produto.

**O validador de citações (`/ia/validar-citacoes`) resolve o maior risco prático da IA jurídica.** Enviei uma citação inventada e ele marcou como possível alucinação e bloqueou a aprovação. Numa profissão onde advogados já foram sancionados por citar jurisprudência inexistente gerada por IA, isso vale mais que 100 das 163 skills.

**A degradação segura da extração de documentos.** Quando a camada de IA cai, o sistema preserva a extração determinística, sinaliza explicitamente a indisponibilidade e marca revisão obrigatória — em vez de inventar dados ou falhar em silêncio. É engenharia madura.

**A arquitetura de guardrails e o fallback multi-provedor.** O conceito está certo e bem executado.

**Os painéis de autodiagnóstico.** Têm bugs, mas o conceito — o sistema que se audita e diz o que está errado — é raro e valioso. Consertar é muito mais barato que construir.

**Soft delete com lixeira e trilha de auditoria.** Correto para o contexto jurídico.

---

## 7. Sobre "bonito"

Aqui discordo do enquadramento mais comum, e vale explicar.

A auditoria encontrou duas paletas de cor coexistindo (dourado de marca e azul padrão do Tailwind) sem tokens nomeados, e 44 de 68 módulos sem qualquer atributo de acessibilidade. São problemas reais e devem ser corrigidos. **Mas não é isso que faz o sistema parecer feio de usar.**

Software jurídico bonito é software **reduzido**. A beleza aqui não está na paleta — está em abrir o sistema e ver exatamente as cinco coisas que precisam da sua atenção hoje, e nada mais. Um sistema que mostra 34 módulos e 281 alertas não lidos é feio mesmo que cada pixel esteja perfeito, porque comunica ao usuário que ele está atrasado em tudo e não sabe por onde começar.

Três mudanças que fariam mais pela percepção de qualidade do que qualquer redesenho visual:

**Organizar a navegação pelo ciclo de vida do caso, não por funcionalidade.** Hoje o menu é uma lista de módulos. Deveria ser o caminho que o trabalho percorre — captação, caso, produção, protocolo, financeiro — porque é assim que o advogado pensa.

**Resolver os 281 alertas não lidos.** Fadiga de alerta destrói a confiança no sistema: quando tudo é alerta, nada é. Melhor mostrar três alertas que importam do que 281 que ninguém lê.

**Fazer os números baterem.** O dashboard dizer "0 peças aguardando revisão" com tudo em rascunho, ou o filtro "ativo" retornar vazio com oito casos — isso não é bug de contador, é destruição de confiança. Depois da terceira vez que o sistema mente sobre um número, o usuário para de acreditar em todos os números, e aí o sistema morreu mesmo funcionando.

Só depois disso eu mexeria na paleta.

---

## 8. A pergunta estratégica que muda tudo

Preciso colocar isto explicitamente, porque muda metade das minhas recomendações e eu não sei a resposta.

**O EJC é ferramenta interna do escritório, ou é produto que o senhor pretende vender?**

Tudo o que escrevi acima assume **ferramenta interna**. Se for esse o caso, minha recomendação é agressiva: corte 60% dos módulos, feche o ciclo cliente→protocolo→faturamento, e pare de construir largura.

**Se for produto de mercado**, a leitura inverte em pontos importantes. A largura de módulos deixa de ser desperdício e vira catálogo. As 163 skills viram argumento comercial. A jurimetria vira roadmap. Mas aí surgem exigências que hoje não existem e que seriam fatais numa venda: multi-tenancy (o sistema hoje é mono-escritório), isolamento de dados entre clientes, SLA, documentação (hoje **zero dos 34 módulos** tem manual), suporte, e um ambiente de homologação separado da produção — que hoje não existe, tanto que há rotina de teste rodando contra o banco real.

E há um ponto duro: **não se vende um sistema jurídico cujo fluxo principal nunca completou uma vez.** O primeiro cliente que testar vai descobrir isso na primeira semana.

Minha recomendação, valendo para os dois cenários: **feche o ciclo primeiro.** Um sistema que leva um caso do cliente ao protocolo e ao recebimento, com excelência, para três advogados — esse sistema é vendável. Um sistema com 34 módulos onde nada chega ao fim, não é.

---

## 9. O que eu faria nos primeiros 90 dias

**Semanas 1 a 3 — fazer o sistema dizer a verdade.**
Corrigir os contadores, os filtros e as métricas divergentes. Nada de funcionalidade nova. O objetivo é que o advogado volte a acreditar no que a tela mostra. É pré-requisito psicológico de tudo o mais.

**Semanas 3 a 6 — fechar a espinha dorsal.**
Um caso percorre cliente → triagem → documento → peça → conferência → PDF. Corrigir o vínculo de validação, consolidar a aprovação em um ato, ligar os embeddings e o modelo local para as peças saírem completas. Ao final, comemore o primeiro caso que chega ao fim — é o marco que importa.

**Semanas 6 a 9 — parar de perder prazo.**
Cadastrar as OABs no DJEN, monitorar por resultado, e construir a tela de "o que eu faço hoje". A partir daqui o sistema deixa de ser um repositório e vira uma ferramenta de trabalho.

**Semanas 9 a 12 — o dinheiro.**
Apontamento de horas, despesas por caso, fatura, conciliação. É o que transforma o EJC de ferramenta de produção em ERP de verdade — e é o que responde se o escritório está ganhando dinheiro.

**Em paralelo, o tempo todo:** cortar módulo. Uma tesourada por semana. E expor as 15 calculadoras jurídicas que já estão prontas no backend e ninguém vê — dosimetria, prescrição penal, dano moral, partilha — porque é o único item da lista que entrega valor imediato sem construir nada.

---

## 10. Onde eu posso estar errado

Honestidade profissional exige delimitar o alcance da opinião:

Nunca vi o código-fonte — toda a análise vem de chamadas à API e dos bundles publicados. Nunca vi a interface renderizada, porque o ambiente da auditoria bloqueia navegador; tudo o que digo sobre design vem da estrutura, não da experiência visual. Nunca acessei o Portal do Cliente, por falta de credencial. E não conversei com os outros dois advogados, que podem usar o sistema de forma muito diferente da que os dados sugerem.

Sobretudo: **é possível que o sistema esteja em uso há pouco tempo e que os números baixos reflitam adoção inicial, não fracasso.** Se o EJC entrou em produção há poucas semanas, "nenhum caso concluído" é normal, não sintoma. Mas há peças em rascunho desde 13/07 e a lixeira registra atividade desde 22/07 — o que sugere pelo menos algumas semanas de uso real sem um ciclo completo. Se essa leitura estiver errada, corrija-me, porque ela sustenta boa parte deste parecer.

---

*Parecer técnico. Não substitui decisão de negócio do escritório sobre destino e escopo do produto.*
