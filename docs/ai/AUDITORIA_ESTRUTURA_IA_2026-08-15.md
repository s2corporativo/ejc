# Auditoria Integral da Estrutura de IA — a IA como advogado de excelência

**Data:** 15 de agosto de 2026
**Base analisada:** `main` no commit `a89e31d` (branch de auditoria `claude/auditoria-ia-juridica-c2tbf2`)
**Issue:** #1150 · **Auditoria anterior:** `AUDITORIA_NUCLEO_IA_CONHECIMENTO_2026-07-19.md` (+ adendo)
**Natureza:** somente leitura — nenhum código foi alterado; achados viram Issues próprias.

## 0. Método e escopo

Cinco frentes auditadas em paralelo, com leitura direta do código (evidência arquivo:linha):
(A) gateway/provedores/kill-switch/PII; (B) núcleo canônico (`services/ai/core/`);
(C) qualidade jurídica dos system prompts (`services/system_prompts/`, 28 ramos);
(D) RAG, base de conhecimento e gate de citações; (E) fluxos ponta a ponta (peça, chat,
governança) e cobertura de testes. Os achados P0 e os P1 estruturais foram **reconferidos
manualmente na thread principal** (prazos.py, honorarios.py, celery_app/ai_gateway,
legal_docs.py, ai.py, agent_registry/intent_classifier/response_validator, flags de config,
`_formatar_fontes`); os demais mantêm a evidência apurada pelas frentes.

PRs ativos considerados (nenhum arquivo deles foi tocado): #1140 (branch protection),
#1143 (endurecimento da biblioteca jurídica do RAG), #1148 (auditoria pós-Manus +
reclassificação de 23 documentos simulados + religamento do CI).

---

## 1. Conclusão executiva

A **arquitetura de governança** da IA do EJC é madura e, nos pontos críticos, fail-closed:
HITL estrutural que nenhuma flag desliga (`is_rascunho=True` incondicional), gate de
citações com política default `bloquear` e override auditado, sanitização/pseudonimização
de PII em barreira única antes de provedor externo, filtro de corpus fictício em todas as
pernas da busca, monitoramento de ingestão por **resultado** (a armadilha DJEN foi
corrigida). As correções P0 de julho continuam de pé no processo web.

O problema central desta auditoria está no **conteúdo jurídico**, não na arquitetura:
o prompt de prazos — justamente a função vendida como "precisão absoluta" — instrui a IA
com **três regras de contagem revogadas** (CLT e JEC em dias corridos; contagem IBAMA sem
fonte), e o prompt de honorários cita três dispositivos errados/revogados do EOAB/CED.
Um sistema que se propõe a trabalhar como advogado de excelência não pode ensinar ao
modelo direito revogado com aparência de fonte.

Além disso, três lacunas estruturais diluem a exigência de excelência:
1. o **caminho mais comum do chat** (agente default `CaseAgent`) produz análise de mérito
   com `exige_fonte=False` — pulando verificação de citações e o carimbo "SEM BASE
   VERIFICÁVEL";
2. a revisão HITL que aprova peça **não exige papel de advogado** e permite auto-revisão
   pelo autor do log;
3. o worker Celery **não carrega o patch fail-closed** do kill-switch (caminho real de
   bypass) nem a telemetria de provedores.

A dívida 5.2 de julho (migrar geração de peça e análise estratégica para o orquestrador
canônico) segue parada nas duas prioridades mais altas — as superfícies novas nasceram no
lugar certo, mas os legados de maior risco continuam fora do `ResponseValidator`.

---

## 2. Achados P0 — conteúdo jurídico errado entregue como fonte

### P0-1. `prazos.py` ensina contagem trabalhista revogada (dias corridos)
- `backend/app/services/system_prompts/prazos.py:8` — "CLT art. 775 = corridos".
  **Errado desde a Reforma Trabalhista** (Lei 13.467/2017): o art. 775 vigente determina
  contagem em **dias úteis**. O prompt cita como fonte o próprio artigo que diz o contrário.
