Vou consolidar o mapa da arquitetura de prompts diretamente a partir dos quatro mapeamentos verificados. Não preciso ler arquivos — os mapeadores já fizeram a verificação e meu trabalho é sintetizar com segurança.

# Mapa da Arquitetura de Prompts — EJC (guia para IA-03)

## 0. Resumo e princípio de segurança

Este documento consolida quatro mapeamentos verificados da arquitetura de prompts anti-alucinação do EJC. Ele **guia** a consolidação IA-03 — **nada será executado aqui**. Toda remoção de regra inline fica condicionada à ordem segura descrita na seção 5.

**Princípio de segurança (regra absoluta OAB do escritório):** *"NUNCA inventar jurisprudência, leis, súmulas ou número de processo"*. Em termos operacionais isso significa: **toda chamada ao LLM precisa carregar, em algum lugar do system prompt, uma barreira anti-alucinação.** Hoje essa barreira vem de duas formas — uma base central injetada pelo gateway, ou uma regra escrita inline no próprio fluxo. A consolidação é perigosa porque **muitas regras inline são a ÚNICA barreira do fluxo** (não há base central cobrindo aquele `task_type`). Removê-las antes de garantir cobertura central reintroduz risco de alucinação exatamente nos pontos mais sensíveis (redação de minuta, triagem de caso, análise de documento, pesquisa de jurisprudência).

**Achado central:** o pacote `system_prompts/` já é canônico e DRY — **não há nada a consolidar dentro dele**. A duplicação real e o risco estão **fora** dele: nos system prompts inline dos fluxos que passam (ou não) pelo `ai_gateway`. E a maior parte desses inlines é **PROTEÇÃO ÚNICA, não redundância**.

**Veredito quantitativo (do inventário consolidado):** de ~33 regras inline mapeadas, apenas **~6 são genuinamente redundantes** (seguras de encolher); **~24 são PROTEÇÃO ÚNICA** (remover viola a regra OAB); e há ainda **lacunas silenciosas** (fluxos sem base e sem inline — risco preexistente).

---

## 1. As fontes de prompt hoje (as 3 arquiteturas + a base do gateway)

Existem **três arquiteturas de prompt coexistindo** e **três camadas independentes de injeção da base**. O risco da consolidação está em confundi-las.

### 1.1 Arquitetura canônica moderna (a fonte boa)

- **`backend/app/services/system_prompts/base.py`** — FONTE CANÔNICA LONGA. Define `IDENTIDADE`, `RESTRICOES` (16 regras numeradas: OAB 1-5, integridade jurídica 6-10 incluindo *"NUNCA invente acórdão/súmula/artigo/processo"*, LGPD 11-14, revisão humana 15-16), `COMPORTAMENTO`, `AVISO_RASCUNHO` e `BASE_PROMPT = IDENTIDADE + RESTRICOES + COMPORTAMENTO`. Importa `DADOS_ESCRITORIO` de `templates_documentos.py`.
- **Pacote `system_prompts/` completo** — todos os 6 módulos de tarefa (`triagem`, `analise_caso`, `minutas`, `prazos`, `honorarios`, `ambiental`) fazem `BASE_PROMPT + prompt_específico + AVISO_RASCUNHO`. Até os 3 prompts inline do `__init__.py` (`rag_query`, `resumo`, `default`) reusam `BASE_PROMPT`. **Arquitetura limpa, sem consolidação interna necessária.**
- **`backend/app/services/legal_base.py`** — FONTE CANÔNICA CURTA. Define `BASE_IDENTIDADE` (versão curta: identidade + 2 proibições — *"NUNCA invente lei/súmula/jurisprudência/processo"* + *"NUNCA prometa resultado"* + nota de RASCUNHO) e a função `aplicar_base(messages, task_type)`.

### 1.2 As três camadas de injeção (mecânica)

| Camada | Fonte da base | Como injeta | Cobertura | Arquivo-chave |
|---|---|---|---|---|
| **A. Gateway moderno (`legal_base`)** | `BASE_IDENTIDADE` (curta, 2 regras) | `aplicar_base(messages, task_type)` — prepend ao 1º system, idempotente (detecta `[IDENTIDADE]`), aditivo | SÓ se `task_type ∈ _TASKS_COM_BASE` | `legal_base.py:25-41`, chamado em `ai_gateway.py:126` |
| **B. Módulo profissional (`SYSTEM_PROMPTS`)** | `BASE_PROMPT` (longa, 16 regras) | Cada prompt em `SYSTEM_PROMPTS` **já começa com `BASE_PROMPT`** | Toda tarefa que passa por `executar_tarefa_ia` | `system_prompts/__init__.py`, `ai_gateway.py:287` |
| **C. Pipeline legada (`ai_service` etc.)** | NENHUMA central | `get_groq()` direto / `client.chat.completions.create` | NÃO recebe A nem B — só a regra inline do próprio arquivo | `ai_service.py`, `ia_extra.py`, `case_intel.py` |

