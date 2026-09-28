# EJC — Arquitetura do Núcleo Único de IA

Decisão de convergência incremental do titular: 27/09/2026. Referência: #1651.
Base inspecionada: `7cc95b097bbb1d47b71c4116b4b9e3977a2a223b`.
Este documento distingue código existente de arquitetura-alvo; não certifica
qualidade jurídica, configuração de provedores ou homologação de produção.

## 1. Decisão e fronteiras

Evoluir o núcleo existente, sem big bang, segundo gateway, segundo RAG ou
segunda memória de caso. Novas integrações e providers ficam congelados durante
a consolidação. Correções e convergência dos existentes continuam permitidas.
`EJCOrchestrator` designa a responsabilidade-alvo: preferir a evolução de
`SingleAICoreOrchestrator`, sem criar classe/serviço paralelo apenas pelo nome.

Manus será supervisor de planos, sujeito ao executor determinístico do EJC.
Não concede permissões, não altera orçamento e não acessa diretamente banco ou
internet por ferramentas do EJC. Sua ativação depende de contrato do fornecedor
verificado e capacidade comprovada de restringir execução; prompt não é barreira.

## 2. Mapa confirmado no código

Caminhos abaixo são relativos a `backend/app/services/`, salvo indicação.

| Componente | Implementação existente | Responsabilidade / limite |
|---|---|---|
| Entrada canônica | `../routers/ai_core.py` | Receber intenção e IDs |
| Orquestrador | `ai/core/orchestrator.py` | `SingleAICoreOrchestrator.run`: contexto, policy, gateway, validação, auditoria e HITL |
| Contexto e sigilo | `ai/core/context_builder.py`, `ai/sanitization_policy.py` | Contexto autorizado e piso de sigilo |
| Elegibilidade | `ai/provider_registry.py` | Flags, disponibilidade de credencial e kill-switches |
| Política | `ai/provider_policy.py` | Afinidade por tarefa e cadeia permitida |
| Seleção econômica | `ai/model_router.py` | Proposta determinística; não concede autorização |
| Execução dos modelos | `ai_gateway.py` | Despacho, fallback e metadados de uso |
| Custos | `ai_cost.py`, `ai/core/audit_logger.py` | Estimativa e AILog; medição não equivale a reserva prévia |
| Validação | `ai/core/response_validator.py`, `citation_gate.py` | Citações e alertas; verificar também o gate de aprovação da peça |
| Revisão humana | `ai/core/hitl_policy.py` | Estado de rascunho e necessidade de revisão |
| Legal Brain | `legal_brain/brain.py` | Planejamento determinístico existente |
| Diagnóstico opt-in | `legal_brain/shadow.py` | Chama o núcleo e anexa plano; não implementa comparação A/B isolada |
| Limites do agente | `ai/agent/budget.py` | Passos, tokens e custo acumulados; não é reserva transacional universal |
| Manus atual | `manus_deep_reasoning.py`, `manus_client.py` | Integração separada de raciocínio explícito; ainda não é supervisor via Tool Broker |

O Manus atual chama `ManusClient.create_task` diretamente, embora tenha guardas
próprias e pseudonimização. `MANUS_AUTO_ROUTING_ENABLED=true` é rejeitado pelo
serviço atual. Não remover essas guardas para implementar supervisão.

## 3. Política-alvo de processamento

| Classe | Motor previsto | Restrição |
|---|---|---|
| Extração, classificação, resumo e estruturação | Groq | Não assumir mérito jurídico silenciosamente |
| Sigilo reforçado | Ollama/local | Piso local vale para supervisão, busca, embeddings, crítica e telemetria |
| Análise, tese, contrato, peça e pesquisa jurídica | Maritaca/Sabiá | Evidências e revisão humana preservadas |
| Benchmark / contingência Claude | Seleção explícita | Sem escalonamento automático para Claude |
| Supervisão Manus | Desligada até homologação | Plano e ferramentas autorizadas, sem autoridade própria |

A política de providers detalhada permanece em `EJC_AI_PROVIDER_POLICY.md`.
Modelo indisponível gera estado explícito; preservar opções manuais existentes
sem confundir seleção explícita com fallback. A flag histórica de Anthropic
não autoriza reativação automática nesta convergência.

## 4. Evidências e produção jurídica

O RAG recupera evidências verificáveis; a análise demonstra sua aplicação.
Separar legislação, jurisprudência, precedentes qualificados, material
institucional e doutrina. Cada evidência deve ter fonte, URL, autoridade,
data, versão, status temporal e data de verificação, com trecho reconstruível.
Norma histórica pode ser relevante à data dos fatos: não excluir por não estar
vigente hoje. Sem comprovação, não apresentá-la como direito vigente/aplicável.

Conclusões relevantes devem apontar evidência, inferência, lacuna e risco.
Falha externa/CAPTCHA não significa ausência de jurisprudência. Concluir #1726
por evidência atual e tratar #1728 sem bypass. Manus depende desses gates.

