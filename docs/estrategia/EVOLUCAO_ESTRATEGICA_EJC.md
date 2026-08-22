# EJC — Evolução estratégica: de biblioteca a sistema de decisão

**O que este documento é:** a avaliação técnica de uma proposta de 15 frentes para
transformar o EJC de repositório de conhecimento em sistema que responde *"diante
deste caso concreto, o que importa, o que falta, qual o risco e o que devo fazer
agora?"*.

**O que ele não é:** um plano de lançamento. O plano ativo continua sendo
`docs/auditoria/plano-lancamento-v3.md`, cujo critério é um advogado levar um caso
real até o protocolo. **Nada deste documento entra antes do Bloco 7 daquele plano.**
A seção final explica por quê e como as duas coisas se encaixam.

**Método:** cada uma das 15 frentes foi conferida contra o código em
`3493d35`. Onde há implementação, o caminho do arquivo está citado. Onde se afirma
que algo não existe, a afirmação vem de busca por nome e por conceito — e está
marcada como tal, porque ausência é mais difícil de provar que presença.

---

## A conclusão que muda a proposta

A proposta assume um sistema que precisa ser abastecido de conhecimento e ganhar
inteligência. **O EJC já tem quase toda essa inteligência construída.** Das 15
frentes, **2 não existem**, **4 existem parcialmente** e **9 já estão
implementadas** — várias com rigor que a proposta não pede: score determinístico
sem LLM, gate anti-alucinação com validação de dígito verificador de número CNJ,
HITL obrigatório, sanitização de PII antes de provedor externo.

O gargalo não é ausência de capacidade. É que **a capacidade construída não chega
ao advogado e não se conecta a si mesma.** Três evidências concretas:

1. **A frente-síntese da proposta já está pronta e acessível.** A frente 15 —
   "EJC como segundo advogado" — existe como `dossie_estrategico.py` no backend
   *e* como `components/DossieEstrategicoCaso.tsx` (770 linhas) no frontend,
   renderizado na aba **"Estratégia"** de cada caso (`CasoDetalhe.tsx:844`), com
   geração, módulos determinísticos, histórico, aprovação HITL e export PDF.
   Está construído, está exposto — e mesmo assim nenhum caso passou da triagem.
2. `docs/FERRAMENTAS_JURIDICAS_SEM_INTERFACE.md` inventaria **55 rotas de
   ferramentas jurídicas** em 14 áreas — calculadoras de prazo, reajuste,
   liquidação — sem nenhuma tela. A página `/ferramentas` que existe é um
   lançador sobre os módulos do registry; não chama nenhuma dessas 55. Valor
   construído e pago, invisível.
3. Tudo roda numa direção só: do caso para o conhecimento. **Nada roda no
   sentido inverso** — da tese para os casos, do precedente novo para as teses
   afetadas, do caso encerrado de volta para a base.

Isso reordena a prioridade, e o item 1 a reordena mais do que parece. Se a
funcionalidade que a proposta coloca como objetivo maior já está no ar e não
mudou o comportamento de ninguém, **o gargalo não é construir a próxima
funcionalidade — é descobrir por que a que existe não é usada.** Pode ser que não
funcione bem, que ninguém saiba que está ali, ou que o resultado não valha o
clique. Ninguém verificou. Essa verificação vale mais que qualquer das 15 frentes,
e custa uma sessão de uso real.

Depois dela, a evidência recomenda a **fiação**: ligações baratas entre peças que
já existem e hoje não se falam. É o mesmo raciocínio que o plano de lançamento
aplicou às 55 ferramentas — *"o maior ganho de valor por esforço"*.

---

## Mapa das 15 frentes contra o código

Legenda: **✅ existe** · **🟡 parcial** · **🔴 não existe**

### 1. Radar jurisprudencial automático — 🟡 parcial

