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

---

## 9. Dívida 5.2 fechada — peça e análise passam pela validação canônica

**O achado.** As duas saídas de maior valor jurídico do sistema — a minuta de peça
(`peca_service.gerar_peca_pipeline`) e a análise estratégica (`analise_estrategica.analisar_caso`)
— eram as únicas que **não** passavam pelo `response_validator`. Rodavam apenas o
`citation_check`, isolado. Consequência prática, medida no código:

| Proteção do núcleo | Orquestrador | Peça (antes) | Análise (antes) |
|---|---|---|---|
| Citações contra a base oficial | sim | sim | sim |
| Grounding ao vivo (nº CNJ, faixa de súmula, redação superada) | sim | **não** | **não** |
| Promessa de resultado (vedação OAB) | sim | **não** | **não** |
| Marca "SEM BASE VERIFICÁVEL" | sim | **não** | **não** |
| Carimbo HITL (`is_rascunho`/`requer_revisao`/`status_hitl`) | sim | parcial (só texto de aviso) | **não** |

Ou seja: uma minuta que prometesse êxito ao cliente saía do sistema sem nenhum alerta, e uma
peça sem uma única âncora verificável era entregue com a mesma aparência de uma peça
fundamentada.

**A correção.** Ambas passaram a chamar `response_validator.validar(db, ..., exige_fonte=True,
fontes=...)` — a mesma função, com os mesmos parâmetros que o orquestrador usa — e a terminar com
`hitl_policy.aplicar()`. Duas decisões de forma, tomadas por diferença de suporte:

- **Peça** tem corpo de texto, então a marca "SEM BASE VERIFICÁVEL" vai no **corpo do documento**
  — e é o documento marcado que é persistido em `LegalDoc.conteudo` e em `AILog.resposta`. O
  revisor não tem como não ver.
- **Análise** é JSON, sem corpo para prefixar: os alertas do validador entram na **mesma lista
  `alertas`** que a interface já renderiza (somados aos do modelo, nunca substituindo), e as
  flags viram `sem_base_verificavel` / `revisao_obrigatoria`.

Em ambas, o teor **não é reescrito**: promessa de resultado vira alerta, nunca correção
silenciosa — reescrever esconderia do revisor exatamente o que ele precisa corrigir. E ambas são
fail-safe: validação indisponível não derruba a entrega, vira alerta e revisão obrigatória.

**Superfície.** O `PecaGeneratorModal` ganhou o painel "Alertas da validação jurídica", ao lado do
painel anti-alucinação que já existia — sem ele os alertas chegariam ao payload e morreriam lá.

**Regressão.** `backend/tests/test_peca_analise_validacao_hitl.py` (9 testes) cobre carimbo HITL,
promessa de resultado alertada sem reescrita, marca de ausência de âncora persistida no banco,
citação confirmada como âncora suficiente e o comportamento fail-safe.

---

## 10. Dívida 5.5 fechada — isolamento do RAG por CASO

**O achado.** O ingestor do DJEN (`ingestors/djen.py`) grava `case_id` em cada comunicação
processual e o comentário do próprio código diz por quê: *"recuperável apenas dentro do caso e do
cliente donos do processo"*. A recuperação nunca usou esse campo — o único filtro era
`kd.client_id = :scope_cli`. Consequência: a intimação do **caso A** entrava como contexto do
**caso B do mesmo cliente**. Um contrato escrito no ingest e não cumprido na leitura.

Isso não é só ruído: o modelo recebe prazo, ato e órgão de OUTRO processo no mesmo bloco de
"fontes internas" e pode fundamentar a peça deste caso com o andamento daquele.

**A correção.** `buscar_contexto_rag` ganhou `scope_case_id`, aplicado nas **quatro pernas** da
recuperação (vetorial, trigram, FTS e o fallback ILIKE):

```sql
AND (kd.categoria <> ALL(:case_cats) OR kd.case_id IS NULL OR kd.case_id = :scope_case)
```

Duas escolhas explícitas:

- **Documento sem `case_id`** (acervo antigo, ingestão manual) continua visível no escopo do
  cliente. Cortá-lo derrubaria recall de conteúdo legítimo, e o vínculo por cliente já é
  garantido pelo filtro anterior.
- **Sem `scope_case_id`, nada muda.** Consulta de nível cliente (dossiê, pesquisa ampla) segue
  exatamente como antes — o filtro só existe quando há caso no escopo.

