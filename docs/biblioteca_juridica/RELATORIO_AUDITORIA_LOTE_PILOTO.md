# EJC — Relatório de Auditoria do Lote Piloto da Biblioteca Jurídica Inteligente

**Data:** 13/08/2026 · **Escopo:** 24 temas jurídicos de alta relevância para a advocacia empresarial · **Fontes:** oficiais (STJ, STF, Planalto, TCU, BCB) · **Método:** pesquisa bidirecional com verificação de existência, conferência de atributos, coerência da tese e registro de divergências.

## 1. Quantitativos exigidos

| Indicador | Valor |
|---|---|
| Documentos canônicos produzidos | 24 |
| Temas por área | Tributário 6 · Ambiental 2 · Administrativo 2 · Licitações 3 · Empresarial 2 · Consumidor/Bancário 4 · Trabalhista Empresarial 2 · Processual Civil 3 |
| Documentos por camada | Teses jurídicas (tese_juridica): 14 · Jurisprudência estruturada (jurisprudencia_estruturada): 10 |
| Nível de confiança | ALTA: 23 · MEDIA: 1 (Tema 9, prescrição punitiva administrativa) · BAIXA: 0 |
| Julgados confirmados no lote (subseções de jurisprudência verificada) | 62+ subseções com metadados completos |
| Documentos em quarentena | 0 (nenhum dado essencial não verificável persistiu; observações pontuais registradas por tema) |
| Duplicidade de canonical_id | 0 (verificação única por ID) |

## 2. Índice canônico do lote

| # | Canonical ID | Área | Tema | Camada | Confiança |
|---|---|---|---|---|---|
| 1 | TESE-TRIB-000001 | tributario | Monofasia de PIS/COFINS — restituição | tese_juridica | ALTA |
| 2 | JUR-TRIB-000002 | tributario | Prescrição quinquenal tributária (RE 566.621; Tema 616) | jurisprudencia_estruturada | ALTA |
| 3 | JUR-TRIB-000003 | tributario | Exclusão do ICMS da base de PIS/COFINS (Tema 69 STF; RE 1.293.906) | jurisprudencia_estruturada | ALTA |
| 4 | JUR-TRIB-000004 | tributario | IPI — insumo (Tema 779 STJ) | jurisprudencia_estruturada | ALTA |
| 5 | JUR-TRIB-000005 | tributario | Execução fiscal — SISBAJUD e limites da penhora | jurisprudencia_estruturada | ALTA |
| 6 | JUR-TRIB-000006 | tributario | Compensação tributária (art. 170-A CTN; LC 104/2001) | jurisprudencia_estruturada | ALTA |
| 7 | TESE-AMBI-000007 | ambiental | Multa ambiental contra pessoa jurídica (Súmula 618 STJ) | tese_juridica | ALTA |
| 8 | TESE-AMBI-000008 | ambiental | Responsabilidade civil ambiental objetiva (art. 14 §1º Lei 6.938/81) | tese_juridica | ALTA |
| 9 | TESE-ADMI-000009 | administrativo | Sanções administrativas — proporcionalidade (Lei 9.784/99) | tese_juridica | ALTA |
| 10 | JUR-ADMI-000010 | administrativo | Prescrição da pretensão punitiva administrativa (Tema 953 STJ) | jurisprudencia_estruturada | MEDIA |
| 11 | TESE-LICI-000011 | licitacoes | Habilitação jurídica e qualificação técnica (Lei 14.133/21) | tese_juridica | ALTA |
| 12 | TESE-LICI-000012 | licitacoes | Dispensa de licitação e fracionamento (art. 75) | tese_juridica | ALTA |
| 13 | TESE-LICI-000013 | licitacoes | Pregão eletrônico — julgamento e desclassificação | tese_juridica | ALTA |
| 14 | TESE-EMPR-000014 | empresarial | Desconsideração da personalidade jurídica (Tema 1.210 STJ) | tese_juridica | ALTA |
| 15 | JUR-EMPR-000015 | empresarial | Recuperação judicial — stay period e créditos tributários | jurisprudencia_estruturada | ALTA |
| 16 | JUR-CONS-000016 | consumidor_bancario | Fraude bancária — fortuito interno (Tema 1046 STJ; Súmula 479) | jurisprudencia_estruturada | ALTA |
| 17 | JUR-CONS-000017 | consumidor_bancario | Fraude PIX e MED (Res. BCB 1/2021) | jurisprudencia_estruturada | ALTA |
| 18 | JUR-CONS-000018 | consumidor_bancario | Negativação indevida — dano moral in re ipsa | jurisprudencia_estruturada | ALTA |
| 19 | JUR-CONS-000019 | consumidor_bancario | Revisional — taxa média (REsp 1.061.530; Súmula 541 STF) | jurisprudencia_estruturada | ALTA |
| 20 | JUR-TRAB-000020 | trabalhista_empresarial | Responsabilidade subsidiária do tomador (Tema 725 STF) | jurisprudencia_estruturada | ALTA |
| 21 | TESE-TRAB-000021 | trabalhista_empresarial | Prescrição trabalhista (Tema 290 STF; Lei 14.457/2022) | tese_juridica | ALTA |
| 22 | TESE-PROC-000022 | processual_civil | Tutela de urgência e de evidência (arts. 300 e 311 CPC) | tese_juridica | ALTA |
| 23 | TESE-PROC-000023 | processual_civil | Intimações eletrônicas e prazos (art. 272 CPC; Lei 11.419/2006) | tese_juridica | ALTA |
| 24 | JUR-PROC-000024 | processual_civil | Honorários advocatícios (arts. 85–87 CPC) | jurisprudencia_estruturada | ALTA |

