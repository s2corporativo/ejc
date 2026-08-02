# 05 — Skills (Fase 5)

> Como em `04-agentes.md`, há **duas camadas** — e, dentro do produto, **quatro superfícies
> paralelas** de "skill". Este é o achado estrutural desta fase.

---

# CAMADA A — skills do Claude Code

## A1. Inventário — 19 skills de projeto

Todas em `.claude/skills/<nome>/SKILL.md`. **Nenhuma tem script anexo** — cada diretório contém
apenas o `SKILL.md`.

| Skill | Objetivo | Consumidor | Status |
|---|---|---|---|
| `ejc-novo-modulo` | módulo vertical completo | citada no `CLAUDE.md` | ativa |
| `ejc-nucleo-ia` | trabalhar em `ai/core/` + `system_prompts/` | citada no `CLAUDE.md` | ativa |
| `arquiteto-docker-deploy` | Docker/Nginx/VPS/CORS/SSL | citada no `CLAUDE.md` | ativa |
| `debugger-sistematico` | metodologia de debug | citada no `CLAUDE.md` | ativa |
| `gestor-rag-ia-juridica` | arquitetura RAG/Ollama/pgvector | citada no `CLAUDE.md` | **parcialmente integrada** (A3) |
| `gestor-migracao-banco` | playbook Alembic | agente `db-migrations` | playbook (A3) |
| `arquiteto-testes-ejc` | playbook de testes | agente `qa-tests` | playbook (A3) |
| `arquiteto-ejc` | playbook de auditoria/reparo | agente `ejc` | playbook (A3) |
| `arquiteto-ci-cd` | pipeline GitHub Actions | agente `ci-triage` | playbook (A3) |
| `gestor-backup-recuperacao` | pg_dump/cron/restore/DR | **nenhum** | sem consumidor / **insegura** (A4) |
| `integrador-apis-externas-ejc` | TJMG/PJe/CNJ/ReceitaWS | **nenhum** | sem consumidor / **insegura** (A4) |
| `orquestrador-celery-redis` | Celery + Redis + Flower | **nenhum** | instalada-não-usada |
| `arquiteto-notificacoes` | email/WhatsApp/push | **nenhum** | instalada-não-usada |
| `arquiteto-monitoramento-observabilidade` | Sentry/UptimeRobot/Prometheus | **nenhum** | instalada-não-usada |
| `integrador-whatsapp-business` | Z-API/Meta/Twilio | **nenhum** | instalada-não-usada |
| `gerador-relatorios-pdf-dinamicos` | WeasyPrint/ReportLab | **nenhum** | instalada-não-usada |
| `edicao-cirurgica` | devolver só o delta editado | **nenhum** | instalada-não-usada |
| `arquiteto-automacao-n8n` | n8n para **EJC + Verde Limp + S2** | **nenhum** | **fora do escopo do repo** |
| `integrador-google-search-console` | GSC para acionejus.com.br / depaulateixeira.adv.br | **nenhum** | **fora do escopo do repo** |

**Achado A2 — P2. 10 de 19 skills sem consumidor declarado**, e 2 tratam de sistemas que não
vivem neste repositório. Só são alcançáveis por invocação direta ou por match de `description`.

## A3. Duplicação com o catálogo global — o achado principal da camada A

**Confirmado por mim** (`diff` arquivo a arquivo): existem **163 skills globais** em
`~/.claude/skills/`, fora do git e fora de qualquer revisão. **17 das 19 skills de projeto têm
cópia lá.**

