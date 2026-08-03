# 00 — Resumo executivo

**Auditoria integral do EJC — Ecossistema Jurídico Clovis**
Commit `aa65974` · branch `claude/auditoria-ejc-graphify-aoa2hi` · 2026-08-02
Escopo: 15 fases, orientada por grafo, baseada em evidência.

---

> ## ⚠️ Estado: os três P0 foram CORRIGIDOS neste mesmo PR
>
> O diagnóstico abaixo descreve o sistema **como encontrado** no commit `aa65974`. Por autorização
> do titular ("faça de acordo com o que achar melhor para o sistema"), os **três defeitos P0 foram
> corrigidos** na sequência recomendada — verificador primeiro. O restante (P1, P2, P3) **não foi
> tocado** e segue valendo como plano.
>
> | Defeito | Estado | Correção |
> |---|---|---|
> | **P0-2** verificador cego | ✅ corrigido | `api_contract.py` — `_podar_prefixo_repetido()` espelha o interceptor de `lib/api.ts:21-23` |
> | **P0-1** prefixo `/v1` | ✅ corrigido | `/v1` removido do `prefix=` dos 8 routers; 33 rotas migraram de `/api/v1/X` para `/api/X` |
> | **P0-3** `/api/rag/docs` 500 | ✅ corrigido | `Depends(get_db)` / `Depends(get_current_user)` declarados em `_listar_docs_escopado` |
>
> **Validação:** 4 537 testes de backend passam (era 4 463 + 9 de regressão novos + os que vieram
> da `main`), `ruff` limpo, frontend com 364 testes e `tsc --noEmit` exit 0. As 33 rotas foram
> conferidas no app montado: **nenhuma colisão, nenhuma rota registrada sob `/api/v1`**.
>
> **Dois fatos que a correção revelou e que valem mais que ela:**
> 1. Com o P0-2 corrigido, `test_api_contract.py` **falhou apontando exatamente as 27 chamadas** —
>    prova de que era falso-verde, não hipótese.
> 2. O snapshot de paridade (`tests/snapshots/openapi_rotas_baseline.json`) tinha
>    **congelado o defeito**: gravou `auth_deps: []` para `/api/rag/docs`. Uma rota sem nenhuma
>    dependência de autenticação estava travada como "estado correto" — e ninguém percebeu.

---

## 1. Veredito em uma frase

> **O EJC está muito mais construído — e muito mais bem construído — do que o seu estado aparente
> sugere. O problema central não é funcionalidade faltando: é que quatro módulos inteiros estão
> inacessíveis por um defeito de roteamento, e o sistema, quando falha, parece apenas vazio.**

O código de segurança, IA e LGPD é sólido e, em vários pontos, exemplar. Três hipóteses graves do
escopo desta auditoria foram **refutadas com evidência**. Em compensação, **três defeitos P0 vivos
passaram por 4 463 testes verdes** — porque nenhum deles é testável por teste de unidade.

## 2. Os três P0

| # | Defeito | Consequência | Prova |
|---|---|---|---|
| **P0-1** | 8 routers declaram `prefix="/v1/…"`; o middleware reescreve `/api/v1/*`→`/api/*`; o interceptor do frontend apara `/v1/`. **27 chamadas em 9 páginas caem em 404** | **Contratos do Escritório, DataJud, Despesas e Kanban estão mortos na interface** — e o advogado vê "lista vazia", não erro | 4 métodos independentes, incl. requisição no app montado: `404 /api/v1/despesas` vs `500 /api/v1/v1/despesas` |
| **P0-2** | `api_contract.py` não reproduz o interceptor — valida a URL que o navegador deixou de enviar | **O guarda-corpo desta classe exata de defeito está cego.** 39 testes verdes com o defeito vivo | `api_contract.py:83-93` vs `lib/api.ts:21-23` |
| **P0-3** | Monkeypatch de `GET /api/rag/docs` perde os `Depends`; `db`/`cu` viram query params | **Rota 500 sempre**, e o controle de visibilidade que o patch deveria instalar **nunca executa** | Introspecção do app: `QUERY_PARAMS=[…,'db','cu']`, `SUBDEPS=[]`; request real → 500 |

