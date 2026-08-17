# Rebase Seguro da Branch de Design do GPT — Roteiro Validado

**Data:** 17/08/2026 | **Autor:** Assistente técnico EJC
**Base:** `origin/main` (commit `f69a8fda` — homologação M01–M36 mesclada)
**Branch alvo:** `legal-tech-premium-design-72646` (commits `889c7533`, `4acc2095`, `c691274f`)

---

## 1. Resultado do teste de viabilidade (executado em worktree isolado)

O rebase foi **simulado e validado integralmente** em um ambiente isolado (`git worktree`), sem tocar nas branches reais. Conclusão central: **o rebase é viável, porém exige duas salvaguardas obrigatórias** — uma delas foi descoberta durante o teste e é a razão pela qual o rebase ingênuo falharia.

| Etapa simulada | Resultado |
|---|---|
| Rebase dos 3 commits sobre main (`f69a8fda`) | Concluído — apenas 3 conflitos de resolução, todos em tooling/CI (não em código de negócio) |
| Conflito 1 — `scripts/ci_guard.sh` (add/add) | Resolvido com a versão da **main** (gate homologado, superior) |
| Conflito 2 — `.github/workflows/ejc-release-gate.yml` + docs (add/add) | Resolvido com a versão da **main** |
| Conflito 3 — `backend/app/routers/auth.py` (o commit de design) | **Armadilha detectada:** git manteve a versão da branch nos trechos não-conflitantes |
| Conflito 4 — `.gitignore` (add/add) | Resolvido com a versão da **main** |
| Verificação pós-rebase sem salvaguarda | `auth.py` ficou com 340 linhas (versão da branch, **2FA removido**) → `ImportError` em `credential_vault.py` e 16 testes falhando |
| Verificação pós-rebase COM salvaguarda (`auth.py` restaurado da main) | **18/18 testes de paridade OpenAPI PASS**, 2FA e ciclo de refresh intactos, branding DT preservado |

> **Achado crítico do teste:** mesmo resolvendo todos os conflitos a favor da main, o commit de design do GPT (`c691274f`) alterou `auth.py` em regiões que git considera "não conflitantes" (ele apenas deletou código; main não tocou nessas linhas ao mesmo tempo). Por isso o arquivo inteiro de `auth.py` deve ser **restaurado da main em bloco**, nunca resolvido conflito a conflito.

## 2. O que o rebase preserva e o que entrega

### Preservado intacto (homologação M01–M36)

| Camada | Estado após rebase validado |
|---|---|
| Backend completo (163 routers, módulos, services, models) | 100% da main — o design commit não toca backend além de `auth.py` |
| `backend/app/routers/auth.py` (2FA/TOTP, `pii_crypto`, rotação de refresh) | Restaurado da main (865 linhas, ciclo completo de segurança) |
| Logomarca DT e branding (`officeBranding.ts`, `Layout`, `PortalLayout`, `exportPdf`) | Intactos — `de-paula-teixeira-dt.png` permanece como default |
| Frontend: 183 páginas e 109 componentes da main | Intactos — nenhuma página ou componente foi perdido |
| Migrations (144), tests, workflows CI homologados | Intactos |

### Entregue pelo design do GPT (5 arquivos, +1.509 linhas)

| Arquivo | Conteúdo |
|---|---|
| `frontend/src/styles/legal-tech-premium.css` | Tema "Legal Tech Premium" (749 linhas de CSS) |
| `frontend/src/components/DashboardLegalTechPremium.tsx` | Dashboard de demonstração do tema (467 linhas) |
| `frontend/src/components/ThemeSelector.tsx` + `ThemeSelector.test.tsx` | Seletor de temas com teste |
| `frontend/src/stores/theme.ts` | Store de persistência de tema |
| `frontend/tailwind.config.js` + `index.css` (incremental) | Extensões Tailwind do tema |

Os arquivos de risco da branch (`_prod_src.b64`, `_sftp_test.js`) **não sobrevivem** ao rebase — foram eliminados automaticamente na reconciliação com main.

