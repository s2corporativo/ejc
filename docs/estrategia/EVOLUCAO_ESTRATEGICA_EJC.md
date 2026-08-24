# EJC — Evolução estratégica: de biblioteca a sistema de decisão

**O que este documento é:** a avaliação técnica de uma proposta de 15 frentes para
transformar o EJC de repositório de conhecimento em sistema que responde *"diante
deste caso concreto, o que importa, o que falta, qual o risco e o que devo fazer
agora?"*.

**O que ele não é:** um plano de lançamento. O plano ativo continua sendo
`docs/auditoria/plano-lancamento-v3.md`, cujo critério é um advogado levar um caso
real até o protocolo. **Nada deste documento entra antes do Bloco 7 daquele plano.**
A seção final explica por quê e como as duas coisas se encaixam.

> **Status canônico em `docs/PLANO_MESTRE_STATUS.md`.** O placar de 15 frentes
> abaixo descreve a avaliação técnica; a partir de 2026-08-24 o status vivo de
> cada item de trabalho (Onda A/B/C) vive só no checklist-mestre, verificado
> por `scripts/status_check.sh`. Este documento não é mais editado com
> cabeçalho de status — a nota de correção na seção "Placar" registra a última
> divergência encontrada entre cabeçalho e placar antes da migração.

**Método:** cada uma das 15 frentes foi conferida contra o código em
`3493d35`. Onde há implementação, o caminho do arquivo está citado. Onde se afirma
que algo não existe, a afirmação vem de busca por nome e por conceito — e está
marcada como tal, porque ausência é mais difícil de provar que presença.

---

## A conclusão que muda a proposta

A proposta assume um sistema que precisa ser abastecido de conhecimento e ganhar
inteligência. **O EJC já tem quase toda essa inteligência construída.** Das 15
frentes, **2 não existem**, **1 existe parcialmente** e **12 já estão
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
3. Falta o sentido inverso em duas das três direções: **da tese para os casos**
   e **do precedente novo para as teses afetadas**. (A terceira — do caso
   encerrado de volta para a base — a primeira versão deu como ausente e
   estava errada: existe e funciona; ver frente 13.)

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

### 1. Radar jurisprudencial automático — 🟡 parcial (a metade das teses entrou nesta sessão)

O radar existe, mas é **legislativo, não jurisprudencial**.
`services/radar_legislativo.py` (541 linhas) monitora proposições na Câmara,
Senado e ALMG, com dedup persistente e degradação graciosa por fonte. Para
jurisprudência há `services/crawler_precedentes.py` — agregador honesto sobre
LexML, TJMG e DataJud, com **STJ e STF marcados explicitamente como
`nao_implementado`**. Há ainda `djen_service.py`, `diario_oficial_service.py` e
ingestores em `services/ingestors/`.

**A segunda metade — o cálculo de impacto — existe, mas sobre a entidade
errada.** `modules/dpt360/radar_service.py` classifica cada publicação de
`diario_oficial_alertas` numa área e a cruza com a carteira: para cada empresa
com caso canônico naquela área, emite um item de `impactos` com aderência,
fundamento e `status: "possivel_impacto"`, respeitando o mesmo escopo de RBAC do
dashboard, e ainda publica a `regra_impacto` que governa a exibição. Ou seja: o
mecanismo de "publicação nova → quem ela atinge" está construído e é honesto
sobre sua granularidade (área, não tese).

**A metade das TESES foi construída nesta sessão** — exatamente pelo caminho
que a correção acima indicou: trocar a entidade cruzada, não reconstruir o
mecanismo. `GET /teses/impacto-regulatorio` responde "o que saiu no Diário nos
últimos N dias pode ter mexido nestas teses", reusando o `classify_area` e o
`AREA_CASE_ALIASES` do próprio radar (uma taxonomia só) e a composição de score
do `tese_caso_matcher` (um peso só). O serviço novo
(`services/impacto_regulatorio.py`) traz **uma regra e só uma**: o alinhamento
de área entre publicação e tese é por *equivalência*, não por igualdade — a
publicação é classificada como `administrativo` e a tese do escritório vive em
`licitacoes`.

