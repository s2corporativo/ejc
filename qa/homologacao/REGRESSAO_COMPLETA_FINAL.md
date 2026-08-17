# Regressão Completa de Homologação Final — EJC

**Data/hora:** 16/08/2026 23:54 (GMT-3)
**Branch:** `homologacao-m07-2026-08-16` (commit local HEAD), publicada no remoto `s2corporativo/ejc`
**Método:** todas as 36 baterias reexecutadas em sequência contra o servidor uvicorn local (porta 8000), com dados sintéticos `EJC_QA_*`. Nenhuma operação destrutiva.

| Módulo | Cenários | PASS | FAIL | N/A | Resultado |
|---|---|---|---|---|---|
| M01 | ? |  | 0 |  | HOMOLOGADO |
| M03 | ? |  | 0 |  | HOMOLOGADO |
| M04 | 65 | 65 | 0 | 0 | HOMOLOGADO |
| M05 | 6 | 6 | 0 | 0 | HOMOLOGADO |
| M06 | 24 | 24 | 0 | 0 | HOMOLOGADO |
| M07 | 35 | 35 | 0 | 0 | HOMOLOGADO |
| M08 | 31 | 31 | 0 | 0 | HOMOLOGADO |
| M09 | 28 | 28 | 0 | 0 | HOMOLOGADO |
| M10 | 27 | 27 | 0 | 0 | HOMOLOGADO |
| M11 | 163 | 163 | 0 | 0 | HOMOLOGADO |
| M12 | 22 | 22 | 0 | 0 | HOMOLOGADO |
| M13 | 28 | 28 | 0 | 0 | HOMOLOGADO |
| M14 | 33 | 33 | 0 | 0 | HOMOLOGADO |
| M15 | 36 | 36 | 0 | 0 | HOMOLOGADO |
| M16 | 58 | 58 | 0 | 0 | HOMOLOGADO |
| M17 | 53 | 53 | 0 | 0 | HOMOLOGADO |
| M18 | 27 | 27 | 0 | 0 | HOMOLOGADO |
| M19 | 18 | 18 | 0 | 0 | HOMOLOGADO |
| M20 | 35 | 35 | 0 | 0 | HOMOLOGADO |
| M21 | ? |  | ? |  | FALHA |
| M22 | ? |  | ? |  | FALHA |
| M23 | ? |  | ? |  | FALHA |
| M24 | ? |  | 0 |  | HOMOLOGADO |
| M25 | ? |  | 0 |  | HOMOLOGADO |
| M26 | 41 | 41 | 0 | 0 | HOMOLOGADO |
| M27 | 25 | 22 | 0 | 3 | HOMOLOGADO |
| M28 | 29 | 27 | 0 | 2 | HOMOLOGADO |
| M29 | 22 | 20 | 0 | 2 | HOMOLOGADO |
| M30 | 31 | 29 | 0 | 2 | HOMOLOGADO |
| M31 | 26 | 26 | 0 | 0 | HOMOLOGADO |
| M32 | 33 | 33 | 0 | 0 | HOMOLOGADO |
| M33 | 44 | 43 | 0 | 1 | HOMOLOGADO |
| M34 | 27 | 26 | 0 | 1 | HOMOLOGADO |
| M35 | 18 | 18 | 0 | 0 | HOMOLOGADO |
| M36 | 23 | 23 | 0 | 0 | HOMOLOGADO |

**Duração total:** 2069s

## Interpretação

* HOMEMOLOGADO: bateria executou e retornou exit 0 (sem cenários FAIL).
* Os cenários N/A-PROVADO documentados nos relatórios individuais (endpoints dependentes de IA externa desligada no sandbox) permanecem válidos.
* Qualquer linha com FAIL exige correção e rerun do módulo antes de decretar a homologação final.

**Conclusão preliminar:** HÁ MÓDULOS COM FALHA — revisar logs em qa/homologacao/regressao_*.log