O radar existe, mas é **legislativo, não jurisprudencial**.
`services/radar_legislativo.py` (541 linhas) monitora proposições na Câmara,
Senado e ALMG, com dedup persistente e degradação graciosa por fonte. Para
jurisprudência há `services/crawler_precedentes.py` — agregador honesto sobre
LexML, TJMG e DataJud, com **STJ e STF marcados explicitamente como
`nao_implementado`**. Há ainda `djen_service.py`, `diario_oficial_service.py` e
ingestores em `services/ingestors/`.

**O que falta é a segunda metade da ideia, e é a metade que vale:** nenhuma das
fontes calcula *impacto*. Nada responde "esta decisão nova muda a tese X,
afeta o modelo de peça Y e atinge os processos A, B e C". O radar deposita
alertas em `diario_oficial_alertas` e para por aí.

> Nota do repositório: `CLAUDE.md` registra que a captura DJEN *"reporta ok há
> meses sem nunca ter capturado nada"*, porque o heartbeat afere execução e não
> resultado. Qualquer trabalho nesta frente precisa monitorar resultado.

### 2. Sistema "Tese → Caso" — 🟡 parcial, e o inverso é o que falta

Existe o caminho caso → teses, e bem feito: `routers/teses.py` (707 linhas) tem
`teses_do_caso`, `sugerir_teses_ia`, `motor_teses` (síncrono e assíncrono);
`services/matriz_teses_service.py` (661 linhas) decompõe o caso em questões
jurídicas e monta matriz com `AuthorityRecord` que **só nasce de retorno real do
RAG** e força determinística com pesos fixos documentados.

**Não existe a varredura reversa.** Não há endpoint que, dada uma tese, procure
nos processos existentes onde ela cabe — exatamente o *"foi identificado possível
cabimento da tese X nos processos A, B e C"* da proposta. É o que converte o
Banco de Teses de catálogo em ferramenta ativa, e é barato: a infraestrutura de
matching (RAG híbrido, embeddings, `matriz_provas.py`) já está pronta.

### 3. Playbooks jurídicos completos — 🔴 não existe

Busca por `playbook` no backend: **zero ocorrências**. O parente mais próximo é
`services/rito_engine.py` (251 linhas) — motor determinístico que, por sinais
documentais, devolve jornada provável, fontes normativas e alertas. É o
esqueleto de um playbook, não o playbook: tem etapas, não tem o conteúdo
operacional (documentos, preliminares, teses defensivas, provas, roteiro de
audiência) que a proposta descreve.

`routers/checklists.py` (473 linhas) e `services/checklist_ia.py` cobrem parte da
camada de execução. Um playbook seria a costura de rito + checklist + matriz de
provas + teses típicas por tipo de demanda.

**Ressalva de esforço:** a proposta fala em "dezenas desses playbooks". Cada um é
trabalho jurídico de curadoria humana, não de engenharia. O código para
hospedá-los é pequeno; o conteúdo é o custo real.

### 4. Biblioteca de argumentos e contra-argumentos — ✅ existe (por caso, não por catálogo)

`services/ai/adversarial.py` implementa o "Modo Duas IAs": uma segunda IA atua
como advogado da parte contrária e magistrado, caçando contradições, lacunas
fáticas, fragilidades probatórias e jurisprudência contrária. Com
**diversidade de provider** (prefere provider diferente do que gerou a peça, para
reduzir erro correlacionado), passando pelo gate de citações e sem nunca
bloquear o fluxo. Há também `services/ia_defensiva_service.py` e o vocabulário
`contratese_de` já previsto no grafo (`services/legal_graph.py`).

**Diferença em relação à proposta:** a crítica é gerada *por peça, sob demanda* e
não se acumula em catálogo consultável por questão jurídica. Transformar o que já
é produzido em acervo reutilizável é incremento, não construção.

### 5. "Revisor Jurídico" interno — ✅ existe, e é dos módulos mais maduros

`services/validador_juridico_service.py` (655 linhas) já faz auditoria pré-peça
com veredito operacional fechado (`APTO PARA REVISÃO` / `REVISAR ANTES DE USAR` /
`BLOQUEAR ATÉ CORRIGIR`), score de confiança, separação entre fonte confirmada,
fonte ausente, artigo possivelmente incorreto, tese sem prova e lacuna
documental.