### 1.3 Os dois subsistemas paralelos no gateway (silos sem interseção)

Dentro do mesmo `ai_gateway.py` há **dois subsistemas desconectados, com vocabulários de tarefa incompatíveis**:

| Subsistema | Função (linha) | Fonte de prompt | Vocabulário | Base |
|---|---|---|---|---|
| **A — `chat()`** | `ai_gateway.py:102` (aplicar_base L126) | system prompt **inline** em cada router/service | `TASK_ROUTING`: `analise_juridica`, `elaboracao_peca`, `resumo`, `chat_rapido`, `estrategia`, `auditoria_peca`, `analise_contrato`, `jurimetria` | só `BASE_IDENTIDADE` (curta), e **só** se task ∈ `_TASKS_COM_BASE` |
| **B — `executar_tarefa_ia()`** | `ai_gateway.py:287` (SYSTEM_PROMPTS L291) | `SYSTEM_PROMPTS` (pacote `system_prompts/`) | enum `TarefaIA`: triagem, analise_caso, minutas, prazos, honorarios, ambiental… | `BASE_PROMPT` completo (16 regras) já embutido |

**Fato crítico:** `chat()` é chamado por ~20 lugares; `executar_tarefa_ia()` é chamado por **UM único endpoint** — `routers/ai_tools.py:79` (`POST /api/v1/ai/executar`). `chat()` **nunca** toca `SYSTEM_PROMPTS`; `executar_tarefa_ia()` **nunca** chama `aplicar_base`. São silos. **Uma consolidação que assuma "a base central já cobre tudo" está errada — ela só cobre o caminho correspondente.**

### 1.4 As três arquiteturas de origem do prompt

| Arquitetura | Onde | Recebe base canônica? | Risco ao mexer |
|---|---|---|---|
| **Canônica moderna** | `system_prompts/base.py` + `legal_base.py` | é a própria fonte | n/a |
| **Gateway moderno** | `ai_gateway.chat` + `executar_tarefa_ia` | sim (prosa) / via SYSTEM_PROMPTS | baixo |
| **LEGADA (`ai_service.py`)** | 6 constantes `SYSTEM_*` chamando `get_groq()` direto | **NÃO** | **ALTO — proteção única** |
| **EM BANCO (`PromptJuridico`)** | `models/prompt_juridico.py` + `routers/prompts_juridicos.py` | sim, indiretamente (passa pelo gateway) | baixo (não duplica regras) |

---

## 2. Fonte canônica recomendada (qual adotar como única)

**Adotar `system_prompts/base.py` (`BASE_PROMPT`, 16 regras) como a fonte única de verdade.**

Justificativa:
- `BASE_PROMPT` é **estritamente mais forte** que `BASE_IDENTIDADE`: 16 regras numeradas (OAB + integridade jurídica + LGPD + revisão humana) + `COMPORTAMENTO` + `AVISO_RASCUNHO`, contra apenas 2 proibições na versão curta.
- **Duplicação canônica oculta:** `base.py` (`BASE_PROMPT`) e `legal_base.py` (`BASE_IDENTIDADE`) são **textos independentes mantidos à mão**. Eles já divergem hoje (drift de wording) e tendem a divergir mais. A consolidação deve fazer `BASE_IDENTIDADE` **derivar de** `base.py` (ou ser substituída por ele), eliminando o drift.
- O pacote `system_prompts/` **não deve ser tocado** — já é DRY e canônico.

**Recomendação adicional:** unificar também o vocabulário de tarefa. Hoje `enum TarefaIA` (subsistema B) e `TASK_ROUTING`/`_TASKS_COM_BASE` (subsistema A) são sets independentes e dessincronizados (ex.: `redacao_peca` está em `_TASKS_COM_BASE` mas não no `TASK_ROUTING`, caindo no default `analise_juridica` para roteamento de modelo; `analise_contrato`/`jurimetria` estão no routing mas sem caller real). Consolidar um set sem o outro gera comportamento inconsistente.

