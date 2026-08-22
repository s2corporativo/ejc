# Roteiro de validação documental pós-piloto

## 1. Fechar o denominador correto

Usar `canonical_process` como unidade de processo. Manter cada sentença, decisão, acórdão, embargos, agravo e recurso em tabela de documentos relacionada ao processo-base. Antes de calcular resultados, excluir sequências duplicadas, recursos fora da origem territorial e registros cuja classe não corresponda ao estrato.

## 2. Fila dos 36 registros V2

A ordem de conferência deve ser: (a) acessar a URL oficial específica; (b) confirmar número CNJ e comarca de origem; (c) localizar o documento decisório; (d) extrair ementa/dispositivo; (e) registrar resultado como favorável, desfavorável, parcial, acordo, extinção ou neutro; (f) registrar recurso e trânsito; e (g) promover somente após revisão.

V2 confirma metadados ou andamento. Não confirma, sozinho, a tese ou o resultado. Se o documento decisório não estiver acessível, o item continua V2 ou é rebaixado para pendente.

## 3. Fila dos 51 em staging

Cada item deve receber uma causa de pendência: URL genérica, identificador incompleto, origem territorial não demonstrada, classe incompatível, duplicidade, sigilo, ausência de documento ou resultado não localizado. A equipe deve corrigir a causa específica, não apenas tentar nova busca com o mesmo termo.

## 4. Protocolo de dupla revisão

Revisar independentemente 10% de cada cidade/estrato. Divergências devem ser resolvidas por terceiro revisor e registradas. O registro final precisa manter fonte, data/hora de acesso, URL, hash do documento quando disponível e decisão de inclusão/exclusão.

## 5. Critério de promoção para RAG

Promover somente registros com V4: fonte oficial específica, identificador íntegro, origem local, classe/assunto compatíveis, documento acessível, resultado explicitamente extraído, ausência de duplicidade e revisão humana. Até a promoção, manter `rag_status=quarentena`.

## 6. Métricas liberadas somente depois

Após concluir a validação, calcular por cidade e estrato: processos encontrados, únicos, V4, resultados, recursos, trânsito, duração quando confiável, valores expressamente documentados e taxa de recuperação. Não calcular taxa populacional, previsão de êxito ou ranking de vara sem denominador oficial e desenho comparável.