`services/verificador_jurisprudencia.py` (646 linhas) é mais rigoroso do que a
proposta pede: valida **dígito verificador de número CNJ** por módulo 97/ISO 7064,
confere faixa de súmula, classifica cada citação em `verificada` / `identificada`
/ `suspeita` / `generica` / `possivelmente_desatualizada` — este último detecta
citação de redação **superada**, que é o item "precedente superado" da proposta.

Da checklist de 10 itens da proposta, os cobertos hoje são: fundamento legal,
vigência de artigos, existência real da jurisprudência, tese sem prova, documento
mencionado e não anexado, precedente superado. **Não cobertos:** competência,
valor da causa, prescrição/decadência e contradição fato↔pedido.

> **Alerta herdado, e é sério:** o plano de lançamento registra um *erro jurídico
> sobre decadência (CPC art. 487, II) nas skills*, que **deve ser corrigido antes
> que a IA gere peça destinada a protocolo**. Qualquer trabalho em
> prescrição/decadência neste módulo começa por aí.

### 6. Banco de erros jurídicos — 🔴 não existe

Busca por `erro_comum`, `banco_de_erros`, `antipadrao`, `tese_superada`: **zero**.

É a ideia mais original da proposta e a única sem nenhum análogo no sistema. Há
matéria-prima espalhada — o `verificador_jurisprudencia` já sabe identificar
citação superada; o `validador_juridico` já produz relatórios de defeito — mas
nada é capitalizado como aprendizado reutilizável.

**Ressalva de governança:** um banco de erros é conteúdo jurídico e cai na regra 5
do `CLAUDE.md` (fonte oficial, vigência, teste) e no gate de curadoria do RAG. Um
"erro" mal catalogado vira antipadrão que a IA passa a evitar sem motivo.

### 7. Golden Dataset (EJC Gold) — ✅ a infraestrutura existe; o conteúdo foi removido de propósito

Isto é o achado mais importante do mapeamento. Existe `backend/app/eval/` completo:
`run_eval.py`, `gold_governance.py`, `compare_providers.py`,
`GOLD_SET_GOVERNANCE.md`, `GUIA_CURADORIA_GOLD_SET.md`,
`HUMAN_GOLD_SET_BACKLOG.md`, além de testes (`test_eval_gold_set_smoke.py`,
`test_gold_governance.py`, `test_eval_agent_trajectory.py`).

E o histórico mostra o gold set entrando e saindo três vezes:

```
5de5fa6  P0 governança: remover gold set sem revisão humana comprovada (#1230)
6a4a299  P0 governança: re-integrar gold set com certificação humana explícita (#1222)
a38f409  P0 governança: reverter gold set sem certificação humana (#1217)
```

**O EJC Gold não está faltando por falta de código. Está bloqueado por falta de
curadoria humana certificada** — e a governança do repositório vem rejeitando,
corretamente, tentativas de preencher isso sem certificação. Construir mais
código aqui não destrava nada. O que destrava é o titular sentar e certificar
conteúdo, guiado por `GUIA_CURADORIA_GOLD_SET.md`.

Essa é a razão principal para não começar por esta frente, ao contrário do que a
proposta sugere: ela não é uma tarefa de engenharia.

### 8. Sistema de avaliação da própria IA — ✅ existe (mesma infraestrutura da frente 7)

`run_eval.py` e `compare_providers.py` já são o harness de regressão descrito.
Some-se `routers/ia_provider_metrics.py`, `routers/ia_saude.py`,
`routers/ia_governanca.py` e `services/observability/`. As perguntas-padrão da
proposta são exatamente o gold set da frente 7 — mesma dependência, mesmo
bloqueio.

**E já existe gate de CI bloqueante** — `ci.yml:183`, *"Eval — smoke dos gold
sets (offline, bloqueante)"*, roda `run_eval --smoke` e
`agent_trajectory --max-violacoes-hitl 0` em todo PR.