Isso torna o repasse do `scope_case_id` a peça crítica, então ele foi ligado em todos os call
sites que sabem em que caso estão: `context_builder` (orquestrador), `peca_service`,
`analise_estrategica`, `anexos_service` e `checklist_ia`. Um teste de regressão cobra esse
repasse por módulo — sem ele o filtro existiria e nunca atuaria.

**Regressão.** 5 testes novos em `backend/tests/test_rag_isolation.py`: categoria escopada,
fragmento SQL (incluindo a tolerância a `case_id IS NULL`), filtro presente com caso, consulta
inalterada sem caso, e o repasse nos cinco call sites.

---

## 11. P2-13 fechado — alarme de envelhecimento dos dados jurídicos embutidos

Duas verdades jurídicas do sistema não vivem no banco nem em fonte consultada ao vivo: são
constantes Python, conferidas à mão numa data e nunca mais. O problema não é existirem — é o
silêncio quando envelhecem.

- **`SUMULA_TETO`** (`verificador_jurisprudencia.py`) — o número da última súmula editada por
  tribunal. Súmula ACIMA do teto é marcada como provável alucinação. Envelhecido o teto, uma
  súmula **nova e verdadeira** passa a ser acusada de inexistente. Esse falso positivo é pior que
  o falso negativo: desacredita o gate inteiro aos olhos do advogado, que passa a ignorá-lo.
- **`DATA_CONFERENCIA`** (`sumulas_ingestion.py`) — a data em que cada verbete do seed foi
  reconferido contra fonte oficial. Súmula cancelada depois disso segue indexada como vigente.

**A correção.** `services/vigencia_dados_juridicos.py` mede a idade de cada constante contra um
limite de 180 dias e devolve o alerta **com o arquivo a reconferir** — alarme sem endereço não é
acionável. Data ilegível conta como vencida: não saber a idade do dado é exatamente o estado que
o alarme existe para eliminar.

Dois consumidores:

1. **`GET /ia-saude/estado-operacional`** ganhou a seção `base_juridica` (itens, dias desde a
   conferência, alertas, `desatualizado`).
2. **O próprio gate**: com o teto vencido, o aviso de súmula acima da faixa deixa de afirmar
   *"provavelmente não existe"* e passa a dizer que a tabela não é reconferida desde a data X,
   mandando confirmar na fonte oficial. O gate continua marcando a citação como suspeita — muda o
   que ele **afirma** ao revisor, que é o que evita descartar súmula verdadeira.

**Regressão.** `backend/tests/test_vigencia_dados_juridicos.py` (7 testes), com `hoje` injetado
para não depender do relógio, cobrindo os dois comportamentos do gate.

---

## 12. P2 fechado — os quatro prompts rasos que serviam agentes de mérito

A auditoria mediu quatro chaves de prompt que entregavam a agentes jurídicos ou **uma frase** ou
o **prompt de outra tarefa**:

| Chave | Agente | Antes | Agora |
|---|---|---|---|
| `bancario` | BankForensicsAgent | uma frase no `__init__.py` | módulo próprio, 10 eixos |
| `seguranca_lgpd` | DigitalLGPDAgent | uma frase no `__init__.py` | módulo próprio, 9 eixos |
| `pesquisa_juridica` | RAGResearchAgent | prompt de análise de caso | método de pesquisa com fonte |
| `audiencia` | rota de audiência | prompt de análise de caso | roteiro de sala por rito |

As duas últimas eram erro de **forma**, não só de profundidade: quem pede pesquisa recebia um
relatório estratégico de nove seções, e quem preparava audiência recebia a mesma coisa — nenhum
dos dois é o que se usa na hora.

O que cada um passou a exigir:

- **Bancário** ancora a tese na **data do contrato** (capitalização após 31/03/2000 — Súmula 539
  STJ; tarifas por período), separa o que é abusivo do que só parece (Súmula 382 STJ: 12% ao ano
  não é abusivo por si), traz fortuito interno (Súmula 479 STJ), comissão de permanência (Súmula
  472 STJ), busca e apreensão (Dec.-Lei 911/1969) e a regra supletiva da Lei 14.905/2024. Onde a
  referência exige conferência (temas repetitivos de tarifas, resolução CMN vigente), o prompt
  manda confirmar em vez de completar com número plausível.
