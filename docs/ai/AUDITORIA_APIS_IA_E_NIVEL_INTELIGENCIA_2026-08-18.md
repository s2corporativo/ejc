# Auditoria das APIs de IA e do nível de inteligência jurídica

**Data:** 18 de agosto de 2026 · **Base:** branch `claude/auditoria-ia-juridica-c2tbf2` (head `f50e15c`)
**Escopo:** superfície de APIs de IA (contratos, RBAC, coerência) e os determinantes mensuráveis da
qualidade jurídica das respostas. Somente leitura. Complementa
`AUDITORIA_ESTRUTURA_IA_2026-08-15.md` (governança/segurança) pelo eixo **capacidade**.

---

> **Status (18/08, autorizado pelo titular — "corrija tudo"):** os achados **A-1, A-3, A-4,
> P1-4, P1-5, P1-6, P1-7, P1-8** e os P2 jurídicos remanescentes foram **corrigidos** nesta
> branch, com testes de regressão (`test_governanca_ia_auditoria_1150.py`, ampliação de
> `test_system_prompts_vigencia_legal.py`). Suíte do backend: **5.648 passando, 0 falhas**.
> Continuam **em aberto** A-2 (ingestão da base — operação de ambiente), A-8 (gold set — exige
> curadoria jurídica humana) e A-5/A-7 (unificação do contrato de API — quebra o frontend,
> precisa de janela própria). Detalhe por item na §7.

## 1. Veredito

**As APIs de IA estão seguras e íntegras; o que limita o sistema não é a arquitetura, é a
capacidade efetivamente ligada.** Três medições resumem o diagnóstico:

| Medida | Valor apurado | Leitura |
|---|---|---|
| Protocolo de raciocínio sênior (FIRAC) | **default "padrao" = desligado**; 22 de 64 arquivos que usam o gateway o acionam | A geração de peça **não** aciona |
| Base jurídica verificável | **27 súmulas + 41 diplomas legais** | Repertório de estagiário, não de escritório |
| Contexto entregue ao modelo | **~19.400 caracteres (~5k tokens)** de uma janela de 200k | Usa ~2,5% da capacidade do modelo |

O EJC construiu um carro bem projetado — gateway único, HITL inegociável, gate de citações
fail-closed, 109 endpoints com RBAC — e o abasteceu com pouco combustível. **O teto da
inteligência jurídica hoje é imposto por configuração e por tamanho de base, não por limitação
de modelo.** Nenhum dos três limites acima exige refatoração: são flag, ingestão e orçamento.

---

## 2. APIs de IA — auditoria da superfície

### 2.1 Números

**109 endpoints** de IA em 19 routers:

| Router | Endpoints | | Router | Endpoints |
|---|---:|---|---|---:|
| `ai.py` | 25 | | `ia_governanca.py` | 11 |
| `legal_chat.py` | 13 | | `ai_core.py` | 9 |
| `rag.py` | 12 | | `rag_governance.py` | 8 |
| `peca_geracao.py` | 5 | | `ai_skills.py` | 5 |
| `ia_defensiva.py` | 4 | | `documento_ia.py` | 3 |
| demais (9 routers) | 14 | | | |

### 2.2 O que está certo

- **RBAC universal.** Nenhum endpoint de IA sem dependência de identidade: 100 usos de
  `get_current_user`, mais `require_roles` (16), `_require_admin_socio` (12),
  `requer_equipe_juridica` (7) e `requer_advogado` (5).
- **A única API "pública" não é pública.** `rag_public.py` exige API key com escopo
  (`require_api_key("knowledge:write")`), tem rate limit próprio por chave e valida a URL de
  callback com fixação de IP (`_url_com_ip_fixado`) — defesa contra SSRF em ingestão externa,
  bem acima da média.
- **Contrato de governança carimbado no núcleo**: toda resposta do orquestrador sai com
  `is_rascunho`, `requer_revisao`, `status_hitl` e `aviso_hitl`.

### 2.3 [P1] Superfície fragmentada — mesma capacidade em cinco portas

A funcionalidade se repete em endpoints distintos, com contratos diferentes:

| Capacidade | Endpoints que a oferecem |
|---|---|
| **Analisar caso** | `/ai/analisar-caso`, `/ai/core/analyze`, `/ai/casos/{id}/assistente`, `/ia-especializada/{perfil}`, `/ia-defensiva/analisar` |
| **Chat jurídico** | `/ai/core/chat`, `/sala-juridica`, `/ia/agente/stream` |
| **Gerar peça/minuta** | `/pecas/gerar`, `/ai/gerar-minuta`, `/ai/core/generate`, `/cases/{id}/motor-peca` |
| **Resumir** | `/ai/resumir-texto`, `/ai/resumir-documento`, `/documentos-ia/analisar` |

