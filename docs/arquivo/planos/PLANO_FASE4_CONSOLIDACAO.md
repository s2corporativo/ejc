Vou consolidar o plano da Fase 4 a partir dos mapeamentos verificados. Como é um documento de planejamento (nada será executado), produzo o Markdown diretamente.

# Plano de Consolidação — Fase 4 (EJC)

> Documento de PLANEJAMENTO. Nada aqui é executado agora. Baseado exclusivamente nos mapeamentos verificados dos domínios IA, Honorários e Dossiê/Análise + blast radius de frontend. Princípios reitores: **Controle > Velocidade** e **Legalidade > Conveniência**.

---

## 0. Princípios e pré-condições (executar só após deploy 1-3 validado; preferir compatibilidade)

**Gatilho de execução (bloqueante):**
1. A Fase 4 **só começa a ser executada após o deploy das Fases 1-3 estar em produção e validado** (smoke test das telas principais + boot do backend + `tsc` do frontend limpos). Antes disso, o trabalho de Fase 4 permanece como plano — não toca código —, para **não contaminar o pacote 1-3** que está prestes a subir.
2. O projeto **não é git**. Isso eleva o custo de erro (sem `git revert`/`git bisect`). Logo:
   - Antes de qualquer sub-fase, **snapshot/backup datado** da pasta de código (ex.: cópia de `backend/` e `frontend/`) — confirmação dupla antes de sobrescrever qualquer backup existente.
   - Cada sub-fase é um **pacote isolado e reversível por cópia de arquivo**, não por commit.
3. **Não renomear caminhos "no cru".** O sistema acabou de sofrer um bug de prefixo `/api/v1` (Fase 1). A regra dura da Fase 4 é: **toda rota antiga continua respondendo via alias deprecado**; o frontend só muda numa fase posterior, separada. Compatibilidade > elegância de namespace.

**Princípios de design da consolidação:**
- **Consolidar namespace e motor, não fundir responsabilidades genuinamente distintas.** Honorários e Dossiê NÃO têm sobreposição funcional real — só compartilham tema/nome. Fusão cega aumenta superfície de regressão sem ganho.
- **Um único ponto de saída para LLM** (ai_gateway) e **um único pipeline LGPD/HITL** para geração de IA. Esse é o ganho de Legalidade da fase.
- **Nivelar controle de acesso e PII por cima, nunca por baixo** ao unificar handlers.

**Pré-condição que ficou incerta (honesto):** não foi possível abrir `RELATORIO_FASE0/FASE5` para o texto exato do bug de prefixo da Fase 1. A estratégia se apoia no docstring de `ai_tools.py:4` (que admite a duplicação `/api/ai` vs `/api/v1/ai`) e na confirmação documental das metas de Fase 4. **Antes de executar, confirmar o texto exato do incidente da Fase 1** para calibrar a janela de deprecação.

---

## 1. Mapa atual (resumo por domínio)

### 1.1 IA — 7 routers de geração + 2 complementares
| Arquivo | include (main.py) | prefixo | Base efetiva |
|---|---|---|---|
| `backend/app/routers/ai.py` | `/api` (L181) | `/ai` | `/api/ai` |
| `backend/app/routers/ia_extra.py` | `/api` (L236) | `/ai` | **`/api/ai` (MESMA base que ai.py)** |
| `backend/app/routers/ia_especializada.py` | `/api` (L259) | `/ia-especializada` | `/api/ia-especializada` |
| `backend/app/routers/ia_saude.py` | `/api` (L228) | `/ia-saude` | `/api/ia-saude` (observabilidade — NÃO gera IA) |
| `backend/app/routers/documento_ia.py` | `/api` (L232) | `/documentos-ia` | `/api/documentos-ia` (OCR) |
| `backend/app/routers/assistente.py` | `/api` (L231) | `/assistente` | `/api/assistente` |
| `backend/app/routers/ai_tools.py` | `/api/v1` (L240) | `/ai` | **`/api/v1/ai` (único sob /v1)** |
| `backend/app/routers/rag.py` | `/api` (L186) | `/rag` | `/api/rag` (base de conhecimento — complementar) |

