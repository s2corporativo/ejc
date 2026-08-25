# EJC — Guia do repositório para assistentes de IA

Versão otimizada para desempenho: regras proporcionais ao diff, decisões
padrão explícitas, histórico movido para os documentos de origem. As regras
canônicas de governança seguem em **`docs/GOVERNANCA_IA.md`** — em divergência,
o canônico prevalece; ajuste de governança se faz lá, não aqui.

## Visão geral

EJC (Ecossistema Jurídico Clovis) v3 — gestão jurídica full-stack do
escritório De Paula Teixeira Advogados: casos/processos, clientes, prazos,
documentos, financeiro/honorários, portal do cliente e núcleo de IA jurídica
(RAG com pgvector, geração de peças, governança/HITL).

- **Stack**: FastAPI (Python 3.11, SQLAlchemy 2 async) + React 19/TypeScript/
  Vite + PostgreSQL 16 + pgvector + Redis/Celery + Docker Compose, atrás de
  Nginx no host. Produção: VPS Contabo, `https://ejc.depaulateixeira.adv.br`.
- **Idioma**: código, rotas, entidades e commits em português brasileiro
  (`casos`, `prazos`, `honorarios`, `pecas`, `intimacoes`).

## Regras inegociáveis (proteções — não relaxar)

1. Nunca alterar a `main` diretamente; integração só via PR.
2. Nunca commitar `.env`, segredos, chaves ou credenciais (`vps-tools/.env`
   incluso). Nunca `DROP`/migração destrutiva sem backup prévio.
3. Jamais enfraquecer HITL, gate de citações, sanitização de PII, kill-switch
   de IA, RBAC ou isolamento de dados (LGPD). Toda chamada de IA passa por
   `services/ai_gateway.py` — nunca provider direto de um router, nunca PII
   não sanitizada para provedor externo.
4. Rotas novas nascem protegidas (`AuthMiddleware` + RBAC); endpoint público é
   exceção explícita e justificada.
5. Migration: conferir head real (`cd backend && python -m alembic heads`),
   reservar número em `backend/alembic/MIGRATION_RESERVATIONS.md`, revisar
   autogenerate manualmente (~30 tabelas são raw-SQL sem model — nunca aceitar
   `drop_table` espúrio), nunca editar migration já aplicada em produção.
6. Proibidos sem confirmação explícita do usuário: `git push --force`,
   `git reset --hard`, `git clean -fd`, `rm -rf`, `docker compose down -v`,
   `docker volume rm`, `dropdb`, `alembic downgrade base`,
   `--dangerously-skip-permissions`.
7. Regra jurídica exige fonte oficial, vigência e teste. Correção de bug entra
   com teste de regressão.
8. Mudança em auth, permissões, uploads ou config → `security-auditor` antes
   de finalizar.
9. Deploy só pela esteira; não acessar banco nem diretório de produção.
10. Não modificar arquivos que pertencem a outro PR ativo.

## Fluxo de trabalho (otimizado)

- **Começo**: leia o pedido por inteiro (Issue ou mensagem do titular) e
  confira PRs abertos que tocam os mesmos arquivos. O pedido do titular por
  chat **é** autorização para começar; abra a Issue você mesmo (problema,
  escopo, critérios) e vincule o PR com `Closes #NNN` — registro rápido, não
  burocracia.
- **Decida sozinho, sem perguntar**: como implementar dentro do escopo; qual
  arquivo tocar; como testar; nomes e refatoração local; corrigir o que o
  próprio pedido quebra. Pedido que implica migration/auth/API/CI-CD/exclusão/
  dependência (§10 da governança) já autoriza aquele item — só ele.
- **Pare e pergunte apenas** quando seguir produziria trabalho inútil ou
  irreversível: leituras plausíveis divergentes com resultados materialmente
  diferentes; perda de dado ou quebra de contrato em uso; conflito com decisão
  permanente do titular (§11). Fora disso: assuma a leitura mais provável,
  registre a suposição no PR e siga.