Decisões deliberadas: **determinístico, sem IA**; **sugere reler, nunca marca
como superada** (reavaliar tese à luz de norma nova é ato jurídico humano);
**explicável** (cada publicação vem com os termos que casaram); e os alertas
passam pelo `visible_alerts_query` canônico — a rota **não amplia** a superfície
de Diário Oficial que o usuário já enxergava. Tem tela: o painel "Teses a reler
pelo que saiu no Diário" no `/teses`, que ao clicar numa tese dispara a
varredura reversa da frente 2. Isso fecha a cadeia **publicação → tese →
processos** sem construir nada novo para o último elo.

**O que continua faltando** é a metade dos MODELOS DE PEÇA: nada responde "esta
decisão afeta o modelo Y". Nem o de fora: as fontes de jurisprudência seguem
sem STJ e STF (`crawler_precedentes` marca os dois como `nao_implementado`), e
o radar continua legislativo. O impacto hoje só alcança o que o DJEN e o Diário
Oficial de fato capturam — e o `CLAUDE.md` registra que a captura DJEN reporta
"ok" há meses sem nunca ter capturado nada. **Este endpoint herda esse limite:
ele é tão bom quanto a coleta que o alimenta.**

> **Correção:** a primeira versão afirmava que "nenhuma das fontes calcula
> impacto". A afirmação veio de `grep impacto` em três arquivos de serviço, sem
> procurar o conceito em `app/modules/`. Mesmo vício das outras quatro correções
> deste documento.

> Nota do repositório: `CLAUDE.md` registra que a captura DJEN *"reporta ok há
> meses sem nunca ter capturado nada"*, porque o heartbeat afere execução e não
> resultado. Qualquer trabalho nesta frente precisa monitorar resultado.

### 2. Sistema "Tese → Caso" — ✅ completo (a varredura reversa entrou nesta sessão)

Existe o caminho caso → teses, e bem feito: `routers/teses.py` (707 linhas) tem
`teses_do_caso`, `sugerir_teses_ia`, `motor_teses` (síncrono e assíncrono);
`services/matriz_teses_service.py` (661 linhas) decompõe o caso em questões
jurídicas e monta matriz com `AuthorityRecord` que **só nasce de retorno real do
RAG** e força determinística com pesos fixos documentados.

**A varredura reversa foi construída nesta sessão.**
`GET /teses/{tese_id}/casos-candidatos` (`services/tese_caso_matcher.py`)
responde exatamente ao *"foi identificado possível cabimento da tese X nos
processos A, B e C"* da proposta: determinístico, sem IA, com os termos que
casaram visíveis em cada candidato, respeitando o filtro de visibilidade de
casos e **sem nunca vincular** — criar o vínculo continua sendo ato humano.

E o catálogo **não tinha tela**: as únicas chamadas a `/teses` no frontend eram
o gerador. A página `/teses` (`pages/BancoTeses.tsx`) é a primeira superfície
das 707 linhas do router.

**O que sobra é calibragem, não construção:** o matching é textual, não
semântico, e os pesos foram escolhidos por raciocínio e fixados por teste —
nunca calibrados contra a base real do escritório. Só uso real diz se o piso
está no lugar.

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