- **LGPD/Digital** obriga a nomear controlador e operador antes de atribuir responsabilidade,
  trata **consentimento como uma base entre várias** (e a mais frágil), separa o regime do dado
  sensível (art. 11), e registra que o **sigilo profissional do advogado é dever autônomo e mais
  restritivo** que a LGPD — base legal de tratamento não autoriza revelar o que o sigilo protege.
  Inclui a regra de que a própria resposta nunca reproduz o segredo que analisa.
- **Audiência** identifica o **rito antes do roteiro** (CPC, CLT 843-852, JEC, CPP 400-405) e
  entrega as perguntas escritas na íntegra, com pena de confissão (CPC 385 §1º), contradita
  (CPC 457 §1º) e o que **consignar em ata** — o protesto é o que preserva a matéria para o
  recurso. Por ser ato irrepetível, passou do modelo econômico para o forte (3.000 tokens).
- **Pesquisa jurídica** impõe hierarquia de fontes (com o rol vinculante do CPC art. 927),
  conferência de vigência e de superação, **contraponto obrigatório** (pesquisa que só confirma a
  hipótese do cliente é armadilha), grau de confiança declarado e a marca "SEM BASE VERIFICÁVEL
  NO CONTEXTO" no lugar de completar com número plausível.

**Regressão.** `backend/tests/test_system_prompts_profundidade.py` (8 testes): prompt próprio por
chave, piso de profundidade, honestidade epistêmica, e as âncoras específicas de cada área.

---

## 13. Dívida 5.3 — inventário canônico de prompts e rastreabilidade de versão

**O achado.** Dezenas de prompts espalhados por módulos, sem lugar único que dissesse quais
existem, quem os consome e **qual versão produziu determinada saída**. Duas consequências:

- um erro jurídico numa peça não é rastreável até a instrução que o causou;
- chave **fantasma** (consumida por um agente e ausente do registro) faz o núcleo cair no prompt
  `default` — o advogado recebe resposta genérica onde deveria haver especialização, sem nenhum
  erro visível. É a pior classe de falha: silenciosa e plausível.

**A correção.** `system_prompts/inventario.py` monta o inventário **derivado** — nunca digitado.
Lê `SYSTEM_PROMPTS`, `PROMPT_EXTRAS`, o `AGENT_REGISTRY` e o router; uma lista escrita à mão
envelheceria como qualquer outra constante, que é o problema que o módulo existe para resolver.
Cada linha traz chave, tipo, **versão** (sha256 truncado do conteúdo), tamanho, consumidores e a
marca de órfão.

A versão não é semântica: muda quando o texto muda — exatamente a pergunta a responder
("a peça de ontem saiu deste prompt ou do anterior?").

**O inventário já achou uma coisa ao ser escrito:** a chave `dossie` existia em `SYSTEM_PROMPTS` e
não era consumida por ninguém — o router usava `analise_caso` para a tarefa `DOSSIE`. Passou a
consumir a própria chave (hoje com o mesmo texto, então sem mudança de comportamento), o que
zera os órfãos e permite que o dossiê divirja depois sem mexer no router.

**Onde aparece.**

- `GET /ia-governanca/prompts-sistema` (admin/sócio) — inventário completo, com `orfaos` e
  `fantasmas`. Distinto de `/ia-governanca/prompts`, que lista os prompts jurídicos do usuário.
- A saída do orquestrador carrega `prompt_key` e `prompt_versao`.
- O payload de conclusão da peça carrega `prompt_versao` — a impressão do prompt **final**
  montado (perfil de complexidade + especialização de área + padrão ouro), que é o texto que de
  fato redigiu a minuta.

**O que ficou de fora, e por quê.** Gravar a versão numa **coluna do `ai_logs`** exige migration.
O repositório tem head único e `test_alembic_single_head.py` fixa o head à mão — "dois PRs com
migration conflitam ali por construção" (`MIGRATION_RESERVATIONS.md`). Como este PR não tem
migration nenhuma, criar uma agora custaria conflito garantido com qualquer PR de schema em
andamento, por um ganho que já está 90% entregue: a versão é calculada num lugar só
(`inventario.impressao`) e chega ao consumidor da resposta. **A coluna é uma tarefa de um PR
dedicado**, e a decisão de quando fazê-la é do titular.

**Regressão.** `backend/tests/test_inventario_prompts.py` (8 testes): cobertura do registro,
ausência de fantasmas e de órfãos, estabilidade da impressão, e a chegada da versão às duas
superfícies de saída.

---