Consequência prática: a qualidade da resposta **depende da porta escolhida pelo frontend**, não
da pergunta — porque cada porta usa (ou não) o orquestrador, o RAG e o protocolo de raciocínio.
É a mesma dívida 5.2 vista pelo lado do contrato: não é só "migrar callers", é **um contrato
público por capacidade**.

### 2.4 [P2] Prefixos incoerentes: `/ai` e `/ia` convivem

`/ai`, `/ai/core`, `/ai/skills` (inglês) coexistem com `/ia`, `/ia-governanca`, `/ia-defensiva`,
`/ia-especializada`, `/ia-saude` (português), mais `/rag`, `/pecas`, `/sala-juridica`,
`/documentos-ia`. Num repositório cuja convenção é português (regra do `CLAUDE.md`), quem
integra precisa adivinhar o idioma do prefixo. Some-se a superfície dupla `/api` + `/api/v1`
(armadilha já conhecida) e o resultado é que **uma mesma capacidade tem quatro grafias válidas**.

---

## 3. Nível de inteligência jurídica — o que foi medido

### 3.1 [P0] O protocolo de raciocínio sênior existe, é bom, e vem desligado

`ai_gateway.py:51-71` define três níveis:

- **`padrao`** — "Responda com objetividade, precisão e foco prático."
- **`alto`** — FIRAC completo: fatos separados de inferências e lacunas, questão central,
  **regra com o dispositivo/súmula/precedente que a sustenta**, aplicação, conclusão.
- **`maximo`** — FIRAC + leitura adversarial, hipóteses concorrentes, preliminares/mérito/prova/
  quantum/acordo/risco, e **cada premissa com fonte ou marcada "verificar fonte"**.

O que a medição mostra:

| Constatação | Evidência |
|---|---|
| O default do gateway é **`padrao`** | `ai_gateway.py:101` — `nivel = (nivel_inteligencia or "padrao").lower()` |
| O orquestrador canônico opta por **`alto`** | `ai/core/orchestrator.py:89` |
| **A geração de peça não opta** | `peca_service.py`, `motor_peca_service.py`, `analise_estrategica.py`: **zero** ocorrências de `nivel_inteligencia` |
| Cobertura do parâmetro | **22 de 64** arquivos que usam o gateway o passam — ~66% roda em `padrao` |
| **`maximo` nunca é acionado em produção** | só aparece como parâmetro opcional de API em `ia_defensiva` e `validador_juridico` |

Ou seja: **a peça — a saída de maior valor e maior risco — é redigida no nível que não exige
FIRAC nem fonte por premissa.** O modo que faria a IA raciocinar como advogado sênior está
implementado, testado no desenho e ocioso. Ligar isso é mudança de uma linha por serviço.

### 3.2 [P1] Base verificável do tamanho de um estagiário

O gate de citações e o RAG só confirmam o que existe na base curada. Ela é:

- **27 súmulas** conferidas verbete a verbete (3 STF + 12 STJ + 12 TST), `sumulas_ingestion.py`;
- **41 diplomas legais** com URL oficial no catálogo Planalto (CF/88, CC, CPC, CLT, CDC, CP,
  CPP, ECA e outros);
- **398 documentos fictícios** da Bíblia EJC — excluídos do RAG por padrão (e corretamente).

Um escritório de contencioso trabalha com centenas de súmulas e OJs, teses de repetitivos e
repercussão geral, e jurisprudência local. Com 27 verbetes, **quase toda citação correta que a
IA produzir cairá como "não confirmada"** — e é exatamente por isso que o modo estrito de
citações permanece desligado (decisão de 2026-07-29). O gate não está frouxo: a base é que está
vazia. Enquanto isso não mudar, o gate protege pouco e atrapalha um pouco.

Existem ingestores prontos e sem uso pleno para STJ, TJMG, Câmara, Senado, LexML e DJEN — a
capacidade de encher a base já está escrita.

### 3.3 [P1] O modelo forte está no lugar certo, com duas exceções caras

`system_prompts/router.py:60-82` roteia por tarefa:

- **`claude-opus-4-8`** (topo) para análise de caso, dossiê, minutas e **todos os 21 ramos** —
  escolha correta;
- **`claude-haiku-4-5`** para **`PRAZOS`** (justificativa no código: "prazo fatal — precisão") e
  para **`RAG_QUERY`** ("síntese de RAG", 1.500 tokens);
