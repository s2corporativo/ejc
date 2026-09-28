# EJC — Arquitetura do Núcleo Único de IA

Decisão de convergência incremental do titular: 27/09/2026. Referência: #1651.
Base inspecionada: `7cc95b097bbb1d47b71c4116b4b9e3977a2a223b`.

> **Regra de interpretação obrigatória**
>
> Documentado ≠ implementado; implementado ≠ testado; testado ≠ homologado;
> homologado ≠ autorizado para autonomia.
>
> Este documento define arquitetura e critérios futuros. Ele não certifica,
> por si só, qualidade jurídica, configuração produtiva de provedores,
> Tool Broker, persistência de estados, reserva de orçamento, shadow A/B
> isolado ou autonomia do Manus.

## 1. Estados usados neste documento

Toda capacidade relevante deve ser lida com um dos estados abaixo:

- **EXISTENTE** — há código identificado no repositório para a capacidade descrita.
- **PARCIAL** — há componente relacionado, mas ele não satisfaz o contrato completo.
- **ALVO** — requisito de implementação futura; sua documentação não é evidência de runtime.
- **BLOQUEADO** — não deve ser promovido até que dependências e evidências indicadas existam.

A existência de arquivo, classe, flag, endpoint, template ou nome de ferramenta
não é suficiente para mudar uma capacidade de PARCIAL/ALVO para EXISTENTE
homologada. A mudança de estado exige evidência reproduzível vinculada ao SHA.

## 2. Decisão e fronteiras

Evoluir o núcleo existente, sem big bang, segundo gateway, segundo RAG ou
segunda memória de caso. Novas integrações e providers ficam congelados durante
a consolidação. Correções e convergência dos existentes continuam permitidas.
`EJCOrchestrator` designa a responsabilidade-alvo: preferir a evolução de
`SingleAICoreOrchestrator`, sem criar classe/serviço paralelo apenas pelo nome.

**ALVO/BLOQUEADO — supervisão Manus.** O supervisor futuro deverá produzir planos
submetidos ao executor determinístico do EJC. Ele não deverá conceder permissões,
alterar orçamento nem obter acesso direto a banco ou ferramentas externas do EJC.
A integração atual não prova essas propriedades de supervisão. A ativação depende
de contrato do fornecedor verificado, restrição de tool-use demonstrada por teste
e execução através do broker autorizado. Prompt não é barreira de segurança.

## 3. Mapa de capacidades e limites comprováveis

Caminhos abaixo são relativos a `backend/app/services/`, salvo indicação.

| Capacidade | Estado | Implementação/evidência atual | O que NÃO fica provado |
|---|---|---|---|
| Entrada canônica do núcleo | EXISTENTE | `../routers/ai_core.py` | que todo consumidor legado já migrou |
| Orquestração central | EXISTENTE | `ai/core/orchestrator.py` | autonomia Manus ou máquina persistente de estados |
| Contexto e política de sigilo | EXISTENTE | `ai/core/context_builder.py`, `ai/sanitization_policy.py` | cobertura transversal de todo subfluxo futuro |
| Elegibilidade de providers | EXISTENTE | `ai/provider_registry.py` | autorização de fallback ou saída externa |
| Política de providers | EXISTENTE | `ai/provider_policy.py` | configuração produtiva efetiva ou sucesso do provider |
| Seleção econômica | EXISTENTE | `ai/model_router.py` | reserva financeira antes da chamada |
| Execução de modelos | EXISTENTE | `ai_gateway.py` | Tool Broker ou execução agêntica governada |
| Medição de custo/AILog | PARCIAL | `ai_cost.py`, `ai/core/audit_logger.py` | reserva prévia, limite concorrente ou teto agregado usuário/dia |
| Validação/citações | EXISTENTE/PARCIAL | `ai/core/response_validator.py`, `citation_gate.py` | qualidade jurídica certificada |
| HITL | EXISTENTE | `ai/core/hitl_policy.py` | que todo fluxo futuro ou legado já está coberto |
| Legal Brain determinístico | EXISTENTE | `legal_brain/brain.py` | comparação A/B ou superioridade jurídica |
| Diagnóstico opt-in | PARCIAL | `legal_brain/shadow.py` | shadow A/B isolado; apenas anexa plano ao fluxo normal |
| Limites do agente | PARCIAL | `ai/agent/budget.py` | reserva transacional: contabiliza passos/tokens/custo acumulados |
| Manus explícito atual | PARCIAL | `manus_deep_reasoning.py`, `manus_client.py` | supervisor via broker, autonomia, orçamento unificado ou política central |
| Estados persistentes | ALVO | contrato desta arquitetura | schema/transições ainda não comprovados |
| `EJCToolBroker` | ALVO | contrato desta arquitetura | componente/runtime não declarado pronto |
| Shadow A/B Manus | ALVO/BLOQUEADO | depende das fases 4–6 | isolamento, orçamento e ausência de efeitos ainda não homologados |