| Situação | Quantidade | Skills |
|---|---|---|
| Idênticas | 13 | `arquiteto-automacao-n8n`, `arquiteto-docker-deploy`, `arquiteto-monitoramento-observabilidade`, `arquiteto-notificacoes`, `debugger-sistematico`, `edicao-cirurgica`, `gerador-relatorios-pdf-dinamicos`, `gestor-backup-recuperacao`, `gestor-rag-ia-juridica`, `integrador-apis-externas-ejc`, `integrador-google-search-console`, `integrador-whatsapp-business`, `orquestrador-celery-redis` |
| **DIVERGENTES** | **4** | **`arquiteto-ejc`, `arquiteto-ci-cd`, `arquiteto-testes-ejc`, `gestor-migracao-banco`** |
| Só no projeto | 2 | `ejc-novo-modulo`, `ejc-nucleo-ia` |

> ### 🟠 A3 — P2. A mitigação documentada no `CLAUDE.md` não se sustenta em runtime
>
> As 4 divergentes são **exatamente** as que receberam, no repositório, o cabeçalho *"playbook de
> referência, não roteador concorrente"* — e o `CLAUDE.md` as descreve assim, corretamente.
> **Mas a cópia global manteve a descrição roteadora antiga.** Exemplo:
> `~/.claude/skills/arquiteto-ejc/SKILL.md:4` ainda diz *"Senior full-stack architect and technical
> auditor for EJC … Use whenever the user needs to: audit EJC codebase…"*.
>
> **Evidência de que a cópia global é a que aparece:** na listagem de skills desta própria sessão,
> `arquiteto-ejc` foi anunciada com o texto **global**, não com o de playbook do projeto.
> A correção existe no repositório e não tem efeito onde importa.

Outras sobreposições:
- **`agente-ejc` (global) vs. agente `ejc` (projeto)** — a skill global se declara *"Agente
  coordenador do EJC … roteamento de skills técnicas"*, disputando o papel de ponto de entrada.
  Não é mencionada no `CLAUDE.md`. → **duplicada**.
- **`gestor-rag-ia-juridica` vs. `ejc-nucleo-ia`** — a primeira ensina RAG com **LangChain/
  LlamaIndex**; o EJC real usa `ai_gateway.py` + `multilingual-e5-large` **1024d** e **não usa
  LangChain**. Nenhuma das duas declara precedência. → **desatualizada**.
- **`debugger-sistematico`** declara a diferença para `arquiteto-ejc`, mas **não menciona
  `ci-triage`**, que é o canônico para falha de CI.

## A4. Segurança das skills e hooks

**Achados reais** (varredura por `rm -rf`, `--force`, `curl|bash`, exfiltração, credenciais):

1. **P2 — Credencial literal versionada.** `integrador-apis-externas-ejc/SKILL.md:35`:
   `DATAJUD_TOKEN = os.getenv("DATAJUD_API_KEY", "cDZHYzlZa0JadVREZDJCendFbzVlQTU2S3NMWDBIQUs=")`
   — chave base64 como **default hardcoded**, ocorrência única no repositório. Ainda que seja a
   chave pública do DataJud/CNJ, viola a regra 1 do `CLAUDE.md` e ensina o padrão errado.
2. **P3 — `curl|sh`.** `gestor-rag-ia-juridica/SKILL.md:71`:
   `curl -fsSL https://ollama.com/install.sh | sh`. Host oficial, mas é o padrão que a regra 12 combate.
3. **P2 — Instruções destrutivas contra produção.** `gestor-backup-recuperacao/SKILL.md:186`
   contém `DROP DATABASE ejc_db;`, e as linhas 119/150/203 operam em **`/opt/ejc`** — que é a
   produção. `arquiteto-ci-cd/SKILL.md:156` faz `cd /opt/ejc` via `ssh-action`, e `:217-225`
   mandam **imprimir a chave SSH privada**. A **regra 9 do `CLAUDE.md` proíbe operar produção**.
4. **Prompt injection / instruções ocultas: NÃO LOCALIZADO.** Nenhum comentário HTML oculto,
   nenhum "ignore previous instructions", nenhum envio a host externo não declarado. Todos os
   tokens usam `os.getenv` com placeholder.

### `.claude/hooks/guarda_comandos.py` — testado empiricamente