**Achado P0 latente (verificado):** `ai.py` e `ia_extra.py` compartilham EXATAMENTE o prefixo `/api/ai` (dois `APIRouter` distintos na mesma base). Não colidem hoje só porque os sufixos diferem; qualquer rota nova com sufixo coincidente causa **shadowing silencioso** (a última registrada em main.py vence). É dívida de organização, não só de domínio.

**Inconsistência de motor (verificado):** parte do domínio usa **Groq direto** (`ai_service.get_groq` em ai.py; helper local `_groq`/`_log` duplicado em ia_extra.py) e parte usa **`ai_gateway`** (Ollama→Groq com fallback + AILog padronizado): rotas `/caso/*` de ai.py, ia_especializada, assistente, ai_tools. Consequência: parte do domínio não tem fallback nem observabilidade do gateway.

### 1.2 Honorários — 4 routers, SEM sobreposição de lógica
| Arquivo | base efetiva | papel |
|---|---|---|
| `backend/app/routers/fees.py` | `/api/fees` | CRUD de honorários + pagamentos (fonte de verdade `Fee`/`FeePayment`) |
| `backend/app/routers/honorarios_calc.py` | `/api/honorarios-calc` | Cálculo determinístico (provisionamento art. 85 §2º CPC; teto ético 50%) — **sem consumidor no frontend** |
| `backend/app/routers/honorarios_oab.py` | `/api/honorarios-oab` | Estimativa via IA ancorada na tabela OAB/MG (RAG + ai_gateway) |
| `backend/app/routers/exito_rateio.py` | **`/api/v1/honorarios-exito`** | Rateio de êxito 50/50 (gera `partner_withdrawal`, SQL bruto, idempotente por `period_reference="exito:{fee_id}"`) |

**Única incoerência REAL:** `exito_rateio` está sob `/api/v1` enquanto os outros 3 estão sob `/api`. Não há duplicação de lógica — são 4 etapas distintas do ciclo de vida do honorário (CRUD / cálculo / precificação / distribuição).

### 1.3 Dossiê + Análise Estratégica — 3 conceitos colidentes + 4 endpoints concorrentes
**Três "dossiês" com mesmo nome, finalidades distintas (NÃO são duplicatas):**
- **A1 — Dossiê estratégico persistido:** `backend/app/routers/dossie_estrategico.py` (`/api/dossie/...`), serviço `dossie_service.gerar_dossie`. Versionado, aprovação HITL por sócio, AILog, custo, export PDF. **É o ÚNICO com pipeline LGPD completo** (`sanitizar_pii` + `validar_sem_pii` com abort + log).
- **A2 — Dossiê do cliente (CRM):** `backend/app/routers/dossie_cliente.py` (`/api/clients/{client_id}/dossie`). SQL puro, read-only. **Entrega CPF/CNPJ sem sanitização e sem role-check forte** (só `get_current_user`).
- **A3 — Dossiê de contexto da IA:** `GET /api/ai/dossie/{case_id}` em `ai.py`, via `case_context.montar_dossie`. Efêmero, sanitizado. `montar_dossie` é **dependência compartilhada** de assistente, dual, estrategia, visual-law e `cases.py::encerrar_caso`.

**Quatro endpoints concorrentes de análise estratégica por IA (sobreposição REAL):**
- **B1** `POST /api/cases/{case_id}/analisar` (`cases.py`, serviço `analise_estrategica.analisar_caso`) — JSON rico (SWOT, 3 cenários, jurimetria com %/faixa de valor). **Não usa `montar_dossie`, não chama `validar_sem_pii`, AILog em try/except silencioso.**
- **B2** `POST /api/ai/caso/{case_id}/estrategia` — Markdown com 3 cenários. **Redundância direta com B1.**
- **B3** `POST /api/ai/caso/{case_id}/dual` — IA-1 analisa, IA-2 audita.
- **B4** `POST /api/ai/caso/{case_id}/assistente` — chat contextual (superset dos modos de B2/B3).
- **B5** `POST /api/ai/analisar-caso` — versão avulsa/triagem por fatos digitados — **complementar, não concorre.**

**Correlatos NÃO concorrentes:** `sala_de_guerra.py` (painel read-only), `relatorio_cliente.py` (`/api/clients/{id}/relatorio-financeiro`, com role-check forte `_FIN_ADV`) — sobreposição PARCIAL com o bloco financeiro de A2.