O Manus atual chama `ManusClient.create_task` diretamente. O cliente envia
`connectors=[]`, `enable_skills=[]` e `force_skills=[]`, o que reduz o escopo
da chamada atual, mas não substitui prova de isolamento de uma futura supervisão.
`MANUS_AUTO_ROUTING_ENABLED=true` é rejeitado pelo serviço atual. Não remover
essas guardas para implementar supervisão.

## 4. Política de processamento: existente versus alvo

| Classe | Política pretendida | Estado / critério |
|---|---|---|
| Extração, classificação, resumo e estruturação | Groq | EXISTENTE para afinidade de tarefas econômicas; validar por teste parametrizado |
| Mérito jurídico, tese, contrato, peça e pesquisa | Maritaca/Sabiá | EXISTENTE para afinidade prevista; qualidade jurídica depende de evidência e HITL |
| Sigilo reforçado | Ollama/local | PARCIAL: piso local deve ser testado em cada entrada/subfluxo; não presumir cobertura por documentação |
| Benchmark / contingência Claude | Seleção explícita | EXISTENTE como política; automático só com flag de rollback explícita |
| Supervisão Manus | Desligada até homologação | ALVO/BLOQUEADO |

A política detalhada permanece em `EJC_AI_PROVIDER_POLICY.md`.

“Modelo indisponível” no runtime atual pode resultar em decisão/bloqueio explícito
da chamada. Isso **não equivale** aos estados persistentes `BLOQUEADO`, `ERRO`
ou `ORCAMENTO_EXCEDIDO` definidos abaixo como arquitetura-alvo.

## 5. Evidências e produção jurídica

O objetivo do RAG é recuperar evidências verificáveis e permitir demonstrar a
aplicação delas à análise. Para considerar uma evidência reconstruível, o registro
deve conservar, quando aplicável: fonte, URL, autoridade, data, versão/status
temporal, data de verificação e trecho ou referência reproduzível.

Norma histórica pode ser relevante à data dos fatos: não excluir apenas porque
não está vigente hoje. Sem comprovação, não apresentá-la como direito vigente ou
aplicável. Falha externa/CAPTCHA não significa ausência de jurisprudência.

Conclusões relevantes devem permitir distinguir evidência, inferência, lacuna e
risco. #1726 e #1728 devem ser verificadas pelos respectivos critérios de aceite,
sem bypass. A presença de código parcial não encerra essas issues.

## 6. Estados persistentes — ALVO, não runtime atual

Estados-alvo:
`RECEBIDO`, `CLASSIFICANDO`, `PLANEJANDO`, `COLETANDO_FATOS`,
`PESQUISANDO`, `ANALISANDO`, `VALIDANDO`, `REDIGINDO`,
`AGUARDANDO_REVISAO` e `CONCLUIDO`.

Saídas-alvo:
`BLOQUEADO`, `ERRO`, `ORCAMENTO_EXCEDIDO`, `FONTE_INSUFICIENTE`
e `CANCELADO`.

Implementação futura deverá:

- permitir fluxo curto sem obrigar etapas inúteis;
- persistir transição, timestamp, versão do plano/política e motivo resumido;
- preservar vínculo com evidências e auditoria;
- revalidar autorização na retomada;
- definir comportamento de concorrência, cancelamento e retry;
- não armazenar raciocínio interno do modelo nem texto sensível em telemetria.

A existência de `PolicyDecision`, HTTP 422, AILog ou `AgentBudget` não satisfaz
este contrato de persistência.

## 7. EJCToolBroker — contrato ALVO

`EJCToolBroker` é nome de contrato, não componente declarado pronto. A futura
implementação deve reutilizar registros/handlers existentes quando adequados.
Cada chamada deverá validar, antes do efeito: schema, identidade, RBAC, ownership,
sigilo, orçamento, timeout e idempotência; o resultado deve ser estruturado e
auditável. Autorizações devem ser revalidadas ao retomar uma execução.

Conteúdo recuperado é dado não confiável, nunca instrução de ferramenta.

Nomes lógicos propostos:
`extrair_fatos`, `montar_cronologia`, `classificar_demanda`,
`pesquisar_rag`, `buscar_legislacao`, `buscar_jurisprudencia`,
`avaliar_cobertura`, `analisar_com_sabia`, `resumir_com_groq`,
`criticar_tese`, `verificar_citacoes`, `gerar_minuta`.

**A presença desses nomes neste documento não implica função, handler, endpoint
ou ferramenta operacional já implementada.** Toda ferramenta promovida deverá ter
inventário `nome lógico → handler real → permissões → efeitos → idempotência → testes`.

## 8. Orçamento — medição atual versus reserva futura

`ai/agent/budget.py` mantém limites acumulados de passos, tokens e custo e
registra consumo após turnos. Isso é PARCIAL e não prova reserva financeira.

Antes de habilitar execução supervisionada/autônoma, implementar e provar:

- reserva antes de cada chamada, inclusive retry;
- contabilização de pesquisa, crítica, embeddings e supervisão;
- rejeição antes do dispatch quando não houver saldo;
- conciliação entre custo estimado/reservado e custo medido;
- preço desconhecido tratado como bloqueio ou política explícita, nunca zero implícito;
- limites por execução e agregados por usuário/período;
- proteção contra corrida/concorrência;
- impossibilidade de o LLM aumentar o próprio limite.