**A causa comum dos três é a mesma lacuna:** não existe teste que verifique *"a URL que o navegador
realmente envia bate numa rota que realmente responde"*. Não é falta de cobertura de unidade — é
falta de **teste de superfície**.

## 3. O que foi refutado (e por que importa)

| Hipótese do escopo | Veredito | Evidência |
|---|---|---|
| RAG misturando dados entre clientes | **REFUTADA** | filtro `_FILTRO_ESCOPO_RAG` nas **4** consultas, `scope_cli` derivado do caso (nunca do usuário), **fail-closed**, com teste **row-level** contra Postgres |
| Agente/router chamando provider de IA direto | **REFUTADA** | zero bypass; todos os candidatos lidos e descartados. `maritaca_provider` tem **4** dependentes reais, não os 136 que o grafo indicava |
| `run_fictitious_smoke.py` cria superadmin em produção | **REFUTADA** | nenhum runner cria usuário; `grep "homolog.qa"` no código → **zero**; o marcador vem de **outro** arquivo. **`CLAUDE.md:265` está errado** |
| Segredo real versionado | **REFUTADA** | `git log --all -- .env` vazio; zero chave fora de placeholder |
| IDOR em recurso jurídico sigiloso | **nenhum confirmado** nos recursos auditados; portal do cliente isolado em 3 camadas | |
| "Vocabulário de status inconsistente" | **JÁ RESOLVIDO** pela migration 126 + `core/status_caso.py` | |

**Por que importa:** quatro dos cinco achados que a auditoria externa marcou como "não podem se
perder" ou não existem no código atual, ou já foram corrigidos. Perseguir fantasmas custa tanto
quanto ignorar defeitos.

## 4. O que o Graphify entregou — e onde erra

O grafo foi atualizado ao commit auditado (19 575 nós, 47 896 relações, 1 638 arquivos) e **pagou
o próprio custo**: apontou `core/ownership.py`, `ai_gateway.py` e `lib/api.ts` como pontos de
concentração, e as comunidades confirmaram `Case`/`User`/`Client`/ownership como núcleo funcional.

**Mas nenhum dos quatro achados P0/P1 desta auditoria veio do grafo.** E ele erra de forma medível:

| Limitação medida | Valor |
|---|---|
| Arestas cujo alvo tem **nome ambíguo** (≥2 arquivos) | **10 336 de 42 768 — 24,2 %** |
| Imports **dentro de função** (invisíveis ao AST) | **743**, em **169 de 539** arquivos (31 %) |
| Hubs fantasma confirmados | `maritaca_provider` (136 no grafo × **4** reais) |
| Comunidade que não é módulo | `_post` (141 nós) |

**Regra derivada:** o graphify serve para *localizar* e *priorizar leitura*. **Não serve para
afirmar que algo não existe, não é usado, ou é o hub principal.** Eu mesmo produzi **4 falsos
positivos** por confiar em extração automática, todos registrados e corrigidos em
`02-relatorio-graphify.md` §6.

## 5. Percentuais — com o cálculo

**Base: os 38 módulos obrigatórios do escopo** (`11-modulos.md`). Percentual = módulos na
categoria ÷ 38.

| Categoria | Módulos | Cálculo | % |
|---|---|---|---|
| **FUNCIONAL** | 8 | 8/38 | **21,1 %** |
| **FUNCIONAL COM RESSALVAS** | 14 | 14/38 | **36,8 %** |
| **PARCIAL** | 8 | 8/38 | **21,1 %** |
| **QUEBRADA** (total ou parcial) | 5 | 5/38 | **13,2 %** |
| **DUPLICADA** | 3 | 3/38 | **7,9 %** |
| **SIMULADA** | **0** | 0/38 | **0 %** |
| NÃO LOCALIZADA / DESCONECTADA / OBSOLETA | 0 | — | 0 % |

> ### Ressalva obrigatória sobre estes números
>
> **"Funcional" aqui significa *"o caminho existe e está íntegro no código, com teste"* — não
> *"exercitado em runtime"*.** Sem banco, sem Docker e sem provedor de IA, o fluxo jurídico não
> pôde ser executado ponta a ponta. **Percentual funcional *comprovado em execução* = não
> medido.** As únicas verificações em runtime foram: a suíte de testes (4 463 + 343), o app FastAPI
> montado (830 rotas, requisições com JWT forjado), `tsc --noEmit`, `ruff` e o probe de URL com o
> axios real.
>
> **0 % simulado** é medida, não estimativa: varredura por `mock`/`fake`/`lorem`/dados de exemplo
> em `frontend/src` → **zero** em código de produção; `Math.random` → 1 ocorrência legítima;
> `assert_called`/`.call_count` em 342 arquivos de teste → **zero**.

