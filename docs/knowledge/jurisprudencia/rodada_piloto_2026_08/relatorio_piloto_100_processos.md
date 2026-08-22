# Rodada-piloto estratificada — Betim e Contagem

## Resultado Final Direto

A rodada foi implementada com período uniforme de **01/01/2019 a 22/08/2026**, quatro estratos e meta operacional de 50 processos únicos por cidade. A coleta inicial gerou 98 candidatos; dois processos consumidores complementares de Betim, diretamente conferidos no TJMG, completaram o frame de 100 processos-alvo.

| Indicador | Resultado |
|---|---:|
| Documentos/ocorrências processuais preservados | 100 |
| Processos únicos após canonicalização | 100 |
| Processos Betim | 50 |
| Processos Contagem | 50 |
| Processos com conferência direta V4 | 13 |
| Registros apenas com metadados V2 | 36 |
| Registros em staging/outros níveis | 51 |
| Quota total pretendida | 100 |

## Resultado por estrato

| Cidade | Estrato | Quota | Únicos | V4 direto | Metadados | Pendentes | Rejeitados | Déficit V4 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Betim | Execução fiscal | 13 | 13 | 0 | 4 | 0 | 0 | 13 |
| Betim | Fraude bancária e PIX | 13 | 13 | 0 | 13 | 0 | 0 | 13 |
| Betim | Empresarial | 12 | 12 | 5 | 1 | 0 | 0 | 7 |
| Betim | Consumidor | 12 | 12 | 4 | 2 | 0 | 0 | 8 |
| Contagem | Execução fiscal | 13 | 13 | 0 | 2 | 0 | 0 | 13 |
| Contagem | Fraude bancária e PIX | 13 | 13 | 0 | 8 | 0 | 0 | 13 |
| Contagem | Empresarial | 12 | 12 | 0 | 3 | 0 | 0 | 12 |
| Contagem | Consumidor | 12 | 12 | 4 | 3 | 0 | 0 | 8 |

## Critérios e interpretação

O frame de 50 por cidade foi atingido como **conjunto de processos únicos**, após a substituição do registro de Belo Horizonte por um processo empresarial de Betim. A elegibilidade para análise de mérito exige o nível V4, com URL oficial específica, identificador íntegro, origem territorial, classe/assunto compatíveis e conteúdo decisório acessível. Os registros V2 comprovam metadados ou andamento, mas não comprovam o resultado jurídico.

A presença de sentença, acórdão, embargos ou recurso ligado ao mesmo processo não cria novo processo. Esses documentos ficam preservados na tabela documental e vinculados a `canonical_process`; para taxas de resultado, a unidade é o processo único.

Os dois candidatos 1.0000.23.255878-3/001 e 1.0000.23.159687-5/008 foram rebaixados/rejeitados nesta etapa porque suas URLs específicas retornaram “Acórdão não encontrado”. A rejeição do link não prova inexistência do processo; apenas impede sua promoção sem nova fonte oficial.

## Limitações

O conjunto ainda é uma amostra de busca pública, não um censo do TJMG. Há risco de subcobertura por CAPTCHA, sigilo, fragmentação entre PJe/Siscom/DJMG e diferenças de indexação. Não foram misturados atos administrativos ou precedentes superiores como processos locais.

As métricas de procedência, improcedência, reforma, tempo, valores ou comparação entre cidades só devem ser calculadas sobre o subconjunto V4, após auditoria final da cadeia processual e confirmação de que os estratos possuem composição equivalente. A quota de 50 por cidade não autoriza, por si só, generalização populacional ou previsão de êxito.

**Conclusão controlada:** o frame-piloto de 100 processos únicos foi estruturado; a amostra documental V4 ainda é inferior à meta em vários estratos. Até a conclusão da validação dos metadados e do preenchimento dos déficits, permanece: **AMOSTRA INSUFICIENTE PARA CONCLUSÃO JURIMÉTRICA.**

## Arquivos

- `EJC_piloto_100_processos.xlsx`: workbook operacional.
- `processos_piloto_documentos.csv/json`: todas as ocorrências e decisões.
- `processos_piloto_unicos.csv`: uma linha por processo canonicalizado.
- `resumo_estratos.csv`: controle de quotas e qualidade.
- `grafico_qualidade_piloto.png` e `grafico_meta_piloto.png`: visualizações de controle.
