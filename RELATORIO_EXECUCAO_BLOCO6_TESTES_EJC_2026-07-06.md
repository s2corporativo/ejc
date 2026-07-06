# Relatório de Execução — Bloco 6 (Testes pendentes) — EJC — 2026-07-06

_Bloco 6 do prompt de correção: os testes que a auditoria funcional original NÃO
exercitou. A forma mais durável de "executar" essas validações é convertê-las em
**testes automatizados** que o CI roda a cada push. Branch reiniciada a partir da
`main` (que já contém os Blocos 1–5, PR #116 mergeada)._

## Resumo

| Item do Bloco 6 | Como foi coberto | Status |
|---|---|---|
| Logout + login com credenciais inválidas | `tests/test_bloco6_auth.py` (5 testes, endpoints reais) | **Coberto (automatizado)** |
| Permissões por perfil (advogado/estagiário/financeiro…) | `tests/test_bloco6_rbac_papel.py` (RBAC central `require_roles`) | **Coberto (automatizado)** |
| Lixeira: exclusão lógica + restauração | `tests/test_bloco6_lixeira_restore.py` (router `/trash` real) | **Coberto (automatizado)** |
| Responsividade mobile/tablet | Auditoria estática (fundamentos corretos) + checklist de QA manual | **Verificado por inspeção; QA visual pendente** |

Suíte backend: **876 passed, 48 skipped** (era 838; +38 testes novos). Sem Postgres
(unidade + `TestClient` com `dependency_overrides`, padrão de `test_search.py`).

---

## 1. Logout e login inválido — `test_bloco6_auth.py`

Exercita `/auth/login` e `/auth/logout` reais (inclui o wrapper `@limiter.limit`),
com DB substituível. Cada teste usa `X-Forwarded-For`/e-mail únicos para isolar os
contadores por-IP (anti-brute-force + slowapi).

- **login e-mail inexistente → 401** e grava `LOGIN_FALHA` na auditoria.
- **login senha incorreta → 401.**
- **anti-brute-force:** 5 falhas (401) e a 6ª tentativa do mesmo IP → **429**.
- **logout com token válido → 200** e emite a revogação (`UPDATE RefreshToken SET revoked=True`) + commit.
- **logout com token inválido → 200 idempotente**, sem escrita no banco.

## 2. Permissões por perfil — `test_bloco6_rbac_papel.py`

Trava o comportamento REAL do gate central `require_roles`, que é **hierárquico
pelo MENOR nível da lista** (não só a lista literal). Achado importante e
não-óbvio, agora coberto:

- **Gate financeiro** `[superadmin, admin, socio, financeiro]` (nível mín. 4): passam
  superadmin/admin/socio/**advogado**/**advogado_auxiliar**/financeiro — advogado
  passa por hierarquia (nível 6 ≥ 4) mesmo sem estar na lista. Barrados: estagiário,
  secretaria, cliente_externo.
- **Gate sensível** `[superadmin, admin, socio]` (nível mín. 7): passam só
  superadmin/admin/socio. **advogado (6) é BARRADO** — confirma que advogado NÃO vê
  Auditoria/Lixeira/Conhecimento/Curadoria RAG.
- `require_admin`: passa admin/superadmin; barra socio e abaixo (403).
- `has_permission`: matriz por perfil (advogado tem `casos`/não `honorarios`;
  financeiro o inverso; estagiário `tarefas`/não `honorarios`; superadmin curinga).
- Hierarquia de níveis estrita e sem empates (regressão do bug v2 da chave `socio`
  duplicada).

> Observação: o RBAC de fato imposto está no backend (estes gates). A restrição de
> menu no frontend (`roles` em `Layout.tsx`) é complementar (UX). Recomendação da
> auditoria mantida: nenhuma tela sensível deve depender só do bloqueio no frontend.

## 3. Lixeira (soft-delete + restauração) — `test_bloco6_lixeira_restore.py`

Router `/trash` real, DB substituível:

- **restaurar** um registro da lixeira → limpa `deleted_at` (soft-delete revertido),
  grava auditoria `RESTORE`, commit, **200**.
- **restaurar** id fora da lixeira → **404**; entidade inválida → **422**.
- **listar** devolve só registros com `deleted_at` preenchido (rótulo por entidade).
- **Gate RBAC:** advogado é barrado (**403**) em restaurar e listar (Lixeira é socio+).

> Nota: a exclusão lógica em si (marcar `deleted_at`) já é coberta por testes de
> ownership/segurança existentes; aqui o foco é a **restauração** e o gate da Lixeira.

## 4. Responsividade mobile/tablet — verificação por inspeção + QA manual

Não automatizado (exigiria adicionar Playwright/vitest — churn de dependência para
uma preocupação essencialmente visual). Fundamentos verificados no código:

- **Viewport meta presente:** `<meta name="viewport" content="width=device-width, initial-scale=1.0">` (`frontend/index.html`).
- **Menu responsivo (drawer):** `Layout.tsx` tem botão hambúrguer `md:hidden`, overlay
  de fundo `md:hidden` e sidebar `menuOpen ? "flex w-72 md:flex" : "hidden md:flex"`
  — padrão correto (esconde a barra no mobile, abre por toque, fixa em `md+`).
- 16 classes de breakpoint Tailwind (`sm:/md:/lg:/xl:`) no shell.

**Checklist de QA manual (executar em dispositivo/DevTools real — 375px e 768px):**
1. Login renderiza sem overflow horizontal; formulário utilizável.
2. Sidebar abre/fecha pelo hambúrguer; overlay fecha ao tocar fora.
3. Tabelas densas (Casos, Prazos, Auditoria, Honorários) rolam dentro do próprio
   container (sem estourar a página).
4. Modais (Novo caso/cliente) cabem na viewport e são roláveis.
5. Kanban e workspaces (Financeiro em abas) navegáveis por toque.

---

## Git

Branch reiniciada de `origin/main` (PR #116 já mergeada — trabalho anterior não é
reaproveitado no mesmo PR). Um commit por arquivo de teste (item). Nova PR aberta
para o Bloco 6.