---

## 2. Alvo proposto (router/serviço canônico por domínio)

### 2.1 IA — alvo 7→2 (NÃO 7→1)
- **Router canônico de geração** `/api/ai` (pacote `backend/app/routers/ai/` com sub-routers no mesmo prefixo), absorvendo `ia_extra.py`, `ai_tools.py`, `ia_especializada.py`, `assistente.py`. **`ai_gateway` como única porta LLM**; `ai_service` reduzido a domínio (prompt/RAG/sanitização) chamando o gateway — eliminando Groq direto.
  - Sub-rotas-alvo: `/api/ai/analise/*`, `/api/ai/redacao/*`, `/api/ai/resumo` (funde resumir-documento + resumir-texto), `/api/ai/chat/{case_id}` (funde `/caso/{id}/assistente` + `/assistente/cases/{id}/chat`), `/api/ai/pesquisa`, `/api/ai/perfis/{perfil}`, `/api/ai/documentos/analisar`, `/api/ai/prazos/detectar`, `/api/ai/logs`, `/api/ai/gateway/health`.
  - Motor interno único: `executar_tarefa_ia` (de ai_tools) por trás de fachadas nomeadas (preserva contratos do frontend).
- **Manter SEPARADOS (não fundir):** `rag.py` (base de conhecimento) e `ia_saude.py` (observabilidade/governança — só lê AILog). São infra complementar.

### 2.2 Honorários — alvo 4→1 organizacional (sem fusão de lógica)
- Prefixo canônico único **`/api/honorarios`** via `include_router(prefix="/api")` + `APIRouter(prefix="/honorarios")`, com **4 sub-routers preservados por responsabilidade**:
  - `backend/app/routers/honorarios/crud.py` (ex-fees) → `/api/honorarios/*`
  - `backend/app/routers/honorarios/calculo.py` (ex-honorarios_calc) → `/api/honorarios/calculo/...`
  - `backend/app/routers/honorarios/oab.py` (ex-honorarios_oab) → `/api/honorarios/oab/...`
  - `backend/app/routers/honorarios/exito.py` (ex-exito_rateio) → `/api/honorarios/exito/...` (sai de `/api/v1`)
- **Tabela `fees` e modelos `Fee`/`FeePayment` inalterados.** Só muda a superfície HTTP.

### 2.3 Dossiê — NÃO fundir 3→1; desambiguar + unificar pipeline de IA
- **Canônico de dossiê estratégico:** manter `dossie_estrategico.py` + `dossie_service.gerar_dossie` (`/api/dossie/...` ou desambiguado para `/api/cases/{id}/dossie` com alias). Todo conteúdo estratégico gerado por IA **nasce aqui** (versionado, HITL, PDF com carimbo de rascunho).
- **Canônico de geração de estratégia por IA:** fundir B1/B2/B3/B4 em **um serviço único**, sempre via `montar_dossie` (contexto sanitizado) e sempre passando por um **helper único de guard LGPD/HITL** — proposta `services/ai_guard.gerar_com_hitl(prompt, case_id, user)`: `sanitizar_pii → validar_sem_pii (abort) → gw_chat → AILog (gerado) → custo`. Os "modos" (cenários/dual/assistente/jurimetria-JSON) viram **parâmetros**, não 4 endpoints.
- **Manter separados:** A2 (dossiê do cliente — CRM), A3/`montar_dossie` (dependência de contexto, renomear conceitualmente para "contexto do caso"), `relatorio_cliente.py`. Avaliar unificar o bloco financeiro de A2 com `relatorio-financeiro` como fonte única do financeiro do cliente.

---

## 3. Estratégia de compatibilidade de rotas (aliases deprecados vs atualizar frontend) — recomendação

**Recomendação: (a) ALIASES DEPRECADOS no backend. Zero mudança de frontend na Fase 4.**

