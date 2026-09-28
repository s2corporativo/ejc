# EJC — AIProviderPolicy (política central de provedores)

> **Política operacional vigente — 20/09/2026**
>
> - **Groq** é o motor automático de tarefas corriqueiras, resumo, triagem e conversa rápida. Não assume mérito jurídico como fallback silencioso.
> - **Maritaca/Sabiá** é o motor automático de leitura, análise, raciocínio jurídico, RAG/pesquisa e jurisprudência. Não é consumida automaticamente por tarefas de rotina.
> - **Claude/Anthropic** permanece habilitável e elegível, porém **não participa do roteamento automático** com `ANTHROPIC_AUTO_ROUTING_ENABLED=false`; entra somente por seleção explícita `provider="anthropic"` no sistema. A flag `true` é rollback operacional.
> - **Ollama** continua sendo a opção local e o único destino admitido quando a política de sigilo exigir `LOCAL_COMPLETO`.
> - No caminho canônico governado pelo núcleo, providers externos ficam sujeitos a pseudonimização/sanitização, kill-switch, controles de acesso/contexto, AILog, validação de citações quando aplicável e HITL. Esta frase não certifica consumidores legados ou integrações futuras; a cobertura transversal deve ser demonstrada por inventário e testes.
> - A ausência de chave não é mascarada: Groq/Maritaca/Claude ficam inelegíveis individualmente sem suas credenciais; nenhuma credencial é versionada.

Data: 2026-07-04 · Código: `backend/app/services/ai/provider_policy.py`.

> **Estado operacional vigente (21/09/2026).**
>
> - **Quatro provedores**: `ollama`, `anthropic`, `maritaca`, `groq`.
> - **Fonte canônica de elegibilidade**: `services/ai/provider_registry.py`;
>   os componentes migrados (`AIProviderPolicy`, gateway e painéis correspondentes) devem consultar essa fonte. A documentação não substitui o inventário de consumidores para provar ausência de caminhos paralelos.
> - **Prioridade-base**: `AI_PROVIDER_PRIORITY="groq,maritaca,ollama,anthropic"`.
>   A afinidade por tarefa prevalece: rotina → Groq/Ollama; mérito →
>   Maritaca/Ollama.
> - **Maritaca**: `MARITACA_ENABLED=true` no contrato atual, mas continua
>   inelegível sem `MARITACA_API_KEY`.
> - **Claude**: `ANTHROPIC_ENABLED=true` pode manter o provider disponível para
>   seleção explícita, porém `ANTHROPIC_AUTO_ROUTING_ENABLED=false` o exclui do
>   automático. `true` é rollback operacional.
> - **Agente com tool-use**: opt-in; requer `AI_AGENT_ENABLED=true` e
>   `AI_AGENT_PROVIDER=anthropic` explicitamente. O `AI_PROVIDER` global
>   permanece em `auto`, preservando Groq/Maritaca nas chamadas comuns.
> - **Perfis**: `AI_PROFILE=externo|local|hibrido|desligado` continuam
>   derivando habilitação e prioridade sem contornar kill-switches explícitos.
> - **Deadline agregado**: `AI_CHAIN_DEADLINE_SECONDS`.
> - **Painel de verdade**: `GET /ia-governanca/provedores`.

A `AIProviderPolicy` decide, ANTES de qualquer chamada de modelo pelo caminho que a utiliza: quais providers são elegíveis, em que ordem tentar, se o conteúdo exige sanitização para destino externo e se a chamada é permitida. É **decisão pura** — não chama modelo; o despacho continua no `ai_gateway`. Esta documentação do componente não prova, isoladamente, que todo caminho legado ou integração futura passe pela policy; essa cobertura deve ser demonstrada por inventário e testes.

## 1. Entrada e saída

```python
AIProviderPolicy().avaliar(texto_completo, task_type, *,
                           ja_sanitizado=False, exige_fonte=False,
                           provider_solicitado=None) -> PolicyDecision
```

`PolicyDecision` (provider_policy.py:32-40):

| Campo | Significado |
|---|---|
| `permitido: bool` | False = chamada bloqueada |
| `provider_chain: list[(provider, model|None)]` | Ordem de tentativa; model=None (o gateway resolve por tarefa) |
| `sanitizar_antes: bool` | Destino externo na cadeia exige conteúdo sanitizado |
| `motivo: str` | Justificativa da decisão (auditável) |
| `requer_hitl: bool` | Espelha `AI_REQUIRE_HITL` |
| `requer_fonte: bool` | Propaga `exige_fonte` do agente |
| `bloqueio_motivo: str|None` | Mensagem SEGURA de bloqueio (nunca ecoa conteúdo/valores de PII) |

O orchestrator invoca a policy após a sanitização do input (`ja_sanitizado=True`) e converte `permitido=False` em HTTP 422 com `bloqueio_motivo` (orchestrator.py:115-122).

## 2. Elegibilidade por provider (`provider_registry.py`)

Todos exigem `AI_ENABLED=true`. Além disso:

| Provider | Condição |
|---|---|
| `ollama` | `OLLAMA_ENABLED` |
| `anthropic` | `ANTHROPIC_ENABLED` + credencial configurada + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| `groq` | `GROQ_ENABLED` + credencial configurada + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| `maritaca` | `MARITACA_ENABLED` + credencial configurada + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| outros | inelegíveis neste registro |