**Cautela JSON:** `AVISO_RASCUNHO` e o `BASE_PROMPT` longo entram bem em fluxos de **prosa**, mas tarefas de **saída estruturada** (JSON) foram excluídas da base **por design** para não quebrar `_parse_json`/`_parse_itens`. Adotar a base única exige uma variante compatível com JSON (ver seção 5).

---

## 3. Quais fluxos recebem a base central e quais NÃO

`legal_base._TASKS_COM_BASE = {estrategia, auditoria_peca, elaboracao_peca, redacao_peca, chat_rapido}`. `aplicar_base` só age se `task_type` estiver nesse set; caso contrário **retorna as messages intactas** (`legal_base.py:33`).

### Tabela task_type → recebe_base (Camada A)

| task_type | recebe base curta? | racional no código |
|---|---|---|
| `estrategia` | **SIM** | prosa estratégica |
| `auditoria_peca` | **SIM** | prosa |
| `elaboracao_peca` | **SIM** | prosa (redação de peça) |
| `redacao_peca` | **SIM** | prosa — porém **fora** do `TASK_ROUTING`, cai no default `analise_juridica` para roteamento de modelo |
| `chat_rapido` | **SIM** | prosa |
| `analise_juridica` | **NÃO** | excluído por design (saída JSON) — **mas vários callers o usam para PROSA jurídica** |
| `resumo` | **NÃO** | excluído por design (não interferir no formato) |
| `analise_contrato` | **NÃO** | está no `TASK_ROUTING` mas fora de `_TASKS_COM_BASE`; nenhum caller real encontrado |
| `jurimetria` | **NÃO** | idem — sem caller real |

**Implicações diretas:**
1. **Camada B (`SYSTEM_PROMPTS`)** está coberta integralmente — acionada apenas via `executar_tarefa_ia()` → `routers/ai_tools.py:79`. Toda tarefa do enum `TarefaIA` já embute `BASE_PROMPT`.
2. **Camada C (`get_groq()` direto)** **nunca** recebe base — `aplicar_base` é inalcançável ali.
3. O grande furo de cobertura é `analise_juridica` e `resumo`: estão **fora** da base por serem "JSON", mas na prática carregam muita prosa jurídica (perfis de IA, teses, etapas de peça, FAQ). Esses são os fluxos onde a regra inline é a única proteção.
4. **`PromptJuridico` (banco):** o endpoint `POST /{id}/executar` usa `task_type` default `analise_juridica` (schema), que **não** está em `_TASKS_COM_BASE`. Logo, prompts da biblioteca executados com o default **rodam sem base**. Não é duplicação — é exposição que depende da escolha do usuário.

---

## 4. Inventário de regras inline — REDUNDANTE (seguro remover) vs PROTEÇÃO ÚNICA (não remover)

**Regra de classificação:** o caller passa um `task_type` que recebe base (Camada A) OU passa por `executar_tarefa_ia` (Camada B)? Se **SIM** e ainda tem regra inline → **REDUNDANTE** (seguro encolher). Se **NÃO** → a inline é a única barreira → **PROTEÇÃO ÚNICA** (remover viola a regra OAB).

### 4.1 REDUNDANTE (recebe base central + duplica inline) — seguro encolher, NÃO deletar

Todas usam `task_type ∈ {redacao_peca, chat_rapido, auditoria_peca, estrategia, elaboracao_peca}`.

| Arquivo:linha | task_type | regra inline | observação |
|---|---|---|---|
| `services/peca_service.py:314-321` (etapa 7 redação) | `elaboracao_peca` ✅ | "Nunca invente fatos, artigos ou julgados… nunca prometa resultado" | inline mais detalhada que a base curta |
| `routers/assistente.py:56-70` (chat do caso) | `chat_rapido` ✅ | "NÃO invente fatos, lei, súmula ou nº de processo… rascunho" | |
| `routers/ia_especializada.py` perfil **jurídica** | `redacao_peca` ✅ | "Nunca invente jurisprudência… nunca promessa de resultado" | só este perfil é redundante (ver 4.2) |
| `routers/qualidade.py:24-30` `_SYS_CONSIST` | `auditoria_peca` ✅ | "NÃO invente conteúdo" | |
| `routers/qualidade.py:32-37` `_SYS_ADVERSARIO` | `estrategia` ✅ | "NÃO invente lei, súmula ou jurisprudência… NÃO prometa resultado" | |
| `services/dossie_service.py:193,197` (`_montar_prompt`) | `estrategia` ✅ | "NUNCA prometa resultado… não invente fatos, julgados ou artigos" | |

