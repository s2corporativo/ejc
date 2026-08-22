# Validar um PR sem depender do GitHub Actions

**Por que este runbook existe.** Em 2026-08-22 o limite de gasto da conta foi
atingido e **nenhum workflow do repositório passou a executar** — `ci.yml`,
`ejc-release-gate.yml` e `governanca.yml` pararam juntos, em todos os PRs
abertos, deixando apenas execuções sintéticas `startup_failure`. Sem CI não há
gate; sem gate, pela governança, nada é promovível. Este documento fecha essa
dependência: o gate roda inteiro na máquina, com o mesmo rigor.

`docs/CI_SEM_GITHUB.md` descreve o desenho do `scripts/ci-local.sh`. **Este
aqui é o procedimento operacional**, com os pré-requisitos que só aparecem
quando se executa de verdade.

---

## O comando

```bash
bash scripts/ci-local.sh required
```

`required` = `backend` + `eval` + `frontend` + `p0` — exatamente os gates que
o PR precisa. `full` acrescenta arquitetura, continuidade e UI extra.

Evidências ficam em `~/.cache/ejc-ci-local/reports/<timestamp>/`
(`backend-tests.log`, `backend-coverage.xml`, `ruff.log`, `pip-audit.log`).
Anexe o caminho e o resumo no PR: é a prova que substitui o print do CI.

---

## Pré-requisitos (os quatro que travam na primeira vez)

### 1. NÃO rode como root

O script recusa: *"CI local promovível não roda como root"*. Não é capricho —
o `initdb` do PostgreSQL também recusa, e um gate rodado como root não tem a
mesma superfície de permissões que o CI.

`EJC_ALLOW_ROOT_DIAGNOSTIC=1` existe só para diagnóstico e **o resultado não é
promovível**. Se o seu ambiente só tem root (contêiner, VM enxuta):

```bash
useradd -m -s /bin/bash ejcci
usermod -aG postgres ejcci          # acesso a /var/run/postgresql
chmod 775 /var/run/postgresql
chown -R ejcci:ejcci /caminho/do/repo
su ejcci -c 'bash scripts/ci-local.sh required'
```

### 2. PostgreSQL 16 **com pgvector**

O script sobe um cluster efêmero próprio (Docker quando há daemon; `initdb`
local caso contrário) e **nunca** aponta para produção. A migration `001` cria
`CREATE EXTENSION vector` — sem a extensão, `alembic upgrade head` falha na
primeira migration.

```bash
apt-get install -y postgresql-16 postgresql-16-pgvector
```

Sem daemon Docker, o modo local é usado automaticamente; só garanta que o
usuário do gate consegue escrever em `/var/run/postgresql` (item 1).

### 3. Node **22**, não 20

`frontend/package.json` exige `>=22.22.0` e o CI fixa `22.22.2`. O script
reprova major diferente:

```
ERRO: Node v20.20.2 detectado; esperado major 22.
```

Rodar o frontend em Node 20 **passa** nos testes e mente sobre o gate. Use a
versão certa (`nvm use 22`, ou instale o tarball oficial).

### 4. Certificados, quando há proxy de saída

Ambientes atrás de proxy TLS precisam do bundle acessível **ao usuário do
gate** — não só ao root. Aponte todas as variáveis, inclusive
`HTTPLIB2_CA_CERTS`, que quebra a coleta de cinco arquivos de teste se ficar
apontando para um caminho ilegível:

```bash
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.crt
export SSL_CERT_FILE=$REQUESTS_CA_BUNDLE
export PIP_CERT=$REQUESTS_CA_BUNDLE
export NODE_EXTRA_CA_CERTS=$REQUESTS_CA_BUNDLE
export HTTPLIB2_CA_CERTS=$REQUESTS_CA_BUNDLE
```

---

## O que o gate cobre — e o que ele não cobre

**Cobre**, com paridade ao `ci.yml`:

| Etapa | O que roda |
|---|---|
| Backend | `alembic upgrade head` em banco vazio, `pytest tests` com `RUN_DB_TESTS=1`, cobertura mínima de 65% |
| Qualidade | `ruff check app`, `pip-audit` em tool-venv isolado |
| Eval | `run_eval --smoke` e `agent_trajectory --max-violacoes-hitl 0` (os gates bloqueantes de `ci.yml:183`) |
| Frontend | `npm ci`, `tsc --noEmit`, `vitest run`, `vite build` |
| P0 | `ci_guard.sh`, wrapper de backup cifrado, rollback de deploy, recuperação de runner |

**Não cobre**, e nenhum desses é opcional antes de integrar:

- **`governanca.yml`** — a trava que reprova PR sem `#<numero>` no corpo. É
  verificação sobre o PR, não sobre o código; confira à mão que o corpo traz
  `Closes #NNN`.
- **Revisão automática** (CodeRabbit) e revisão humana.
- **Merge e deploy**, que seguem exigindo a esteira do GitHub.

Rodar o gate local **não autoriza integrar** — substitui a evidência técnica,
não a decisão. As regras 8 e 9 da governança continuam valendo.

---

## Alternativa estrutural: runner self-hosted

O gate local resolve o hoje, mas exige alguém rodando o comando. A saída
permanente já está montada pela metade: **`deploy-vps.yml` roda em
`runs-on: [self-hosted, ejc-vps]`** — o runner existe e está registrado.

Os workflows de PR é que continuam em `ubuntu-latest`:

| Workflow | `runs-on` hoje |
|---|---|
| `ci.yml` | `ubuntu-latest` (3 jobs) |
| `ejc-release-gate.yml` | `ubuntu-latest` (3 jobs) |
| `governanca.yml` | `ubuntu-latest` |

Minutos de runner **self-hosted não são cobrados**; os de runner hospedado
pelo GitHub são. Migrar os jobs de PR para o `ejc-vps` restauraria o CI
automático sem custo de minuto.

**Antes de fazer isso, três coisas precisam de decisão do titular** — por isso
não está implementado:

1. **Carga na VPS de produção.** O job de backend sobe Postgres com pgvector e
   roda ~6.150 testes. Hoje isso acontece em máquina descartável do GitHub;
   no `ejc-vps` passaria a disputar CPU, memória e disco com a aplicação que
   atende o escritório. Convém isolar (contêiner dedicado, limite de recursos)
   ou usar outra máquina.
2. **Superfície de segurança.** Runner self-hosted executando workflow de
   `pull_request` roda código da branch. Em repositório privado sem forks o
   risco é contido, mas a decisão é explícita.
3. **É mudança de CI/CD** — `docs/GOVERNANCA_IA.md` §10 exige autorização
   nominal do titular.

Não verifiquei se o bloqueio por limite de gasto poupa o runner self-hosted:
a documentação do GitHub trata minutos self-hosted como gratuitos e não
medidos, mas isso precisa de um teste real antes de ser tratado como certeza.

---

## Ordem recomendada enquanto o CI estiver parado

1. Escreva o código e rode `bash scripts/ci-local.sh required`.
2. Corrija até o script terminar com `CI local concluído com sucesso.`
3. Só então faça `commit` e `push`.
4. No corpo do PR, registre o caminho do relatório e o resumo (contagem de
   testes, cobertura, versão de Node, que o banco foi efêmero).
5. Marque as caixas de "Evidências de CI" como **pendentes**, não como
   aprovadas: o gate local é evidência técnica equivalente, mas não é o CI do
   HEAD exato que a governança cobra.
