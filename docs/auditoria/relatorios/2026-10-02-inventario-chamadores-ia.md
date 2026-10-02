# Inventário de chamadores de IA (I2, Fase 0)

Data: 2026-10-02. Insumo de medição do achado I2 de
`2026-10-01-auditoria-inteligencia-juridica.md`. **Somente medição**: nenhum
comportamento de produção foi alterado, nenhum chamador foi migrado, não há
allowlist.

Ferramenta: `backend/scripts/inventario_chamadores_ia.py` (AST, sem executar nem
importar o código). Reprodução: `cd backend && python scripts/inventario_chamadores_ia.py --formato ambos`.
Testes: `backend/tests/test_inventario_chamadores_ia.py`.

## Resultado (árvore `backend/app`, base `origin/main`)

| Métrica | Valor |
|---|---|
| Pontos de chamada (total) | 84 |
| Pontos dentro do núcleo (`ai_gateway.py`, `ai/core/`) | 3 |
| Pontos de chamada fora do núcleo | 81 |
| Arquivos fora do núcleo com ao menos uma chamada | 52 |
| Funções chamadoras fora do núcleo | 72 |
| Arquivos que chamam `orchestrator.run`/`run_ai_task` | 10 |
| Arquivos que chamam o gateway direto (`chat`/`executar_tarefa_ia`/`chat_agentico`) | 42 |
| Arquivos que fazem as duas coisas | 0 |

Arquivos por alvo: `ai_gateway.chat` 39, `ai_gateway.executar_tarefa_ia` 3,
`ai_gateway.chat_agentico` 1, `orchestrator.run` 9, `run_ai_task` 1.

Flags por função chamadora fora do núcleo (72 funções; valores definidos abaixo):

| Flag | sim | indireto | nao_determinado | nao |
|---|---|---|---|---|
| `usa_orquestrador` | 15 | 0 | 51 | 6 |
| `registra_log` (`registrar_ai_log`/`registrar_log_resposta`) | 22 | 4 | 38 | 8 |
| `citacoes` (`validate_citations`/citation gate) | 5 | 0 | 59 | 8 |

Das 57 funções que chamam o gateway diretamente (sem orquestrador na mesma
função): 6 não registram log nem em helper do módulo e não chamam nenhum
símbolo de `app.*` que pudesse delegar (`registra_log = nao`); 31 não têm
prova de log (`nao` ou `nao_determinado`); 52 não têm prova de gate de citações.

## Correção das estimativas do relatório de auditoria

| Estimativa do relatório (busca textual) | Medido por AST |
|---|---|
| ≈16 arquivos usam o orquestrador | **10** arquivos (9 por `orchestrator.run`, 1 por `run_ai_task`). A estimativa superestimou: contava imports, comentários e docstrings. |
| ≈35–40 chamam `ai_gateway.chat`/`executar_tarefa_ia`/`chat_agentico` direto | **42** arquivos fora do núcleo (81 pontos de chamada fora do núcleo, em 72 funções). A faixa estava levemente abaixo. |
| "Só ≈10 aplicam verificação de citações" | **5** arquivos fora do núcleo têm chamada de validação de citações **na mesma função** que chama a IA. Não equivale a "apenas 5 aplicam": a verificação pode ocorrer em função/arquivo vizinho (por isso a maioria é `nao_determinado`). |

A conclusão qualitativa de I2 (controle por chamador, não pelo núcleo) fica
**reforçada quanto à topologia**: nenhum arquivo mistura os dois caminhos e 42
arquivos chamam o gateway sem passar pelo orquestrador. O que a medição **não**
prova é a ausência de governança em cada um desses 42 (ver limitações).

## Definição das flags

- `sim`: chamada direta no corpo da função chamadora (incluindo funções aninhadas).
- `indireto`: a função chama outra função do mesmo módulo que contém a chamada.
- `nao_determinado`: sem prova no corpo, mas a função chama símbolos de `app.*`
  (exceto `app.models`/`app.schemas`) ou usa despacho dinâmico, que poderiam delegar.
- `nao`: ausente no corpo e sem chamadas a `app.*` que pudessem delegar.

Chamadas de citações reconhecidas: `validate_citations`, `validar_citacoes`,
`verificar_citacoes`, `aplicar_gate_hitl`, `avaliar_bloqueantes`,
`avaliar_bloqueantes_pertinencia`. A função chamadora é a função/método mais
externo que contém a chamada (`<modulo>` para chamadas fora de função).