**Casos especiais (manter por função, não por ética):**
- `services/analise_estrategica.py:159-161` (grounding RAG, `estrategia` ✅): redundante quanto à identidade, **mas é instrução de uso do RAG** ("baseie-se SOMENTE nestes precedentes; NÃO invente fora daqui") — **manter o corpo**.
- `routers/ai.py:442-453` `system2` (dual-IA crítica): formato de auditoria, sem regra anti-invenção própria — instrução funcional, manter.

**Aviso sobre "redundante":** mesmo nos fluxos cobertos, `aplicar_base` injeta só `BASE_IDENTIDADE` (2 regras), e várias inline são **mais específicas** ("não invente datas/prazos", "cite só itens do contexto"). Encolher sem elevar a base ao nível das 16 regras **degrada a proteção**. Por isso a recomendação é **encurtar/referenciar, não deletar**, e só depois de a base central ser fortalecida.

### 4.2 PROTEÇÃO ÚNICA (NÃO recebe base — inline é a única barreira) — remover é PERIGOSO

**Subgrupo (a): Gateway + task fora da base (`analise_juridica` / `resumo`)**

| Arquivo:linha | task_type | regra inline (única proteção) |
|---|---|---|
| `routers/ia_especializada.py:18` perfil comercial | `analise_juridica` | "sem prometer resultado… Nunca invente dados" |
| `routers/assistente.py:81-96` `_SYS_PRAZOS` | `analise_juridica` | "NÃO invente datas nem prazos" (saída JSON) |
| `services/documento_service.py:24-29,110,187` `REGRAS` | `analise_juridica` | "não invente CPF/processo/súmula/lei… cite SOMENTE itens do contexto… NUNCA prometa resultado" |
| `services/peca_service.py:236-242` (etapa 4 jurisprudência) | `analise_juridica` | "NUNCA invente julgados. Se não houver, diga explicitamente" |
| `routers/teses.py:341-352` (recomendar/`/sugerir-ia`) | `analise_juridica` | "Não invente julgados ou artigos" |
| `routers/teses.py:468-474` (gerar/`/motor`) | `analise_juridica` | "PROIBIDO inventar julgado/súmula… NUNCA prometa resultado" |
| `routers/honorarios_oab.py:26-29,115` `REGRAS` | `analise_juridica` | "NUNCA invente número de item… NUNCA prometa resultado" |
| `routers/analise_bancaria.py:17-20,95` `REGRAS` | `analise_juridica` | "NÃO invente súmulas, leis… NUNCA prometa resultado" |
| `routers/conteudo.py:21-31` `_SYS_FAQ` / `_SYS_GLOSSARIO` | `resumo` | "NÃO invente lei, súmula ou número… NUNCA prometa resultado" |
| `services/checklist_ia.py:24-31,83` `_SYS_CHECKLIST` | `resumo` | "NUNCA invente número de lei/súmula" |
| `services/movimento_ia.py:22-26,60` `_SYS` | `resumo` | "NÃO invente prazos/valores/nomes/fatos… NÃO prometa resultado" |
| `services/visual_law.py:16` | `resumo` | "Não invente datas, partes ou fatos" |
| `routers/ai.py:244-253` `SYSTEM_ASSISTENTE_CASO` | misto (modo dominante `analise_juridica`/`resumo`) | "Nunca invente fatos, julgados ou artigos… Nunca prometa resultado" |
| `routers/ai.py:427-430` `system1` (dual IA-1) | misto, parcial | só "RASCUNHO — revisão obrigatória" (frágil, sem "não invente" próprio) |

**Subgrupo (b): Camada C — fluxos que NEM passam pelo gateway (`get_groq()` direto)**

Aqui `aplicar_base` é **inalcançável**. Remover a inline = **zero proteção**. Inclui pontos de altíssimo risco (redação de minuta, triagem de caso).

