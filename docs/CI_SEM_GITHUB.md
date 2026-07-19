# CI sem custo — rodando a validação fora do GitHub Actions

## Por que

O **repositório privado no GitHub é grátis** — o que cobra é o **GitHub Actions**
(as máquinas na nuvem que rodavam os testes a cada push). O plano grátis dá um
teto mensal de minutos; a suíte do EJC (~8 min) rodava a cada push e estourava,
bloqueando o CI (os jobs morriam em ~2s sem runner). **Solução: manter o código
no GitHub (grátis) e rodar a validação de graça no seu VPS/máquina.**

## O CI local (`scripts/ci-local.sh`)

Roda exatamente o que o antigo `ci.yml` rodava — backend (Postgres+pgvector →
`alembic upgrade head` → `pytest` com banco) e frontend (typecheck + build) —
**sem custo, sem GitHub**.

```bash
scripts/ci-local.sh            # tudo (backend + banco + frontend)
scripts/ci-local.sh backend    # só backend (com banco)
scripts/ci-local.sh frontend   # só frontend
scripts/ci-local.sh fast       # backend SEM banco (rápido — para pre-push)
```

- **Postgres:** usa Docker (`pgvector/pgvector:pg16`) se houver; senão sobe um
  cluster local efêmero com `initdb` (requer `postgresql-16` +
  `postgresql-16-pgvector`). O banco é criado e destruído a cada execução.
- **Pré-requisitos:** `python3`, e para o frontend `node`/`npm`. Numa 1ª execução
  ele cria um venv e instala as dependências; use `CI_SKIP_PIP=1` para re-runs
  rápidos quando as dependências já estão instaladas.
- Sai com código ≠ 0 se qualquer etapa falhar (serve de gate real, como o CI).

Validado nesta configuração: **2157 passed, 2 skipped** (suíte completa com banco).

### No VPS
Você já tem Docker no VPS (usa docker-compose pro EJC). Lá o script usa o Docker
automaticamente:

```bash
cd /caminho/do/ejc && git pull && scripts/ci-local.sh
```

## Gate automático antes do push (opcional)

Ative o hook uma vez e o CI local roda sozinho a cada `git push`:

```bash
git config core.hooksPath .githooks
```

- Por padrão roda o modo `fast` (segundos). Para o gate completo:
  `EJC_PREPUSH_MODE=full git push`.
- Pular pontualmente: `git push --no-verify`.

## O que foi desligado no GitHub

Os workflows que rodavam sozinhos (e consumiam minutos) foram postos em
**manual-only** (`workflow_dispatch`), de forma reversível:

- `.github/workflows/ci.yml` — Backend + Frontend
- `.github/workflows/ejc-release-gate.yml` — P0 guard

> Observação: os gatilhos de `push`/`pull_request` são lidos do branch **default**
> (`main`). Então a desativação passa a valer quando esta mudança estiver na
> `main` — a partir daí, nada roda sozinho no Actions e o "X vermelho" some.
> `deploy-vps.yml` e `frontend-ci.yml` já eram manuais e ficaram como estavam.

### Reativar o CI na nuvem depois
Se um dia quiser o CI de volta no GitHub (com billing do Actions ativo), restaure
os gatilhos originais nos dois arquivos:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

### Alternativa: runner self-hosted (grátis, com a UI do GitHub)
Se quiser manter os checks bonitos de PR no GitHub **sem pagar minutos**, dá para
registrar um **self-hosted runner** no VPS (Settings → Actions → Runners) e trocar
`runs-on: ubuntu-latest` por `runs-on: self-hosted` nos workflows — a computação
passa a ser do seu VPS (Actions minutes = 0). Peça que eu preparo o passo a passo.