Elegibilidade não autoriza fallback ou saída externa de conteúdo local.
`AI_EXTERNAL_PROVIDERS_ALLOWED=false` bloqueia os externos.
Manus possui integração separada; não integra este registro. A existência do
`ManusClient` não deve ser interpretada como provider governado por esta policy.
A convergência, seus limites e gates estão em `EJC_SINGLE_AI_CORE_ARCHITECTURE.md`.

## 3. Ordem base — `AI_PROVIDER_PRIORITY`

CSV em Settings: `groq,maritaca,ollama,anthropic`. `_ordem_prioridade` deduplica e normaliza; vazio usa essa mesma ordem-base. Depois da elegibilidade, a afinidade por tarefa restringe a cadeia.

## 4. Priorização por perfil de tarefa (provider_policy.py:21-29, 112-119)

- `TAREFAS_COMPLEXAS` → Maritaca primeiro, com Ollama como alternativa local; Groq não assume mérito silenciosamente.
- `TAREFAS_ECONOMICAS` → Groq primeiro, com Ollama como alternativa local; Maritaca não é consumida silenciosamente por rotina.
- Anthropic só entra automaticamente com `ANTHROPIC_AUTO_ROUTING_ENABLED=true`; seleção explícita continua permitida quando elegível.
- Aceita tanto nomes de `TarefaIA` quanto task_types do gateway.

## 5. Barreira LGPD (provider_policy.py:95-110)

Se há externo elegível e `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=true`:
1. `sanitizar_antes=True`; se `ja_sanitizado=False`, aplica `sanitizar_pii` internamente;
2. `validar_sem_pii` checa residual (CPF/CNPJ/processo/RG/e-mail/telefone/CEP);
3. residual encontrado → **externos removidos da cadeia** (fica só Ollama local, se habilitado); motivo registra apenas os TIPOS de PII;
4. cadeia vazia → `permitido=False` com `bloqueio_motivo` seguro: "Nenhum provedor de IA elegível... Habilite o Ollama local (OLLAMA_ENABLED=true) ou remova dados pessoais do texto" (provider_policy.py:123-136). O conteúdo jamais é ecoado.

## 6. Dupla barreira

A policy decide no núcleo, mas o `ai_gateway` **não confia** nessa decisão: antes de despachar a cada provider externo ele re-sanitiza toda mensagem e pula o provider se sobrar PII (`_sanitizar_messages_externo` + loop, ai_gateway.py:192-207, 333-347). Se todos os externos forem pulados por PII e não houver local, o gateway falha com mensagem segura (ai_gateway.py:242-247). Regras de elegibilidade são idênticas nos dois pontos (`_provider_elegivel`, ai_gateway.py:272-283).

## 7. Roteamento recomendado por cenário

| Cenário | Cadeia resultante | Por quê |
|---|---|---|
| Análise de caso/minuta/dossiê, conteúdo limpo | maritaca → ollama | Mérito jurídico usa Maritaca; sem degradação silenciosa para Groq/Claude |
| Resumo/triagem/chat rápido | groq → ollama | Rotina usa Groq; sem consumo silencioso de Maritaca/Claude |
| Qualquer tarefa com PII residual após sanitização | somente ollama | Externos removidos (LGPD) |
| PII residual e `OLLAMA_ENABLED=false` | (vazia) → HTTP 422 | Bloqueio com motivo seguro |
| `AI_EXTERNAL_PROVIDERS_ALLOWED=false` | somente ollama | Modo soberania total |
| `ANTHROPIC_AUTO_ROUTING_ENABLED=false` | Claude fora do automático | Continua disponível por seleção explícita, sujeito à elegibilidade |

## 8. Fronteira de evidência

As afirmações acima descrevem comportamento identificável no código do provider
registry/policy/gateway. Elas não certificam configuração produtiva, disponibilidade
de credencial, qualidade jurídica, cobertura de todos os consumidores ou
homologação de autonomia.

Para cada alteração futura na política, registrar no PR o estado:

- **EXISTENTE**: caminho de código identificado e teste reproduzível;
- **PARCIAL**: componente existe, mas falta cobertura/integração;
- **ALVO**: requisito ainda não implementado;
- **BLOQUEADO**: não promover até dependência explícita ser satisfeita.

Critérios mínimos para afirmar política homologada no SHA:

| ID | Critério | Evidência mínima |
|---|---|---|
| PROV-01 | rotina automática não seleciona Maritaca/Claude | teste parametrizado observando provider final |
| PROV-02 | mérito não degrada silenciosamente para Groq | teste negativo da cadeia final |
| PROV-03 | provider solicitado inelegível falha sem fallback silencioso | teste com flag/chave ausente |
| SEC-01 | `AI_ENABLED=false` bloqueia provider local e externo | teste de registry + entrypoint |
| SEC-02 | `AI_EXTERNAL_PROVIDERS_ALLOWED=false` impede despacho externo | teste com spies/mocks no gateway |
| SEC-03 | PII residual não chega a provider externo | teste negativo na policy e barreira final |
| CLAUDE-01 | Claude não entra no automático com rollback flag desligada | teste de tarefas econômica/complexa |
| MANUS-01 | Manus não é tratado como provider deste registry | teste/inventário de integração separado |

Um status/check verde de documentação não substitui esses testes quando o runtime
for alterado.