| Arquivo:linha | constante | função / endpoint vivo |
|---|---|---|
| `services/ai_service.py:42` `SYSTEM_ANALISE_CASO` | `analisar_caso` (legada) | `ai.py:39` — Groq direto (L361) |
| `services/ai_service.py:67` `SYSTEM_RESUMO_DOC` | `resumir_documento` | `ai.py:84` — Groq direto (L419) |
| `services/ai_service.py:473` `SYSTEM_TESES_OCULTAS` | `detectar_teses_ocultas` | `ai.py:191` — Groq direto (L560) |
| `services/ai_service.py:498` `SYSTEM_AUDITOR_PECA` | `auditar_peca` | `ai.py:209` — Groq direto (L591) |
| `services/ai_service.py:520` `SYSTEM_AUDIENCIA` | `preparar_audiencia` | `ai.py:224` — Groq direto (L621) |
| `services/ai_service.py:641` `SYSTEM_ANALISE_CONTRATO` | `analisar_contrato` | `ai.py:664` — Groq direto (L697) |
| `routers/ia_extra.py:51-55` `SYS_TRADUZIR` | tradução | Groq direto |
| `routers/ia_extra.py:78-81` `SYS_RESUMIR` | resumo | Groq direto |
| `routers/ia_extra.py:107-112` `SYS_MINUTA` | **redação de minuta** | Groq direto — **peça redigida sem base** |
| `routers/ia_extra.py:140-144` `SYS_PESQUISA` | pesquisa | Groq direto |
| `routers/ia_extra.py:182-192` `SYS_HONORARIOS` | honorários | Groq direto |
| `services/case_intel.py:32-48` `SYS_TRIAGEM` | **triagem de caso** | Groq direto |
| `services/case_intel.py:146-154` `SYS_ENCERRAMENTO` | encerramento | Groq direto |

As 6 funções de `ai_service.py` estão **vivas em produção** — não são código morto. Suas regras inline são equivalentes funcionais às regras 1, 3, 6, 8, 10 de `RESTRICOES`, escritas de forma independente.

### 4.3 LACUNAS SILENCIOSAS (não recebe base E não tem regra inline) — risco preexistente

Não é redundância nem proteção — é **ausência**. A consolidação não deve ignorar nem assumir como coberto.

| Arquivo:linha | task_type | situação |
|---|---|---|
| `services/peca_service.py:154,193,259,285` (etapas 1,2,3,5,6) | `analise_juridica` | system prompts SEM regra anti-alucinação E sem base. São etapas intermediárias (enquadramento/argumentos/riscos) cujo texto **alimenta a peça final** — risco de alucinação propagada. |
| `routers/ia_especializada.py` perfis atendimento/financeira/societária | `analise_juridica` | usam `analise_juridica` sem regra inline E sem base — rodam **sem nenhuma barreira explícita** hoje. |
| `routers/prompts_juridicos.py:240` | `req.task_type` **arbitrário do request** | envia **só `{"role":"user"}`, SEM system message**. Se o task do request ∉ `_TASKS_COM_BASE`, a chamada vai ao LLM **sem identidade E sem regra anti-alucinação**. É o furo mais grave e **independe da consolidação** — corrigir já. |

### 4.4 Síntese do inventário

- **Sem consolidação interna:** pacote `system_prompts/` (canônico, DRY) e `PromptJuridico` (template de usuário, delega ao gateway, não duplica regras).
- **REDUNDANTE (encolher, não deletar):** ~6 ocorrências — `peca_service` etapa 7, `assistente` chat, `ia_especializada` perfil jurídica, `qualidade` ×2, `dossie_service`.
- **PROTEÇÃO ÚNICA (não remover):** ~24 ocorrências, divididas entre gateway-fora-da-base (subgrupo a) e Camada C fora do gateway (subgrupo b).
- **LACUNAS:** etapas intermediárias de `peca_service`, perfis sem regra de `ia_especializada`, e o furo de `prompts_juridicos.py:240`.

---

## 5. Plano de consolidação SEGURO, em passos

Cada passo é verificável. Os passos 1, 3 e 4 **exigem deploy + avaliação do comportamento da IA** (rodar fluxos reais e checar se a saída não alucina e não quebra parse JSON).

> **Não tocar no pacote `system_prompts/` em nenhum passo** — já é canônico.

**Passo 0 — Correção independente e imediata (não espera nada):**
Corrigir `routers/prompts_juridicos.py:240` para sempre incluir um system message com a base, e **não** confiar no `task_type` arbitrário do request. É o furo mais grave e não depende da consolidação.
*Verificável:* inspeção do código + teste de execução de um prompt da biblioteca observando que a base entra no system. **Exige avaliação do comportamento da IA.**