## 14. P2-9 fechado — o 409 do gate de citações deixou de ser beco sem saída

**O achado, e ele era pior do que a auditoria descreveu.** O gate antialucinação devolve **409**
quando a peça cita o que a base oficial não confirma, e o backend já tinha o override auditável
(`override_citacoes` + `justificativa_override`) em `PATCH /ai/logs/{id}/hitl`. Mas o caminho que
o advogado usa de fato — `POST /legal-docs/{id}/conferir-e-assinar`, o **único** caminho de
aprovação de peça na tela de Peças — chamava o gate com o override **fixo em `False`**:

```python
await aplicar_gate_hitl(db, log, "revisado", False, None, cu)
```

Ou seja: com política `bloquear` (o default) e uma citação bloqueante, a peça ficava **impossível
de aprovar pela interface**. O advogado via uma mensagem de erro e o fluxo morria ali — sem
corrigir, sem assumir, sem trilha. Um gate que não pode ser respondido não protege: ele empurra o
trabalho para fora do sistema, que é exatamente o critério de lançamento deste projeto.

**A correção, nas duas pontas.**

- **Backend** — `LegalDocAprovacao` ganhou `override_citacoes` (default `False`) e
  `justificativa_override`; `conferir-e-assinar` repassa os dois ao `aplicar_gate_hitl`, que
  continua exigindo justificativa (422 se vazia) e registrando o override em `fontes_rag` e em
  `audit_logs`. A decisão também entra no detalhe do `APROVAR_HITL`. **Nada foi afrouxado**: quem
  não pede override não recebe override, e o override sem justificativa continua rejeitado.
- **Frontend** — o dialog de aprovação em `Pecas.tsx` passou a tratar o 409: mostra as citações
  bloqueantes com o aviso de cada uma e a confiabilidade, e abre o campo de justificativa. O botão
  muda para "Aprovar assumindo as citações", e o envio só ocorre com a justificativa escrita. O
  texto da peça **não é reescrito** — corrigir ou assumir é decisão do advogado, e é ela que fica
  registrada com o nome dele.

**Regressão.** `backend/tests/test_legal_doc_flow_contract.py` (+2: repasse do override e defaults
seguros do schema) e `frontend/src/pages/Pecas.citacoes.test.tsx` (4: o 409 vira decisão no
dialog, override não sai sem justificativa, override sai com ela, e aprovação normal não manda
override nenhum).

---

## 15. Cadeia de provedores e piso de raciocínio — o que puxava a inteligência para baixo