**Mas ele afere formato e trajetória, não qualidade de resposta.** O próprio
`run_eval.py` avisa que sem `--areas-obrigatorias` o smoke *"valida FORMATO, não
qualidade"*. O harness tem o que falta — `--full` (roda a IA e mede citações),
`--judge` (groundedness por LLM-juiz), `--min-recall` e `--min-recall-area`
(pisos que reprovam), `--out` (baseline para diff entre execuções) — e **nada
disso está ligado ao CI**.

**Incremento real:** ligar os pisos de recall ao gate já existente. É pequeno em
código e responde exatamente ao *"saber objetivamente se o EJC está melhorando ou
piorando"* da proposta. Mas depende do gold set da frente 7: piso de recall sobre
gold set não certificado mede ruído com autoridade de número.

### 9. Knowledge Graph — ✅ existe o motor; falta massa

`services/legal_graph.py` já define o grafo canônico com **15 tipos de relação**
(`fundamentado_por`, `cita`, `aplica`, `interpreta`, `diverge_de`, `supera`,
`distingue`, `contratese_de`, `pedido_relacionado`, …) e valida integridade
referencial e vocabulário. A regra de ouro está escrita no módulo: *"relação de
grafo nunca cria autoridade jurídica"* — só vale depois que os nós estão
aprovados no RAG.

O exemplo da proposta (busca e apreensão → DL 911/69 → mora → notificação → tema
STJ → contestação → purgação) é **expressável hoje** nesse vocabulário. O que
falta são as milhares de arestas — de novo, curadoria, não engenharia.

### 10. Inteligência documental automática — ✅ existe, e é extensa

`services/extracao_estruturada.py` extrai deterministicamente número CNJ (com
validação de DV), CPF/CNPJ (com DV), datas, valores, e-mails e telefones, com
posição no texto para realce e auditoria. `services/document_classifier.py`
sugere o tipo pelo catálogo oficial, **sempre como sugestão, nunca gravação
automática**. Somam-se `document_ingestion_orchestrator.py`,
`document_intake_service.py`, `document_case_link_service.py`, `ocr_service.py` e
`routers/documento_ia.py` (437 linhas).

Da lista da proposta, o que fica descoberto é a camada interpretativa —
obrigações, pedidos e decisões extraídos do documento — e o "relacionar ao
restante da base", que depende da frente 9.

> **Armadilha registrada:** `CLAUDE.md` alerta que *gravação não transacional
> entre registros relacionados é classe de defeito recorrente* no EJC — inclusive
> "validação que não vincula ao documento". Trabalho aqui exige conferir a
> transação.

### 11. Linha do tempo processual — 🟡 parcial

A matéria-prima é forte: `services/evento_processual.py` é catálogo
determinístico de eventos → termo inicial, com semântica de *dies a quo* correta
(CPC arts. 224 e 231) e recusa explícita em calcular o que não tem certeza
absoluta. Há `routers/andamentos.py`, `movimentos.py`, `services/movimento_ia.py`
e a tela `/casos/:id/jornada`.

Falta a segunda metade — a que a proposta destaca como "mais importante": **o
sistema explicar o que aconteceu juridicamente e o que provavelmente vem
depois**. O `rito_engine` sabe a jornada provável; ninguém a cruza com a linha do
tempo real do processo para dizer "você está aqui, o próximo passo é este".

### 12. Sistema "o que está faltando?" — 🟡 parcial, e mais perto do que parece

`routers/pending_items.py` (228 linhas) tem CRUD de pendências com vocabulário
fechado (documento/informação/assinatura/pagamento). `services/matriz_provas.py`
(257 linhas) é referência determinística tese×prova — para cada tese típica, as
provas mínimas para instruir a pretensão. `services/ficha_triagem_service.py`
já usa isso para apontar provas faltantes. Há ainda
`solicitacao_documento_service.py` e `kit_documental.py`.