**Passo 1 — Unificar e fortalecer a base no gateway (sem remover nada inline ainda):**
- (1a) Fazer `legal_base.BASE_IDENTIDADE` **derivar de** `system_prompts/base.py` (ou ser substituída por `BASE_PROMPT`), eliminando o drift de wording. Elevar a base injetada ao nível das 16 regras.
- (1b) Criar uma variante **`BASE_ESTRUTURADA`** curta e compatível com JSON (instrução anti-alucinação que não polui o parse).
- (1c) Ampliar `_TASKS_COM_BASE` para incluir `analise_juridica` (com `BASE_ESTRUTURADA` quando a saída for JSON; base de prosa quando for prosa) e avaliar `resumo`.
- (1d) Garantir que `chat()` também anexe o `AVISO_RASCUNHO` (hoje ausente no Caminho A).
*Verificável:* rodar `tests/test_legal_base.py`; confirmar idempotência; **deploy + avaliação**: rodar fluxos `analise_juridica`/`resumo` e checar que o JSON não quebra (`_parse_json`/`_parse_itens`) e que a base aparece.

**Passo 2 — Migrar a Camada C para o gateway (antes de tocar nas inlines dela):**
Rotear `ai_service.py` (6 funções), `ia_extra.py` e `case_intel.py` para `ai_gateway.chat(messages, task_type=...)` com `task_type` coberto pela base. **Migração não-trivial:** essas funções têm pipeline própria (`buscar_contexto_rag`, `AILog`/`_log_ai`, formato de saída estruturado) que o gateway **não replica 1:1** — preservar logging HITL e grounding RAG.
*Cuidado de homônimos:* existem **duas `analisar_caso`** — a legada (`ai_service.py`, Groq direto, sem base, `ai.py:39`) é a desprotegida; a moderna (`analise_estrategica.py:100`, via gateway com `task_type="estrategia"` + grounding RAG) **já está coberta**. Não confundir.
*Cuidado de task_type:* ao migrar `resumir_documento`, escolher um task de **prosa** coberto, **não** `resumo` (que não recebe base).
*Verificável:* **deploy + avaliação** dos 6 endpoints de `ai.py` (L39,84,191,209,224,664) e dos endpoints de `ia_extra`/`case_intel` — confirmar base injetada, logging e RAG intactos.

**Passo 3 — Cobrir as lacunas silenciosas:**
- Etapas intermediárias 1,2,3,5,6 de `peca_service.py`: garantir base (via task coberto após Passo 1).
- Perfis atendimento/financeira/societária de `ia_especializada.py`: garantir base.
*Verificável:* **deploy + avaliação** da geração de peça ponta a ponta.

**Passo 4 — Só então remover/encolher as inlines REDUNDANTES, uma a uma:**
Para cada item da seção 4.1, confirmar o `task_type` do call site na tabela, encurtar (não deletar) preservando qualquer instrução específica (datas/prazos, "cite só o contexto", formato JSON, grounding RAG). Avaliar após **cada** remoção.
*Verificável:* diff isolado por call site + **deploy + avaliação** do fluxo correspondente.

**Passo 5 — Sincronizar vocabulários e o `PromptJuridico`:**
Alinhar `_TASKS_COM_BASE`, `TASK_ROUTING` e `enum TarefaIA`; avaliar mudar o `task_type` default do executor de `PromptJuridico` para um valor coberto pela base.
*Verificável:* inspeção + **avaliação** de execução da biblioteca.

---

## 6. Riscos e regra de ouro

**REGRA DE OURO:** *Nunca remover a única proteção anti-alucinação de um fluxo.* Antes de remover qualquer regra inline, **a base central tem de estar comprovadamente injetada naquele `task_type`/fluxo** (e em wording igual ou mais forte). Na dúvida sobre se um call site recebe base, **não remover**.

**Riscos concretos (do consolidado dos mapeadores):**

1. **Remover inline de `analise_juridica`/`resumo` sem antes incluí-los em `_TASKS_COM_BASE`** deixa o fluxo sem qualquer barreira — viola "NUNCA inventar jurisprudência". São proteção única: `ia_especializada` (perfil comercial + lacuna atendimento/financeira/societária), `peca_service` etapa 4, `teses` ×2, `assistente`/detectar-prazos, `documento_service`, `honorarios_oab`, `analise_bancaria`, `conteudo`, `checklist_ia`, `movimento_ia`, `visual_law`.