Roda em `PreToolUse` **só no matcher `Bash`**. Emite `permissionDecision: "deny"`.

**Bloqueia (confirmado por mim, alimentando o hook por stdin):** `--dangerously-skip-permissions`;
`git push --force`/`-f`; `git reset --hard`; `git clean -fd`; `docker compose down -v`;
`docker volume rm`; `dropdb`/`DROP DATABASE`; `alembic downgrade base`; qualquer comando que toque
**`/opt/ejc`**; `rm -rf` fora de `/tmp`; `git commit|push|merge|rebase` **quando a branch é
`main`/`master`**.

> ### 🔴 A4.5 — P1. Bypass do guarda por aspas — comprovado nesta auditoria
>
> `CITACAO` (`:79`) substitui todo literal entre aspas por `" ARG "` **antes** de aplicar os
> padrões (`:154`) — decisão deliberada, para não bloquear `grep -rn "rm -rf" docs/`. A
> consequência é que **o comando destrutivo dentro de aspas escapa**. Teste executado:
>
> | Comando | Resultado |
> |---|---|
> | `rm -rf /home/user/ejc/backend` | **DENY** ✅ |
> | `bash -c "rm -rf /home/user/ejc/backend"` | **passa** ❌ |
> | `ssh vps "rm -rf /opt/ejc"` | **passa** ❌ |
>
> A terceira linha é a mais grave: é exatamente o caminho para a produção que a regra 9 proíbe, e
> é a forma natural de escrever um comando remoto. Correção sugerida: aplicar os padrões
> destrutivos **também** ao conteúdo entre aspas quando o comando externo for `bash -c`, `sh -c`,
> `ssh` ou `eval`.

Outras lacunas do guarda: `EJC_GUARDA_OFF=1` desativa tudo (documentado como consciente); **não
cobre `Write`/`Edit`**, então gravar em `/opt/ejc` por ferramenta de arquivo não é barrado.

### `.claude/hooks/orienta_graphify.py`

**Não bloqueia nada** — injeta `additionalContext` uma única vez por sessão, só em arquivo de
código, e avisa quando o grafo está mais velho que o último commit. O texto é explicitamente
recomendação e manda confirmar no arquivo. **Coerente com o que o `CLAUDE.md` descreve.**

**Achado A4.6 — P2 (cadeia de suprimento).** O hook `SessionStart` (`settings.json:8`) roda
`pip3 install -q graphifyy` a cada sessão — instalação de pacote de terceiro **sem pin de versão e
sem verificação de integridade**, com a saída suprimida.

## A5. Governança da camada A — quase tudo ausente

| Item | Situação |
|---|---|
| Catálogo oficial | **NÃO LOCALIZADO** — só a prosa do `CLAUDE.md` e `docs/MAPA_DE_MODULOS.md:9-11` |
| Versionamento (campo `version`) | **NÃO LOCALIZADO** — nenhum `SKILL.md` tem versão; só o git |
| Allowlist de skills permitidas | **NÃO LOCALIZADO** |
| Checksum / assinatura | **NÃO LOCALIZADO** |
| Log de ativação | **NÃO LOCALIZADO** — nenhum hook registra qual skill foi acionada |
| Gate de CI sobre `.claude/` | **NÃO LOCALIZADO** — nenhum workflow referencia `.claude` |
| Controle sobre as 163 skills globais | **NÃO LOCALIZADO** — fora do repo, fora do git, fora de revisão |

Este é o vetor por onde entram as 17 cópias-sombra da A3.

---

# CAMADA B — skills do produto

## B1. Quatro superfícies paralelas de "skill" — achado de arquitetura (P2)

