# EJC — Relatório de Remoção de Duplicidades de IA

Data: 2026-07-04 · Branch: `claude/ejc-legal-ai-architecture-s2ctes`

## Duplicidades eliminadas

### 1. Dois gateways de IA → um
- **Antes:** `services/ai_gateway.py` (correto) coexistia com o gateway-sombra `core/ai_brain.py` (httpx direto ao Ollama, modelos hardcoded, sem sanitização, sem AILog, sem fallback), consumido por ~16 pontos (routers `cerebro`, `prompts`, `jurimetria`, `teses`, `intelligence_v3`, `curadoria_renomada`, `cases`, `clients`, `rag` e services `rag_juridico`, `gatilhos_estruturais`, `sentimento_magistrado`, `minerador_sucesso`, `motor_estrategico`, `war_room`).
- **Depois:** `core/ai_brain.py` é um wrapper fino **DEPRECATED** que sanitiza PII e delega a `services/ai_gateway.chat()` (herda barreira final de PII, cadeia por prioridade e fallback). Zero chamada httpx direta a modelo fora de `services/providers/`. A interface pública foi preservada para não quebrar os consumidores; novos usos devem ir direto ao núcleo (`services/ai/core/orchestrator`).

### 2. Lógica de IA por módulo → núcleo único
Endpoints que montavam pipeline próprio (`cerebro/analise-estrategica`, `prompts-biblioteca/executar`, `jurimetria/predicao-exito`, `documentos-ia/analisar`) agora delegam ao `SingleAICoreOrchestrator` — um só fluxo de intenção→agente→contexto→sanitização→policy→gateway→validação→HITL→AILog. Detalhe por endpoint: `EJC_AI_ENDPOINT_MIGRATION_MATRIX.md`.

### 3. Decisão de provider espalhada → AIProviderPolicy
- **Antes:** a escolha de provider/modelo estava fragmentada em `TASK_ROUTING` (gateway), `system_prompts/router.py` (por tarefa) e `AI_PROVIDER` (env), sem regra LGPD unificada.
- **Depois:** `services/ai/provider_policy.py` é a autoridade única de elegibilidade/ordem/bloqueio (com `AI_PROVIDER_PRIORITY`, `AI_EXTERNAL_PROVIDERS_ALLOWED`, `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL`); o gateway aplica as MESMAS regras na resolução de cadeia e na barreira final.

### 4. Prompt jurídico no frontend → servidor
O único prompt montado no navegador (comparação de contratos, `CasoDetalhe.tsx`) migrou para o backend (`ai_service.analisar_contrato` com `modo="comparacao"`). O frontend envia apenas os dois textos e o modo.

### 5. Tráfego redundante de conteúdo → referência por ID
`/ai/auditar-peca` aceita `peca_id`; o backend busca o conteúdo de `LegalDoc` com validação de ownership, em vez de o navegador reenviar a peça inteira.

## Duplicidades reduzidas (caminhos mantidos por compatibilidade)

- **AILog por 3 caminhos de escrita** → padronizado nos fluxos novos/corrigidos via `ai_guard.registrar_ai_log` (canônico). O SQL cru de `executar_tarefa_ia` e INSERTs manuais antigos permanecem em fluxos não tocados — pendência de migração gradual.
- **Múltiplas "análises de caso"** (`/ai/analisar-caso`, `/ai/executar`, `/cerebro/analise-estrategica`, `case_intel.triagem_caso`, `teses_v4/analise`): todas agora passam pelo gateway central com San+AILog; a unificação de UX/produto (qual tela usa qual) é decisão futura de produto, não de arquitetura.
- **Dois "detectar-prazos"** (`ai.py`, `assistente.py`) e **duas sugestões de honorários** (`ia_extra`, `honorarios_oab`): mantidos (ambos governados); candidatos a deprecação por redirecionamento no frontend.

## Não removido (por quê)

- **Routers legados**: mantidos como wrappers — remoção quebraria o frontend em produção; a matriz de migração documenta o caminho de deprecação.
- **`veredito_ia` (heurística)**: não é LLM; mantido, mas documentado como simulação — recomenda-se renomear na UI ou migrar para `JurimetryAgent` no futuro.
- **`system_prompts/`**: não é duplicidade — é a biblioteca canônica de prompts do núcleo (agentes novos adicionaram keys ali, no mesmo padrão).