**Faltam duas coisas:** classificação de impacto (alto/médio/baixo) e providência
recomendada (solicitar ao cliente / obter no processo / emitir certidão). São os
dois campos que transformam uma lista de ausências em plano de ação — e são o
delta mais barato do documento inteiro.

### 13. Memória institucional — ✅ existe a tabela; 🔴 falta o ciclo que a alimenta

`routers/memoria_institucional.py` (185 linhas) tem CRUD auditado, restrito à
equipe jurídica por allowlist exata, com tipos fechados incluindo
`tese_vencedora` e `estrategia`, e resultados (`favoravel`, `desfavoravel`,
`parcial`, `acordo`). Exposto no frontend em `CasoDetalhe/TabMemoria.tsx`.

**Mas é inteiramente manual.** Nada dispara no encerramento do caso. Nenhum
registro retroalimenta o RAG ou o ranking de teses. A proposta acerta no ponto
mais valioso — *"em alguns anos o EJC terá conhecimento que nenhuma IA pública
possui"* — e esse valor depende inteiramente de captura automática no momento
do encerramento, porque registro manual pós-caso não acontece na prática.

### 14. Matriz de estratégia processual — ✅ existe

`routers/matriz_teses.py` + `services/matriz_teses_service.py` já produzem
estratégias com força determinística, fundamento, provas vinculadas e
vulnerabilidades listadas — as colunas Benefício/Risco/Prova/Base jurídica da
tabela da proposta. Somam-se `services/analise_estrategica.py`,
`routers/indice_risco.py`, `routers/score_juridico.py`, `routers/jurimetria.py`
(752 linhas) e `services/sentimento_magistrado.py`.

O que falta é apresentação: a matriz existe como dado, não como a tabela
comparável lado a lado que a proposta desenha.

### 15. EJC como "segundo advogado" — ✅ existe ponta a ponta

Esta é a frente-síntese, e é o achado mais desconfortável do mapeamento — por
motivo oposto ao esperado.

`routers/dossie_estrategico.py` (292 linhas) tem `POST /{case_id}/gerar`,
`GET /{case_id}`, módulos determinísticos, histórico, aprovação HITL e export
PDF. `routers/raio_x.py` (766 linhas) tem análise contextual por caso, reanálise,
exportação e conversão. `routers/case_intelligence.py` mantém snapshots com
aprovação.

E **tem interface**: `components/DossieEstrategicoCaso.tsx` (770 linhas) consome
todo o contrato — `gerar`, `modulos`, `historico`, `aprovar`, `pdf` — e é
renderizado na aba **"Estratégia"** de cada caso (`CasoDetalhe.tsx:844`,
`config/caseNav.ts`). O painel que a proposta descreve como objetivo maior está
construído e a um clique do advogado.

**A pergunta relevante deixa de ser "como construir" e passa a ser "por que não
mudou nada".** O sistema tem o segundo advogado que a proposta pede, e nenhum
caso passou da triagem. Isso é uma informação sobre o produto, não sobre o
backlog — e nenhuma das outras 14 frentes responde a ela.

> Registro honesto: a primeira versão desta análise afirmou que esta frente não
> tinha frontend. A busca usara o prefixo `/dossie-estrategico`, e o router é
> `/dossie`. O erro está registrado aqui porque a conclusão que ele quase
> produziu — "construa a tela" — era o oposto da correta.

---

## Placar

| # | Frente | Situação | Natureza do trabalho que falta |
|---|---|---|---|
| 1 | Radar jurisprudencial | 🟡 | Engenharia (análise de impacto) |
| 2 | Tese → Caso | 🟡 | Engenharia (varredura reversa) |
| 3 | Playbooks | 🔴 | **Curadoria jurídica** + estrutura |
| 4 | Argumentos/contra-argumentos | ✅ | Acumular em catálogo |
| 5 | Revisor Jurídico | ✅ | 4 checagens novas |
| 6 | Banco de erros | 🔴 | **Curadoria jurídica** + estrutura |
| 7 | EJC Gold | ✅ código | **Certificação humana** (bloqueio conhecido) |
| 8 | Avaliação da IA | ✅ (gate de formato já bloqueia) | Ligar pisos de qualidade — dep. de 7 |
| 9 | Knowledge Graph | ✅ motor | **Curadoria** (massa de arestas) |
| 10 | Inteligência documental | ✅ | Camada interpretativa |
| 11 | Linha do tempo | 🟡 | Engenharia (cruzar real × rito) |
| 12 | O que está faltando | 🟡 | Engenharia (impacto + providência) |
| 13 | Memória institucional | ✅ tabela | Engenharia (captura automática) |
| 14 | Matriz de estratégia | ✅ | Apresentação |
| 15 | Segundo advogado | ✅ completo | **Validar uso real** — não é backlog |