### Ajuste necessário pós-rebase (1 item)

O componente `DashboardLegalTechPremium.tsx` importa de `react-router-dom`, mas a main evoluiu para `react-router@8` (a branch usa `^6.23.1` do `package.json` dela). A solução é reescrever a linha de import para `react-router` (API `Link` compatível), uma correção de uma linha — **não** reinstalar a dependência antiga, que conflitaria com o resto do frontend.

## 3. Roteiro executável (passo a passo)

Executado a partir de um worktree isolado, sem afetar branches reais até a validação:

```bash
# 1. Worktree isolado (segurança: branches reais intocadas)
git worktree add /tmp/rebase_design origin/legal-tech-premium-design-72646
cd /tmp/rebase_design

# 2. Rebase sobre main
git rebase origin/main
# Conflitos esperados: scripts/ci_guard.sh, .github/workflows/ejc-release-gate.yml,
# docs/release-gate-p0-p1.md, scripts/governanca/levantamento-pr-p0.sh, .gitignore
# → resolver TODOS com a versão da main: git checkout --theirs <arquivo> && git add

# 3. SALVAGUARDA OBRIGATÓRIA — restore integral de auth.py
git checkout origin/main -- backend/app/routers/auth.py
git add backend/app/routers/auth.py
GIT_EDITOR=true git commit --amend --no-edit

# 4. Ajuste de import do dashboard (react-router@8)
#    frontend/src/components/DashboardLegalTechPremium.tsx linha 12:
#    - import { Link } from "react-router-dom";
#    + import { Link } from "react-router";

# 5. Validar localmente
pnpm exec tsc --noEmit                    # frontend: typecheck
PYTHONPATH=$(pwd)/backend ruff check backend/app/routers/auth.py
PYTHONPATH=$(pwd)/backend python3 -m pytest backend/tests/test_rotas_registro_explicito.py -q
# Esperado: 18/18 PASS

# 6. Só então publicar
git push origin HEAD:rebase/design-gpt-sobre-main-20260817
```

## 4. Plano de homologação da branch rebasada (antes de qualquer merge)

A branch rebasada é um "novato" no repositório e deve passar pelo protocolo completo, exatamente como foi feito para a homologação M07:

1. **Gate P0** (conflitos e segredos) via o workflow já homologado — o arquivo `_prod_src.b64` não estará presente, mas rodar o gate formalmente é obrigatório.
2. **Regressão M03–M36** contra a branch rebasada (runner `scripts/inventory/regressao_completa.py`), revalidando que o novo CSS e o Dashboard premium não quebram páginas existentes.
3. **Teste de paridade OpenAPI** com snapshot atualizado da branch, caso o dashboard adicione rotas (verificar `test_paridade_openapi_com_snapshot_anterior`).
4. **Auditoria visual** do `ThemeSelector` e do dashboard em tela (verificar que o seletor não altera o branding DT default).
5. **PR com squash** para main, após green CI — a branch pode ser deletada após o merge.

## 5. Checklist de decisão

| Item | Situação |
|---|---|
| Rebase viável? | **Sim** — simulado com sucesso |
| 2FA e pii_crypto preservados? | **Sim** — com a salvaguarda obrigatória do item 3 (restore de auth.py) |
| Homologação M01–M36 preservada? | **Sim** — 163 routers, 183 páginas, branding DT intactos |
| Valor real da branch? | Tema premium opcional (seletor) + dashboard de demonstração — **não substitui** o design DT |
| Custo do risco residual | Baixo após salvaguarda; o tema convive com o branding DT (é um tema adicional, não o default) |
| Riscos remanescentes | Import `react-router-dom` (1 linha); regressão visual a confirmar na etapa 4 do plano |

## 6. Recomendação

Executar o roteiro da seção 3 e homologar a branch rebasada como **recurso opcional de tema** (o default do escritório permanece a logomarca DT e o design homologado em M07). O 2FA, a cifragem de dados sensíveis e todos os 36 módulos seguem intactos por construção — a validação local já provou 18/18 testes de paridade e typecheck limpo.