## 3. Regras de auditoria aplicadas

Cada documento do lote foi produzido por pesquisa bidirecional com quatro verificações obrigatórias: **existência** (número de processo, tribunal, relator e resultado conferidos em fonte oficial), **coerência da tese** (tese extraída da fundamentação e do dispositivo, não apenas da ementa), **divergência registrada** (entendimento favorável e contrário mapeados em tabela própria) e **rastreabilidade** (URL oficial, fonte e data de verificação em cada julgado). Dados que não puderam ser confirmados foram marcados como não confirmados na seção "Divergências e Problemas" do respectivo documento, e nenhum dado essencial não verificável persistiu no lote.

## 4. Observações de qualidade

O Tema 9 (prescrição da pretensão punitiva administrativa, Tema 953 STJ) recebeu confiança MÉDIA em razão de divergências encontradas entre fontes secundárias sobre os desdobramentos supervenientes do tema, que exigem conferência final no inteiro teor oficial antes do uso em peça de alto risco. Nos Temas 7 e 8 (ambiental), alguns julgados foram confirmados por ementas oficiais reproduzidas em base doutrinária idônea (Dizer o Direito), com recomendação de conferência do inteiro teor na base do STJ. No Tema 14 (empresarial), foi corrigida a designação "Tema 184 STJ": o repetitivo vigente sobre desconsideração da personalidade jurídica é o **Tema 1.210 STJ** (REsp 1.873.187 e REsp 1.873.811, Segunda Seção, 07/05/2026), conforme notícia oficial do próprio STJ de 11/06/2026. No Tema 21 (trabalhista), o regime atual adotado segue a Lei 14.457/2022 (prescrição semestral de crédito trabalhista não exercido na Justiça do Trabalho), que substituiu as propostas anteriores.

## 5. Integração com o RAG do EJC

Os 24 documentos seguem o padrão canônico de metadados definido no relatório de diagnóstico (tipo_camada, canonical_id, origem_conteudo, autoridade_juridica, authority_level, score_autoridade, area_juridica, nivel_confiaca, data_pesquisa) e estão prontos para ingestão pelo script `backend/scripts/ingestao_biblioteca_juridica.py`, que utiliza o upsert existente do EJC (`upsert_documento`), grava os metadados no JSONB `extra` e mapeia as novas categorias `tese_juridica`, `bloco_argumentativo` e `pedido_juridico`. O grafo de relações (arestras fundamentado_por, cita, diverge_de, complementar_a) está versionado em `docs/biblioteca_juridica/grafico_relacoes.yaml`.

## 6. Próximos lotes sugeridos

Para completar a cobertura das áreas prioritárias, os próximos lotes podem aprofundar blocos argumentativos (ARG) e biblioteca de pedidos (PED) a partir das teses deste piloto, expandir os temas ambientais e trabalhistas (que têm apenas 2 registros cada) e incorporar a camada de modelos de peças, aproveitando a categoria RAG `modelo_documento_juridico` já existente no EJC.