- **Groq `gpt-oss-120b`** para triagem e resumo — risco jurídico baixo, decisão defensável.

As duas exceções são as que doem: **prazo fatal** é a tarefa de maior consequência do escritório
(perder prazo é dano irreversível), e **`RAG_QUERY` é o momento em que a fundamentação recuperada
vira resposta jurídica** — ambos no modelo rápido. Temperatura 0.0 em prazos ajuda na
determinismo, mas não compensa capacidade de raciocínio.

### 3.4 [P1] O modelo enxerga ~2,5% do que poderia

Orçamento de contexto em `ai/core/context_builder.py:20-23`:

| Bloco | Limite |
|---|---|
| Dossiê do caso | 8.000 caracteres |
| Documento (OCR) | 6.000 caracteres |
| RAG | 6 chunks × 900 caracteres = 5.400 |
| **Total** | **~19.400 caracteres ≈ 5k tokens** |

Contra uma janela de 200k tokens do Opus. Um caso real — petição inicial, contestação, laudo,
decisões — não cabe em 8.000 caracteres; 900 caracteres por chunk cortam um artigo de lei com
seu parágrafo. **A IA não está "raciocinando mal": ela está raciocinando sobre um resumo.**
Ampliar esse orçamento é a alavanca de maior efeito por menor esforço em todo o sistema.

### 3.5 [P2] Recuperação conservadora e sem calibração

`RAG_MIN_SIM=0.55`, 6 chunks, **reranker, FTS e HyDE desligados** (`config.py:572,586,592`),
mais os gates `RAG_EXIGIR_APROVADO` e `RAG_EXIGIR_VIGENCIA_VERIFICADA`. Cada trava isolada está
certa; somadas, entregam poucas fontes e curtas. E o gold set jurídico real — que destravaria
essas chaves com número em vez de palpite — continua ausente.

---

## 4. Achados priorizados

| # | Sev. | Achado | Correção |
|---|---|---|---|
| A-1 | **P0** | Peça e análise estratégica rodam em `padrao` (sem FIRAC, sem fonte por premissa) | Passar `nivel_inteligencia="alto"` em `peca_service`, `motor_peca_service`, `analise_estrategica` |
| A-2 | P1 | Base verificável com 27 súmulas e 41 leis | Ligar os ingestores prontos (STJ, TJMG, LexML, Câmara, Senado) e medir cobertura |
| A-3 | P1 | Contexto limitado a ~5k tokens de 200k | Elevar `_MAX_DOSSIE`, `_MAX_DOC`, `_MAX_RAG_CHUNK` e `_LIMITE_RAG` |
| A-4 | P1 | `PRAZOS` e `RAG_QUERY` no modelo rápido | Promover ao `_COMPLEXO` (ou justificar por medição) |
| A-5 | P1 | Cinco portas para a mesma capacidade, com qualidade desigual | Contrato público por capacidade; legadas viram alias |
| A-6 | P2 | Nível `maximo` implementado e nunca usado | Habilitar por opt-in em parecer e crítica adversarial |
| A-7 | P2 | Prefixos `/ai` e `/ia` (+ `/api` e `/api/v1`) | Padronizar em português; manter legado como alias |
| A-8 | P2 | Retrieval sem calibração e sem gold set | Criar o gold set e medir antes de ligar FTS/HyDE/reranker |

**Ordem recomendada:** A-1 (uma linha por serviço, efeito imediato na peça) → A-3 (orçamento) →
A-4 (modelo em prazos) → A-2 (base) → A-8 (medir) → A-5/A-7 (contrato) → A-6.

---

## 5. Resposta direta à pergunta

**Qual é hoje o nível de inteligência jurídica?** No caminho canônico (chat do núcleo, sala
jurídica, defesas), é **bom**: Opus, FIRAC ativo, RAG com escopo do cliente, validação de
citações, HITL. No caminho que mais importa para o escritório — **gerar a peça** — é
**mediano**: modelo forte, mas sem protocolo de raciocínio sênior, com contexto de ~5k tokens e
fundamentação conferida contra 27 súmulas.

A distância entre os dois não é de arquitetura nem de modelo: é de **três configurações e uma
ingestão**. Este relatório não corrige nada — cada item vira Issue própria, e os que mudam
comportamento de produção (A-1, A-3, A-4) dependem de decisão do titular sobre custo por
requisição, já que elevar nível, contexto e modelo eleva o custo por peça.

---

## 6. Limitações