## Limitações do AST

- Resolução por imports e re-exports (até 3 saltos). Não resolve atribuição a
  variável (`f = ai_gateway.chat; f(...)`), `getattr`, `importlib`, callbacks
  passados como argumento, nem `SingleAICoreOrchestrator()` instanciado fora do
  singleton `orchestrator`: chamadas assim **não aparecem** no inventário.
- Flags medem presença sintática de chamada, não fluxo: uma chamada de log/citação
  em ramo morto ou depois do `return` conta como `sim`; log/citação feitos em outra
  função (caller, middleware, helper em outro módulo) aparecem como
  `nao_determinado`.
- Não classifica a saída (jurídica, administrativa, estruturada), HITL nem
  `entidades`; isso exige análise de fluxo (Fase 1/2).
- Não cobre o Manus (`manus_client.py`), que não passa pelo gateway (LB1), nem
  chamadas HTTP diretas a provedores.
- Comentários e docstrings são ignorados (vantagem sobre grep). Testes e scripts
  fora de `backend/app` não são varridos.
- Referência cruzada com `grep`: dos 88 arquivos que citam `ai_gateway`/orquestrador
  textualmente, os que não aparecem no inventário são importadores sem chamada
  (config, modelos, registries, comentários), verificados por amostragem; um caso
  só aparece por re-export (`ai_service.gw_chat`, em `ai_core_hardening_patch.py`).

## Tabela completa

