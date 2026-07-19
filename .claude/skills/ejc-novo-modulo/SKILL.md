---
name: ejc-novo-modulo
description: >
  Receita para construir um MÓDULO VERTICAL completo no EJC ponta a ponta — model
  SQLAlchemy + schema Pydantic + service + router FastAPI + registro em main.py +
  migration Alembic + página React + entrada no moduleRegistry + testes (pytest/vitest),
  preservando auth/ownership/auditoria e os padrões do repo. Use SEMPRE que a tarefa for
  CRIAR funcionalidade nova no EJC (nova tela + endpoints), não só corrigir. Aciona em:
  "novo módulo EJC", "nova funcionalidade EJC", "nova tela EJC", "novo endpoint EJC",
  "criar módulo", "adicionar página no EJC", "novo router FastAPI EJC", "moduleRegistry".
---

# Novo módulo vertical no EJC — a receita

Como adicionar uma vertical completa (backend + frontend + banco + testes) no padrão real
do repo, sem quebrar auth, ownership, auditoria ou o design system.

> Antes de ler código cru, oriente-se pelo grafo: `graphify query "<módulo parecido>"`,
> `graphify explain "<conceito>"`. Inclua esta regra em todo subagente que explorar código.
> Após editar, o hook roda `graphify update .`.

## Delegação (não faça tudo na thread principal)
`backend-fastapi` (model/schema/service/router) + `db-migrations` (migration) + `frontend-react`
(página + registry) em paralelo → `qa-tests` → `security-auditor` (se tocar auth/uploads/PII)
→ `code-reviewer` → `verifier` → `simplifier`.

## Backend

**Onde:** módulo simples → `backend/app/routers/<modulo>.py`. Vertical coeso → pasta
`backend/app/modules/<modulo>/` (`router.py`, `__init__.py`, `service.py`), como
`app/modules/case_partes/`.

1. **Model** (`app/models/<modulo>.py`): SQLAlchemy 2.0, herda `Base` de `app.core.database`;
   enums via `str, enum.Enum`; FKs para `cases`/`clients`/`users` quando aplicável.
2. **Schema** Pydantic v2: inline no router (padrão de `checklists.py`) ou em `app/schemas/`.
   Use `Field(min_length=…, max_length=…)` — a validação de entrada é a 1ª barreira.
3. **Service** (regra de negócio): mantenha o router fino; lógica no service (`app/services/`
   ou `modules/<x>/service.py`). Não repita query/permissão em cada endpoint.
4. **Router**:
   ```python
   from fastapi import APIRouter, Depends, HTTPException
   from sqlalchemy.ext.asyncio import AsyncSession
   from app.core.database import get_db
   from app.core.security import get_current_user, ROLE_LEVEL   # ou app.core.auth_middleware
   from app.core.ownership import verificar_acesso_caso          # se for escopado por caso
   from app.modules.auditoria.middleware import registrar_acao

   router = APIRouter(prefix="/<modulo>", tags=["<Módulo>"])

   @router.post("", status_code=201)
   async def criar(payload: <Schema>In, db: AsyncSession = Depends(get_db),
                   current_user=Depends(get_current_user)):
       await verificar_acesso_caso(db, payload.case_id, current_user)   # anti-IDOR
       # ... service ...
       await registrar_acao(...)   # trilha de auditoria
   ```
5. **Registrar** em `backend/app/main.py`: `app.include_router(<modulo>.router, prefix=API)`
   (`API = "/api"`; o middleware JWT global já cobre `/api/*`).

## Banco (Alembic) — delegue a `db-migrations`
`cd backend && alembic revision --autogenerate -m "add <modulo>"` → **revise** o arquivo
gerado (há guarda no autogenerate; nunca confie cego) → `alembic upgrade head`. Todo
migration precisa de `downgrade` funcional. Não crie heads múltiplos.

## Frontend

1. **Página** `frontend/src/pages/<Modulo>.tsx`: reutilize `components/UI.tsx`
   (`PageHeader`, etc.) e `Toast.tsx`; **toda** chamada HTTP via `lib/api.ts` (nunca crie
   instância axios paralela). Tipos em `src/types`.
2. **Registrar** em `frontend/src/config/moduleRegistry.tsx` — a rota nasce daqui (App.tsx
   consome o registry). Adicione o lazy import e uma entrada `ModuleRoute`:
   ```ts
   const <Modulo> = lazy(() => import("../pages/<Modulo>"));
   // ...
   { key: "<modulo>", path: "/<modulo>", label: "<Rótulo>", description: "…",
     group: "<grupo>", icon: <LucideIcon>, component: <Modulo>,
     roles: ROLES.juridico, status: "beta", showInNav: true,
     backendPrefixes: ["/<modulo>"], usesAI: false, sensitive: false }
   ```
   `roles` espelha a matriz do backend; `status` (`active|beta|legacy|hidden`); marque
   `sensitive`/`usesAI` quando aplicável.

## Testes
- Backend: `cd backend && python -m pytest tests -v` — siga o estilo de `tests/` (client
  async, fixtures de `conftest.py`). Cubra caminho feliz + 403 (ownership/role) + validação.
- Frontend: `cd frontend && npm run lint` (tsc), `npm run test` (vitest — ex.:
  `lib/moduleLifecycle.test.ts`), `npm run build`.

## Regras invioláveis
- Endpoint escopado por caso → SEMPRE `verificar_acesso_caso` (anti-IDOR). Ação relevante →
  `registrar_acao` (auditoria). RBAC no backend (`ROLE_LEVEL`/`Depends`) E no `roles` do
  registry — o backend é a fonte de verdade.
- Sem segredos no código; `.env.example` é o contrato. Uploads/entrada do usuário validados
  por Pydantic + sanitização.
- Não introduza dependência nova sem necessidade; reutilize service/UI/tipos existentes.

## Antes de concluir
`qa-tests` (pytest + vitest/tsc/build verdes) → `security-auditor` (se sensível) →
`code-reviewer` → `verifier` (exercita o fluxo real, não só testes) → `simplifier` →
`graphify update .`.