**Riscos:** **3 críticos (P0)** · **10 altos (P1)** — sendo 1 operacional (`homolog.qa`) e 1
registrado como **risco aceito** pelo titular (2FA, `GOVERNANCA_IA.md:254`).

## 6. Agentes e skills

| | Total | Ativos | Órfãos / sem consumidor |
|---|---|---|---|
| **Agentes Claude Code** | 12 | 12 | 0 |
| **Agentes jurídicos (produto)** | 37 | 37 (todos roteáveis, HITL universal) | 0 órfãos; **8 sem teste comportamental** |
| **Skills de projeto (Claude Code)** | 19 | 9 | **10 sem consumidor** (2 tratam de sistemas fora deste repo) |
| **Skills globais** | 163 | — | **17 duplicam as de projeto; 4 divergem, e a versão global é a que prevalece** |
| **Skills do produto — nativas** | 48 | 48 | 0 |
| **Skills do produto — base** | 28 | 12 metadados + **1 handler executado** | **16 handlers nunca invocados** |
| **Skills do produto — em banco** | ~170 | ativas | superfície não catalogada |

**Achado estrutural:** existem **quatro superfícies paralelas de "skill"** no produto
(`SKILL_REGISTRY`, `EjcSkill` em banco, `SkillRouter`, tools do agente), e **duas** de "agente"
(dev e produto). `SkillRouter` é um segundo classificador de intenção, com 5 ramos, rodando
**antes** do `intent_classifier` de 37 agentes e poluindo o prompt.

## 7. Hubs identificados

**Backend:** `core/database.py` (247 dependentes) · `models/user.py` (232) · `core/security.py`
(207) · `core/config.py` (184) · **`core/ownership.py` (99 — barreira de IDOR)** ·
`models/case.py` (98) · `services/ai_gateway.py` (62 — única saída de IA) ·
`services/sanitizer.py` (41) · `services/pii_crypto.py` (25).

**Frontend:** `lib/api.ts` (137) · `components/UI.tsx` (118) · `Toast.tsx` (86) ·
`stores/auth.ts` (33) · `config/moduleRegistry.tsx` (15).

**Contraexemplo que vale a lição:** `core/api_version_middleware.py` tem **um** dependente no
grafo e é a causa raiz do P0-1. **Centralidade de grafo não mede criticidade.**

## 8. Principais interrupções do fluxo

1. **P0-1** — contrato, DataJud, despesas e Kanban inacessíveis, **sem erro visível**.
2. **P0-3** — governança da base de conhecimento não abre.
3. **Gate de citações sobre base possivelmente vazia** — `RAG_EXIGIR_APROVADO=true` é o default;
   com acervo não curado, **nenhuma citação valida e nenhuma peça chega ao protocolo**, sem
   mensagem que explique. *(Hipótese mais provável para "nenhuma peça foi protocolada" — exige
   homologação para confirmar.)*
4. **41 `.catch(() => {})`** — em 6 abas de `CasoDetalhe`, falha de rede é indistinguível de
   "sem dados". Num ato jurídico, concluir que não há prazo/parte/prova quando há tem consequência.
5. **`peca_geracao_router.py` sem nenhum teste** — a rota do critério de lançamento é a menos
   protegida do sistema.

## 9. Ordem recomendada das correções

```
P0-2 (verificador cego)  →  P0-1 (prefixo /v1)  →  P0-3 (rag/docs)  →  P0-4 (gate de cobertura)
     ↓
P1 de segurança (rate limit de IA · RBAC de victory_vault e document-templates · AI_ENABLED)
     ↓
P1 de LGPD (case_partes cifrado · anonimização completa) + P1 operacional (homolog.qa)
     ↓
P1 de qualidade (teste do peca_geracao_router · extrair regra jurídica de ramos.py)  →  P2  →  P3
```

**P0-2 vem primeiro**: corrigir os routers sem corrigir o checker deixa a regressão livre para
voltar.

