# Biblioteca Jurídica Inteligente — EJC (Fonte de Verdade Versionada)

Este diretório contém a fonte de verdade versionada da Biblioteca Jurídica Inteligente do EJC, iniciada com o **Lote Piloto de 24 temas** (13/08/2026). Os arquivos-fonte em Markdown são ingeridos na base RAG de produção pelo script `backend/scripts/ingestao_biblioteca_juridica.py`, que utiliza o `upsert_documento` existente (versionamento, deduplicação por `chave_origem` e geração de embeddings).

## Estrutura

```
docs/biblioteca_juridica/
├── README.md                          (este arquivo)
├── RELATORIO_AUDITORIA_LOTE_PILOTO.md (auditoria do lote: quantitativos, índice canônico, regras de verificação)
├── grafico_relacoes.yaml              (grafo conceitual: fundamentado_por, cita, diverge_de, complementar_a)
├── quarentena/                        (documentos reprovados — vazia no piloto)
└── {area}/                            (tributario, ambiental, administrativo, licitacoes, empresarial,
    NN_tema.md                          consumidor_bancario, trabalhista_empresarial, processual_civil)
```

## Padrão de metadados (front-matter YAML obrigatório)

| Chave | Exemplo |
|---|---|
| `tipo_camada` | tese_juridica, jurisprudencia_estruturada, bloco_argumentativo, pedido_juridico, modelo_peca |
| `canonical_id` | TESE-TRIB-000001 (único no lote; TIPO-AREA-NNNNNN) |
| `origem_conteudo` | fonte_oficial, jurisprudencia_oficial, legislacao |
| `autoridade_juridica` | vinculante, jurisprudencial, persuasiva, doutrinaria |
| `authority_level` | precedente_vinculante, jurisprudencia_oficial, ... (valores de knowledge_governance) |
| `score_autoridade` | 0–100 (90 repetitivo; 95 vinculante; 100 súmula vinculante) |
| `area_juridica` | tributario, ambiental, administrativo, licitacoes, empresarial, consumidor_bancario, trabalhista_empresarial, processual_civil |
| `nivel_confiaca` | ALTA, MEDIA, BAIXA |
| `data_pesquisa` | DD/MM/AAAA |
| `gerado_por_IA` | false (conteúdo verificado) |

## Uso

```bash
# Validação (dry-run) — sem banco de dados
python3 backend/scripts/ingestao_biblioteca_juridica.py

# Ingestão real na base de produção (requer DATABASE_URL e ambiente do backend)
python3 backend/scripts/ingestao_biblioteca_juridica.py --execute
```

## Regras de governança

Nenhum documento deste diretório ingressa na base de produção sem passar pela validação do script (metadados canônicos completos, `canonical_id` único, score 0–100, confiança no vocabulário). Julgados citados exigem URL oficial da fonte e data de verificação. Documentos reprovados vão para `quarentena/` com motivo registrado no relatório de auditoria do lote. A cadeia conceitual (fonte primária → jurisprudência estruturada → tese → bloco argumentativo → pedido → modelo) é rastreada em `grafico_relacoes.yaml`.

## Lote Piloto — resumo

| Indicador | Valor |
|---|---|
| Documentos canônicos | 24 (14 teses + 10 registros de jurisprudência estruturada) |
| Confiança ALTA / MEDIA / BAIXA | 23 / 1 / 0 |
| Quarentena | 0 documentos |
