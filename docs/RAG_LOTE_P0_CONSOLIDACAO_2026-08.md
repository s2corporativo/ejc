# Lote P0 — Consolidação e Abastecimento Jurídico

**Issue:** [#1239](https://github.com/s2corporativo/ejc/issues/1239)  
**Branch:** `feat/rag-lote-p0`  
**Data da execução:** 2026-08-22  
**Responsável técnico:** Manus AI

## 1. Resultado executivo

A auditoria confirmou que o EJC já possui um caminho único para legislação federal: o catálogo `CATALOGO` do ingestor Planalto, o wrapper `backend/scripts/seed_legislacao.py`, o `upsert_documento` idempotente, a divisão por artigo e a governança de vigência/qualidade. Por isso, não foi criado módulo paralelo, migration, tabela nova, endpoint novo ou segunda fonte de verdade.

Dos dezesseis itens do primeiro ciclo obrigatório, quatorze já estavam representados no catálogo ou nos mecanismos jurídicos existentes. As duas lacunas objetivas no catálogo de lei seca eram a **Lei nº 6.830/1980 — Lei de Execução Fiscal** e a **Lei nº 9.514/1997 — Sistema de Financiamento Imobiliário e Alienação Fiduciária**. Ambas foram adicionadas ao catálogo único com chaves estáveis, URLs oficiais e áreas jurídicas coerentes. A jurisprudência não foi artificialmente misturada ao ingestor Planalto: súmulas STF/STJ/TST e o ingestor STJ já existentes permanecem em seus caminhos próprios; jurisprudência dinâmica adicional permanece como frente futura, sujeita a fonte oficial verificável e curadoria.

## 2. Arquitetura utilizada

| Camada | Implementação preservada | Regra operacional |
|---|---|---|
| Documento pai | `KnowledgeDoc` | Um registro por fonte lógica e versão; `client_id`/`case_id` permanecem nulos para base jurídica pública. |
| Trechos | `KnowledgeChunk` | Unidade semântica vinculada a `doc_id`; legislação é dividida por artigo pelo parser existente. |
| Fonte de lei seca | [`backend/app/services/ingestors/planalto.py`](../backend/app/services/ingestors/planalto.py) | URL oficial do Planalto; nenhuma transcrição manual de texto foi adicionada ao repositório. |
| Interface de seed | [`backend/scripts/seed_legislacao.py`](../backend/scripts/seed_legislacao.py) | Reexporta o mesmo catálogo e usa as mesmas chaves do job agendado. |
| Persistência | `upsert_documento` | Canonicalização, deduplicação por `chave_origem`, hash de conteúdo, versionamento e histórico. |
| Recuperação | Pipeline RAG híbrido governado | Respeita status, vigência, autoridade, isolamento e citation gate. |
| Governança | [`backend/app/routers/rag_governance.py`](../backend/app/routers/rag_governance.py) e [`backend/app/services/knowledge_governance.py`](../backend/app/services/knowledge_governance.py) | Revisão humana, qualidade, frescor, autoridade, situação jurídica, comparação de versões e smoke tests. |
| Jurisprudência | `sumulas_ingestion.py`, `services/ingestors/stj.py` e LexML | Mantida separada da lei seca; ausência de texto integral ou de status verificado não é tratada como vigência. |

## 3. Taxonomia única

A taxonomia operacional deve usar uma categoria estrutural e tags semânticas controladas. A categoria determina o tipo de conhecimento; a tag combina **área/conceito**, evitando sinônimos concorrentes para o mesmo assunto.

| Dimensão | Valores canônicos | Exemplos de tags |
|---|---|---|
| Legislação | `legislacao` para lei seca oficial; `referencia_legislativa` para índice/ementa federada sem texto legal integral | `ambiental/licenciamento`, `tributario/execucao-fiscal`, `administrativo/licitacao`, `imobiliario/alienacao-fiduciaria` |
| Súmulas | `sumula_stf`, `sumula_stj`, `sumula_tst` | `trabalhista/vinculo`, `consumidor/bancario`, `administrativo/precatorio` |
| Jurisprudência | `jurisprudencia` | `civil/responsabilidade`, `ambiental/auto-infracao`, `tributario/execucao-fiscal` |
| Modelos e peças | categorias internas já existentes | `processual/tutela-urgencia`, `licitacao/recurso`, `empresarial/contrato` |
| Doutrina | `doutrina` | `civil/contratos`, `tributario/credito`, `administrativo/controle` |

A área jurídica deve preferir os valores existentes no serviço de governança, incluindo Civil, Consumidor, Trabalhista, Penal, Empresarial, Tributário, Administrativo, Ambiental, Previdenciário, Família e Sucessões, Imobiliário, Bancário e Digital/LGPD. Quando não houver informação segura, o campo permanece nulo ou recebe `Geral` apenas quando a regra atual de detecção determinar esse resultado; não se deve inferir área a partir de conteúdo incerto.

## 4. Metadados mínimos e temporais

O contrato abaixo é a referência de preenchimento. Campos inexistentes ou desconhecidos permanecem nulos; aprovação interna não altera a autoridade jurídica da fonte.

| Grupo | Campos | Regra |
|---|---|---|
| Identidade | `titulo`, `categoria`, `chave_origem`, `versao`, `versao_anterior_id`, `vigente` | Chave estável por fonte lógica; Planalto usa `planalto:<slug>`. |
| Origem | `fonte`, `extra.fonte_url`, `extra.link_official`, `extra.tipo_fonte`, `extra.origem` | Usar domínio oficial quando disponível; nunca persistir URL não autorizada como fonte principal. |
| Conteúdo | `hash_conteudo`, `extra.divisao`, `extra.artigos`, `extra.pagina`, `extra.ocr` | Lei seca por artigo; guardar relação pai–chunk e advertências de extração. |
| Jurídicos | `extra.area_juridica`, `extra.diploma`, `extra.numero`, `extra.ano`, `extra.authority_level`, `extra.legal_status` | Não preencher por inferência quando o dado não estiver na fonte ou na curadoria. |
| Temporal | `extra.last_verified_at`, `extra.data_ultima_verificacao`, `extra.proxima_verificacao_recomendada` | Legislação e jurisprudência exigem revisão periódica; `last_verified_at` é o campo consumido pelo frescor atual. |
| Governança | `extra.rag_status`, `extra.requires_human_review`, `extra.human_reviewed`, `extra.human_reviewed_by`, `extra.quality_note` | Aprovação e retirada de quarentena são decisões distintas e auditadas. |
| Isolamento | `client_id`, `case_id`, permissões e auditoria | Base jurídica geral sem cliente/caso; conteúdo privado nunca é promovido automaticamente ao corpus geral. |

O código atual já consome `last_verified_at` para o cálculo de frescor e exige curadoria para vigência não verificada. A nomenclatura portuguesa `data_ultima_verificacao` e `proxima_verificacao_recomendada` deve ser adicionada somente quando houver contrato de API ou migration que a suporte; não foi criado campo paralelo nesta rodada.

## 5. Cobertura do primeiro ciclo obrigatório

| Item | Situação em 2026-08-22 | Tratamento |
|---|---|---|
| Constituição Federal | Existente: `cf88` | Mantido no catálogo Planalto. |
| Código Civil | Existente: `cc` | Mantido no catálogo Planalto. |
| CPC | Existente: `cpc` | Mantido no catálogo Planalto. |
| CDC | Existente: `cdc` | Mantido no catálogo Planalto. |
| CLT | Existente: `clt` | Mantido no catálogo Planalto. |
| CPP | Existente: `cpp` | Mantido no catálogo Planalto. |
| Código Penal | Existente: `cp` | Mantido no catálogo Planalto. |
| CTN | Existente: `ctn` | Mantido no catálogo Planalto. |
| Lei nº 14.133/2021 | Existente: `l14133` | Mantida no catálogo Planalto. |
| Lei nº 9.605/1998 | Existente: `lca` | Mantida no catálogo Planalto. |
| Legislação ambiental estruturante | Existente: `cflo`, `lca`, `pnma` | Mantido o conjunto já catalogado; expansão será feita por lotes temáticos. |
| LGPD | Existente: `lgpd` e fontes ANPD | Mantida a separação entre lei seca e atos/guias da ANPD. |
| Lei do Mandado de Segurança | Existente: `l12016` | Mantida no catálogo Planalto. |
| Lei de Execução Fiscal | **Adicionada:** `l6830` | URL oficial confirmada; parser e chunks verificados em dry-run. |
| Lei nº 9.514/1997 | **Adicionada:** `l9514` | URL oficial confirmada; parser e chunks verificados em dry-run. |
| Jurisprudência vinculante e qualificada | Parcialmente coberta | Súmulas STF/STJ/TST, STJ CKAN e LexML existentes; jurisprudência dinâmica adicional não foi inventada nem duplicada. |

## 6. Alterações efetivamente realizadas

O catálogo do Planalto foi ampliado de 36 para 38 entradas, com os seguintes registros:

| Slug | Chave de persistência | Título | Área | Fonte oficial |
|---|---|---|---|---|
| `l6830` | `planalto:l6830` | Lei de Execução Fiscal (Lei 6.830/1980) | `tributario` | [Planalto — Lei nº 6.830/1980][1] |
| `l9514` | `planalto:l9514` | Lei do Sistema de Financiamento Imobiliário e Alienação Fiduciária (Lei 9.514/1997) | `imobiliario` | [Planalto — Lei nº 9.514/1997][2] |

O teste `test_catalogo_unificado_planalto_sem_duplicatas` foi atualizado para exigir 38 entradas, preservar unicidade e verificar as duas URLs oficiais. Não houve alteração de schema, autenticação, RBAC, dependências do projeto, migrations ou PRs concorrentes.

## 7. Validação de fonte e preparação para RAG

As páginas oficiais foram confirmadas diretamente. A Lei nº 6.830/1980 foi identificada pela ementa relativa à cobrança judicial da Dívida Ativa da Fazenda Pública e apresentou 42 artigos reconhecidos no dry-run. A Lei nº 9.514/1997 foi identificada pela ementa relativa ao Sistema de Financiamento Imobiliário e à alienação fiduciária de coisa imóvel e apresentou 43 artigos reconhecidos. As marcações de dispositivos revogados existentes na página da Lei nº 9.514/1997 não foram apagadas nem reinterpretadas; serão tratadas pelo parser e pela governança de vigência.

O dry-run executado foi:

```text
python -m scripts.seed_legislacao --apenas l6830,l9514 --dry-run --cache-dir /home/ubuntu/ejc_p0_cache
```

O resultado foi `2 ok / 0 falha(s)`, com 28 chunks e 23.471 caracteres para `l6830`, e 55 chunks e 47.494 caracteres para `l9514`. O procedimento apenas baixou/cacheou, parseou e montou os chunks; não gravou no banco. A evidência detalhada está em [`/home/ubuntu/ejc_p0_dry_run_evidence.md`](../../ejc_p0_dry_run_evidence.md), fora do repositório.

A inserção persistente e a geração de embeddings não foram executadas no sandbox porque não há banco PostgreSQL/pgvector autorizado nem credenciais de produção disponíveis nesta execução. O caminho seguro, quando o ambiente autorizado estiver disponível, é rodar o wrapper com `--apenas l6830,l9514`, sem `--com-embeddings` na mesma transação, deixando o reembed agendado preencher os vetores. Depois, devem ser executados os endpoints de governança de saúde, cobertura e smoke tests jurídicos por usuário gestor.

## 8. Relações jurídicas progressivas

O lote P0 não cria texto interpretativo fictício para simular relações. A relação **norma → interpretação → precedente → hipótese de aplicação → estratégia → documento** deve ser construída com documentos reais e vínculos rastreáveis nas etapas seguintes. Para a infraestrutura, o EJC já dispõe de `KnowledgeDoc`/`KnowledgeChunk`, categorias, áreas, `referencia_id` para súmulas e governança de recuperação. O próximo desenvolvimento estrutural, se necessário, deve usar issue própria e somente depois de demonstrar que os metadados existentes não bastam.

## 9. Conteúdo demonstrativo

Nenhum conteúdo jurídico fictício foi inserido. O recorte HTML existente usado nos testes é fixture técnica e permanece marcado no contexto de testes; não deve ser promovido para a base jurídica real.

## 10. Inconsistências e riscos registrados

| Achado | Classificação | Tratamento |
|---|---|---|
| O ingestor LexML recebe ementas/índices, não lei seca integral | Limitação de fonte | Mantido em `referencia_legislativa`, fora do prefixo `legislacao%`, para não enfraquecer o citation gate. |
| LexML não informa, de forma estruturada, a vigência normativa do item | Risco jurídico | Vigência permanece não verificada, salvo declaração explícita no título; exige curadoria. |
| Jurisprudência dinâmica STF/TST/TCU/CARF não possui conector integral verificado nesta rodada | Lacuna futura | Não foi criado scraper frágil; priorizar API ou fonte oficial verificável antes da implementação. |
| Execução de seed persistente depende de PostgreSQL/pgvector autorizado | Limitação operacional | Dry-run concluído; inserção e embeddings ficam pendentes do ambiente autorizado. |
| O serviço de governança usa `last_verified_at`; os nomes portugueses são requisito documental | Compatibilidade | Não criar coluna/JSON paralelo sem contrato; mapear em futura evolução compatível. |

## 11. Próximos dez lotes recomendados

A ordem considera impacto profissional, reutilização no EJC e segurança de fonte. Cada lote deve ser concluído com validação, deduplicação, conferência de fonte, teste de recuperação e registro antes do próximo.

| Ordem | Lote | Conteúdo prioritário | Critério de conclusão |
|---:|---|---|---|
| 1 | Ambiental — Autos de Infração | Lei nº 9.605/1998, PNMA, Código Florestal, licenciamento, sanções e checklist probatório | Recuperação conjunta de norma, requisitos, provas e riscos sem misturar cliente. |
| 2 | Ambiental — Responsabilidade Civil | Dano ambiental, responsabilidade objetiva, reparação, nexo e súmulas STJ ambientais | Smoke tests com fonte oficial e alerta de vigência. |
| 3 | Lei nº 14.133/2021 — Habilitação | Habilitação jurídica, fiscal, trabalhista, econômico-financeira e técnica | Matriz artigo–exigência–documento–risco para editais. |
| 4 | Lei nº 14.133/2021 — Sanções | Infrações, sanções, defesa, reabilitação, dosimetria e controle | Teste de distinção entre sanção administrativa e penalidade contratual. |
| 5 | Execução Fiscal — Defesa | Lei nº 6.830/1980, CTN, CPC subsidiário, embargos, exceção e prescrição intercorrente | Recuperação por fase processual com citações específicas e vigência revisada. |
| 6 | Imobiliário — Garantias | Lei nº 9.514/1997, Código Civil, registros, mora, consolidação e leilão | Comparação de versões e separação de dispositivos revogados. |
| 7 | LGPD — Operação jurídica | Lei nº 13.709/2018, atos/guias ANPD, bases legais, segurança e incidentes | Nenhum dado de cliente entra no corpus geral; testes de isolamento e citação. |
| 8 | Trabalhista — Vínculo e jornada | CLT, súmulas TST ativas e jurisprudência oficial validada | Súmulas históricas/quarentenadas fora da fundamentação automática. |
| 9 | Civil/Consumidor — Contratos e responsabilidade | Código Civil, CDC, súmulas STJ e precedentes oficiais selecionados | Relação norma–tese–prova–modelo com fontes estruturadas. |
| 10 | Jurisprudência superior dinâmica | STF, STJ, TST, TCU e CARF somente por APIs/portais oficiais verificáveis | Conector testado ponta a ponta, deduplicação, vigência e curadoria humana. |

## Referências

[1]: https://www.planalto.gov.br/ccivil_03/leis/l6830.htm "Planalto — Lei nº 6.830, de 22 de setembro de 1980"
[2]: https://www.planalto.gov.br/ccivil_03/leis/l9514.htm "Planalto — Lei nº 9.514, de 20 de novembro de 1997"
[3]: RUNBOOK_INGESTAO_RAG.md "EJC — Runbook de ingestão RAG"
[4]: ../backend/app/services/ingestors/planalto.py "EJC — Ingestor unificado Planalto"
[5]: ../backend/app/services/knowledge_governance.py "EJC — Governança da base de conhecimento"
[6]: https://www.lexml.gov.br/ "LexML — Rede de Informação Legislativa e Jurídica"