Cinco das quinze (3, 6, 7, 9, 15) dependem de **trabalho humano — curadoria,
certificação ou julgamento de uso**, não de código; e uma sexta (8) fica
bloqueada pela 7. É a informação mais acionável do documento: um terço largo
desta proposta não é trabalho de engenharia, e nenhuma quantidade de sessão de
Claude Code a resolve.

---

## Ordem revisada

A proposta sugere: Gold → Playbooks → Tese→Caso → Revisor → Documentos faltantes
→ Radar → Testes → Memória → Grafo → Inteligência estratégica.

A evidência recomenda inverter a cabeça da fila. Gold e Playbooks são os dois
itens **mais caros e menos dependentes de engenharia** de toda a lista — começar
por eles é gastar o começo, que é quando se aprende, na parte que o código não
resolve.

**Onda A — fiação (semanas, não meses; só depois do Bloco 7 do plano ativo)**

| Ordem | Item | Por quê |
|---|---|---|
| **A0** | **Usar o Dossiê Estratégico num caso real e julgar o resultado** (frente 15) | **Pré-requisito de tudo.** A frente-síntese já está no ar e não mudou o comportamento de ninguém. Enquanto não se souber se ela funciona, qualquer construção nova é aposta. Não é tarefa de engenharia: é o titular abrindo a aba "Estratégia" de um caso e dizendo se o que sai vale o clique. |
| A1 | Impacto + providência em pendências (frente 12) | Dois campos. Transforma lista de ausências em plano de ação. |
| A2 | Varredura reversa Tese → Caso (frente 2) | Ativa o Banco de Teses. Infra de matching já existe. |
| A3 | Captura automática no encerramento (frente 13) | Sem isto a memória institucional nunca acumula. Quanto antes, mais história capturada. |
| A4 | Pisos de qualidade no gate de eval (frente 8) | O gate bloqueante já existe (`ci.yml:183`), mas afere formato e trajetória. `--min-recall` e `--full` já estão no harness e não estão ligados. Só vale com o gold set da frente 7 certificado. |

**A0 pode invalidar o resto desta lista, e é para isso que serve.** Se o dossiê
sair ruim, o trabalho vira consertá-lo — não construir A1–A4 em volta de um
núcleo que não funciona. Se sair bom e ainda assim não for usado, o problema é de
descoberta ou de confiança, e também não se resolve com feature nova.

De A1 a A4 a ordem não é rígida — A1 e A2 são independentes e podem ir em
paralelo. O que importa é que a Onda A inteira mexe em coisa construída, tem
risco baixo e produz valor visível a cada item.

**Onda B — engenharia nova**

Frente 11 (linha do tempo interpretada), frente 1 (impacto do radar), frente 5
(as 4 checagens faltantes do revisor — **começando pela correção do erro de
decadência**), frente 10 (camada interpretativa de documentos).

**Onda C — curadoria (paralela, ritmo do titular, não da engenharia)**

EJC Gold (frente 7), Playbooks (frente 3), Banco de Erros (frente 6), massa do
grafo (frente 9). Estas quatro **não devem ser sequenciadas junto com as outras**:
seu gargalo é hora de advogado sênior, e tratá-las como sprint de engenharia é o
que produziu os três reverts do gold set.

---

## Relação com o plano de lançamento

