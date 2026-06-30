# Correções aplicadas — EJC (base V6.6 OMNI LEX DIAMOND)
**Data:** 28/06/2026 · **Base:** working tree V6.6 (superset). Sem deploy executado — apenas código.
**Validação:** `python -m compileall app` = 0 erros · chain Alembic = head único `053_reconcile_schema` · 107 routers resolvem.

> Trabalho feito sobre cópia limpa. NENHUM comando foi rodado na VPS de produção.
> As migrations são IDEMPOTENTES (`IF NOT EXISTS`) — seguras em prod (no-op) e em banco limpo.

---

## FASE 0 — Destravar deploy/DR (schema reproduzível)
| Arquivo | Mudança |
|---|---|
| `backend/alembic/versions/053_reconcile_schema.py` (novo) | Cria idempotente: `caso_areas`, `bank_analyses`, `bank_transactions`, `bank_abusive_charges`, `kanban_columns`, `areas`, `agenda_eventos`, `client_pending_items`, `domain_events`, `office_contracts`, `office_expenses`, `partner_withdrawals`, view `vw_atividades`; + 9 colunas faltantes em `cases` (`ADD COLUMN IF NOT EXISTS`). down_revision=`052_workflow_tables`. Downgrade não dropa dados (só a view). |
| `backend/app/models/__init__.py` | Registra TODOS os models (17 que faltavam) para o Alembic autogenerate enxergar a metadata completa — causa-raiz do drift. |

## FASE 1 — Rotas e IA
| Arquivo | Mudança |
|---|---|
| 9 routers (`curadoria_renomada, mediacao, datajud, despesas, kanban, office_contracts, partner_withdrawals, pending_items, whatsapp`) | Removido o `/api` (e `/api/v1`) embutido no `prefix`. main.py já adiciona `/api`. Agora resolvem em `/api/v1/datajud` etc. — exatamente o que o frontend chama (antes era `/api/api/...` → 404). |
| `backend/app/core/ai_brain.py` | Adicionado método `generate(prompt, modo)` (usado por intelligence_v3, jurimetria, cerebro); `modo_duas_ias(contexto="")` agora opcional (corrige chamada de 1 arg no cerebro); `base_url` lido de `OLLAMA_BASE_URL` do config (antes `localhost:11434` hardcoded → não conecta no Docker). |
| `backend/app/routers/jurimetria.py` | Import corrigido `app.services.ai_brain` → `app.core.ai_brain`; retorno embrulhado em JSON. |

## FASE 2 — Segurança e caminhos
| Arquivo | Mudança |
|---|---|
| `backend/app/core/auth_middleware.py` | Removido `/api/victory_vault/` da lista pública (expunha teses do escritório sem login). |
| `backend/app/routers/victory_vault_router.py` | `APIRouter(dependencies=[Depends(get_current_user)])` — todas as rotas exigem JWT. |
| `backend/app/core/victory_vault.py` | Caminho do mock relativo a `__file__` (antes `/home/ubuntu/...` absoluto, inexistente no container); `print` → `logger`. |
| `backend/app/services/scheduler.py` | Backup diário usa `settings.BACKUP_DIR` + `DATABASE_URL_SYNC` (antes `/home/ubuntu/backups` + URL async → backup silenciosamente perdido). |
| `backend/app/services/visual_law_templates.py` | `logo_path` relativo ao pacote. |
| `backend/app/routers/sala_de_guerra_v3.py` | PDF gravado em `UPLOAD_DIR/visual_law`; `import datetime`/`os` que faltavam (NameError latente); strftime `%Y%6m%d` malformado corrigido. |
| `backend/.dockerignore` / `.gitignore` | Adicionado `*.zip`, `*.bak`. |

## FASE 3 — Limpeza
- Removidos: `backend/ejc_project.zip` (5,6 MB no contexto de build), `_dead_code/`, `Dashboard_light_backup.tsx`, `Workflow.tsx.bak`, `docker-compose.ml.yml` (stub vazio), `docker-compose.yml.bak.*`, `frontend/Dockerfile.bak`, `frontend/public/sw.js.bak`, `frontend/tailwind.config.bronze.js`, scripts soltos (`check_*.py`, `chk2.py`, `tmp_fix.py`, `test_s.py`, `seed_sumulas.py`, `verify_sumulas.py`), `backend/test_drive_container.py`, todos os `__pycache__`/`*.pyc`.
- `frontend/src/pages/FinanceiroDashboard.tsx`: corrigido `/api/v1/v1/` → `/api/v1/`.
- 11 `.md` de versão/relatório movidos para `docs/`.

---

