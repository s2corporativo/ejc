# Auditoria — importação, leitura e geração de documentos + qualidade da IA

**Data:** 2026-08-09 · **Escopo:** todos os módulos que importam, leem ou geram
documento no EJC, mais a qualidade da IA sobre esse material.
**Método:** leitura do código-fonte (não da produção) + **geração de documentos
reais** com o gerador do próprio repositório, renderizados em PDF e inspecionados
página a página. Diferente da auditoria externa de julho/2026 (`plano-correcao-v2.md`),
que rodou às cegas por HTTPS, aqui cada afirmação foi conferida no arquivo.

> **Como ler.** Cada achado traz: o que está errado, a **crítica** (por que
> importa para o advogado), a **sugestão** e a **sugestão de implementação**.
> Achados marcados `[CORRIGIDO]` já entraram neste PR; `[RETIDO]` está em arquivo
> que pertence a PR aberto (regra 4 da governança) e vai com patch pronto.

---

## Sumário executivo

O EJC lê documentos **bem** e gera documentos **bonitos**. O que ele não faz é
**entregar ao advogado o que a IA já pensou**. O sistema tem hoje um advogado
sênior sintético que lê a peça, monta tese, aponta risco e sugere estratégia — e
joga esse parecer num campo de log truncado que nenhuma tela abre. O gargalo do
critério de lançamento ("mais fácil do que fazer fora do sistema") não está na
extração nem no visual: está no fato de o raciocínio produzido não voltar para
quem decide.

| # | Achado | Sev. | Estado |
|---|--------|------|--------|
| A1 | Parecer da leitura de documento morre em `AILog`, nunca vira dado do caso | Crítico | [CORRIGIDO] |
| A2 | Hook de análise é *monkey-patch* no boot e perde a classificação de risco | Alto | [CORRIGIDO] |
| A3 | `DocumentoIntakeResult.provas` é campo morto — nunca populado | Alto | [CORRIGIDO] |
| C1 | Prompt do advogado não pedia provas necessárias nem brechas preliminares | Alto | [CORRIGIDO] |
| A4 | Mapper do intake descarta estratégia, pontos fortes e brechas do LLM | Médio | Parcial |
| B1 | Chrome fixo do PDF de peça sem acentuação | Alto (imagem) | [RETIDO] |
| A5 | `bank_analysis.upload` sem magic bytes, enquanto o irmão valida | Médio | [RETIDO] |
| A6 | Falha da leitura em background é silenciosa para o advogado | Médio | Aberto |

---

## A. Importação e leitura de documentos

### Mapa real do que existe

Há **quatro** caminhos de ingestão, todos confirmados no código:

| Caminho | Arquivo | Validação de conteúdo | Hash | Análise IA |
|---|---|---|---|---|
| GED | `routers/documents.py` | `_validar_conteudo` (magic bytes) | sha256 (em PR #759) | sim, background |
| Raio-X | `routers/raio_x.py` | `upload_lote_service` | sha256 | sim, fila |
| Sala Jurídica | `routers/legal_chat.py` | `upload_lote_service` | sha256 | sim, inline |
| Entrada Universal | `routers/entrada.py` → `entrada_service` | via serviço | — | sim |

Mais uploads especializados: `rag.ingerir_pdf` (`_validar_pdf_upload`),
`defesas_revisoes` (`upload_guard.validar_upload`), `analise_bancaria`
(`validar_upload(exigir_pdf=True)`), `portal_documentos`, `nfse`,
`tributario_fiscal`, `ai_skills`, `users`.

**Crítica geral (positiva):** a extração é melhor do que a média de mercado.
`documento_service.extrair_e_analisar` faz o que quase ninguém faz: extrai o
dado pessoal exato por **regex local determinística** e só manda para o LLM o
texto **sanitizado** — o CPF real nunca sai do VPS, mas o advogado recebe o CPF
real na tela. Isso é arquitetura correta de LGPD, não teatro de conformidade. O
fallback também degrada bem: cadeia de IA inteira fora do ar devolve
`ok=True, parcial=True` com o texto extraído, em vez de erro seco.

### A1 [CRÍTICO] [CORRIGIDO] — o parecer da IA morria no log

**O que acontece.** Ao subir documento vinculado a um caso, dispara-se em
background `analise_estrategica.analisar_caso` — a análise mais cara e mais
completa do sistema (RAG interno, pseudonimização reversível, conferência de
citações). O resultado é serializado para `AILog.resposta` **cortado em 8.000
caracteres** e o `AILog` termina ali. Nenhuma tela lê esse campo como parecer;
nada é escrito no caso.

**Crítica.** Este é o defeito mais caro do sistema e não é um bug de código — é
um bug de produto. O escritório paga tokens para um advogado sênior sintético
ler a peça, formar tese, medir risco e propor estratégia, e o resultado é
descartado num log de auditoria. É a mesma classe de armadilha que o `CLAUDE.md`
já nomeia ("chance de êxito fica no log e não no caso"), só que na versão mais
grave: aqui morre o parecer inteiro. Enquanto isso, `case_intel.triagem_caso`
— criação de caso — **já** grava snapshot corretamente. Ou seja: a infraestrutura
existia, o caminho do documento é que não a usava.

**Sugestão.** O parecer da leitura de documento deve virar dado versionado do
caso, sujeito a HITL, no mesmo caminho de triagem/intake/motor de peça.

**Sugestão de implementação — aplicada.** `CaseIntelligenceSnapshot` já é
append-only, versionado por caso, nasce `congelado=False` (aprovar é ato humano)
e tem API de leitura com RBAC (`GET /cases/{case_id}/inteligencia`). Bastava
uma origem nova:

- `models/case_intelligence.py`: `ORIGENS_SNAPSHOT` ganha `"documento"`.
  Coluna é `String` validada no service — **aditivo, sem migration**.
- `services/event_subscribers.py`: `_payload_leitura_documento()` traduz o
  parecer para o payload documentado (`fatos`, `teses`, `riscos`, `provas`,
  `pontos_fortes`, `estrategia`, `brechas`, `proximos_passos`, `alertas`,
  `fontes`) e `_gravar_snapshot_documento()` grava via `gravar_snapshot_seguro`.
- O snapshot aponta para o `AILog` que o gerou (`ai_log_ids`) — a trilha LGPD
  continua íntegra e agora é navegável nos dois sentidos.

Duas decisões de projeto que valem registro: brecha sem indício **não vira
achado** (um `brechas_preliminares` com tudo `null` faria a tela anunciar
nulidade onde a IA admitiu lacuna), e parecer vazio/com erro **não gera
snapshot** (não polui o histórico versionado do caso).

### A2 [ALTO] [CORRIGIDO] — monkey-patch no boot, com regressão embutida

**O que acontece.** `event_subscribers._patch_documents_background_analysis()`
substitui, em tempo de boot, a função `documents._analisar_doc_bg` por uma cópia
de ~40 linhas quase idêntica. A cópia — que é a que **efetivamente roda** —
omitia `risco_ia=classificar_risco_ia("analise_juridica")`, presente no
original.

**Crítica.** Duas coisas ruins somadas. A primeira é o padrão: reescrever um
símbolo de router em runtime é invisível para quem lê `documents.py`, some do
`grep`, e o `graphify` não mostra. Quem for corrigir a análise documental vai
editar a função errada e concluir que "a correção não teve efeito". A segunda é
a consequência: **todo `AILog` de análise documental em produção nasceu sem
classificação de risco de IA**, porque a cópia esqueceu o campo. Governança de
IA que classifica risco só no caminho que não executa não classifica nada.

**Sugestão.** Curto prazo: restaurar o campo perdido (feito). Médio prazo:
matar o patch — a única diferença real entre as duas versões era o corte do OCR,
que pode ser parâmetro da função original.

**Sugestão de implementação.** Promover `_analisar_doc_bg` a serviço próprio
(`services/analise_documental_service.py`) chamado pelos dois lados, e deletar
`_patch_documents_background_analysis`. Não foi feito aqui porque exige editar
`routers/documents.py`, que pertence aos PRs #759 e #758 (regra 4).

### A3 [ALTO] [CORRIGIDO] — `provas` era campo morto no contrato tipado

**O que acontece.** `DocumentoIntakeResult` (schema do intake) declara
`provas: list[ProvaExtraida]`. Uma varredura no repositório mostra que
**`ProvaExtraida` nunca foi instanciada em lugar nenhum** — o campo é sempre
`[]`. O esquema do prompt também não pedia provas de forma estruturada: existia
só `estrategia.producao_de_provas`, uma lista de strings soltas que o mapper
descartava.

**Crítica.** "O que eu ainda preciso provar?" é a pergunta mais operacional que
um advogado faz ao ler um documento novo — mais do que resumo, mais do que área.
O contrato tipado tinha o campo certo, com os subcampos certos (`titulo`, `tipo`,
`finalidade`), e ninguém ligou os fios. É pior que ausência: o campo existente e
sempre vazio faz o frontend e o próximo desenvolvedor acreditarem que a
funcionalidade existe e que a IA "não achou provas".

**Sugestão de implementação — aplicada.** Esquema do prompt passa a pedir
`provas_necessarias` estruturado (`titulo`, `tipo`, `fato_probando`,
`ja_disponivel`) com instrução explícita de devolver `[]` quando não houver fato
controvertido identificável — em vez de encher a lista de provas genéricas.
`_provas_extraidas()` mapeia para `ProvaExtraida`, descartando item sem título
(prova sem nome não é acionável) e mantendo o fail-safe do módulo: entrada
malformada vira lista vazia, nunca exceção.

### A4 [MÉDIO] — o mapper ainda descarta parte do raciocínio

**O que acontece.** O LLM do intake devolve `diagnostico` (pontos fortes/fracos,
riscos, oportunidades), `brechas_processuais` (prescrição, decadência,
incompetência, ilegitimidade, nulidades, falhas documentais) e `estrategia`
(medidas cabíveis, recursos, ações, negociação). O `_montar_intake_result`
aproveita **só** `diagnostico.riscos` e `brechas_processuais.teses_defensivas`.
Pontos fortes, oportunidades, estratégia inteira e as brechas nominais
(prescrição/decadência/nulidades) são calculados, pagos em tokens e jogados fora
na conversão para o contrato tipado.

**Estado.** Parcialmente resolvido: `provas` foi ligado (A3) e o caminho do
documento anexado a caso agora persiste tudo via snapshot (A1). O intake de
documento **novo** (antes de existir caso) continua perdendo esses campos.

**Sugestão de implementação.** Estender `DocumentoIntakeResult` com
`pontos_fortes: list[str]`, `pontos_fracos: list[str]`, `oportunidades: list[str]`
e `brechas: dict` — aditivo, default vazio, sem quebrar consumidor. Não foi feito
neste PR para não misturar mudança de contrato público de API com a correção
central; vira Issue própria.

### A5 [MÉDIO] [RETIDO] — dois irmãos, uma guarda só

`routers/analise_bancaria.py:138` faz `validar_upload(raw, exigir_pdf=True)`.
`routers/bank_analysis.py:60` — mesmo domínio, extrato bancário — lê o arquivo
inteiro **sem nenhuma validação de magic bytes**, confiando no campo `formato`
do formulário ou na extensão do nome, e grava o PDF em disco antes de entregar
ao parser. O teto também é `25 * 1024 * 1024` hardcoded em vez de
`settings.MAX_UPLOAD_MB`.

**Crítica.** É exatamente o padrão que o repositório já batizou em outro PR:
"caminho paralelo sem a guarda do irmão". Extensão e `content_type` são dados do
cliente; a decisão de qual parser roda sai deles. Dois routers para a mesma
função, com políticas de segurança diferentes, é dívida que se paga em incidente.

**Sugestão de implementação (patch pronto).** Em `bank_analysis.upload`, após
`conteudo = await file.read()`:

```python
from app.core.upload_guard import validar_upload
validar_upload(conteudo, exigir_pdf=(fmt == "pdf"))
```

e remover o teto hardcoded (o guard já aplica `MAX_UPLOAD_MB`). **Retido**:
`bank_analysis.py` pertence aos PRs `fixes-without-github-45v7ep` e
`portal-varredura-publicacao-698`. Decisão de fundo, para Issue: os dois routers
deveriam virar um.

### A6 [MÉDIO] — falha de leitura é silenciosa para quem importou

`_analisar_doc_bg` termina em `except Exception: logger.warning(...)`. Se a
leitura estratégica falhar, o advogado que subiu o documento não recebe sinal
nenhum — a ausência de parecer é indistinguível de "a IA não achou nada".

**Crítica.** O `CLAUDE.md` já registra que "monitoramento afere execução, não
resultado" e que por isso a captura DJEN reportou "ok" por meses sem capturar
nada. Aqui é a mesma doença na leitura documental.

**Sugestão de implementação.** Gravar snapshot de origem `documento` com
`payload={"falha": "..."}`? Não — poluiria o histórico. O caminho certo é
`pending_items` / notificação: registrar pendência "leitura automática do
documento X falhou — reprocessar", que já é um módulo existente. Issue própria.

---

## B. Geração de documentos e Visual Law

### Evidência gerada nesta auditoria

Foram geradas três peças reais pelo gerador do repositório e inspecionadas em
PDF: minuta de IA, peça pronta para protocolo e cronologia processual.

**Veredito visual: o Visual Law do EJC é bom.** A peça sai com logo do
escritório, cabeçalho com OAB/e-mail/endereço, filete dourado, capa com kicker
e meta-grid (Controle/Versão/Status em caixas), selo vermelho de minuta de IA no
topo, títulos com barra dourada lateral, *callouts* destacados para linhas de
alerta, texto justificado, rodapé com linha de controle `EJC-...` e paginação
"p. X de Y". A cronologia (`visual_law_pdf`) sai com banner dourado cheio, logo
centralizado e linha do tempo zebrada. Isso não é template genérico — é
identidade visual de escritório.

**Nota metodológica honesta:** a primeira rodada desta auditoria chamou o helper
interno `_texto_peca_para_html` e concluiu que o PDF saía **sem estilo nenhum**.
Estava errado: o CSS entra em `peca_para_pdf_async`, o ponto de entrada público.
O achado foi refeito pelo caminho real. Fica o registro porque o helper interno
produzir HTML com classes Visual Law e nenhum CSS é uma armadilha real para quem
for reusá-lo.

### B1 [ALTO] [RETIDO] — o texto fixo do documento não tem acento

O conteúdo do advogado sai acentuado corretamente. O **chrome fixo**, escrito no
código, não:

| Onde | Sai hoje | Deveria |
|---|---|---|
| `document_format.marca_minuta_ia` | `MINUTA GERADA POR IA - REVISAO E ASSINATURA POR ADVOGADO HABILITADO (OAB) OBRIGATORIAS. NAO PROTOCOLAR SEM REVISAO.` | REVISÃO / OBRIGATÓRIAS / NÃO … REVISÃO |
| `pdf_service.py:202` | `ATENCAO: Rascunho sujeito a revisao humana obrigatoria por advogado responsavel…` | ATENÇÃO … revisão … obrigatória … responsável |
| `pdf_service.py:218` | `Versao` | Versão |
| `pdf_service.py:197` | `Peca final validada` | Peça final validada |
| `pdf_service.py:40` | `Pagina N de M` | Página |
| `pdf_service.py:89` | `Responsabilidade tecnica condicionada a revisao e assinatura do advogado responsavel.` | técnica … revisão … responsável |

**Crítica.** É o defeito mais visível do sistema inteiro e o mais barato de
corrigir. O documento que o escritório entrega ao cliente e protocola no
tribunal tem, em destaque na primeira página, um selo em caixa-alta sem
acentuação — enquanto o texto ao lado, escrito pelo advogado, está perfeito. Um
cliente não sabe o que é `_montar_intake_result`; sabe ler "OBRIGATORIAS" no topo
da própria petição. Pior: `document_format.py` já documenta que "o conteúdo
armazenado agora preserva acentuação" — a migração aconteceu para o conteúdo do
usuário e **esqueceu o chrome do próprio módulo**. E `visual_law_theme.py`, o
irmão que gera a cronologia, é 100% acentuado: dois geradores, dois padrões.

Confirmei que o defeito **persiste na branch mais avançada em aberto** — não é
algo já resolvido e não mesclado.

**Sugestão de implementação (patch pronto).** Substituição literal das seis
strings acima. Zero risco funcional: `_ALERT_WORDS` já casa as duas grafias
(`"ATENCAO", "ATENÇÃO"`), então o realce visual continua funcionando durante a
transição. **Retido**: `pdf_service.py` e `document_format.py` pertencem à
linhagem de PRs #765/#785, presente em sete branches abertas — editá-los aqui
geraria conflito em todas.

### B2 — sugestão de melhoria: o PDF não mostra o raciocínio

Hoje o PDF de peça mostra **o produto** (a petição). Com A1 corrigido, o caso
passa a ter parecer estruturado — e há um gerador de PDF Visual Law ocioso para
ele.

**Sugestão de implementação.** Um `parecer_estrategico_pdf(case_id)` reusando
`visual_law_theme` (o gerador acentuado): capa com o caso, um bloco por eixo do
raciocínio — pontos fortes / pontos fracos / brechas a verificar / provas
necessárias (com quem produz e urgência) / cenários estratégicos / próximos
passos — e rodapé com a marca de minuta e o `ai_log_id`. Seria o artefato que o
advogado leva para a reunião com o cliente, e o argumento mais direto de que o
sistema é "mais fácil do que fazer fora dele".

---

## C. Qualidade da IA na leitura

### O que já era bom

`analise_estrategica.analisar_caso` é um pipeline sério: dossiê do documento
(não corte cego em 4.000 caracteres), *grounding* RAG com escopo por cliente,
sanitização de PII com **segunda barreira** (`validar_sem_pii` aborta se sobrar
PII), pseudonimização **reversível** de nomes (a resposta volta com o nome real
sem o nome ter ido ao provedor) e `citation_check` conferindo súmulas/artigos
citados contra a base oficial. O prompt já proibia inventar jurisprudência e já
exigia `null` na lacuna.

### C1 [ALTO] [CORRIGIDO] — faltava o que o advogado mais usa

O prompt pedia partes, ramo, fatos, pontos fortes/fracos, três cenários
estratégicos, teses campeãs, riscos, jurimetria, próximos passos e alertas.
**Não pedia provas necessárias nem brechas preliminares.**

**Crítica.** A análise era boa como parecer de risco e fraca como plano de
trabalho. Faltavam as duas perguntas que decidem a semana do advogado: *o que eu
preciso provar e quem produz cada prova?* e *tem prescrição, decadência,
incompetência, ilegitimidade ou nulidade em cima da mesa?* Sem elas a saída lê
como consultoria; com elas, lê como advogado.

**Sugestão de implementação — aplicada.** Duas chaves novas no JSON do prompt:

- `provas_necessarias[]` — `titulo`, `tipo` (documental/pericial/testemunhal/
  inspecao/depoimento_pessoal), `fato_probando`, `ja_disponivel`, `quem_produz`
  (cliente/escritório/juízo/parte contrária/terceiro), `urgencia`.
- `brechas_preliminares{}` — prescrição, decadência, incompetência,
  ilegitimidade, nulidades, falhas da parte contrária.

E uma seção nova de postura, **"COMO LER (POSTURA DE ADVOGADO, NÃO DE
EXTRATOR)"**, que instrui: você não está resumindo o documento, está formando o
juízo profissional de quem o lê pensando no caso do seu cliente. Ela também
fecha o risco que a mudança abre — toda brecha é **hipótese a verificar**, com o
indício concreto que a sustenta, nunca a conclusão de que algo "é nulo". As
regras anti-alucinação continuam intactas e há teste travando isso.

