# Homologação H01–H15 (roteiro P0)

Ativos da **P0 "Homologação H01–H15"** do `RELATORIO_MELHORIA_GERAL_EJC_2026-07-22.md` (§6, §10).
Espelha `qa/e2e/run_fictitious_smoke.py`: HTTP contra a API real, com massa fictícia
(marcador `HOMOLOG-FICTICIO`).

## Arquivos

| Arquivo | O que é |
|---|---|
| `matriz_homologacao.json` | Matriz declarativa dos 15 cenários. Cada cenário: caminho feliz + ≥1 acesso negativo + (onde cabe) idempotência/retomada. Cada passo declara `actor`, `expected` e `requires` (capacidades). |
| `run_homologacao.py` | Executor. Modo `--validate` (sem rede, para CI) e modo HTTP real. Reporta por cenário `PASS` / `FALHA` / `BLOQUEADO`. |
| `reports/homologacao_report.json` | Saída da última execução real (gerada; não versionar como verdade). |

## Modelo de capacidades (o que é BLOQUEADO-por-ambiente)

| Capacidade | Como habilitar | Sem ela |
|---|---|---|
| `stack` | Backend+banco de pé em `EJC_BASE_URL` e login staff OK | tudo BLOQUEADO |
| `portal` | `EJC_PORTAL_EMAIL`/`EJC_PORTAL_PASSWORD` (um login `cliente_externo`) | positivos do portal + IDOR cross-client BLOQUEADO (os NEGATIVOS de allowlist não dependem disso) |
| `ai` | provedor de IA + `EJC_HAS_AI=true` | passos de IA (H03/H07/H10) BLOQUEADO |
| `ops` | procedimento operacional (backup/deploy) | H13/H14 são BLOQUEADO — validação **manual** por RUNBOOK |

`BLOQUEADO` **não é falha**: é honestidade sobre o que aquele ambiente não consegue exercitar.
`FALHA` só ocorre quando um passo executável devolve status fora do `expected`.

## Uso

```bash
# 1) Validação estrutural — SEM rede (roda em CI; valida a matriz e imprime o plano)
python qa/homologacao/run_homologacao.py --validate

# 2) Execução real — exige a stack de pé (staging/homologação/localhost)
EJC_BASE_URL="http://localhost:8000" \
EJC_TEST_EMAIL="admin@dominio-valido.com.br" EJC_TEST_PASSWORD="..." \
EJC_PORTAL_EMAIL="cliente@dominio-valido.com.br" EJC_PORTAL_PASSWORD="..." \
EJC_HAS_AI=true \
python qa/homologacao/run_homologacao.py
```

Proteção de produção: o executor recusa uma `EJC_BASE_URL` que não contenha
`staging`/`homolog`/`localhost`/`127.0.0.1`, salvo `EJC_ALLOW_PRODUCTION_E2E=true`.

> **Atenção — domínio de e-mail (trap P0 #8):** o login usa `EmailStr`, que **rejeita
> domínios reservados** (`.test`, `.local`, `.example`) com **422** antes de checar a
> senha. Use um domínio **válido** (ex.: `...@homolog.com.br`) para as credenciais e
> para os e-mails de teste — senão o login trava em 422, não em 401. Isto corrobora
> o achado P0 #8 do relatório (armadilha de `ADMIN_EMAIL` com domínio reservado).

## Cobertura em CI vs. stack

- **Roda no CI sem stack:** `--validate` (integridade da matriz, presença dos 15
  cenários, ≥1 negativo por cenário com passos, capacidades declaradas).
- **A matriz exaustiva de IDOR/segregação do Portal** (os negativos de allowlist e o
  isolamento row-level) já é **automatizada e verde** no pytest:
  - `backend/tests/test_portal_idor_matrix.py` — allowlist do `cliente_externo` +
    gate `_exigir_cliente` (SEM banco; roda na suíte rápida do CI).
  - `backend/tests/test_portal_idor_matrix_dblevel.py` — isolamento row-level entre
    clientes A/B (Postgres; `RUN_DB_TESTS=1`).
- **Exige stack de pé:** o modo HTTP do executor (caminhos felizes reais + negativos
  reais ponta a ponta).
- **Exige IA:** H03/H07/H10 (extração/geração/Raio-X).
- **Manual (RUNBOOK):** H13 (backup/restauração ponta a ponta) e H14 (deploy/rollback real).