## 5. Orquestração e ferramentas — requisitos ainda a implementar/validar

Evoluir estados persistentes: RECEBIDO, CLASSIFICANDO, PLANEJANDO,
COLETANDO_FATOS, PESQUISANDO, ANALISANDO, VALIDANDO, REDIGINDO,
AGUARDANDO_REVISAO e CONCLUIDO; saídas BLOQUEADO, ERRO, ORCAMENTO_EXCEDIDO,
FONTE_INSUFICIENTE e CANCELADO. Permitir fluxo curto sem obrigar etapas inúteis.
Persistir transições, versão do plano/política, evidências e motivos resumidos;
não armazenar raciocínio interno do modelo nem texto sensível em telemetria.

`EJCToolBroker` é contrato-alvo, não componente declarado pronto. Reutilizar o
registro e os handlers existentes. Cada chamada valida schema, identidade,
RBAC, ownership, sigilo, orçamento e timeout; resultado estruturado e auditado.
Revalidar autorização ao retomar. Idempotência evita efeitos duplicados em retry.
Conteúdo recuperado é dado não confiável, nunca instrução de ferramenta.

Ferramentas iniciais propostas: extrair_fatos, montar_cronologia,
classificar_demanda, pesquisar_rag, buscar_legislacao, buscar_jurisprudencia,
avaliar_cobertura, analisar_com_sabia, resumir_com_groq, criticar_tese,
verificar_citacoes e gerar_minuta. Não criar endpoints para cada nome por padrão.

Reservar orçamento antes de cada chamada, incluindo retries, pesquisa, crítica,
embeddings e supervisão. Conciliar custo estimado/medido; preço desconhecido
não equivale a zero. Definir limites por execução e agregados por usuário/dia.
Referências iniciais: até 8 passos, 6 chamadas e 2 ciclos de pesquisa; valores
monetários por classe exigem definição antes da ativação. Não expandir limites
por decisão do LLM. Cache só quando autorização, sigilo e versão forem compatíveis.

## 6. Entregas e critérios de saída

| Fase | Entrega incremental | Gate |
|---|---|---|
| 1 | Mapa único, congelamento e conciliação de issues | Inventário dos caminhos, dependências e baseline; nenhuma exclusão por nome |
| 2 | Roteamento econômico e observabilidade | Identidade real do modelo; limites prévios; testes negativos de fallback e sigilo |
| 3 | RAG confiável e citações | Evidência temporal reconstruível e lacuna explícita; #1726/#1728 verificadas |
| 4 | Orquestrador e broker | Estados, cancelamento, retomada, concorrência e idempotência testados |
| 5 | Manus em shadow isolado | Controle de ferramentas comprovado; sem efeitos em casos, prazos ou peças |
| 6 | Avaliação humana e promoção gradual | Critérios fixados antes da comparação; qualidade/custo/latência e rollback comprovados |

Iniciar baseline na fase 1. Reutilizar #1201 como backlog humano de 75 casos:
15 por área e cenários normal/fronteira/exceção. Pesquisa, análise e produção
são dimensões adicionais, não substituem a estratificação por área. A existência
de templates ou candidatos não comprova corpus homologado. Não inventar casos
nem atestar revisão humana. Conciliar o requisito de revisor independente da
issue com a opção de revisor no backlog/código antes de certificar.

Comparar mesmos fatos, pergunta e snapshot RAG; fixar versões de prompts/modelos.
Medir acerto, citações, alucinação, cobertura, omissões, custo, latência, tokens
e correção humana. Preferência por modelo não é prova de superioridade.

Shadow A/B futuro tem amostragem, orçamento separado e isolamento de efeitos.
Não encaminhar dados locais ao supervisor externo. A resposta atual continua
visível; resultados experimentais ficam restritos à avaliação autorizada.

## 7. Integração, testes e rollback

Uma frente estrutural por vez, conforme `docs/engineering/WIP_AND_RELEASE_POLICY.md`.
Confirmar SHA, arquivos de PRs concorrentes e consumidores antes de cada lote.
Não fechar issue inteira porque parte do comportamento foi implementada.
Remover caminho legado apenas após migração dos consumidores e telemetria.

Testes por lote: roteamento e sigilo negativos; fonte ausente/desatualizada;
limites concorrentes; retomada e duplicação; autorização nas ferramentas;
shadow sem efeitos; HITL. Não alterar schema sem necessidade comprovada;
quando necessário, migration aditiva e compatível com rollback.

Promoção pela esteira com checks do SHA exato, health/readiness e smoke.
Rollback para fluxo anterior homologado, preservando auditoria e execuções
pendentes; cancelar/drenar trabalhos antes de recuar componente incompatível.
Este lote é documental: não muda runtime, flags, banco ou produção.