| Arquivo:linha | Funcao | Alvo | Orquestrador | Log | Citacoes |
|---|---|---|---|---|---|
| `app/core/veredito_ia.py:241` | `VereditoIA.predict_success` | `ai_gateway.chat` | nao_determinado | sim | sim |
| `app/eval/compare_providers.py:58` | `groundedness_judge` | `ai_gateway.chat` | nao | nao | nao |
| `app/eval/compare_providers.py:100` | `avaliar_provider` | `ai_gateway.chat` | nao_determinado | nao_determinado | sim |
| `app/eval/run_eval.py:100` | `_groundedness_judge` | `ai_gateway.chat` | nao | nao | nao |
| `app/eval/run_eval.py:138` | `_avaliar_caso` | `ai_gateway.executar_tarefa_ia` | nao_determinado | nao_determinado | sim |
| `app/eval/run_gold_ia.py:230` | `_juiz_llm` | `ai_gateway.chat` | nao | nao | nao |
| `app/modules/dpt360/intelligence_service.py:83` | `run_dpt_action` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/ai.py:890` | `assistente_estrategico` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/routers/ai.py:1005` | `dual_ia` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/routers/ai.py:1042` | `dual_ia` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/routers/ai.py:1223` | `motor_estrategia` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/routers/ai.py:1353` | `_ia` | `ai_gateway.chat` | nao | nao | nao |
| `app/routers/ai_core.py:125` | `core_chat` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/ai_core.py:143` | `core_task` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/ai_core.py:163` | `core_analyze` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/ai_core.py:184` | `core_generate` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/ai_core.py:201` | `core_report` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/ai_tools.py:159` | `executar_ia` | `ai_gateway.executar_tarefa_ia` | nao_determinado | nao_determinado | nao_determinado |
| `app/routers/analise_bancaria.py:107` | `_analisar` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/routers/cerebro.py:38` | `analise_estrategica` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/clients.py:814` | `ia_analise_cliente` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/conteudo.py:69` | `gerar_faq` | `ai_gateway.chat` | nao_determinado | indireto | nao_determinado |
| `app/routers/conteudo.py:88` | `gerar_glossario` | `ai_gateway.chat` | nao_determinado | indireto | nao_determinado |
| `app/routers/defesas_revisoes.py:301` | `analisar` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/defesas_revisoes_avancado.py:182` | `_executar_ia` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/entrada_universal.py:241` | `_analisar_ia` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/routers/honorarios_oab.py:136` | `estimar` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/routers/ia_especializada.py:116` | `consultar` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/routers/intake.py:140` | `_identificar_area` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/routers/intake.py:236` | `_estrategia_recomendada` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/routers/intelligence.py:66` | `analise_impacto` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/routers/jurimetria.py:411` | `analise_prospectiva_qualitativa` | `orchestrator.run` | sim | nao | nao |
| `app/routers/jurisprudencia_interna.py:232` | `classificar_com_ia` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/routers/prompts_juridicos.py:296` | `executar_prompt` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/routers/provas.py:421` | `sugerir_provas_faltantes` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/routers/qualidade.py:79` | `consistencia` | `ai_gateway.chat` | nao_determinado | indireto | nao_determinado |
| `app/routers/qualidade.py:96` | `simular_adversario` | `ai_gateway.chat` | nao_determinado | indireto | nao_determinado |
| `app/routers/score_juridico.py:100` | `calcular_score` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/routers/teses.py:596` | `sugerir_teses_ia` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/routers/teses.py:744` | `_gerar_teses` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/ai/adversarial.py:331` | `criticar_peca` | `ai_gateway.chat` | nao_determinado | nao_determinado | sim |
| `app/services/ai/agent/loop.py:431` | `rodar_agente` | `ai_gateway.chat_agentico` | nao_determinado | sim | nao_determinado |
| `app/services/ai/agent/loop.py:447` | `rodar_agente` | `ai_gateway.chat_agentico` | nao_determinado | sim | nao_determinado |
| `app/services/ai/agent/tools/escrita.py:70` | `gerar_minuta_peca` | `ai_gateway.executar_tarefa_ia` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/ai/core/capacidades.py:188` | `_executar` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/services/ai/core/orchestrator.py:302` | `SingleAICoreOrchestrator.run` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/ai/core/skill_registry.py:81` | `_h_call_model` | `ai_gateway.chat` | nao | nao | nao |
| `app/services/ai/pertinencia.py:360` | `avaliar_citacao` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/ai_core_hardening_patch.py:162` | `_instalar_hyde_local_fail_closed` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/ai_service.py:427` | `_hyde_expandir` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/ai_service.py:708` | `_gateway_text` | `ai_gateway.chat` | nao | nao | nao |
| `app/services/ai_skill_service.py:257` | `executar_skill` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/ai_skill_service.py:432` | `executar_skill_documento_longo` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/ai_skill_service.py:483` | `executar_skill_documento_longo` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/analise_estrategica.py:344` | `analisar_caso` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/anexos_service.py:154` | `gerar_legenda_ia` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/anexos_service.py:509` | `gerar_razoes_juridicas` | `ai_gateway.chat` | nao_determinado | sim | sim |
| `app/services/case_intel.py:87` | `_gateway_json` | `ai_gateway.chat` | nao | nao | nao |
| `app/services/checklist_ia.py:89` | `gerar_checklist_ia` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/deep_research_service.py:104` | `decompor_tese` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/deep_research_service.py:232` | `executar_deep_research` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/document_classifier.py:146` | `classificar_documento` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/documento_service.py:526` | `extrair_e_analisar` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/documento_service.py:707` | `_sugerir_honorarios` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/documento_service.py:758` | `sugerir_tipo` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/dossie_service.py:283` | `gerar_dossie` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/ficha_triagem_service.py:204` | `pre_preencher` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/ia_defensiva_service.py:338` | `executar_ia_defensiva` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/legal_brain/shadow.py:32` | `run_shadow_ai_task` | `orchestrator.run` | sim | nao_determinado | nao_determinado |
| `app/services/legal_chat_service.py:411` | `enviar_mensagem` | `run_ai_task` | sim | nao_determinado | nao_determinado |
| `app/services/legal_chat_service.py:621` | `_extrair_estado_automatico` | `run_ai_task` | sim | nao | nao |
| `app/services/matriz_teses_service.py:197` | `decompor_questoes` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/motor_peca_service.py:529` | `motivacao_pecas_ia` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/movimento_ia.py:58` | `traduzir_movimento` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/peca_service.py:834` | `gerar_peca_pipeline` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/peca_service.py:882` | `gerar_peca_pipeline` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/peca_service.py:949` | `gerar_peca_pipeline` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/peca_service.py:974` | `gerar_peca_pipeline` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/peca_service.py:1004` | `gerar_peca_pipeline` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/peca_service.py:1124` | `gerar_peca_pipeline` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/peca_service.py:1195` | `gerar_peca_pipeline` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/triagem_entrevista_service.py:168` | `analisar_relato` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
| `app/services/validador_juridico_service.py:554` | `validar_rascunho_juridico` | `ai_gateway.chat` | nao_determinado | nao_determinado | nao_determinado |
| `app/services/visual_law.py:93` | `gerar_diagrama` | `ai_gateway.chat` | nao_determinado | sim | nao_determinado |