**Justificativa (alinhada a Controle > Velocidade):**
1. O sistema **acabou de quebrar por mudança de prefixo** (`/api/v1`, Fase 1). Repetir uma mudança de prefixo que atinge **~13 arquivos `.tsx`** de uma vez multiplica a superfície de regressão exatamente no padrão que já falhou.
2. FastAPI permite **montar o mesmo handler em dois prefixos** ou criar rotas-alias que delegam ao handler novo, com `deprecated=True` no OpenAPI + log de deprecação. Isso **desacopla** a refatoração de backend da migração de frontend.
3. O blast radius está **concentrado em `CasoDetalhe.tsx` e `IA.tsx`** (tocam múltiplos domínios). São telas centrais — quebrá-las é alto impacto operacional.

**Fluxo de compatibilidade por rota:**
1. Cria-se o handler/sub-router canônico.
2. A rota antiga **vira alias fino** que delega ao canônico (mesma resposta, `deprecated=True`, log "DEPRECATED: <rota antiga> → <rota nova>").
3. Frontend só migra em **fase posterior, com PR/pacote próprio**.
4. Remoção dos aliases **só após confirmação dupla** e janela de deprecação cumprida.

**O que NÃO fazer:** renomear cru `/api/v1/honorarios-exito`, `/api/v1/ai/*`, `/api/ia-especializada/*`, `/api/assistente/*`, `/api/documentos-ia/*` sem alias. Isso reproduz o incidente da Fase 1.

---

## 4. Plano de execução em sub-fases incrementais (uma por vez)

> Cada sub-fase é um pacote isolado, verificável por **tests + `tsc` + boot do backend**, e reversível por restauração de backup (não há git). Ordem por menor blast radius primeiro e maior ganho de Legalidade cedo.

### Sub-fase 4A — IA (a mais densa; faseada internamente)
- **4A.0 — Resolver a colisão P0 primeiro:** confirmar que nenhum sufixo coincide entre `ai.py` e `ia_extra.py` no estado atual; documentar. Este é o **primeiro item** porque é risco ativo.
- **4A.1 — Padronizar serviço no gateway SEM mudar rotas:** migrar handlers Groq-direto (ai.py: analisar-caso, resumir-documento, teses-ocultas, auditar-peca, preparar-audiencia, analisar-contrato; todo ia_extra.py) para `ai_gateway`. Remover `_groq`/`_log` duplicados de ia_extra.py **só após teste de paridade de saída** (provedor/modelo/custo/AITipoUso preservados). Rotas inalteradas.
- **4A.2 — Criar pacote `routers/ai/` com sub-rotas canônicas** (`/api/ai/resumo`, `/api/ai/chat/{case_id}`, etc.).
- **4A.3 — Transformar rotas antigas em aliases deprecados** (inclui `/api/v1/ai/*`, `/api/ia-especializada/*`, `/api/assistente/*`, `/api/documentos-ia/*`).
- Verificável em cada passo; só avança com 4A.x anterior validado.

### Sub-fase 4B — Honorários (baixo risco de lógica)
- **4B.1 — Criar pacote `routers/honorarios/`** com os 4 sub-routers reapontados para `/api/honorarios/*`.
- **4B.2 — Manter as 4 rotas antigas como alias deprecado** — com atenção especial a `/api/v1/honorarios-exito/{fee_id}/rateio` (GET+POST). **Não alterar nomes de tabela nem a chave de idempotência `period_reference="exito:{fee_id}"`** (risco de duplicar saques de sócios).
- **4B.3 — Decidir sobre `honorarios-calc` órfão:** integrar à UI ou marcar como API interna (não migrar URL sem confirmar que nenhum job/teste a chama).

### Sub-fase 4C — Dossiê + Análise (maior risco de regressão semântica/ética)
- **4C.1 — Criar o `ai_guard.gerar_com_hitl`** e migrar PRIMEIRO `cases.py::/analisar` (B1) para ele — fechar o buraco LGPD (validar_sem_pii + AILog garantido) **antes** de mover qualquer tráfego.
- **4C.2 — Reescrever `analise_estrategica` para delegar a `montar_dossie` + ai_guard**; unificar B1/B2/B3/B4 em modos do mesmo motor, persistindo como versão de `DossieEstrategico`.
- **4C.3 — Desambiguar namespaces de dossiê** com alias (estratégico, cliente, contexto-IA), nivelando role-check/sanitização de A2 **por cima**.
- **4C.4 — (opcional)** unificar bloco financeiro A2 ↔ relatorio-financeiro.

---

## 5. Blast radius (frontend) e mitigação