## 10. Módulos liberados × bloqueados

**Liberados** (íntegros, com teste, sem P0/P1 próprio): **Casos · Clientes** (menos pendências) **·
Prazos · Agenda · Documentos · Portal do cliente · Usuários · Tarefas**.

**Bloqueados até correção:** Contratos do escritório (P0-1) · DataJud (P0-1) · Financeiro–despesas
(P0-1) · Base de conhecimento/RAG (P0-3) · Produção jurídica→protocolo (P1-9 + T-P0-1 + curadoria)
· Honorários/financeiro consolidado (sem teste de cálculo).

## 11. O que merece ser dito a favor do sistema

Uma auditoria que só lista defeitos engana tanto quanto uma que os esconde. O que está bem-feito,
com evidência:

- **`core/ownership.py`** — gate ABAC documentado, com o *hardening* de caso órfão já aplicado e o
  raciocínio registrado no próprio arquivo.
- **`ai_gateway.py`** — invariante "toda IA passa por aqui" **de fato respeitada**, com barreira de
  PII de fonte única, `_ProviderPulado` que não envia conteúdo quando sobra PII, e boot que falha em
  produção se a sanitização for desligada.
- **HITL universal** — `is_rascunho=True` incondicional, não desligável por flag.
- **Citation gate fail-secure** — política inválida **força** `bloquear`, com override auditado em
  trilha dupla e ~45 testes.
- **Portal do cliente** — isolamento em 3 camadas, com a melhor cobertura de segurança do repo e a
  melhor experiência de erro (`ErrorState` com retry).
- **Suíte de testes sem a patologia do mock** — **zero** `assert_called` em 342 arquivos.
- **`core/status_caso.py`** — matou cinco definições incompatíveis de "caso ativo" e documenta por
  quê.
- **PDF de minuta sem gate** — correção de atrito que inverte a ordem errada do ato profissional.

## 12. Correções necessárias no `CLAUDE.md`

A auditoria encontrou **12 divergências** entre a documentação e o código
(`01-arquitetura-atual.md` §4). As que mais desorientam:

1. *"o frontend compensa chamando `/v1/x`"* e *"Resolvido em 2026-08-02"* — **a compensação virou
   a causa do P0-1**;
2. *"ruff/pip-audit informativos"* — **ambos são bloqueantes**;
3. CI descrito com 2 jobs — **são 3** (falta `eval-smoke`);
4. origem da conta `homolog.qa` atribuída ao **runner errado**;
5. *"163 routers"* — são **162**;
6. *"o grafo versionado"* — `graphify-out/` está **no `.gitignore`**.

---

## Documentos desta auditoria

| Arquivo | Conteúdo |
|---|---|
| `00-resumo-executivo.md` | este documento |
| `01-arquitetura-atual.md` | Fases 1 e 3 — ambiente, escala, divergências documentação × código |
| `02-relatorio-graphify.md` | Fase 2 — grafo, taxa de erro medida, hubs, comunidades |
| `03-mapa-dependencias.md` | matriz de impacto, contrato frontend↔backend |
| `04-agentes.md` · `05-skills.md` | Fases 4 e 5 — as duas camadas, órfãos, segurança dos hooks |
| `06-ia-rag-grafo-juridico.md` | Fase 6 — gateway, PII, HITL, RAG, isolamento |
| `07-banco-de-dados.md` | Fase 7 — Alembic, schema, LGPD, seeds |
| `08-backend.md` · `09-frontend.md` | Fases 8 e 9 |
| `10-fluxo-juridico.md` · `11-modulos.md` | Fases 10 e 11 |
| `12-seguranca-lgpd.md` · `13-ux-design.md` · `14-testes.md` | Fases 12, 13, 14 |
| `15-plano-correcao.md` | plano P0-P3 com ID, evidência, correção e critério de aceite |
| `16-matriz-rastreabilidade.md` | requisito → tela → endpoint → service → tabela → agente → skill → teste |

**Condição de encerramento atendida**, com uma exceção declarada: os testes adversariais dos
agentes e a execução do fluxo jurídico ponta a ponta **exigem ambiente de homologação** e estão
registrados em `15-plano-correcao.md` como lacunas de verificação, não como achados.

**Aguardando ordem específica para iniciar as correções por módulo.**