O titular perguntou, em 18/08, por que o **Ollama** aparecia na configuração ("não sei se é pra
rodar a chave Grok, ou se não tem necessidade dele"), informou que as chaves de **Anthropic,
Maritaca e Groq estão preenchidas e válidas**, e pediu que o nível de inteligência fosse
**altíssimo**.

### O que o Ollama é (e o que ele não é)

O Ollama **não tem relação nenhuma com a chave da Groq**, nem com qualquer provedor externo. Ele
é a **IA local**: roda modelos abertos dentro do próprio VPS. Existe por um motivo específico — é
o único provedor que pode ver conteúdo que **não pode sair do servidor**.

Isso não é teórico. `sanitization_policy` classifica nove rótulos como **sigilo reforçado**
(`criminal`, `penal`, `familia`, `saude`, `medico`, `menores`, `infancia_juventude`, `violencia`,
`violencia_domestica`): nessas áreas o conteúdo não vai a provedor externo nem pseudonimizado,
porque a combinação de fatos raros permite reidentificação sem identificador direto. A regra é
fail-closed: **sem IA local, a IA dessas áreas fica indisponível**.

> **Decisão pendente do titular.** O escritório atende Família e Criminal — estão na identidade do
> próprio prompt. Hoje, em produção, a IA **não atende** essas áreas, e isso não estava visível em
> lugar nenhum. São duas saídas, e as duas são decisão do titular: **(a)** subir a IA local
> (`docker compose --profile ia-local up -d` + `OLLAMA_ENABLED=true`), ou **(b)** decidir que essas
> áreas podem ir a provedor externo **pseudonimizado**, ajustando `AI_SANITIZATION_MODE_MAP`.
> Não tomei essa decisão: ela é de sigilo profissional e de dado pessoal sensível.

Fora dessas áreas, o Ollama não é necessário — e é por isso que o desligamento pedido é seguro.

### Três defaults que puxavam a qualidade para baixo

| O que | Antes | Agora |
|---|---|---|
| `AI_PROVIDER_PRIORITY` | `ollama,anthropic,maritaca,groq` | `anthropic,maritaca,groq,ollama` |
| `OLLAMA_ENABLED` | `True` | `False` (opt-in, como toda integração do repo) |
| Piso de raciocínio | `"padrao"` para quem não pedisse nível | mérito `maximo`, demais prosa `alto` |

O primeiro item era o mais caro: **um modelo local de 8-14B na frente do Claude** para redigir
peça e analisar caso. O `docker-compose` de produção já corrigia isso por env — e o comentário de
`ROTEAMENTO_PROVIDER_MEDIO` no próprio `config.py` registrava o motivo ("o stack de produção não
sobe ollama... apontar o tier médio para provider morto só gerava tentativa-e-fallback a cada
tarefa"). O **default do código** é que continuava dizendo o contrário, e ele vale para tudo que
roda fora do compose: dev, testes, scripts, um deploy alternativo.

O terceiro item é o que mais muda na prática, porque **atinge produção**: `_aplicar_nivel` usava
`nivel_inteligencia or "padrao"`, e a maior parte dos call sites chama o gateway sem pedir nível.
O protocolo de raciocínio sênior (FIRAC, fonte por premissa, contraditório) existia e ficava
desligado justamente nas chamadas que mais precisam dele. Agora o piso vem por **perfil de
tarefa**:

- **mérito jurídico** (`analise_juridica`, `elaboracao_peca`, `estrategia`, `auditoria_peca`,
  `analise_contrato`, `jurimetria`, `critica_adversarial`) → `maximo`;
- **demais tarefas de prosa** → `alto`;
- **saída JSON** (`prazos`, `honorarios`, `triagem`) e **econômicas** (`resumo`, `chat_rapido`) →
  `padrao`. Nas de JSON o valor está na fidelidade do formato, e instrução de raciocínio em prosa
  disputaria com o "SAÍDA OBRIGATÓRIA — JSON" do próprio prompt; elas já foram elevadas pelo outro
  caminho, o **modelo forte**.

Custo: `maximo` produz resposta mais longa e mais cara. É deliberado e é o que foi pedido — para
trabalho jurídico de mérito, a resposta rasa custa mais caro que o token. Ambos os pisos são
configuráveis (`AI_NIVEL_INTELIGENCIA_MERITO`, `AI_NIVEL_INTELIGENCIA_PADRAO`).

### Duas fontes de verdade que divergiam

- **Ordem da cadeia.** A `AIProviderPolicy` decidia "tarefa complexa → Anthropic priorizado" e o
  `ai_gateway` **ignorava** essa decisão, resolvendo a cadeia só por `AI_PROVIDER_PRIORITY`. Quem
  valia era o gateway. Agora a regra é uma só, aplicada no gateway; fora do mérito, a ordem
  configurada continua mandando (é assim que se escolhe local-first).
- **Elegibilidade de provedor.** Havia três cópias da regra (gateway, policy, registry) e só a do
  registry checava `GROQ_ENABLED` — o kill-switch do Groq só valia depois que
  `provider_registry_runtime.instalar()` trocava as funções. Fora do runtime (testes, scripts,
  worker sem o patch) a policy dizia "elegível" para provedor desligado. As duas definições
  estáticas passaram a delegar ao registry.

### O que exige ação fora do código

**O `.env` do VPS sobrescreve o default do código.** Não tenho (nem devo ter) acesso a ele, então:

1. `AI_PROVIDER_PRIORITY` e `OLLAMA_ENABLED` — o `docker-compose.yml` já passa os valores certos
   (`anthropic,maritaca,groq,ollama` e `false`) para backend e worker. **Nada a fazer**, a não ser
   conferir que o `.env` não os sobrescreve de volta.
2. `AI_NIVEL_INTELIGENCIA_MERITO` / `AI_NIVEL_INTELIGENCIA_PADRAO` — **novos**; não estão no `.env`
   nem no compose, então o default do código (`maximo`/`alto`) vale imediatamente após o deploy.
3. Conferir o estado real em `GET /api/ia-governanca/provedores`: sistema "100%" = Anthropic,
   Maritaca e Groq com `motivo_inelegivel: null`. O Ollama aparecerá como inelegível — é o
   esperado enquanto a IA local não for necessária.
4. **`ANTHROPIC_MODEL_COMPLEXO` está em `claude-opus-4-8`.** Não troquei: apontar para um modelo a
   que a conta talvez não tenha acesso derrubaria toda a IA jurídica de uma vez. Se o titular
   quiser o modelo mais capaz disponível na conta, é uma linha de `.env` — e a conferência de
   acesso tem que vir antes.

**Regressão.** `backend/tests/test_cadeia_provedores_qualidade.py` (13 testes): defaults de
configuração, piso por perfil de tarefa (incluindo aliases), preservação do nível explícito do
chamador, kill-switch do Groq nas três definições, e o aviso das áreas sem IA. Mais dois testes
reescritos em `test_anthropic_gateway.py` e `test_roteamento_gateway.py`, que fixavam o
comportamento antigo ("soberania local primeiro") e agora fixam o novo — com um teste extra
provando que, fora do mérito, a ordem configurada continua sendo respeitada.

---

## 16. Retrieval RAG — duas pernas aditivas ligadas por padrão

Última rodada da auditoria (18/08): com a cadeia de provedores e o piso de raciocínio já
corrigidos (§15), o próximo alavancador de qualidade era o **retrieval** — de nada adianta o
modelo mais forte raciocinando sobre um contexto pior do que podia ser.

Duas pernas do RRF híbrido existiam no código, prontas e testadas, e vinham **desligadas por
padrão** só por não terem sido validadas em produção:

- **`RAG_FTS_ENABLED`** — perna léxica full-text (tsvector `portuguese`, estilo BM25), melhor que
  a busca semântica para termos raros e citações exatas (número de artigo, súmula, processo CNJ).
  Usa o índice GIN já existente (migration 001) — **sem migration nova**.
- **`RAG_HYDE_ENABLED`** — gera uma "resposta hipotética" curta e barata e a embute na busca
  vetorial, melhorando o recall quando o vocabulário do caso novo diverge do registrado. Custa uma
  chamada extra barata (tier econômico) por busca.

Ambas são **aditivas** à fusão RRF (somam candidato, nunca removem) e **fail-safe** (erro cai no
comportamento de antes — nunca derruba a busca). Não há como esta mudança piorar recall; no pior
caso, o resultado é idêntico ao de antes.

**O que ficou explicitamente de fora, e por quê:** `RAG_RERANK_ENABLED` continua desligado. O
único cross-encoder multilíngue do fastembed pinado tem licença **CC-BY-NC-4.0**, incompatível
com uso empresarial; o alternativo com licença MIT (`BAAI/bge-reranker-base`) "não deve ser
ativado sem medir qualidade no corpus jurídico em português" — é a única trava desta rodada que
não é uma questão de configuração, é uma decisão que precisa de dado de avaliação que não existe
ainda. Ligá-lo às cegas poderia **piorar** o ranking (reranker treinado majoritariamente em
inglês, sem eval em PT-BR jurídico), o oposto do que foi pedido.

**Regressão.** `backend/tests/test_cadeia_provedores_qualidade.py` ganhou o teste que fixa os três
defaults juntos (HyDE e FTS ligados, rerank desligado com o motivo).

### Itens que seguem fora do alcance de código (revalidados nesta rodada)

- **A-2** (base verificável rasa: 27 súmulas / 41 diplomas) — populá-la exige **curadoria
  jurídica** de conteúdo oficial verificado. Não é tarefa de código: escrever "súmulas" ou
  "diplomas" novos sem fonte oficial conferida violaria a própria regra que a auditoria inteira
  existe para proteger (`NUNCA invente lei, súmula, jurisprudência`). Fica para ingestão de
  documentos reais, sob revisão de advogado.
- **A-8** (gold set real) — mesma razão: exige curadoria de advogado sobre casos reais.
- **DataJud/grounding ao vivo** (`DATAJUD_ENABLED`, `AI_GROUNDING_DATAJUD_ENABLED`) — seguem OFF
  por padrão: são rede externa ao CNJ, e toda integração externa nasce opt-in neste repositório
  (regra de design do CLAUDE.md). Ligar exige decisão operacional (rate limit público, chave se
  houver) — não é ajuste de qualidade unilateral.
- **`CITACOES_MODO_ESTRITO`** — permanece `False` por desenho: o próprio comentário do código
  avisa que ligá-lo antes de a base estar abrangente (ver A-2) geraria falso-positivo em citação
  real ainda não ingerida. Ligar isso agora **pioraria** a experiência, não melhoraria.