**Arquivos `.tsx` que emitem HTTP às rotas afetadas (verificado; baseURL axios = `/api`):**
- **IA `/ai` (ai.py + ia_extra.py) — 7 arquivos:** `AssistenteIA.tsx`, `CasoDetalhe.tsx`, `IA.tsx`, `Pecas.tsx`, `components/ExplicarMov.tsx`, `components/NoticiasCard.tsx`, `ramos/RamoBase.tsx`.
- **IA `/v1/ai` (ai_tools) — 1:** `AgenteIA.tsx` (`/v1/ai/status`, `/v1/ai/executar`).
- **IA `/ia-especializada` — 1:** `AssistenteIA.tsx`.
- **Honorários — 3:** `Honorarios.tsx` (`/fees/*`, `/v1/honorarios-exito/{id}/rateio`), `CasoDetalhe.tsx` (`/fees/?case_id=`), `components/EstimadorHonorarios.tsx` (`/honorarios-oab/estimar`).
- **Dossiê — 3:** `DossieCliente.tsx` (`/clients/{id}/dossie`), `CasoDetalhe.tsx` (`/dossie/{id}/historico`), `IA.tsx` (`/ai/dossie/{caseId}`).
- **Complementares que NÃO mudam de prefixo:** `/rag/*` (Dashboards, CasoDetalhe, Conhecimento, KnowledgeHub, Noticias, NoticiasCard), `/ia-saude/dashboard` (DashboardIA), `/documentos-ia/analisar` (ImportarDocumento).

**Total ~13 `.tsx` distintos**, com `CasoDetalhe.tsx` e `IA.tsx` em múltiplos domínios.

**Mitigação:**
1. **Aliases deprecados** (Seção 3) = blast radius de frontend **ZERO na Fase 4**.
2. Migração de frontend em fase própria, **começando pelas telas de menor toque** e deixando `CasoDetalhe.tsx`/`IA.tsx` por último, com verificação dedicada.
3. **Corrigir ANTES da Fase 4 (não dependem de consolidação) — 2 chamadas já quebradas (404 hoje):**
   - `FerramentasIA.tsx:34,68,72` → `/ai/skills/*` (não existe router `/skills`).
   - `GovernancaIA.tsx:32,48` → `/ia-governanca/*` (não existe router `/ia-governanca`).
   Documentar essas como pré-existentes para não virarem **falso-positivo** de regressão atribuído à Fase 4.

---

## 6. Riscos e o que NÃO consolidar

**O que NÃO consolidar (complementar — manter separado):**
- **IA:** `rag.py` (base de conhecimento) e `ia_saude.py` (observabilidade — só lê AILog). `documento_ia.py` é pipeline OCR distinto (vira sub-rota `/api/ai/documentos/...`, não funde com chat). `assistente.py::detectar-prazos` é extração estruturada (alimenta módulo de prazos), não chat. `B5 /api/ai/analisar-caso` (triagem por fatos) é complementar a B1-B4.
- **Honorários:** NÃO fundir handlers — CRUD vs cálculo vs OAB vs rateio são responsabilidades distintas. Consolidar **só namespace/versão**.
- **Dossiê:** NÃO fundir 3→1 — A1 (caso estratégico) / A2 (cliente CRM) / A3 (contexto-IA) são entidades diferentes; fusão quebra semântica REST (`/clients/{id}/dossie`). `montar_dossie` é **dependência**, não endpoint concorrente.

