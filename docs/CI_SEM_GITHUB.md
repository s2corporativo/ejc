# CI local-first — validação sem dependência do GitHub Actions

## Regra operacional atual

O EJC adota **local-first**: checkout DEV + Git local + `scripts/ci-local.sh` são o caminho primário de desenvolvimento e validação. GitHub/GitHub Actions permanecem úteis para sincronização, colaboração e controles adicionais, mas a indisponibilidade do remoto não deve bloquear checkpoint, edição ou testes locais.

Use o orquestrador:

```bash
bash scripts/ejc-local-first.sh work full
```

Ele cria checkpoint recuperável, roda o CI local e tenta sincronizar a branch em best-effort. Se o GitHub estiver indisponível, entra em modo offline sem reset/rebase/force e mantém o trabalho preservado. Procedimento completo: `docs/OPERACAO_LOCAL_FIRST.md`.

## Por que

O risco operacional não é apenas custo de GitHub Actions: DNS, autenticação, disponibilidade do serviço, limite de runner ou falha de rede podem tornar o remoto temporariamente inacessível. Nenhuma dessas falhas deve impedir o EJC de preservar código e executar validação técnica na infraestrutura já disponível.

O GitHub continua como histórico remoto e destino de sincronização. O trabalho imediato, contudo, não depende dele.

## O CI local (`scripts/ci-local.sh`)

Executa a validação de backend e frontend fora do GitHub Actions:

```bash
scripts/ci-local.sh            # tudo (backend + banco + frontend)
scripts/ci-local.sh backend    # só backend (com banco)
scripts/ci-local.sh frontend   # só frontend
scripts/ci-local.sh fast       # backend sem banco, ciclo rápido
```

No modo com banco:

- cria PostgreSQL + pgvector efêmero;
- habilita extensões exigidas pelo EJC;
- executa `alembic upgrade head`;
- roda a suíte backend com banco;
- no fluxo completo, executa typecheck/build do frontend.

O próprio CI local também executa o teste de regressão do mecanismo `ejc-local-first.sh` quando ele está presente.

## No VPS ou máquina DEV

```bash
cd /caminho/do/checkout-dev
bash scripts/ejc-local-first.sh work full
```

`git pull` não é pré-condição para validar. Se o remoto estiver fora, o checkout local permanece utilizável e os checkpoints ficam fora da árvore versionada.

## GitHub Actions

Os workflows continuam sendo controles adicionais quando o GitHub está disponível. **Não documente o estado de seus gatilhos por memória.** A fonte de verdade é o YAML atual em `.github/workflows/`.

Na revisão de 2026-08-09, `.github/workflows/ci.yml` estava configurado para `pull_request`, `push` em `main` e `workflow_dispatch`. Esse fato é temporal; confirme novamente no arquivo antes de qualquer decisão futura.

A indisponibilidade de Actions não transforma falha em sucesso: para uma mudança ficar tecnicamente validada em contingência, execute o equivalente local e preserve a evidência do SHA/checkpoint. Quando o GitHub retornar, sincronize a branch e deixe os controles remotos complementarem a prova local.

## Gate antes do push

O hook existente pode continuar sendo usado:

```bash
git config core.hooksPath .githooks
```

O mecanismo local-first não depende desse hook. Ele existe apenas como camada adicional.

## Princípio de contingência

Quando GitHub falhar:

```text
preservar localmente -> validar localmente -> continuar trabalho -> sincronizar depois
```

Nunca substituir por:

```text
force push -> reset destrutivo -> edição direta em produção -> bypass de teste
```

A contingência reduz dependência externa sem reduzir governança, LGPD, segurança ou rollback.