> **Alerta herdado — e JÁ RESOLVIDO; os planos da auditoria é que não sabem.**
> `plano-lancamento-v3.md` trata o *erro jurídico sobre decadência (CPC art.
> 487, II) nas skills* como a única ressalva bloqueante para a IA gerar peça
> destinada a protocolo, e `plano-correcao-v2.md` §5.4 ainda o marca `[ALTO]`
> em aberto. **A correção entrou em 2026-08-14 (PR #1015)**, com defesa em
> profundidade:
>
> - `services/ai/juridico_guardrails.py` detecta e corrige a qualificação de
>   prescrição/decadência como "extinção sem resolução de mérito", com janela
>   de proximidade para não disparar em menção incidental do art. 485, e
>   checagem separada da cumulação indevida vício/fato do CDC;
> - ligado em **dois** pontos: `ai_skill_service.py` corrige no momento da
>   geração, e `routers/ai.py` aplica guardrail de **leitura** — resposta
>   antiga e errada é corrigida ao ser lida;
> - a origem também foi tratada: o seed força atualização do prompt das duas
>   skills afetadas (`prescricao-decadencia`, `simulador-defesa-adversarial`),
>   com backup dos prompts sobrescritos.
>
> Verificado por execução em 2026-08-22: `test_juridico_guardrails_decadencia`,
> `test_ai_logs_guardrail_leitura` e `test_skills_expansion_seed` — 35 testes e
> 54 subtestes, todos passando.
>
> **Atualizar os dois documentos da auditoria é decisão do titular** — este
> documento não altera o plano ativo. Mas quem ler §5.4 hoje vai refazer
> trabalho pronto, ou manter represada uma decisão que já está liberada.

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

> **Correção:** a primeira versão dizia que "a camada interpretativa —
> obrigações, pedidos e decisões extraídos do documento" ficava descoberta.
> `raio_x_enrichment` faz exatamente isso: `construir_decisoes` devolve tipo,
> data, **fundamento**, **comando/dispositivo**, **obrigação** e prazo por
> decisão; `construir_matriz_fatos_provas` correlaciona fato a prova e marca o
> que ficou `sem_prova_correlacionada`; `detectar_contradicoes_documentais`
> aponta divergências entre documentos. Tudo com `origem` por documento e
> `confirmado: False` — sugestão, nunca gravação.

**A ressalva real é outra, e mais fina:** essa camada é **consolidadora**, não
extratora. `_coletar` lê chaves já presentes no `intake` e no
`resultado_analise` de cada documento; quando a análise a montante não produziu
`decisoes`/`pedidos`, não há varredura do texto bruto para suprir. O que falta,
portanto, não é a interpretação — é a garantia de que ela é alimentada. Some-se
o "relacionar ao restante da base", que depende da frente 9.

> **Armadilha registrada:** `CLAUDE.md` alerta que *gravação não transacional
> entre registros relacionados é classe de defeito recorrente* no EJC — inclusive
> "validação que não vincula ao documento". Trabalho aqui exige conferir a
> transação.

### 11. Linha do tempo processual — ✅ existe (e tinha um defeito, corrigido aqui)

A matéria-prima é forte: `services/evento_processual.py` é catálogo
determinístico de eventos → termo inicial, com semântica de *dies a quo* correta
(CPC arts. 224 e 231) e recusa explícita em calcular o que não tem certeza
absoluta. Há `routers/andamentos.py`, `movimentos.py`, `services/movimento_ia.py`
e a tela `/casos/:id/jornada`.

> **Correção — a primeira versão deste documento dizia que "ninguém cruza o
> `rito_engine` com a linha do tempo real". É falso, e em três lugares
> independentes.** `raio_x_enrichment.enriquecer_relatorio` monta um
> `rito_context` com a cronologia documental real, as decisões e os prazos do
> caso, chama `identificar_rito` e devolve `etapa_atual` + `acoes_recomendadas`
> costuradas nos `proximos_passos` do relatório. `dossie_modulos.consolidar_modulos`
> monta `linha_do_tempo` com fase atual, fases concluída/atual/futura, eventos
> reais, estagnação e próximos passos que **misturam prazos reais do caso com
> passos típicos, cada um rotulado com sua origem** (`prazo` vs `estimativa`).
> `legal_case_orchestrator.proximo_passo` é a mesma pergunta por outro caminho:
> máquina de estados determinística sobre artefatos, devolvendo passo
> recomendado, ações disponíveis e pendências bloqueantes. Tudo isso tem
> frontend: `components/visual/LinhaDoTempoProcessual.tsx` consome
> `GET /visual-law/casos/{id}/timeline`.

**O que a verificação por execução encontrou não foi ausência — foi um defeito
ativo.** Executando `identificar_rito` sobre a mesma causa com cronologias
crescentes, `etapa_atual` acertava os cinco estágios, mas `proximas_etapas`
apontava **para trás**: um caso já sentenciado recebia *"petição inicial →
análise inicial"* como próximas etapas.

A causa é a classe de defeito que o `CLAUDE.md` registra como recorrente no EJC:
**vocabulário divergente entre duas camadas**. O estágio detectado é um código
(`pos_sentenca`, `defesa`); a jornada de cada rito é texto jurídico (`sentença`,
`contestação`). A busca procurava o rótulo pelo próprio código e localizava a
posição em **15 das 80** combinações rito × estágio; nas outras 65 caía num
`etapas[:3]` — o começo da jornada. Sem exceção, sem log, com saída plausível.

O texto errado era visível: `RaioXProcesso.tsx` imprime o `rito_jornada`
inteiro na tela, o mesmo dicionário vai para o PDF/DOCX exportado
(`raio_x_export_service`, seção "Jornada sugerida") e é entregue ao agente de IA
pela tool `identificar_rito_e_fase`.

**Corrigido nesta sessão** (`services/rito_engine.py`): a posição passa a ser
procurada pelos **mesmos marcadores** que identificaram o estágio — sem criar
uma terceira lista para manter em sincronia —, com prioridade pelo termo e não
pela ordem da jornada. Cobertura de posicionamento: **15/80 → 41/80**. Fim da
jornada devolve lista vazia, e estágio sem correspondente no rito devolve
silêncio, em vez de apontar para o começo — mesma recusa do `evento_processual`.
Regressão em `tests/test_rito_engine_proximas_etapas.py` (6 testes; 4 falham no
código anterior).

**O que de fato falta** é menor do que a proposta sugere: a explicação
*jurídica* do que cada movimento significa (hoje o evento é classificado e
posicionado, não interpretado).

### 12. Sistema "o que está faltando?" — ✅ os dois campos entraram nesta sessão

`routers/pending_items.py` (228 linhas) tem CRUD de pendências com vocabulário
fechado (documento/informação/assinatura/pagamento). `services/matriz_provas.py`
(257 linhas) é referência determinística tese×prova — para cada tese típica, as
provas mínimas para instruir a pretensão. `services/ficha_triagem_service.py`
já usa isso para apontar provas faltantes. Há ainda
`solicitacao_documento_service.py` e `kit_documental.py`.

**Os dois campos que faltavam entraram nesta sessão** (migration `147`):
`impacto` (alto/médio/baixo) e `providencia` (solicitar ao cliente / obter no
processo / emitir certidão / diligência externa). Ambos NULLABLE — pendência
antiga fica `NULL`, lido como "não avaliado", nunca como "sem impacto".

**O que sobra é preenchimento, não código:** os campos não se preenchem
sozinhos. Classificar impacto e providência é juízo do advogado; o sistema
agora tem onde guardar essa decisão, e antes não tinha. Enquanto ninguém
classificar, a lista continua sendo uma lista de ausências.

### 13. Memória institucional — ✅ existe e é alimentada automaticamente

`routers/memoria_institucional.py` (185 linhas) tem CRUD auditado, restrito à
equipe jurídica por allowlist exata, com tipos fechados incluindo
`tese_vencedora` e `estrategia`. Exposto no frontend em
`CasoDetalhe/TabMemoria.tsx`.

**E o ciclo automático existe.** `POST /cases/{id}/encerrar` exige pós-mortem
(resultado, motivo, provas determinantes, lições) e dispara duas coisas:

1. **RAG** — `upsert_documento` grava o precedente interno, idempotente por
   `chave_origem = caso:{id}` (`routers/cases.py`);
2. **`case_intel.aprendizado_encerramento`** — grava `memoria_institucional`
   (tipo `tese_vencedora` no êxito, `estrategia` na derrota) **e semeia o
   Banco de Teses**, com a tese nascendo `rascunho`/`sugerida_ia` para não
   entrar ativa sem revisão humana. Idempotente pela marca
   `metadados->>'fonte' = 'auto_encerramento'`, com PII sanitizada e
   degradação sem IA.

> **Correção da primeira versão deste documento.** Ela afirmava, sobre esta
> frente: *"é inteiramente manual; nada dispara no encerramento; nenhum
> registro retroalimenta o RAG ou o ranking de teses"*. **As três afirmações
> são falsas.** O erro foi ler só o router de memória institucional e concluir
> pela ausência do que estava do outro lado — no fluxo de encerramento do caso.

**O que faltava era prova de funcionamento, não código.** A única cobertura era
um guard ESTÁTICO (`test_migracao_gateway_fase1b.py` lê o fonte com
`inspect.getsource` procurando `task_type="estrategia"`); ninguém nunca
executara a função contra um banco. E ela **engole toda exceção** — mesma forma
do defeito que o `CLAUDE.md` registra na captura DJEN, que "reporta ok há meses
sem nunca ter capturado nada".

Exercitada contra Postgres real em 2026-08-22
(`tests/test_aprendizado_encerramento_dblevel.py`, 5 testes): a memória é
gravada, a reexecução não duplica, a tese nasce em rascunho com os contadores
certos, derrota vira `estrategia` sem contar como vitória, e caso inexistente
sai em silêncio sem derrubar o background do encerramento. **Funciona.**

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
| 2 | Tese → Caso | ✅ | Calibragem do matching contra base real, não construção |
| 3 | Playbooks | 🔴 | **Curadoria jurídica** + estrutura |
| 4 | Argumentos/contra-argumentos | ✅ | Acumular em catálogo |
| 5 | Revisor Jurídico | ✅ | 4 checagens novas |
| 6 | Banco de erros | 🔴 | **Curadoria jurídica** + estrutura |
| 7 | EJC Gold | ✅ código | **Certificação humana** (bloqueio conhecido) |
| 8 | Avaliação da IA | ✅ (gate de formato já bloqueia) | Ligar pisos de qualidade — dep. de 7 |
| 9 | Knowledge Graph | ✅ motor | **Curadoria** (massa de arestas) |
| 10 | Inteligência documental | ✅ | Camada interpretativa |
| 11 | Linha do tempo | ✅ | Interpretação jurídica do movimento, não código |
| 12 | O que está faltando | ✅ | Preenchimento pelo advogado, não código |
| 13 | Memória institucional | ✅ completo | Nada — verificado por execução |
| 14 | Matriz de estratégia | ✅ | Apresentação |
| 15 | Segundo advogado | ✅ completo | **Validar uso real** — não é backlog |

> **Nota de correção (2026-08-24):** esta linha do placar para as frentes 2, 11
> e 12 estava desatualizada em relação aos cabeçalhos das seções acima — os
> três já documentavam ✅ com evidência (varredura reversa de teses, correção
> do `rito_engine`, campos `impacto`/`providencia` da migration 147), mas o
> placar e a Onda A abaixo ainda as listavam como 🟡/pendentes. É o mesmo vício
> de disciplina de status que motivou o checklist-mestre único
> (`docs/PLANO_MESTRE_STATUS.md`) — ver banner no topo deste documento.

Duas das quinze (3, 6) dependem de **curadoria jurídica humana**, e três (7, 9,
15) de **certificação ou julgamento de uso**, não de código; e uma sexta (8)
fica bloqueada pela 7. É a informação mais acionável do documento: um terço
largo desta proposta não é trabalho de engenharia, e nenhuma quantidade de
sessão de Claude Code a resolve.

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
| ~~A1~~ | ~~Impacto + providência em pendências (frente 12)~~ | **Cancelado — já existe.** Campos `impacto`/`providencia` entraram pela migration `147`; falta preenchimento pelo advogado, não código. |
| ~~A2~~ | ~~Varredura reversa Tese → Caso (frente 2)~~ | **Cancelado — já existe.** `GET /teses/{tese_id}/casos-candidatos` (`services/tese_caso_matcher.py`) ativa o Banco de Teses; falta calibrar pesos contra a base real, não construir. |
| ~~A3~~ | ~~Captura automática no encerramento (frente 13)~~ | **Cancelado — já existe.** `aprendizado_encerramento` grava memória e semeia o Banco de Teses desde antes desta avaliação. O que faltava era prova: exercitado contra Postgres em 22/08, 5 testes, funciona. |
| A4 | Pisos de qualidade no gate de eval (frente 8) | O gate bloqueante já existe (`ci.yml:183`), mas afere formato e trajetória. `--min-recall` e `--full` já estão no harness e não estão ligados. Só vale com o gold set da frente 7 certificado. |

Com A1–A3 cancelados por já existirem, a Onda A inteira se resume a **A0**
(gate humano) **e A4** (bloqueado pela frente 7). Não sobra trabalho de
engenharia nesta onda — só validação de uso real e certificação humana.

**A0 pode invalidar o resto desta lista, e é para isso que serve.** Se o dossiê
sair ruim, o trabalho vira consertá-lo — não construir A1–A4 em volta de um
núcleo que não funciona. Se sair bom e ainda assim não for usado, o problema é de
descoberta ou de confiança, e também não se resolve com feature nova.

De A1 a A4 a ordem não é rígida — A1 e A2 são independentes e podem ir em
paralelo. O que importa é que a Onda A inteira mexe em coisa construída, tem
risco baixo e produz valor visível a cada item.

**Onda B — engenharia nova**

Depois da verificação por execução, esta onda encolheu — e o que sobrou mudou de
natureza. Ordem sugerida:

1. ~~**Frente 1 — impacto sobre teses.**~~ **FEITO nesta sessão**
   (`GET /teses/impacto-regulatorio` + painel no `/teses`), por reaproveitamento
   do mecanismo do DPT360. Resta a metade dos **modelos de peça** — e, antes
   dela, a pergunta que vale mais: **a coleta que alimenta o radar está de fato
   capturando alguma coisa?** Endpoint de impacto sobre coleta vazia devolve
   lista vazia com cara de "nada mudou".
2. **Frente 5 — as 4 checagens faltantes do revisor:** competência, valor da
   causa, prescrição/decadência e contradição fato↔pedido. O erro de decadência
   que esta lista mandava atacar primeiro **já está corrigido** (ver frente 5).
3. **Frente 10 — alimentar a camada interpretativa**, não construí-la: garantir
   que `decisoes`/`pedidos` cheguem ao `raio_x_enrichment` quando a análise a
   montante não os produziu.
4. **Frente 11 — interpretação jurídica do movimento.** O "você está aqui, o
   próximo passo é este" já existe e o defeito que o corrompia foi corrigido
   nesta sessão; o resto da frente é o menor resto da lista.

**Nenhum destes quatro itens é o que a proposta original descrevia.** Os quatro
foram redefinidos pela verificação, e três deles encolheram de "construir" para
"ligar" ou "alimentar". Vale repetir o método antes de qualquer linha de código:
das cinco frentes verificadas por execução até agora, **cinco tiveram afirmação
de ausência derrubada** — e a única que produziu trabalho de engenharia produziu
uma *correção de defeito*, não uma funcionalidade nova.

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

- **Verificação estática — e o que aconteceu quando ela deixou de ser estática.**
  O mapeamento original leu código, não executou nada. "Existe" ali significava
  "está implementado", não "funciona". O `CLAUDE.md` documenta o caso da captura
  DJEN, que reportava sucesso há meses sem nunca ter capturado nada. Três frentes
  já foram exercitadas de verdade — 13 (contra Postgres real), 5 (guardrails de
  decadência) e 11 (motor de ritos) — e o resultado justifica o método: **a
  execução derrubou a afirmação de ausência nas três e, na frente 11, revelou um
  defeito ativo que a leitura não veria**, porque a saída errada era plausível e
  não levantava exceção. Antes de tratar qualquer ✅ como pronto, exercite o
  fluxo; o inverso também vale — antes de tratar qualquer "falta" como
  verdadeira, execute o que existe.
- **Cinco correções, um só vício.** As frentes 15, 8, 13, 5, 11, 1 e 10 tiveram
  afirmações corrigidas neste documento. O padrão nunca mudou: **procurar por
  string em vez de por conceito, e num escopo estreito demais**. `dossie` em vez
  de `dossie-estrategico`; `routers/memoria_institucional.py` sem abrir quem
  escreve nele; `grep impacto` em três serviços sem olhar `app/modules/`;
  `proximas_etapas` julgada ausente sem rodar a função. A regra que restou:
  **procure quem escreveria naquele recurso, não só quem o lê — e depois execute.**
- **Ausências são mais frágeis que presenças.** Os dois 🔴 (playbooks, banco de
  erros) vêm de busca por nome e conceito no backend. É a mesma limitação que o
  `CLAUDE.md` registra sobre o graphify: *confirme no arquivo antes de afirmar que
  algo não existe*.
- **A frente 13, um dos casos.** A frente 13 foi
  dada como "inteiramente manual, nada dispara no encerramento, nada
  retroalimenta o RAG nem o ranking de teses" — as três cláusulas falsas. O
  padrão é sempre o mesmo: **ler um lado da integração e concluir pela ausência
  do outro**. Aqui, ler `routers/memoria_institucional.py` e não abrir
  `POST /cases/{id}/encerrar`, que é quem alimenta. Antes de tratar qualquer 🔴
  ou "falta" deste documento como verdade, procure quem *escreveria* naquele
  recurso, não só quem o *lê*.
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