- `prazos.py:15` — "Recurso Ordinário TRT→TST 8 corridos (CLT 895); ED CLT 5 corridos
  (CLT 897-A)". Os prazos são de 8 e 5 dias **úteis** (art. 775 pós-2017).
- Efeito: todo cálculo trabalhista sai com data fatal antecipada. Conservador, porém
  juridicamente errado, assinado com fonte — mina a confiança no módulo e contamina o
  JSON de saída (`tipo_dias`, `base_legal_prazo`).

### P0-2. `prazos.py` ensina contagem de JEC revogada
- `prazos.py:9` — "JEC (Lei 9.099/95) = corridos". A Lei 13.728/2018 inseriu o
  **art. 12-A** na Lei 9.099/95: contagem **em dias úteis** nos Juizados Cíveis.
  Errado há ~8 anos; contradiz o próprio `juizados.py`, que manda confirmar a norma vigente.

*Nota:* o repositório tem cálculo determinístico de prazos parametrizado
(`prazo_dias_uteis`, PR #1146) — o erro aqui é no **prompt da IA**, que responde por cima
disso quando consultada. Correção é pontual (2 linhas + teste de invariante do prompt).

## 3. Achados P1

### P1-1. Contagem IBAMA "úteis" sem fonte, na direção perigosa
- `prazos.py:8-9` e `system_prompts/ambiental.py:11` — "IBAMA/Administrativo = úteis
  (Dec. 6.514/2008 art. 71)". O art. 71 fixa 20 dias mas **não diz "úteis"**; a regra
  subsidiária (Lei 9.784/1999, art. 66) é de dias **contínuos**. Aqui o erro alonga o
  prazo → risco de **perder a defesa por intempestividade**. Exige confirmação em fonte
  oficial; se "úteis" tiver base (norma específica), a fonte precisa constar no prompt.

### P1-2. `honorarios.py` cita três dispositivos errados/revogados
- `honorarios.py:11` — "PROIBIÇÕES (CED arts. 38/39)": referência ao CED de **1995,
  revogado**; no CED vigente (Res. CFOAB 02/2015) a matéria está nos arts. 48-50.
- `honorarios.py:14` — titularidade da sucumbência atribuída ao "art. 22 §4º EOAB";
  o dispositivo correto é o **art. 23** da Lei 8.906/94.
- `honorarios.py:15` — vedação de garantia de resultado fundada no "art. 34, XX EOAB";
  o inciso XX trata de **locupletamento**; o fundamento correto é o CED e o Provimento
  205/2021 (como cita, corretamente, `modo_executivo.py:29`).

### P1-3. Lei 14.905/2024 (juros/correção) ausente de todo o pacote de prompts
- `civel.py:31`, `contratual.py:30`, `padrao_ouro.py:33-34` exigem pedidos com índice de
  correção e termo de juros, mas nenhum prompt menciona a regra supletiva vigente desde
  ago/2024: **IPCA para correção e SELIC−IPCA para juros** (CC arts. 389 e 406 reformados).
  Peça condenatória tende a sair no padrão antigo (1% a.m./art. 161 CTN) sem alerta.

### P1-4. Agente default do chat produz mérito sem exigência de fonte
- `services/ai/core/agent_registry.py:30` — default `exige_fonte=False`; `CaseAgent`
  ("fatos, teses, riscos") não o sobrepõe, tampouco `EJCCoordinatorAgent` e `FinanceAgent`.
- `intent_classifier.py:281-282` — **CaseAgent é o fallback do classificador** e o alvo de
  `task_type="chat"`: o caminho mais comum do chat do núcleo responde tese jurídica sem
  verificação de citações — `response_validator.py:82` só roda o citation_check quando
  `exige_fonte=True`, e o carimbo "SEM BASE VERIFICÁVEL" também depende da flag.
- HITL e detecção de promessa continuam valendo; o que falha é o princípio "toda tese
  precisa de fonte". Correção: `exige_fonte=True` nesses agentes, ou validar citações
  sempre que a resposta contiver citação, independentemente da flag.

### P1-5. Revisão/aprovação de peça sem piso de papel "advogado" + auto-revisão
- `routers/legal_docs.py:596` (`/revisar`), `:632` (`/aprovar`), `:688`
  (`/conferir-e-assinar`) — apenas `get_current_user` + acesso ao caso; `requer_advogado`
  só em "marcar protocolada" (`:540`) e `/protocolo` (`:883`). Um interno não-advogado
  pode registrar `human_reviewed=True` e aprovar a peça (a revisão do Provimento OAB
  205/2021 é ato de advogado).
- `routers/ai.py:210` — `PATCH /ai/logs/{id}/hitl` permite ao **próprio autor** marcar
  `revisado/aplicado` (mesmo padrão em `ia_defensiva.py:145`). Recomenda-se piso de
  advogado e segregação autor≠revisor para peças. Não há teste cobrindo esse invariante.

### P1-6. Worker Celery roda sem o hardening fail-closed do kill-switch
- `core/celery_app.py:26-29` importa só os módulos de tasks; `event_subscribers` (que
  instala o resolver fail-closed e a telemetria) é importado apenas em `main.py:188`.
- `ai_gateway.py:762-764` mantém o fallback sintético `[("groq", model_override)]` sem
  checar elegibilidade. Cenário concreto: worker com `AI_EXTERNAL_PROVIDERS_ALLOWED=false`
  + `GROQ_API_KEY` presente + Ollama indisponível → chamada real ao Groq (conteúdo
  sanitizado, mas soberania de dados violada). Bônus negativo: chamadas de IA do worker
  não aparecem em `/ia-governanca/provedores`.
- Correção dupla: instalar o hardening no boot do worker **e** internalizar o filtro no
  próprio `_resolver_cadeia`, aposentando o patch transitório (dívida 5.1).

### P1-7. Julgado inventado "estruturalmente perfeito" passa sem confirmação externa
- `citation_gate.py:176` chama `verificar_jurisprudencia` **sem** `consultar_datajud=True`
  (default False em `verificador_jurisprudencia.py:414`). Número CNJ com DV válido +
  tribunal + data fica `identificada` e não bloqueia — só o revisor humano barra.
  A consulta DataJud existe e é fail-safe; recomenda-se ligá-la no caminho de aprovação
  HITL e considerar bloquear `processo_cnj` não confirmado quando o DataJud estiver ativo.

### P1-8. Metadados de fonte não chegam ao modelo (dívida 5.4 pela metade)
- O retrieval/reranker devolve URL oficial, autoridade, situação jurídica
  (`ai/reranker.py:214-243`), mas `_formatar_fontes` (`ai_service.py:522-532`) e a geração
  de peça (`peca_service.py:915`) entregam ao modelo só `titulo (categoria — fonte)` +
  conteúdo — **sem data, tribunal, vigência ou status de conferência**. O modelo não tem
  como citar com identificação completa; a exigência de julgado completo (tribunal,
  número, relator, data) existe só no prompt da Sala Jurídica.

### P1-9. Dívida 5.2 parada nas prioridades 1-2 (peça e análise estratégica fora do orquestrador)
- Geração de peça: `peca_service.py:835-1179` (7 chamadas `gw_chat` encadeadas),
  `motor_peca_service.py:504,529`, `prompts_juridicos.py:268`. Reimplementa parte da
  governança (citation_check em `peca_service.py:1241-1242`, AILog, rascunho), mas sem
  `ResponseValidator` (sem detecção de promessa de resultado, sem grounding ao vivo, sem
  `hitl_policy.aplicar`).
- Análise estratégica: `analise_estrategica.py:325`, `score_juridico.py:93`,
  `ia_especializada.py:91`, `teses.py:382,507`, `provas.py:411` e ~8 outros.
- Total remanescente: ~13 routers + ~20 services chamando `ai_gateway.chat` direto.
  As superfícies novas (defesas, entrada universal, DPT360, jurimetria, sala jurídica,
  legal_chat) nasceram no orquestrador — a direção está certa, os legados de maior risco
  não andaram. Mitigação mínima sem migração completa: chamar
  `response_validator.validar` + `hitl_policy.aplicar` nesses serviços.

### P1-10. Gate de citações pode ser desligado por flag sem trava de produção
- `citation_gate.py:159-163` — `CITACOES_POLITICA=desligado` retorna relatório vazio sem
  verificar nada. Diferente de `SECRET_KEY`/CORS, o boot de produção **não falha** nem
  alerta nesse estado. Recomendação: sonda de flags de produção tratar
  `CITACOES_POLITICA≠bloquear` como achado crítico (a exemplo de
  `scripts/check_flags_producao.py`).

## 4. Achados P2 (síntese)

| # | Achado | Evidência |
|---|---|---|
| P2-1 | Súmula 437/TST e Súmula 331/TST citadas sem ressalva pós-reforma/Temas STF (art. 71 §4º CLT; ADPF 324/Tema 725) | `trabalhista.py:23,31` |
| P2-2 | ACP art. 16 tratado como "debate atual" — STF já decidiu (Tema 1075/2021) | `constitucional.py:27` |
| P2-3 | Lei 14.879/2024 (foro de eleição) ignorada nos templates de contrato/honorários | `templates_documentos.py:361-362,419-420`; `honorarios.py:15` |
| P2-4 | Triagem restringe classificação a 7 áreas (caso tributário/imobiliário/empresarial recebe rótulo errado); identidade da base lista 8 áreas para 28 ramos | `triagem.py:9`; `base.py:9-10` |
| P2-5 | Ramos rasos: prompts inline de 1 frase (`bancario`, `seguranca_lgpd`, `comunicacao_cliente`, `processo`, `jurimetria_pred`); `analise_caso.py` atende 4 chaves em 21 linhas; `ambiental.py` (área nuclear do escritório) cobre só auto de infração IBAMA | `system_prompts/__init__.py:91-95`; `analise_caso.py`; `ambiental.py` |
| P2-6 | Chamada por `TarefaIA` sem membro no enum cai em prompt genérico DEFAULT silencioso (só BASE_PROMPT, modelo rápido) | `system_prompts/router.py:18-39`; `ai_gateway.py:931-932` |
| P2-7 | `PRAZOS` roteado para Haiku (tarefa de prazo fatal em modelo rápido); com `ROTEAMENTO_INTELIGENTE_ENABLED=false`, peça vai primeiro a modelo local 8-14B; áreas LOCAL_COMPLETO (criminal/família/saúde) limitadas a modelos locais pequenos — tradeoff sigilo×capacidade a decidir pelo titular | `system_prompts/router.py:63`; `config.py:711-712`; `sanitization_policy.py:70-78` |
| P2-8 | Auto-crítica adversarial de peças OFF por default (`PECAS_AUTOCRITICA_ENABLED=False`); laço Duas IAs pronto e fail-safe | `config.py:623`; `peca_service.py:1153-1231` |
| P2-9 | UI não trata o 409 do gate de citações nem oferece campo de justificativa de override — fluxo trava sem caminho de exceção pela interface | `IA.tsx:156-161`; `ContextualAIAssistant.tsx:228` |
| P2-10 | Contexto da peça não inclui prazos/andamentos/histórico de peças; geração avulsa (sem caso) não passa pelo gate de ficha de triagem | `peca_geracao.py:141-149,243-246`; `peca_service.py:1033-1079` |
| P2-11 | `ollama_provider.py:61` aceita resposta vazia como sucesso (groq tem guard; ollama não) | `ollama_provider.py:61` vs `groq_provider.py:49-50` |
| P2-12 | `ai_cost.py` sem preço para `claude-fable-5`/`mythos` → custo R$ 0 na governança se configurados | `ai_cost.py:15-22`; `anthropic_provider.py:27-33` |
| P2-13 | `SUMULA_TETO` e `DATA_CONFERENCIA` (2026-07-18) estáticos, sem alarme de envelhecimento no painel | `verificador_jurisprudencia.py:70`; `sumulas_ingestion.py:31` |
| P2-14 | Gold set jurídico real da suíte de avaliação nunca foi criado — CI roda só `--smoke` (formato/PII); a régua que destravaria FTS/HyDE/reranker e o modo estrito de citações está montada e vazia | `app/eval/run_eval.py`; `gold_set.example.jsonl` (3 casos); `ci.yml:205` |
| P2-15 | Templates fixam "COMARCA DE … MINAS GERAIS" e "OAB/MG" hardcoded | `templates_documentos.py:84,88` |
| P2-16 | Sigilo profissional (EOAB art. 7º, II/CED) não nomeado no BASE_PROMPT (só no stub `seguranca_lgpd`) | `base.py`; `__init__.py:95` |
| P2-17 | Carimbo de rascunho artesanal nos routers legados (heterogêneo, depende do autor); no núcleo é estrutural | `conteudo.py:74-77`; `prompts_juridicos.py:305` |
| P2-18 | Kill-switch `AI_ENABLED` só por .env+restart, sem atuação de emergência em runtime (decisão a registrar como consciente) | `config.py:134`; `ia_saude.py:79-124` |

## 5. Estado das dívidas de julho (§5.1–5.7)

| Dívida | Estado | Evidência |
|---|---|---|
| 5.1 Registro único de provedores | **Parcial** — `provider_registry.py` existe, conectado por monkey-patch em runtime; implementações duplicadas persistem e o patch não roda no worker (P1-6); config de modelo/tarefa segue em 4 lugares | `provider_registry_runtime.py:24-33`; `ai_gateway.py:121-181,667-711` |
| 5.2 Migração para o orquestrador | **Parada nas prioridades 1-2** (P1-9); superfícies novas nascem no lugar certo | ver P1-9 |
| 5.3 Inventário canônico de prompts | **Aberta** — prompts ainda em serviços, templates, registry e módulos legados; sem versão/hash no AILog | — |
| 5.4 Metadados uniformes do RAG | **Parcial** — ingestão e reranker ricos; prompt não os recebe (P1-8) | ver P1-8 |
| 5.5 Memória por caso vs cliente | **Aberta** — isolamento por `client_id`; `comunicacao_processual` sem filtro por `case_id` | `ai_service.py:69-73`; `ingestors/djen.py:244` |
| 5.6 SLA de atualidade por fonte | **Avançou muito** — saúde por resultado (`ingestao_saude.py`), marcador `ja_produziu`, vigência com proveniência positiva; falta SLA por tipo de fonte e alarme de envelhecimento (P2-13) | `ingestao_saude.py`; `rag_coverage.py:82,153` |
| 5.7 Calibração de busca | **Infra pronta, medição não feita** — FTS/HyDE/reranker seguem OFF (correto); sem gold set real (P2-14) | `config.py:572-592` |

## 6. Pontos fortes confirmados

1. **HITL estrutural inviolável no núcleo**: `is_rascunho=True` incondicional
   (`hitl_policy.py:54-62`), AILog obrigatório com erro propagado, alertas da crítica
   adversarial propagados. Máquina de estados até "protocolada" com gates encadeados e
   imutabilidade pós-assinatura.
2. **Gate de citações fail-closed**: política default `bloquear`, vigência de artigo
   bloqueia mesmo sem modo estrito, falha do verificador = 503, override com justificativa
   auditada. Decisão do modo estrito documentada com critério objetivo de virada.
3. **Barreira LGPD em fonte única** (`_chamar_com_barreira`), pseudonimização recursiva no
   agêntico, NER local de 3ª passada, piso de sigilo por área não-rebaixável com
   normalização anti-bypass, guarda de boot de produção.
4. **RAG com defesa em profundidade**: quarentena de curadoria, exclusão incondicional de
   norma revogada, vigência com prova positiva, filtro de corpus fictício em todas as
   pernas, embeddings E5 com prefixos query/passage corretos, degradação graciosa.
5. **Monitoramento por resultado** na ingestão (`ingestao_saude.py`) — resposta direta e
   bem desenhada à armadilha DJEN.
6. **Prompts acima da média em ramos-chave**: `tributario.py` (transição EC 132/2023 +
   LC 214/2025 correta e sofisticada), `juizados.py` (anti-transplante JEC/JEF/JEFP),
   `padrao_ouro.py` (fatos ancorados em "(doc. NN)", pedidos com memória de cálculo),
   `modo_executivo.py`. Atualização legislativa 2023-2025 globalmente boa — as exceções
   estão nos achados.
7. **Cobertura de testes dos invariantes de governança é extensa**: 204 testes só no
   recorte hitl/citation/gateway/guardrail, incluindo testes de nível de banco.

## 7. Plano de correção recomendado (ordem de prioridade)

1. **Imediato (P0)** — corrigir `prazos.py` (CLT/JEC dias úteis; conferir contagem IBAMA
   em fonte oficial) + teste de invariante do conteúdo do prompt. Uma linha errada aqui
   contamina toda a função de maior risco do sistema.
2. **P1 jurídico** — corrigir `honorarios.py` (CED 2015, art. 23 EOAB, Provimento
   205/2021); incluir Lei 14.905/2024 em `civel`/`contratual`/`padrao_ouro`; ressalvas
   nas Súmulas 437/331 TST; Lei 14.879/2024 nos templates.
3. **P1 governança** — `exige_fonte=True` em CaseAgent/EJCCoordinator (ou citation_check
   sempre que houver citação); `requer_advogado` em `/revisar`, `/aprovar`,
   `/conferir-e-assinar` e no HITL de peça, com segregação autor≠revisor; hardening no
   boot do worker Celery + internalizar fail-closed no `_resolver_cadeia`; DataJud no
   caminho de aprovação HITL; metadados completos (data, tribunal, vigência, URL) no
   `[Fonte N]` do prompt; sonda de produção alertando `CITACOES_POLITICA≠bloquear`.
4. **Convergência (dívida 5.2)** — migrar geração de peça e análise estratégica para o
   orquestrador (ou, mínimo, `ResponseValidator`+`hitl_policy` nos serviços legados).
5. **Excelência contínua** — criar o **gold set jurídico real** (destrava modo estrito,
   FTS/HyDE/reranker e mede groundedness de verdade); aprofundar `ambiental.py` e os
   stubs (`bancario`, `analise_caso`); ampliar triagem para as 28 áreas; avaliar ligar
   `PECAS_AUTOCRITICA_ENABLED` em produção; UI de override do gate; enriquecer contexto
   da peça com prazos/andamentos.

## 8. Decisões que exigem o titular

- **Tradeoff sigilo×capacidade** nas áreas LOCAL_COMPLETO (criminal/família/saúde):
  aceitar modelos locais pequenos, investir em modelo local forte, ou rever a política
  (P2-7).
- **Ligar auto-crítica adversarial** de peças em produção (custo × qualidade, P2-8).
- **Modo estrito de citações**: executar a medição prevista na decisão de 2026-07-29 e,
  se ≤2%, virar a chave.
- **Piso de papel na revisão HITL** (P1-5): definir quem pode revisar/aprovar peça.

## 9. Limitações desta auditoria

Somente leitura de código no commit `a89e31d`; sem acesso a banco/ambiente de produção
(flags efetivas, conteúdo real da base RAG e telemetria não foram inspecionados — a fonte
de verdade de provedores em produção é `GET /ia-governanca/provedores`). Achados P2 não
reconferidos individualmente na thread principal mantêm a evidência arquivo:linha apurada
pelas frentes de auditoria. Os PRs #1143/#1148 endereçam a biblioteca jurídica ingerida
(lote piloto) — este relatório não repete aqueles achados.