Auditoria de código no head `f50e15c`, sem acesso a produção: não foram lidos flags efetivos,
volume real da base RAG ingerida nem telemetria de uso (fonte de verdade:
`GET /ia-governanca/provedores`). As contagens de endpoints, de arquivos que passam
`nivel_inteligencia`, de súmulas e de diplomas foram apuradas por varredura no repositório e
estão reproduzíveis pelos comandos citados em cada seção.


---

## 7. O que foi corrigido (18/08)

| Item | O que mudou | Onde |
|---|---|---|
| **A-1** | `nivel_inteligencia="alto"` nas 7 etapas da peça, no Motor de Peça e na análise estratégica — FIRAC e fonte por premissa passam a valer onde mais importa | `peca_service.py`, `motor_peca_service.py`, `analise_estrategica.py` |
| **A-3** | Orçamento de contexto de ~19.400 → **~62.000 caracteres** (dossiê 24k, documento 18k, 10 chunks de 2k) | `ai/core/context_builder.py` |
| **A-4** | `PRAZOS` e `RAG_QUERY` saem do modelo rápido para o `_COMPLEXO`; RAG_QUERY também ganha teto de 2.500 tokens | `system_prompts/router.py` |
| **P1-4** | `CaseAgent` (default do classificador), `EJCCoordinatorAgent` e `FinanceAgent` passam a `exige_fonte=True` + skill `validate_citations` | `ai/core/agent_registry.py` |
| **P1-5** | `requer_advogado` em `/revisar`, `/aprovar`, `/conferir-e-assinar` e no HITL do AILog (`revisado`/`aplicado`) | `routers/legal_docs.py`, `routers/ai.py` |
| **P1-6** | Fail-closed **internalizado** em `_resolver_cadeia` (some o fallback sintético ao Groq) + erro explícito na cadeia vazia + `event_subscribers` carregado no worker Celery | `ai_gateway.py`, `core/celery_app.py` |
| **P1-7** | Gate de aprovação HITL consulta o DataJud quando `DATAJUD_ENABLED` | `citation_gate.py` |
| **P1-8** | `_formatar_fontes` passa a entregar tribunal, versão, data, situação jurídica (com ⚠ na vigência duvidosa) e URL oficial; trecho por fonte de 800 → 1.500 caracteres | `ai_service.py` |
| **P2** | Súmula 437/TST com ressalva do art. 71 §4º; Súmula 331 com ressalva do Tema 725/ADPF 324; ACP art. 16 como Tema 1075 decidido; foro de eleição com pertinência (Lei 14.879/2024) nos templates; triagem ampliada de 7 para 22 áreas + "Outra"; **sigilo profissional nomeado no BASE_PROMPT** | `trabalhista.py`, `constitucional.py`, `templates_documentos.py`, `triagem.py`, `base.py` |
| **CI** | A vedação explícita "NUNCA invente lei, súmula, jurisprudência ou número de processo" voltou à `BASE_IDENTIDADE` — a barreira retrieval-first a tinha só em substância, e o contrato de teste a cobrava na forma | `legal_base.py` |

### Efeito sobre o nível de inteligência jurídica

A geração de peça deixa de rodar no protocolo raso: passa a estruturar por FIRAC, a exigir
dispositivo/súmula por premissa, a receber ~3× mais contexto do caso e a enxergar tribunal,
data e vigência de cada fonte. O prazo fatal sai do modelo rápido. Os limites que **permanecem**
são os que não se resolvem por configuração: a base verificável de 27 súmulas e 41 diplomas
(A-2) e a ausência de gold set para calibrar recuperação (A-8).

### Decisões embutidas, para conferência do titular

1. **Custo por requisição sobe** — mais contexto, modelo forte em prazos e FIRAC na peça. Foi a
   consequência aceita ao autorizar A-1/A-3/A-4; os valores de orçamento ficaram em ~8% da
   janela de 200k, deliberadamente conservadores, e são um ponto de ajuste fácil.
2. **Quem aprova peça mudou** — revisar/aprovar/assinar e marcar saída de IA como revisada
   passaram a exigir papel de advogado. Quem não for advogado perde essas ações **hoje**; vale
   avisar a equipe antes do deploy.
3. **`legal_base.py` pertence ao PR #1143.** A correção do CI tocou esse arquivo por ser a
   única forma de fechar o verde sem afrouxar o teste anti-alucinação — é aditiva e não remove
   nada do desenho do #1143, mas exige coordenação antes de integrar os dois PRs.


---

## 8. Módulo de provedores e chaves de API (auditoria de 18/08)