**Riscos principais:**
1. **Colisão `/api/ai` (ai.py × ia_extra.py)** — shadowing silencioso se sufixos coincidirem. Primeiro item a tratar.
2. **Mudança de motor (Groq direto → gateway)** pode alterar provedor/modelo/custo/latência. Exige **teste de paridade** antes de cortar o Groq direto.
3. **Quebra de prefixo sem alias** (`/api/v1/*` de ai_tools e exito) — repete o incidente da Fase 1. Mitigado por aliases.
4. **`exito_rateio`**: SQL bruto + idempotência `period_reference`. Alterar nome de tabela ou a chave **duplica saques de sócios** (`partner_withdrawals`).
5. **LGPD/HITL inconsistente** (B1 sem `validar_sem_pii`, AILog silencioso) — **pré-requisito** corrigir no `ai_guard` antes de migrar tráfego. Legalidade > Conveniência.
6. **Ético/OAB:** jurimetria de B1 (`chance_sucesso_percent`, `faixa_valor`) — ao torná-la canônica, reforçar **não-promessa de resultado** e carimbo de RASCUNHO/HITL em TODA saída.
7. **A2 expõe CPF/CNPJ sem role-check** — nivelar acesso **por cima** (como `_FIN_ADV`), nunca afrouxar ao unificar.
8. **Regressão de permissão (ROLE_LEVEL)** ao reorganizar sub-módulos — revisar nível mínimo caso a caso (estagiário/advogado/sócio/admin).
9. **AuthMiddleware global (main.py L156)** — o agregador deve preservar o prefixo `/api` para não expor rotas fora da proteção.
10. **`honorarios-calc` órfão** — confirmar ausência de qualquer consumidor (job/teste) antes de mexer na URL.

---

## 7. Verificação por sub-fase (zero regressão)

**Bateria comum a toda sub-fase (não há git — rodar antes e depois):**
- **Boot do backend** sem erro de rota duplicada/import (`uvicorn` sobe; `/openapi.json` gera).
- **`tsc` do frontend** limpo (mesmo sem mudar frontend, garante que nada quebrou).
- **Suite de testes** do backend (pytest) + testes existentes do domínio.
- **Smoke das telas centrais:** `CasoDetalhe.tsx` e `IA.tsx`.
- **Diff de `/openapi.json` antes×depois:** toda rota antiga ainda presente (como `deprecated`) — **nenhuma rota some**.

**4A (IA):**
- 4A.1: **teste de paridade de saída** Groq-direto vs gateway (provedor, modelo, `AITipoUso` registrado no AILog idêntico para o `ia_saude/dashboard` não corromper métricas).
- Verificar todas as rotas dos 7 arquivos respondendo (inclusive aliases `/api/v1/ai/*`).
- Confirmar `rag.py` e `ia_saude.py` intactos.

**4B (Honorários):**
- `GET/POST` em `/api/honorarios/*` **e** nos aliases antigos (`/api/fees/*`, `/api/honorarios-calc/*`, `/api/honorarios-oab/*`, `/api/v1/honorarios-exito/*`).
- **Teste de idempotência do rateio:** dois POST no mesmo `fee_id` geram **um** `partner_withdrawal` (chave `exito:{fee_id}` preservada).
- Testes de visibilidade por perfil em `fees` (admin/sócio vê tudo; advogado só próprios casos).

**4C (Dossiê/Análise):**
- **Teste LGPD do `ai_guard`:** entrada com PII residual → `validar_sem_pii` **aborta** o envio; AILog sempre gravado (não em try/except silencioso).
- Paridade de contrato: B1 continua devolvendo JSON estruturado (SWOT/jurimetria/cenários); modos B2/B3/B4 acessíveis via parâmetro.
- `montar_dossie` intacto para todos os dependentes (assistente, dual, estrategia, visual-law, `encerrar_caso`).
- A2: confirmar role-check reforçado e sanitização adicionada **sem** quebrar `DossieCliente.tsx`.
- Carimbo de RASCUNHO/HITL presente em toda saída estratégica (verificação ética/OAB).

---

**Pendência de confirmação antes de executar (honestidade):** texto exato do incidente de prefixo da Fase 1 (`RELATORIO_FASE0/FASE5` não pôde ser aberto nos mapeamentos) — usado apenas para calibrar a janela de deprecação, não altera a estratégia de aliases.

Arquivos-chave referenciados (caminhos relativos ao repo EJC, raiz `backend/app/routers/` e `frontend/src/`): `ai.py`, `ia_extra.py`, `ai_tools.py`, `ia_especializada.py`, `assistente.py`, `documento_ia.py`, `ia_saude.py`, `rag.py`, `fees.py`, `honorarios_calc.py`, `honorarios_oab.py`, `exito_rateio.py`, `dossie_estrategico.py`, `dossie_cliente.py`, `cases.py`, `sala_de_guerra.py`, `relatorio_cliente.py`, `services/{ai_service,ai_gateway,case_context,dossie_service,analise_estrategica,sanitizer}.py`, `main.py`.