- **Escopo**: achado fora do escopo não interrompe a tarefa — vira Issue nova
  e uma linha no relatório.
- **PR**: template preenchido é o relatório da tarefa — não duplique em
  relatório separado; acrescente ao corpo apenas o que o template não cobre
  (suposições, riscos residuais, pontos de decisão humana). Nasce draft e é
  promovido a pronto quando a evidência de verificação estiver completa.
  Correções de review vão na mesma branch e no mesmo PR.
- **Precedência de regras**: `docs/GOVERNANCA_IA.md` → este arquivo →
  `AGENTS.md` → skills/agentes. Conflito não se resolve em silêncio: corrija
  no PR ou aponte no relatório.

## Verificação — local, proporcional ao diff

O Actions da organização está indisponível no nível da conta (desde ~22/08).
CI ausente ou `startup_failure` **não é sinal em nenhuma direção** — não
sonde, não re-dispare, registre uma vez e siga. A verificação oficial é local
e escala com o que o diff toca:

| Mudança | Portão antes do push |
|---|---|
| Só documentação/`.md`/comentários | Nenhum (declare docs-only no PR) |
| Só `frontend/src` | `cd frontend && npm run lint && npm test && npm run build` |
| Só backend, sem tocar banco/models/services/routers compartilhados | `cd backend && ruff check app && pytest <área alterada>` + suíte completa `pytest` uma vez antes do push |
| Banco, models, migrations, seeds | Acima + `alembic upgrade head` do zero em PostgreSQL 16 + pgvector local |
| Cruza backend e frontend | Ambas as colunas |

- Durante a iteração, rode só os testes da área que está mexendo; o portão
  completo da linha correspondente roda **uma vez, antes do push** (a suíte
  completa já pegou regressões que a análise estática não pegou — por isso ela
  fica, mas só onde o diff a justifica).
- Ambiente que não compila dependência nativa não é desculpa: use venv
  isolado.
- **Evidência no corpo do PR**: resultado portão a portão, commit e branch —
  substitui o verde do CI.
- **Merge**: manual, do titular, mediante a evidência acima (o merge
  automático §6-A está suspenso com `governanca.yml`/`auto-integracao.yml`
  desligados; quando a esteira voltar, volta o fluxo automático).

## Comandos essenciais

```bash
# Backend (Python 3.11)
cd backend && pip install -r requirements.txt
pytest                        # suíte completa; testes de banco só com RUN_DB_TESTS=1
ruff check app
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend (Node >= 22.22.0)
cd frontend && npm ci
npm run dev                   # :5173, proxy /api → :8000
npm run lint                  # = tsc --noEmit
npm test                      # vitest run
npm run build

# Stack completa / CI local
docker compose up -d --build
scripts/ci-local.sh
```

## Arquitetura — o essencial

- **Backend**: entrypoint `backend/app/main.py` (163 routers registrados
  manualmente, prefixo `/api`; toda rota também responde em `/api/v1` —
  regras por path cobrem as duas superfícies). Camadas: routers finos →
  `app/services/` → models em `app/models/` → schemas Pydantic. Banco async
  (`asyncpg`) via `get_db()`; Alembic usa `DATABASE_URL_SYNC`. Auth: JWT
  HS256 + refresh httpOnly + 2FA TOTP + bcrypt puro (não reintroduzir
  passlib/python-jose). CPF/CNPJ cifrados (Fernet + HMAC cego). Integração
  externa nova segue o padrão do repo: flag env default OFF + degradação
  graciosa. Premissa de worker único (rate-limit memória, APScheduler).
- **Frontend**: rotas têm fonte da verdade em `src/config/moduleRegistry.tsx`
  (RBAC por rota) — módulo novo entra no registry, nunca solto no `App.tsx`.
  API client `src/lib/api.ts`: `baseURL /api/v1` + interceptor que apara
  prefixo repetido — dentro do cliente `api`, caminhos **sem** prefixo
  (`/casos`); `axios` cru usa o path real (`/api/auth/refresh`). Estado em
  stores Zustand (`src/stores/`).
