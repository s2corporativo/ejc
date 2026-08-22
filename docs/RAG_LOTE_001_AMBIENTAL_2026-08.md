# Lote 001 — Direito Ambiental e Autos de Infração

**Status:** implementado em branch isolada, validado localmente e ainda não mesclado.

**Rastreamento:** Issue [#1243](https://github.com/S2corporativo/ejc/issues/1243). O lote foi desenvolvido a partir do commit validado do Lote P0, sem alterar a branch principal nem a produção.

## Resultado executivo

O Lote 001 acrescenta ao catálogo unificado do ingestor Planalto três diplomas federais diretamente relacionados à apuração e à cobrança de infrações administrativas ambientais: o Decreto nº 6.514/2008, a Lei nº 9.873/1999 e a Lei Complementar nº 140/2011. As três URLs foram confirmadas em fontes oficiais do Governo Federal e passam a utilizar o mesmo caminho de ingestão, a mesma chave global `planalto:<slug>`, o mesmo mecanismo de versionamento e o mesmo conjunto de testes já utilizado pelos demais diplomas.

A implementação também corrigiu, de forma restrita, uma incompatibilidade do parser com páginas antigas do Planalto que separam o ordinal superscrito em linhas distintas, como `Art. 1` seguido de `o`. A correção recompõe somente esse padrão inequívoco, preserva o texto oficial e permite a divisão por artigo sem criar um parser paralelo. O caso foi coberto por teste de regressão para artigo comum e artigo com sufixo.

## Fontes e delimitação normativa

| Identificador | Diploma ou fonte | Papel no lote | Situação |
|---|---|---|---|
| `d6514` | Decreto nº 6.514/2008 | Infrações, sanções administrativas ambientais e processo administrativo federal | Inserido no catálogo Planalto |
| `l9873` | Lei nº 9.873/1999 | Ação punitiva federal, prescrição e prescrição intercorrente no âmbito federal | Inserido no catálogo Planalto |
| `lcp140` | Lei Complementar nº 140/2011 | Cooperação federativa, licenciamento e atuação supletiva/subsidiária | Inserido no catálogo Planalto |
| `l9784` | Lei nº 9.784/1999 | Processo administrativo federal geral | Já existente no catálogo |
| `pnma` | Lei nº 6.938/1981 | Política Nacional do Meio Ambiente e instrumentos administrativos | Já existente no catálogo |
| `lca` | Lei nº 9.605/1998 | Sanções penais e administrativas ambientais | Já existente no catálogo |
| `cflo` | Lei nº 12.651/2012 | Proteção da vegetação nativa, APP e Reserva Legal | Já existente no catálogo |
| CONAMA 001/1986, 237/1997, 357/2005 e 430/2011 | Resoluções ambientais | Licenciamento, EIA/RIMA, classificação de águas e efluentes | Não inseridas neste catálogo; dependem de fluxo próprio para PDFs e controle de vigência |
| IN Conjunta MMA/IBAMA/ICMBio nº 1/2021 e IN ICMBio nº 9/2023, compilada em 2026 | Procedimento institucional sancionador | Rito interno de IBAMA e ICMBio | Não inseridas no Planalto; dependem de corpus institucional versionado |
| Súmula 467/STJ, Temas 1.159, 1.204 e 1.294 e demais precedentes | Jurisprudência qualificada | Prescrição, responsabilidade administrativa e temas ambientais | Não convertida em lei seca; deve entrar em corpus jurisprudencial individualizado |

A separação acima é deliberada. Resoluções, instruções normativas, orientações administrativas e jurisprudência não foram artificialmente convertidas em entradas de legislação do Planalto. Cada documento deve conservar o órgão emissor, o identificador, a data, a URL, a situação de vigência e, quando aplicável, o inteiro teor e o precedente relacionado.

## Alteração técnica

O catálogo `CATALOGO` do módulo `backend/app/services/ingestors/planalto.py` passou de 38 para 41 entradas. Foram adicionados os slugs `d6514`, `l9873` e `lcp140`, com as URLs oficiais abaixo:

| Slug | URL oficial | Categoria |
|---|---|---|
| `d6514` | https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2008/decreto/d6514.htm | `ambiental` |
| `l9873` | https://www.planalto.gov.br/ccivil_03/leis/l9873.htm | `ambiental` |
| `lcp140` | https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp140.htm | `ambiental` |

Não houve alteração de schema, endpoint, autenticação, modelo RAG, estratégia de embeddings, chave de deduplicação ou job concorrente. O wrapper `backend/scripts/seed_legislacao.py` continua delegando ao catálogo único.

## Validação do parser e dry-run

O dry-run foi executado com as três páginas oficiais cacheadas localmente, sem escrita em PostgreSQL, sem criação de embeddings persistentes e sem alteração de produção.

| Fonte | Artigos reconhecidos | Chunks | Caracteres | Resultado |
|---|---:|---:|---:|---|
| Decreto nº 6.514/2008 | 170 | 179 | 151.610 | Aprovado |
| Lei nº 9.873/1999 | 10 | 5 | 4.211 | Aprovado após correção do ordinal superscrito |
| Lei Complementar nº 140/2011 | 22 | 28 | 24.206 | Aprovado |

A Lei nº 9.873/1999 expôs um comportamento específico do HTML antigo do Planalto: o marcador `Art. 1º` aparece como `Art. 1` e `o` em linhas separadas, e o marcador `Art. 1º-A` pode separar também o sufixo. O parser agora recompõe somente essas sequências inequívocas antes da validação do cabeçalho. O corpo permanece verbatim, sem resumo ou reescrita.

## Gates executados

| Gate | Resultado |
|---|---:|
| Teste focado `tests/test_seed_legislacao.py` | 30 aprovados, 3 ignorados |
| Dry-run `d6514,l9873,lcp140` | 3 aprovados, 0 falhas |
| Ruff nos arquivos alterados | Aprovado |
| Compilação dos arquivos alterados | Aprovada |
| `git diff --check` | Aprovado |
| Ajuda do wrapper de seed | Aprovada |
| Suíte completa do backend | 5.855 aprovados, 273 ignorados, 34 warnings, 79 subtestes aprovados |

O conjunto de testes de banco real permanece condicionado à disponibilidade de PostgreSQL/pgvector autorizado. A validação atual demonstra a integridade do catálogo, do parser, da divisão por artigo, do chunking e do caminho de seed, mas não declara ingestão persistente em produção.

## Conclusão operacional

O Lote 001 está tecnicamente pronto para revisão no PR desta branch. A execução persistente deverá ocorrer somente em ambiente autorizado, com migrações já aplicadas, credencial de banco adequada e registro da execução em `fontes_ingestao`. Depois da ingestão, devem ser executados os smoke tests de cobertura, citação e recuperação do EJC. O próximo lote não deve ser iniciado como implementação até a confirmação desses resultados.

## Referências

[1]: https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2008/decreto/d6514.htm "Decreto nº 6.514/2008 — Planalto"

[2]: https://www.planalto.gov.br/ccivil_03/leis/l9873.htm "Lei nº 9.873/1999 — Planalto"

[3]: https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp140.htm "Lei Complementar nº 140/2011 — Planalto"

[4]: https://www.planalto.gov.br/ccivil_03/leis/l9784.htm "Lei nº 9.784/1999 — Planalto"

[5]: https://www.planalto.gov.br/ccivil_03/leis/l6938.htm "Lei nº 6.938/1981 — Planalto"

[6]: https://www.planalto.gov.br/ccivil_03/leis/l9605.htm "Lei nº 9.605/1998 — Planalto"

[7]: https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm "Lei nº 12.651/2012 — Planalto"

[8]: https://www.ibama.gov.br/sophia/cnia/legislacao/MMA/RE0237-191297.PDF "Resolução CONAMA nº 237/1997 — arquivo institucional IBAMA"

[9]: https://conama.mma.gov.br/?option=com_sisconama&task=arquivo.download&id=450 "Resolução CONAMA nº 357/2005 — CONAMA"

[10]: https://www.ibama.gov.br/component/legislacao/?view=legislacao&legislacao=138939 "IN Conjunta MMA/IBAMA/ICMBio nº 1/2021 — IBAMA"

[11]: https://www.gov.br/icmbio/pt-br/acesso-a-informacao/autuacoes-ambientais/infracoes-ambientais/normativas/instrucao-normativa-no-9-gabin-icmbio-de-23-de-agosto-de-2023 "IN nº 9/GABIN/ICMBio/2023, compilada em 2026 — ICMBio"

[12]: https://scon.stj.jus.br/SCON/sumstj/doc.jsp?livre=%22467%22+INPATH%28NUM%29&b=SUMU&p=false&l=10&i=1&operador=AND&ordenacao=-@NUM "Súmula 467/STJ"

[13]: https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias/2025/30122025-Decreto-federal-nao-pode-embasar-prescricao-intercorrente-em-processos-administrativos-estaduais-e-municipais.aspx "Tema 1.294/STJ — notícia oficial"

[14]: https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias/2023/03122023-Cidadania-ambiental-a-construcao-do-futuro-sustentavel-tambem-passa-pela-jurisprudencia-do-STJ.aspx "Jurisprudência ambiental — notícia institucional do STJ"