O `plano-lancamento-v3.md` é explícito: o critério é **um advogado levar um caso
real até o protocolo, e achar mais fácil do que fazer fora do sistema**. Até a
data da auditoria, nenhum caso passou da triagem e nenhuma peça foi protocolada.

Toda esta proposta é, na taxonomia daquele plano, "depois do lançamento". E o
plano é firme sobre a razão: o Bloco 4 se chama **"Enxugar"** — o problema
diagnosticado do EJC não é falta de funcionalidade, é excesso de funcionalidade
não usada. `docs/FERRAMENTAS_JURIDICAS_SEM_INTERFACE.md` recomenda
explicitamente **não construir as 55 telas** que já teriam backend pronto.

Adicionar 15 subsistemas a um sistema cujo diagnóstico é excesso de superfície
piora exatamente a métrica que o plano está tentando consertar.

Há uma exceção, e ela não é uma frente nova: **A0 pertence ao plano de
lançamento, não a este documento.** O Bloco 7 é "o teste do primeiro caso real";
o Dossiê Estratégico já está na aba "Estratégia" desse caso. Julgá-lo é parte de
fazer o teste, não trabalho adicional — e o resultado desse julgamento diz mais
sobre o que construir depois do que as 15 frentes somadas.

Vale considerar também se o dossiê não deveria ser mais proeminente dentro do
Bloco 3 ("o caso como espaço de trabalho"): ele entrega o caso mastigado em vez
de mais um menu, que é exatamente o que o Bloco 3 persegue. Mas isso é decisão do
titular depois de A0, não antes.

---

## Riscos e limitações desta análise

- **Verificação estática.** O mapeamento leu código, não executou nada. "Existe"
  aqui significa "está implementado", não "funciona em produção". O próprio
  `CLAUDE.md` documenta o caso da captura DJEN, que reportava sucesso há meses sem
  nunca ter capturado nada. Antes de tratar qualquer ✅ como pronto, exercite o
  fluxo.
- **Ausências são mais frágeis que presenças.** Os dois 🔴 (playbooks, banco de
  erros) vêm de busca por nome e conceito no backend. É a mesma limitação que o
  `CLAUDE.md` registra sobre o graphify: *confirme no arquivo antes de afirmar que
  algo não existe*.
- **Busca textual erra por prefixo — e errou aqui.** A frente 15 foi inicialmente
  dada como sem frontend porque a busca usou `dossie-estrategico` e o router é
  `/dossie`. O componente tinha 770 linhas e estava renderizado numa aba visível.
  A lição vale para os dois 🔴 e para qualquer ✅ deste documento: **o nome da
  rota não é o nome do arquivo**. Antes de agir sobre qualquer linha desta tabela,
  confirme por conceito, não por string.
- **Afirmação sobre CI também errou, pelo mesmo vício.** A primeira versão dizia
  que a régua de eval "não trava nada"; existe gate bloqueante desde
  `ci.yml:183`. O `CLAUDE.md` avisa literalmente para conferir os workflows
  *"antes de afirmar que algo não roda"* — o aviso estava certo e foi ignorado.
- **Frontend inspecionado por amostragem.** Os 46 caminhos vêm de
  `moduleRegistry.tsx`; muita funcionalidade vive em abas e componentes fora do
  registry — como a própria frente 15 demonstrou. Contagem de rotas não mede
  superfície funcional.
- **Nenhuma estimativa de esforço.** Onde este documento diz "barato", quer dizer
  "mexe em código existente e não exige curadoria" — não é estimativa de prazo.
- **Governança inalterada.** Nenhuma frente aqui autoriza enfraquecer HITL, gate
  de citações, sanitização de PII ou kill-switch. A frente 6 (banco de erros) e a
  frente 9 (grafo) são as que mais tangenciam o gate de curadoria do RAG e exigem
  desenho de governança antes de linha de código.

---

*Documento de avaliação estratégica. Não altera o plano de lançamento ativo nem
substitui `docs/auditoria/plano-lancamento-v3.md`.*