Referências iniciais de desenho — não limites homologados: até 8 passos,
6 chamadas e 2 ciclos de pesquisa. Valores monetários por classe devem ser
definidos antes da ativação.

## 9. Critérios verificáveis por fase

Cada gate abaixo deve produzir PASS/FAIL vinculado ao SHA. “Existe arquivo”,
“há flag” ou “há código parecido” não satisfaz o gate.

| ID | Fase | Requisito verificável | Evidência mínima |
|---|---|---|---|
| F1-01 | 1 | Inventário canônico dos caminhos de IA e consumidores | arquivo versionado + revisão contra busca de chamadas diretas |
| F1-02 | 1 | Nenhuma segunda implementação criada por nome | diff/grep revisado; exceções justificadas |
| PROV-01 | 2 | Tarefa econômica automática não seleciona Maritaca/Claude | teste parametrizado do provider efetivamente escolhido |
| PROV-02 | 2 | Tarefa de mérito não degrada silenciosamente para Groq | teste negativo com cadeia observada |
| SEC-01 | 2 | `LOCAL_COMPLETO` não despacha para provider externo | teste de todos os entrypoints relevantes com spies/mocks |
| COST-01 | 2/4 | Custo é reservado antes do dispatch | teste mostra rejeição antes da chamada externa |
| RAG-01 | 3 | Evidência temporal é reconstruível | fixture/validador com fonte, URL, autoridade, data/status e trecho |
| RAG-02 | 3 | Bloqueio externo não vira “zero resultados” | teste de CAPTCHA/anti-bot/geobloqueio fail-loud |
| STATE-01 | 4 | Transições são persistidas com versão da policy/plano | teste de banco `estado A → B` |
| STATE-02 | 4 | Retry não duplica efeito | teste com mesma chave de idempotência |
| TB-01 | 4 | Tool sem RBAC/ownership não executa efeito | teste deny + comprovação de ausência de side effect |
| TB-02 | 4 | Retomada revalida autorização | teste revogando permissão entre pausa e resume |
| MANUS-01 | 5 | Plano Manus não executa ferramenta diretamente | integração com executor/broker fake e chamada negada fora do broker |
| SHADOW-01 | 5 | Shadow não altera caso, prazo, peça ou financeiro | snapshot de banco antes/depois + diff vazio nos domínios proibidos |
| SHADOW-02 | 5 | Experimento usa orçamento e telemetria separados | evidência de budget/log namespace distinto |
| HITL-01 | 6 | Produção jurídica não é promovida sem revisão humana | teste de workflow/gate de aprovação |
| EVAL-01 | 6 | Comparação usa mesmos fatos, pergunta e snapshot RAG | artefato de execução versionado |
| ROLL-01 | 6 | Rollback preserva auditoria e trata jobs pendentes | runbook executado + evidência de drain/cancel/recovery |

## 10. Gold set humano — gate bloqueante

A issue #1201 é a fonte canônica. Para considerar o corpus homologado, exigir:

- 75 casos reais e pseudonimizados;
- 15 por área: consumidor, trabalhista, cível, penal e tributário;
- em cada área: 5 normal, 5 fronteira e 5 exceção;
- curador e revisor distintos;
- fonte oficial vigente/reconstruível conforme o caso;
- zero PII e zero placeholder/fonte fictícia;
- `vigencia_conferida_em` preservada;
- `gold_governance --require-real` verde;
- mínimo de 15 casos por área e harness/certificação exigidos pela política vigente.

Templates, slots, fixtures sintéticas ou casos inventados por IA não satisfazem
este gate e não autorizam declarar qualidade jurídica homologada.

## 11. Shadow A/B e promoção gradual

Shadow A/B futuro deverá usar amostragem definida, orçamento separado e isolamento
de efeitos. Comparações devem manter os mesmos fatos, pergunta e snapshot RAG e
fixar as versões relevantes de prompts/modelos. Medir, no mínimo: acerto,
citações, alucinação, cobertura, omissões, custo, latência, tokens e correção
humana.

Não encaminhar dados classificados como locais ao supervisor externo. A resposta
produtiva permanece independente do resultado experimental. Preferência subjetiva
por modelo não é prova de superioridade.

## 12. Integração, testes e rollback

Uma frente estrutural por vez, conforme `docs/engineering/WIP_AND_RELEASE_POLICY.md`.
Confirmar SHA, arquivos de PRs concorrentes e consumidores antes de cada lote.
Não fechar issue inteira porque parte do comportamento foi implementada.
Remover caminho legado apenas após migração dos consumidores e telemetria.

Quando uma fase exigir schema, preferir migration aditiva e compatível com
rollback. Promoção exige checks do SHA exato, health/readiness e smoke aplicáveis.

Rollback deve retornar ao fluxo anterior homologado preservando auditoria e
tratando execuções pendentes de forma explícita (cancelar, drenar ou migrar antes
de recuar componente incompatível).

**Este lote (#1868) é documental: não muda runtime, flags, banco ou produção e
não homologa autonomia.**