| # | Superfície | Onde | Tamanho | Situação |
|---|---|---|---|---|
| 1 | `SKILL_REGISTRY` (código) | `services/ai/core/skill_registry.py` | **76** (28 base + 48 nativas) | base = **espelho não executado**; nativas = ativas |
| 2 | `EjcSkill` (banco) | `models/ai_skill.py`, `services/ai_skill_service.py` | **~170**, por 6 seeds | ativa, **não catalogada** |
| 3 | `SkillRouter` | `core/skill_router.py` | **5 ramos** por keyword | **duplicada / obsoleta** |
| 4 | Tools do agente | `services/ai/agent/tools/registry.py` | — | **bem construída** (RBAC por papel, HITL por `requer_confirmacao`) |

**Colisão de nome real:** `listar_skills` existe em `ai_skill_service.py:50` **e** em
`skill_registry.py:265` — o mesmo nome para duas superfícies diferentes já confunde busca.

## B2. As 28 skills base são código-espelho

Das 28, **17 têm `handler`** e 11 têm `handler=None` (patch/rollback, intencionalmente, travado
por `test_ai_core_nucleo.py:815-816`). Mas `grep "\.handler("` em todo `app/` retorna **2
ocorrências** (verificado por mim):

- `orchestrator.py:185` → `SKILL_REGISTRY["diagnose_system_module"].handler()`
- `ai/agent/tools/registry.py:82` → **outra** superfície (tools), não este registro.

**Ou seja: o `skill_pipeline` do orchestrator é declarativo.** Ele monta a lista de nomes
(`orchestrator.py:104-114`) e a devolve na resposta (`:344`), mas executa as etapas chamando os
serviços **diretamente**: `context_builder.montar_contexto` (`:136`), `sanitizar_ou_abortar`
(`:151`), `AIProviderPolicy().avaliar` (`:156`), `ai_gateway.chat` (`:266`),
`response_validator.validar` (`:278`), `audit_logger.registrar` (`:288`).

Os **16 handlers restantes** (`_h_classify_intent`, `_h_build_case_context`, `_h_retrieve_rag`,
`_h_call_model`, `_h_validate_citations`, `_h_mark_as_draft`, …) **nunca são invocados** — são
wrappers duplicados dos serviços reais, **sem nenhum teste que os execute**.

**Risco concreto:** podem divergir da implementação real sem quebrar teste algum. É a definição de
código-espelho. → **P2: consolidar (executar os handlers) ou remover (assumir que a lista é
documentação).** Decisão do titular.

## B3. As 48 skills nativas são ativas

Geradas em `skill_registry.py:234-258` a partir de `native_skill_specs()` = **14 ramos + 34
módulos** (`ejc_skill_catalog.py`). Os 34 `MODULE_METHODS` batem 1:1 com os 34 `_mod(...)` de
`module_registry.py` — **nenhum órfão dos dois lados**. São consumidas de fato como blocos de
prompt (`orchestrator.py:169-173`). → **ativas**.

Nenhuma skill do `SKILL_REGISTRY` é órfã no sentido de "não referenciada":
`tests/test_agentes_invariantes.py:63-66` garante que toda skill citada por agente existe no
registro. **O inverso não é testado** (skill no registro sem agente que a cite).

## B4. Consolidação recomendada

| Situação | Item | Ação sugerida |
|---|---|---|
| Sobreposta | 4 superfícies de skill | definir **uma** superfície canônica; as outras viram adaptador ou saem |
| Deveria ser determinística | `SkillRouter` (5 ramos por keyword) | remover — o `intent_classifier` já faz melhor, com 37 agentes |
| Espelho sem execução | 16 handlers do `SKILL_REGISTRY` | executar de fato **ou** rebaixar a metadado explícito |
| Grande demais | `gestor-backup-recuperacao`, `arquiteto-ci-cd` | remover as instruções que operam `/opt/ejc` |
| Fora de escopo | `arquiteto-automacao-n8n`, `integrador-google-search-console` | mover para outro repositório/perfil |
| Sem catálogo | as 163 globais | criar allowlist + catálogo versionado (A5) |
