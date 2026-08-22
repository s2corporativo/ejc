# Rodada-piloto de jurisprudência — Betim e Contagem

## Resultado Final Direto

Este lote contém o frame de **100 processos únicos**, com 50 atribuídos a Betim e 50 a Contagem, no período de 01/01/2019 a 22/08/2026. Os estratos são Execução fiscal, Fraude bancária e PIX, Empresarial e Consumidor.

Somente os registros classificados como **V4_DIRETO** foram transformados em JSONL de seed. O seed contém 13 registros e entra em **quarentena de curadoria**, não em aprovação automática para citação. O conteúdo é factual e não fictício, mas a promoção para uso citável exige revisão no fluxo de governança do RAG.

## Camadas

| Camada | Quantidade | Destino |
|---|---:|---|
| Processos únicos do frame | 100 | `processos_piloto_unicos.csv` |
| Documentos/ocorrências | 100 | `processos_piloto_documentos.csv` |
| V4 direto | 13 | `backend/seeds/.../processos_v4.jsonl` |
| Metadados V2 | 36 | Não entram no seed até documento decisório |
| Staging/outros | 51 | Não entram no seed até saneamento e conferência |

## Regras

Processo originário e recurso ligado são vinculados por `canonical_process`; não se contam como processos diferentes. Precedentes superiores e atos administrativos não são promovidos como decisões locais. O seed usa `chave_origem` canônica `julgado:TJMG:<dígitos>` para permitir reexecução idempotente.

## Execução

O seed pode ser executado pelo script `backend/scripts/seed_jurisprudencia_ejc.py`. Por padrão, os documentos permanecem em quarentena (`rag_status=quarentena`) e não devem ser usados automaticamente para citação antes da revisão de governança.

## Próximas validações

Os 36 registros V2 devem ser encaminhados à conferência do inteiro teor, dispositivo e trânsito/resultado. Os 51 itens em staging devem passar por correção de identificador, confirmação de origem, teste de URL oficial, verificação de duplicidade e reclassificação. A quota de 50 por cidade é um frame operacional; não constitui, por si, amostra jurimétrica de mérito.