## FASE 4 — Victory Vault: persistência real (executado 28/06/2026)
| Arquivo | Mudança |
|---|---|
| `backend/alembic/versions/054_victory_vault.py` (novo) | Cria idempotente `teses_vitoriosas` e `modelos_documentos` (varchar IDs, soft-delete). down_revision=`053_reconcile_schema`. |
| `backend/app/core/victory_vault.py` (reescrito) | Agora grava/lê no PostgreSQL via `AsyncSessionLocal` (antes lista in-memory — POSTs se perdiam no restart). Assinaturas dos métodos mantidas → `victory_vault_router` e `core/veredito_ia` não precisaram mudar. Auto-seed do JSON mock na 1ª vez que a tabela está vazia (preserva o conteúdo de demonstração). Adicionado `vault` (instância de módulo) + alias `buscar_modelos` para resolver o import do engine órfão. |

> Head do Alembic agora é **`054_victory_vault`** (chain único 054→053→052). O `scripts/aplicar_correcoes_053.sh` já copia ambas as migrations e `alembic upgrade head` aplica as duas.

## FASE 4b — Engine de geração por template religado (executado 28/06/2026)
| Arquivo | Mudança |
|---|---|
| `backend/app/core/document_template_engine.py` (reescrito) | Métodos agora **async** e com `await` (antes eram sync chamando o vault async sem await — nunca funcionavam); campos corrigidos (`m.nome` inexistente → `tipo_documento`/`descricao`); usa `vault.get_modelo_por_id` p/ render. |
| `backend/app/core/victory_vault.py` | Adicionado `get_modelo_por_id(id)`. |
| `backend/app/routers/peca_geracao_router.py` (reescrito) | Era órfão, sem auth, quebrado. Agora **registrado** com prefixo único `/api/document-templates`, **exige JWT**, endpoints async: `GET /` (lista) e `POST /generate` (renderiza Jinja2). Sem colisão com `peca_geracao.py` (`/pecas`, geração via IA). |
| `backend/app/main.py` | `peca_geracao_router` importado e incluído. → 108 routers, 0 órfãos. |

> `jinja2==3.1.4` já está em `requirements.txt` — registrar o router não quebra o boot.

## FASE 4c — Frontend Victory Vault religado na UI (executado 28/06/2026)
| Arquivo | Mudança |
|---|---|
| `frontend/src/components/VictoryVaultPanel.tsx` | `axios` cru → cliente central `lib/api` (com JWT/refresh); paths `/api/v1/victory_vault/*` → `/victory_vault/*`; `modelo.nome` (inexistente) → `descricao`/`tipo_documento`. |
| `frontend/src/components/AssistedWritingMode.tsx` | `lib/api`; `/api/v1/templates`→`/document-templates/`; `/api/v1/generate-document` (querystring) → `POST /document-templates/generate` com **body JSON** `{template_id, data}`; `template.nome`→`descricao`/`tipo_documento`. |
| `frontend/src/components/VeredutoIAWithVictoryVault.tsx` (reescrito) | `lib/api`; path inexistente `/api/v1/veredito-ia/predict-success` → real `POST /veredito_ia/analisar` com body `{tese_juridica, area_juridica, tribunais_selecionados}`; render alinhado à resposta real (`probabilidade_exito`, `teses_vitoriosas_similares`, `jurisprudencia_suporte`, `sugestoes_contextualizadas`); adicionado seletor de área. |
| `frontend/src/pages/VictoryVault.tsx` (novo) | Página com abas (Acervo / Veredito IA / Escrita Assistida) hospedando os 3 painéis. |
| `frontend/src/App.tsx` | Lazy import + `<Route path="/victory-vault">`. |
| `frontend/src/components/Layout.tsx` | Item de menu "Victory Vault" no grupo **Inteligência** (ícone Gavel). |

> Os 5 endpoints chamados agora batem com o backend real e autenticado: `/api/victory_vault/{teses,modelos}`, `/api/document-templates/` + `/generate`, `/api/veredito_ia/analisar`. **Ressalva:** sem `node_modules` nesta máquina, validei por **análise estática** (imports/paths/exports/tipos) — não por `tsc`/`vite build`. Rode `npm run build` antes do deploy do frontend.

## NÃO alterado
- `DashboardModernLuxury.tsx` permanece não-roteado (era um dashboard alternativo). Os 3 painéis agora vivem na página dedicada `/victory-vault`, então não dependem mais dele.
- **Componentes frontend órfãos** (VictoryVaultPanel, VeredutoIAWithVictoryVault, AssistedWritingMode, DashboardModernLuxury, WhatsAppChatbot, MarketIntelligencePanel): inertes (não renderizados). Decidir destino.

## DEPLOY (executar manualmente — backup ANTES)
```bash
# a partir de /opt/ejc, com backup do banco já feito (Regra 10)
docker cp backend/alembic/versions/053_reconcile_schema.py ejc_backend:/app/alembic/versions/
docker cp backend/app/. ejc_backend:/app/app/         # ou rebuild da imagem
docker compose exec backend sh -c 'cd /app && alembic upgrade head'
docker compose restart backend
docker compose build frontend && docker compose up -d frontend
# validar
curl -s http://localhost:8000/api/health
curl -s "http://localhost:8000/api/v1/datajud/..." -H "Authorization: Bearer $TOKEN"
```