2. **Camada C é inalcançável pela base:** `ai_service.py`, `ia_extra.py`, `case_intel.py` chamam `get_groq()` direto. Inclui redação de minuta (`SYS_MINUTA`) e triagem de caso (`SYS_TRIAGEM`) — alto risco. Migrar ao gateway **antes** de mexer nas inlines.

3. **`prompts_juridicos.py:240`** envia só `{"role":"user"}` sem system e com task arbitrário do request — furo mais grave, independe da consolidação, corrigir já (Passo 0).

4. **Drift de wording / consolidar "para o lado fraco":** `BASE_IDENTIDADE` (2 regras) é muito mais fraca que `BASE_PROMPT` (16 regras + LGPD + COMPORTAMENTO). Consolidar deve **elevar tudo ao `BASE_PROMPT`**, nunca rebaixar. E como os dois textos são mantidos à mão, é preciso derivar um do outro para não divergirem.

5. **Saída estruturada (JSON):** ampliar `aplicar_base` para `analise_juridica`/`resumo` sem uma `BASE_ESTRUTURADA` compatível pode **poluir a saída e quebrar** `_parse_json`/`_parse_itens`.

6. **Silos sem interseção:** `chat()` nunca toca `SYSTEM_PROMPTS`; `executar_tarefa_ia()` nunca chama `aplicar_base`. Não assumir cobertura cruzada. Além disso, `chat()` hoje não anexa `AVISO_RASCUNHO` — preservar/adicionar ao unificar.

7. **Lacunas silenciosas propagadas:** etapas intermediárias de `peca_service` sem base nem inline alimentam a peça final — alucinação propagada que a consolidação não pode ignorar.

8. **Vocabulários dessincronizados:** `_TASKS_COM_BASE`, `TASK_ROUTING` e `enum TarefaIA` são sets independentes (`redacao_peca` recebe base mas não tem rota de modelo; `analise_contrato`/`jurimetria` têm rota mas sem caller). Mexer num set sem o outro gera inconsistência.

9. **Migração não-trivial da Camada C:** pipeline própria (RAG, `AILog`/HITL, formato estruturado) não replicada 1:1 pelo gateway — migração apressada quebra logging e grounding.

10. **Ordem das operações é obrigatória:** (0) corrigir `prompts_juridicos.py`; (1) fortalecer/ampliar base no gateway + `tests/test_legal_base.py`; (2) migrar Camada C; (3) cobrir lacunas; (4) só então encolher inlines redundantes uma a uma; (5) sincronizar vocabulários. **Inverter a ordem reintroduz alucinação em produção nos fluxos mais sensíveis.**

---

**Arquivos-chave (paths absolutos):**
- Fonte canônica longa: `C:/Users/User/EJC/backend/app/services/system_prompts/base.py`
- Agregador + map prompt_key: `C:/Users/User/EJC/backend/app/services/system_prompts/__init__.py`
- Router de tarefa/modelo: `C:/Users/User/EJC/backend/app/services/system_prompts/router.py`
- Base curta + `aplicar_base`: `C:/Users/User/EJC/backend/app/services/legal_base.py`
- Gateway (dois caminhos): `C:/Users/User/EJC/backend/app/services/ai_gateway.py` (chat L102-177; aplicar_base L126; executar_tarefa_ia L287-322; SYSTEM_PROMPTS L291)
- Único caller do Caminho B: `C:/Users/User/EJC/backend/app/routers/ai_tools.py` (L79)
- Camada C (fora do gateway): `C:/Users/User/EJC/backend/app/services/ai_service.py`, `C:/Users/User/EJC/backend/app/routers/ia_extra.py`, `C:/Users/User/EJC/backend/app/services/case_intel.py`
- Furo grave: `C:/Users/User/EJC/backend/app/routers/prompts_juridicos.py` (L240)
- Demais callers com proteção única inline: `routers/ia_especializada.py`, `routers/teses.py`, `routers/assistente.py`, `routers/honorarios_oab.py`, `routers/analise_bancaria.py`, `routers/conteudo.py`, `routers/qualidade.py`, `routers/ai.py`, `services/documento_service.py`, `services/peca_service.py`, `services/checklist_ia.py`, `services/movimento_ia.py`, `services/visual_law.py`, `services/dossie_service.py`, `services/analise_estrategica.py`