- **Testes**: backend sem harness global de banco — siga o padrão do arquivo
  vizinho (`_FakeDB`, `TestClient`, `aiosqlite`, `dependency_overrides`).
  Frontend: vitest + testing-library, testes co-localizados.
- **graphify** (`graphify-out/`): índice de símbolos para LOCALIZAR código
  gastando pouco contexto (`graphify query "<pergunta>"`). Não é fonte da
  verdade, não indexa prosa e envelhece — confirme no arquivo antes de editar
  ou de afirmar que algo não existe. Hooks mantêm o grafo atualizado
  automaticamente; não rode update à mão.

## Subagentes — por risco, não por ritual

Delegue quando a delegação paga o próprio custo (trabalho multi-área,
exploração ampla, frente autocontida); edição pontual se faz na thread
principal. Frentes independentes em paralelo, na mesma mensagem. Achado de
subagente não conferido não vira afirmação sua no PR.

- Implementação: `ejc` (orquestrador), `backend-fastapi`, `frontend-react`,
  `db-migrations`.
- Qualidade — acione conforme o risco do diff, não em cadeia obrigatória:
  `qa-tests` (mudança de comportamento), `security-auditor` (OBRIGATÓRIO para
  auth/permissões/uploads/config — caminho canônico de revisão de segurança),
  `code-reviewer` e `verifier` (mudança não trivial), `simplifier` (feature
  grande já funcionando), `ci-triage` (falha de CI), `app-runner` (validação
  de UI no navegador), `researcher` (pesquisa externa apenas).
- Skills de projeto em `.claude/skills/` quando a tarefa casar com o nome.

## Armadilhas conhecidas (resumo — detalhe em docs/auditoria/)

- Fonte de verdade sobre provedores de IA: `GET /ia-governanca/provedores`
  (não `/ai/status` nem `/diagnostico/central`, que divergem entre si).
- `GET /system-modules/mapa` é diagnóstico curado, não inventário de rotas.
- Fluxo que grava em duas tabelas → verifique a transação (classe de defeito
  recorrente; os cinco casos citados pela auditoria de julho já foram medidos
  e resolvidos/reenquadrados — não re-audite sem reproduzir).
- Job agendado novo deve monitorar **resultado**, não só execução (o
  tratamento existente é específico do `JOB_DJEN`).
- Numeração de migration envelhece até dentro de PR aberto — o head real é o
  do `alembic heads`, nunca o de um documento.
- Estado de workflow se confere na **API** (`state != active`), não no
  arquivo YAML; PR sem check algum não é PR aprovado.
- Deploy manual (Actions parado): `RUNBOOK_DEPLOY_MANUAL.md` +
  `scripts/deploy_manual.sh`. Nunca chamar `deploy_vps_safe.sh` direto
  (`RUN_MIGRATIONS` default 0 → deploy "verde" com schema desatualizado).

## Git/GitHub

- `gh auth status` uma vez no início; nunca `gh auth login`. Todo `gh` com
  flags completas — nada interativo. Leitura em lote via `gh api graphql`
  (allowlist libera `-f query=*`; escrita `-X`/`--method`/mutations exige
  confirmação específica). Comando travado → interromper e reportar.
- `git commit --no-verify`, `git push --force`, `git reset --hard`: só com
  confirmação explícita para aquele comando.

## Onde ler mais (sob demanda)

`README.md` (operação) · `docs/ai/` (núcleo de IA, HITL, LGPD) ·
`docs/CATALOGO_APIS_EJC.md` · `docs/DESIGN_SYSTEM_EJC.md` ·
`docs/auditoria/` (plano ativo e achados — leia só o bloco em execução) ·
`RUNBOOK_*.md` (procedimentos) · `RELATORIO_*.md` (histórico, não
procedimento).

**Critério de lançamento**: um advogado leva um caso real do início ao
protocolo dentro do sistema e acha **mais fácil que fazer fora dele**.