### C2 — sugestão: a leitura não é adversarial

Mesmo enriquecida, a IA lê o documento pelos olhos de quem o recebeu.

**Sugestão.** Um segundo passe curto, "advogado da parte contrária": dado o
mesmo material e o parecer já produzido, *como eu atacaria esta tese?* As
objeções voltam como `pontos_fracos` de verdade — testados, não declarados. Cabe
como skill do núcleo (`ai/core`), reusando o gateway, com custo de uma chamada.
Issue própria — é feature, não correção.

---

## Correções aplicadas neste PR

| Arquivo | Mudança |
|---|---|
| `models/case_intelligence.py` | origem `"documento"` em `ORIGENS_SNAPSHOT` (aditivo, sem migration) |
| `services/event_subscribers.py` | `_payload_leitura_documento` + `_gravar_snapshot_documento`; `risco_ia` restaurado |
| `services/analise_estrategica.py` | `provas_necessarias`, `brechas_preliminares` e seção de postura de advogado |
| `services/documento_service.py` | esquema pede provas estruturadas; `_provas_extraidas` popula `DocumentoIntakeResult.provas` |
| `tests/test_leitura_estrategica_documento.py` | 16 testes de regressão |

**Sem migration** (coluna `origem` é `String` validada no service) e sem mudança
de contrato público de API — apenas campos que já existiam passam a vir
preenchidos.