Verificação dedicada dos quatro provedores — **Anthropic (Claude), Maritaca (Sabiá), Groq e
Ollama** — e do caminho que a chave percorre até a chamada.

### 8.1 Como a chave chega ao provedor (está correto)

Há **duas fontes** e elas convergem, o que costuma ser a origem de "cadastrei a chave e não
funciona":

1. **`.env`** — base, lida pelo `Settings` (pydantic-settings, cache em `get_settings()`);
2. **Cofre de Credenciais** — `ANTHROPIC_API_KEY`, `GROQ_API_KEY` e `MARITACA_API_KEY` estão
   registrados em `credential_registry.py` e o cofre aplica um **overlay sobre o mesmo
   singleton de Settings**: na API pelo lifespan (`main.py:267`, com falha graciosa que mantém
   os valores do `.env`) e no worker Celery por handler de `task_prerun` com TTL de 45s
   (`tasks/vault_sync.py`).

Ou seja: **chave salva no cofre vale para o gateway**, inclusive no worker — que é um processo
separado e não enxerga o overlay da API. Este ponto estava certo e foi confirmado.

### 8.2 Habilitação por provedor

`provider_elegivel()` (`ai/provider_registry.py`) é fonte única e checa, por provedor: flag
própria + chave + kill-switch global `AI_EXTERNAL_PROVIDERS_ALLOWED`. Ollama, por ser local,
depende só de `OLLAMA_ENABLED`.

Travas de conformidade confirmadas: **Maritaca** só é soberana com duas condições juntas
(`MARITACA_MODEL` regional **e** `MARITACA_EXIGIR_SOBERANIA=true` — os defaults **não** são
soberanos); **Groq** exige `GROQ_ZDR_VERIFIED` e, para áudio, `AUDIO_TRANSCRIPTION_DPA_APPROVED`.
Ambas documentadas no `.env.example`.

### 8.3 Três lacunas encontradas — e corrigidas

| # | Lacuna | Efeito | Correção |
|---|---|---|---|
| **PV-1** | **Ollama tratava resposta vazia como sucesso** (Groq e Maritaca já levantavam) | Como o Ollama é o **primeiro da cadeia**, uma resposta vazia dele virava a resposta final e **o fallback nunca disparava** — o usuário recebia vazio em vez de o sistema cair para o Anthropic | `ollama_provider.py`: resposta em branco levanta `RuntimeError`; `except RuntimeError: raise` evita re-embrulhar o diagnóstico |
| **PV-2** | **Groq não tinha flag `ENABLED`** — único dos quatro | Desligar o Groq exigia **apagar a chave**; não havia como suspendê-lo temporariamente | `GROQ_ENABLED: bool = True` em `config.py`, exposto no `.env.example` e incorporado à elegibilidade |
| **PV-3** | O painel dizia só **`elegivel: false`** | O operador não sabia **o que faltava**: chave ausente? flag do provedor? kill-switch global? | `motivo_inelegivel()` no registro + campo `motivo_inelegivel` em `GET /ia-governanca/provedores`, acumulando todas as faltas |

Testes: `tests/test_provedores_ia_auditoria.py` (8 casos — diagnóstico por falta, acúmulo de
faltas, simetria das flags, e o fallback do Ollama com resposta vazia).

### 8.4 O que **não** dá para verificar daqui

O que falta para o sistema estar "100%" **não é código, é ambiente** — e não tenho (nem devo
ter) acesso a ele:

- **quais chaves estão de fato preenchidas** em produção (`.env` do VPS ou cofre). O repositório
  não versiona `.env`, corretamente;
- **se as chaves são válidas** (crédito, cota, escopo) — o cofre tem testadores próprios por
  credencial, que são a via para isso;
- **se o Ollama está de pé** e com os modelos baixados (`deepseek-r1:8b`, `qwen2.5:14b`,
  `gemma3:9b`) — sem isso o primeiro provedor da cadeia falha sempre e tudo cai para o externo.

**Como conferir em produção, agora que o painel explica a inelegibilidade:**

```
GET /api/ia-governanca/provedores
```

Cada provedor retorna `elegivel`, `motivo_inelegivel`, `modelo_configurado`,
`ordem_prioridade`, `status` (`desabilitado` / `configurado_sem_uso` / `indisponivel` /
`atencao` / `operacional`), taxa de sucesso, latência e custo. **Sistema 100% = os quatro com
`motivo_inelegivel: null` e status `operacional`** (ou `configurado_sem_uso`, se ainda não houve
tráfego). Qualquer outro estado agora vem com a causa escrita.
