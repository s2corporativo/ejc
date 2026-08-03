# Relatório — FASE 5 (parcial): Testes + Higiene (EJC)

**Data:** 2026-06-29 · **Escopo:** rede de segurança (testes) + remoção reversível de órfãos/resíduos. Sem refatoração ampla, sem deletar nada.

---

## A. Testes (rede de segurança das Fases 1–3)

Suíte em `backend/tests/` (pytest + pytest-asyncio, **sem banco**). **64 testes, todos passando.**
Rodar: `cd backend && python -m pytest tests -q`.

| Arquivo | Protege |
|---|---|
| `test_security.py` | hash bcrypt (seed/login) |
| `test_sanitizer.py` | sanitização PII/LGPD — Fase 3B |
| `test_ownership.py` | gate IDOR (gestão/equipe/anti-lockout/403/404) — Fase 3A |
| `test_rag_isolation.py` | filtro fail-closed do RAG por cliente — Fase 3B |
| `test_smoke.py` | app monta (453 rotas) + rotas Fase 1 + cadeia Alembic íntegra (Fase 2) |
| `test_calc_prescricao.py` | prescrição/decadência (CC/CDC/CLT/CTN) |
| `test_calc_trabalhista.py` | verbas rescisórias CLT (aviso proporcional, teto 90d, multa FGTS, validações) |
| `test_calc_custas.py` | custas/UFEMG TJMG (conversões + guarda fail-closed da tabela) |
| `test_tax_tables.py` | INSS/IRRF 2026 (faixa-a-faixa, teto, isenção Lei 15.270, redutor parcial) |
| `test_deadline_calculator.py` | prazos: Páscoa (Gauss), feriados móveis, dias úteis, prazo corrido c/ prorrogação, prescrição |
| `test_document_format.py` | padronização jurídica (remove `**`/markdown, normaliza ASCII) — "asteriscos brutos" do laudo |
| `test_security_service.py` | IP real (X-Forwarded-For/Real-IP) + anti-brute-force (bloqueio após N falhas) |

Config: `backend/pytest.ini`, `backend/conftest.py`. Os testes **não** entram na imagem de produção (Dockerfile só copia `app`/`alembic`/`seeds`).

### A.1. Telas sem backend (404) → "em desenvolvimento" (2026-06-29)

`FerramentasIA` (`/ai/skills/*`) e `GovernancaIA` (`/ia-governanca/*`) têm frontend pronto mas o
**backend nunca foi construído** → davam 404 e quebravam. Por decisão do usuário, criado
`components/EmDesenvolvimento.tsx`; as 2 telas detectam a falha e mostram aviso claro em vez de
quebrar (`tsc --noEmit` = 0). **Não é nova funcionalidade** — construir esses backends fica como
projeto à parte.

### A.3. Modelos ORM das tabelas antes só-SQL (2026-06-29)

Criado `app/models/operacional.py` com 6 modelos espelhando **exatamente** o DDL das migrations
(verificado gerando `CREATE TABLE` via SQLAlchemy e comparando): `Process` (processes),
`PricingRule`, `InadimplenciaAlert`, `CaseAmbiental`, `DueDiligenceTemplate`, `DocumentAccessLog`.
Registrados em `models/__init__.py`. `Base.metadata` foi de **65 → 71 tabelas** (baseline `create_all`
agora cobre tudo). Sem `relationship()` (não altera models existentes); tipos/FKs/CHECKs/defaults/
índices idênticos às migrations; `create_all` usa checkfirst (não toca banco existente). App sobe
(453 rotas), 38 testes verdes, cadeia Alembic intacta (head 051).

### A.2. Itens adiados (não validáveis neste ambiente)

Docker **indisponível** no sandbox → não dá pra validar build de imagem. Adiados para o deploy:
**container não-root** (Dockerfile `USER`) e **slim de dependências de dev** (separar pytest/ruff/
pre-commit em `requirements-dev.txt`). Seriam mudanças no build sem como testá-las aqui.

## B. Higiene — quarentena reversível (nada apagado)

Todos os itens **movidos** para `_QUARENTENA/` (restauráveis). `tsc --noEmit` do frontend **continua exit 0** após a remoção.

### `_QUARENTENA/frontend_orfaos/` (11 arquivos, 0 imports vivos)
Inclui a **mina de jurisprudência falsa** (laudo §10): `EscritaAssistida` ("Tema 69 STF"),
`RadaresEspecializados` ("Nova Súmula TST"), `MarketIntelligencePanel` (concorrentes
fictícios) — risco direto à regra "NUNCA inventar jurisprudência" se reativados.
Também: `DashboardModernLuxury` (raiz órfã), `RadarLegislativo`, `PortalClientePlatinum`,
`WhatsAppChatbot`, `FocusToday`, `pages/Login.tsx` (app usa `LoginModern`), 2 CSS órfãos.

### `_QUARENTENA/residuos/` (sem segredo, já verificado na Fase 0)
`frontend/Dockerfile.bak`, `frontend/public/sw.js.bak`, `vps-tools/generated/` (22 patches),
`_session_componentes_bronze/`.

### Mantido no lugar
`backend/.venv-codex` (522 MB) — único venv com dependências (roda os testes); já gitignored. Remoção física só com confirmação.

## C. Validação
- ✅ Backend: `pytest` 21/21 verde.
- ✅ Frontend: `tsc --noEmit` exit 0 (sem imports quebrados após a quarentena).

## D. Pendente
- **Fase 4** (consolidação de domínios duplicados: IA 7→1-2, honorários 4→1, dossiê 3→1) — refatoração ampla; recomendado **após** validar o deploy das Fases 0–3.
- **Fase 5 restante**: modelos ORM para tabelas SQL-cru; re-indexação do RAG (apagar PII já vetorizada); testes de integração com Postgres efêmero; separar dev-deps da imagem de produção; container não-root.