## Riscos residuais e limitações

- **Não foi executado contra ambiente de pé.** Não há Postgres/pgvector nesta
  sessão; a validação é unitária + geração real de PDF. O caminho
  upload → background → snapshot precisa de um teste de fumaça em homologação.
- **Custo de tokens sobe.** O prompt ficou maior e a saída também. Não foi
  medido. Vale acompanhar `AILog.custo_estimado` na primeira semana.
- **Qualidade da saída nova não foi medida com LLM real.** Os testes travam a
  *estrutura* do prompt e o mapeamento, não a qualidade jurídica das provas e
  brechas que o modelo vai devolver. Isso exige avaliação humana sobre casos
  reais — é o próximo passo natural.
- **Dois achados ficaram retidos** por pertencerem a PRs abertos (B1, A5), com
  patch pronto acima.

## Decisões que dependem do titular

1. **Matar o monkey-patch** de `_analisar_doc_bg` (A2) exige mexer em
   `routers/documents.py`, hoje de outro PR — precisa de ordem de integração.
2. **Unificar `bank_analysis` e `analise_bancaria`** (A5): são dois módulos para
   a mesma função. Unificar é exclusão de código — §10 da governança.
3. **Estender `DocumentoIntakeResult`** (A4) mexe em contrato lido pelo
   frontend.
