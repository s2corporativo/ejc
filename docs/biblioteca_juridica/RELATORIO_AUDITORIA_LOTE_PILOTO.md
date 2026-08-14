# EJC — Auditoria de Segurança do Lote Piloto da Biblioteca Jurídica

**Status atual:** QUARENTENA / NÃO HOMOLOGADO PARA FUNDAMENTAÇÃO AUTOMÁTICA  
**Revisão de segurança:** 14/08/2026

## 1. Conclusão executiva

O relatório anterior declarava o lote piloto integralmente verificado e apto à ingestão. Essa conclusão foi revogada após auditoria do código e do corpus encontrar, no registro `JUR-CONS-000016`, URL expressamente marcada como simulada, metadados incorretos de precedente e associação equivocada de tema repetitivo.

A partir desta revisão, **nenhum documento do lote piloto deve adquirir autoridade operacional apenas por constar neste diretório ou por declarar `nivel_confiaca: ALTA`**. A aprovação no RAG depende do gate de governança do EJC e de validação individual de proveniência.

O script `backend/scripts/ingestao_biblioteca_juridica.py` passou a operar em modo fail-closed: inconsistência de fonte, metadado, classificação ou marcador de simulação encerra a validação com código de erro e impede `--execute`.

## 2. Inventário legado do lote

O lote permanece com 24 documentos canônicos distribuídos nas áreas Tributário, Ambiental, Administrativo, Licitações, Empresarial, Consumidor/Bancário, Trabalhista Empresarial e Processual Civil. O inventário serve apenas para controle de arquivos; **não equivale a certificação jurídica**.

| # | Canonical ID | Área | Tema resumido | Camada | Status após auditoria |
|---|---|---|---|---|---|
| 1 | TESE-TRIB-000001 | tributario | Monofasia PIS/COFINS | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 2 | JUR-TRIB-000002 | tributario | Prescrição tributária | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 3 | JUR-TRIB-000003 | tributario | ICMS na base PIS/COFINS | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 4 | JUR-TRIB-000004 | tributario | IPI / conceito de insumo | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 5 | JUR-TRIB-000005 | tributario | Execução fiscal / SISBAJUD | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 6 | JUR-TRIB-000006 | tributario | Compensação tributária | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 7 | TESE-AMBI-000007 | ambiental | Multa ambiental | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 8 | TESE-AMBI-000008 | ambiental | Responsabilidade civil ambiental | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 9 | TESE-ADMI-000009 | administrativo | Sanções administrativas | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 10 | JUR-ADMI-000010 | administrativo | Prescrição punitiva administrativa | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 11 | TESE-LICI-000011 | licitacoes | Habilitação e qualificação técnica | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 12 | TESE-LICI-000012 | licitacoes | Dispensa e fracionamento | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 13 | TESE-LICI-000013 | licitacoes | Pregão eletrônico | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 14 | TESE-EMPR-000014 | empresarial | Desconsideração da personalidade jurídica | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 15 | JUR-EMPR-000015 | empresarial | Recuperação judicial | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 16 | JUR-CONS-000016 | consumidor_bancario | Fraude bancária / fortuito interno | jurisprudencia_estruturada | CORRIGIDO; AINDA SUJEITO À CURADORIA RAG |
| 17 | JUR-CONS-000017 | consumidor_bancario | Fraude PIX / MED | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 18 | JUR-CONS-000018 | consumidor_bancario | Negativação indevida | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 19 | JUR-CONS-000019 | consumidor_bancario | Revisional bancária | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 20 | JUR-TRAB-000020 | trabalhista_empresarial | Responsabilidade do tomador | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |
| 21 | TESE-TRAB-000021 | trabalhista_empresarial | Prescrição trabalhista | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 22 | TESE-PROC-000022 | processual_civil | Tutelas provisórias | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 23 | TESE-PROC-000023 | processual_civil | Intimações e prazos | tese_juridica | PENDENTE DE REVALIDAÇÃO |
| 24 | JUR-PROC-000024 | processual_civil | Honorários advocatícios | jurisprudencia_estruturada | PENDENTE DE REVALIDAÇÃO |

## 3. Correção confirmada — JUR-CONS-000016

A versão anterior associava fraude bancária a tema repetitivo incorreto e continha links marcados como simulados. O registro foi reconstruído com base na fonte oficial do STJ.

Referência operacional adotada:

- **Tema Repetitivo 466/STJ**;
- REsp 1.197.929/PR e REsp 1.199.782/PR;
- Segunda Seção;
- Relator Ministro Luis Felipe Salomão;
- julgamento em 24/08/2011;
- Súmula 479/STJ como consolidação sumular da tese.

O arquivo correspondente contém as URLs oficiais utilizadas e a data da última verificação.

## 4. Regras obrigatórias para retirada da quarentena

Cada documento deverá, individualmente:

1. possuir front-matter canônico e `canonical_id` único;
2. declarar origem e autoridade compatíveis com sua natureza;
3. não conter marcador de simulação, exemplo fictício ou processo inventado;
4. quando jurisprudencial, identificar tribunal e referência verificável;
5. quando de confiança ALTA, possuir fonte oficial rastreável;
6. ter data de verificação;
7. ser ingerido inicialmente como `rag_status: pendente`;
8. passar por revisão humana antes de receber `rag_status: aprovado`;
9. permanecer sujeito aos gates de vigência e de citação do EJC.

## 5. Mudança de política

Fica revogada a regra implícita de que um lote produzido por pesquisa ou IA pode ingressar na base ativa por autodeclaração de confiança.

A hierarquia operacional passa a ser:

**fonte oficial validada → precedente validado → tese derivada → bloco argumentativo → pedido → modelo → texto gerado por IA.**

Conteúdo derivado não cria autoridade jurídica própria.

## 6. Estado do grafo

`grafico_relacoes.yaml` permanece um artefato documental. Relações que dependam de documentos ainda em quarentena não constituem prova jurídica e não devem elevar score de autoridade no retrieval até que ambos os nós relacionados estejam aprovados.

## 7. Critério para declarar o lote homologado

O lote somente poderá voltar a ser descrito como “homologado” quando a validação fail-closed terminar sem erro e todos os documentos destinados à fundamentação tiverem aprovação humana registrada no RAG.

Até lá, a descrição correta é: **corpus de trabalho em processo de revalidação**.
