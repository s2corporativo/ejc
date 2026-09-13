# Baseline do SAST (semgrep) — passo `security-sast`

Gate: `.woodpecker.yml` → `semgrep scan --config=auto --error .`
(imagem `semgrep/semgrep:1.172.0`). O `--error` faz qualquer achado reprovar
o passo, em qualquer severidade.

**Ponto de partida:** 219 achados bloqueantes (109 ERROR, 110 WARNING) na
`main` — situação herdada, não introduzida por PR recente. O passo nunca
passou desde que foi criado em #1533.

**Depois desta triagem:** 0 achados, exit 0. O gate continua vivo: violação
nova em código de produção reprova (prova ao fim deste documento).

---

## Como as decisões foram tomadas

Ordem de preferência, sem atalho:

1. **Vulnerabilidade real → corrigir o código.**
2. **Regra inaplicável àquele ponto, com justificativa técnica → supressão
   mais estreita possível**, sempre com o motivo escrito ao lado.
3. Nunca: desligar `--error`, trocar `--config=auto`, excluir `backend/app/`,
   silenciar regra no repositório inteiro, ou `# nosemgrep` sem comentário.

Duas ferramentas de supressão, com papéis distintos:

| Mecanismo | Alcance | Onde é aceitável |
|---|---|---|
| `.semgrepignore` | **todas** as regras naquele caminho | só diretório que não é código de produção |
| `# nosemgrep: <regra>` na linha | **uma** regra, **uma** linha | código de produção, com o porquê ao lado |

Consequência desejada da segunda: `text()` novo, `sha1` novo ou `shell=True`
novo **reprovam o gate** até alguém olhar e decidir conscientemente.

---

## Decisão por categoria

| Categoria (regra) | Achados | Decisão | Justificativa |
|---|---:|---|---|
| `avoid-sqlalchemy-text` | 65 | suprimido por linha | A regra marca **todo** `text()`, sem examinar interpolação. Auditados os 65: SQL literal com bind params. Onde há f-string, o interpolado é **identificador** (nome de tabela/coluna) vindo de `information_schema` ou de constante do módulo — nunca valor de request. |
| `sqlalchemy-execute-raw-query` | 36 | 33 excluídos por caminho · 3 **corrigidos** | 33 em `backend/alembic/versions/` (DDL offline). 3 em `m22_retrieval_acl_tests.py` eram interpolação real → parametrizados. |
| `formatted-sql-query` | 33 | excluídos por caminho | Todos em `backend/alembic/versions/`. Migration não tem entrada de request; a "entrada" é o schema anterior. |
| `github-actions-mutable-action-tag` | 55 | excluídos por caminho | `docs/arquivo/ci/github-actions-legacy/` — workflows APOSENTADOS em #1533. Não existe `.github/workflows/` no repositório; nenhum runner lê esses YAML. |
| `insecure-hash-algorithm-sha1` | 7 | suprimidos por linha | Todos são chave de deduplicação/identidade (`_hash_mov`, `_ref_datajud`, slug de URL, hash de conteúdo). Nenhum é assinatura, token ou senha. |
| `insecure-file-permissions` | 5 | suprimidos por linha | A regra chama `0o700` de "amplamente permissivo" e recomenda `0o644`. Está invertido: `0o700` é dono-apenas. **Seguir a regra afrouxaria** diretório de backup e de evidência de CI — e quebraria testes que exigem `0o700` (`test_reclassificacao_guardas_auditoria.py`, `test_ci_fallback_activation_journal.py`). |
| `psycopg-sqli` | 3 | **corrigidos** | Interpolação real de `_d3_id` em SQL. |
| `subprocess-shell-true` | 3 | 2 **corrigidos** · 1 suprimido | 2 viraram `argv` (não precisavam de shell). 1 usa `&&`/`>`/`&`, que só existem no shell, e é montado só com constantes do módulo. |
| `run-shell-injection` | 2 | excluídos por caminho | `docs/arquivo/` — workflow aposentado. |
| `dynamic-urllib-use-detected` | 2 | suprimidos por linha | `coleta_fontes.py` valida o host contra allowlist oficial **antes** e reconfere `geturl()` **depois** do redirect. `probe_apis.py` é sonda de operador com URLs literais. |
| `detect-non-literal-regexp` | 2 | suprimidos por linha | Padrão vem do catálogo estático de módulos, já com metacaracteres escapados. Sem entrada de usuário. |
| `tarfile-extractall-traversal` | 1 | **corrigido** | Ver abaixo. |
| `possible-nginx-h2c-smuggling` | 1 | **corrigido** (+ supressão) | Ver abaixo. Correção aplicada; a supressão existe porque a regra não enxerga a correção. |
| `nan-injection` | 1 | **corrigido** | Ver abaixo. |
| `python-logger-credential-disclosure` | 1 | suprimido por linha | A regra casou a palavra "token" na string **literal** do log (`"[nfse] falha HTTP no /oauth/token: %s"`). O único valor interpolado é `type(e).__name__`. |
| `curl-pipe-bash` | 1 | suprimido por linha | Instalador oficial do fornecedor, HTTPS, rodado à mão pelo operador ao provisionar host novo. Fixar checksum de instalador rolante quebraria a cada atualização do fornecedor. |
| `missing-user-entrypoint` | 1 | **dívida aceita e rastreada** | Ver abaixo — é o único achado real que ficou em aberto. |

---

## Defeitos reais corrigidos

**`nginx/ejc.conf` — H2C smuggling (o mais grave).**
O `map` era `default upgrade`, ou seja, **qualquer** protocolo de Upgrade era
repassado ao uvicorn — inclusive `h2c`. Um cliente podia negociar HTTP/2 em
texto claro direto com o backend e daí em diante falar com ele por fora do
Nginx: sem o roteamento por `location`, sem a normalização de
`X-Forwarded-For`, sem os limites do proxy. Virou allowlist: só `websocket`
sobe; qualquer outro valor recebe `Connection: close` e header `Upgrade`
vazio. SSE não usa Upgrade e não é afetado.

**`scripts/backup/validar_restauracao_cifrada.py` — extração de tar.**
A validação dos membros rodava numa abertura do `.tar.gz` e o `extractall()`
extraía **tudo** numa segunda abertura — duas leituras do mesmo arquivo em
disco, que outro processo pode trocar no intervalo. Agora valida e extrai na
mesma abertura, só sobre a lista de membros aprovados, com `filter="data"`
como segunda barreira.

**`scripts/inventory/m22_retrieval_acl_tests.py` — SQL injection.**
`_d3_id` era interpolado por f-string no SQL. Virou parâmetro (`%s`).

**`backend/app/routers/evolution_webhook.py` — typecast em caminho de auth.**
`bool(valor_de_header)` no `_autorizado()`. Semântica preservada
(saída antecipada explícita + `hmac.compare_digest`), sem typecast sobre
entrada não confiável. Coberto por `tests/test_evolution_webhook_secret.py`
(6 casos, incluindo header vazio e secret não configurado).

**`scripts/inventory/regressao_completa.py` — `shell=True` desnecessário.**
Duas invocações eram `argv` puro sem nenhum recurso de shell. Viraram lista
(também conserta caminho com espaço).

---

## Dívida aceita — 1 item

**`backend/Dockerfile`: o container roda como root** (`missing-user-entrypoint`).
Não é falso positivo; é endurecimento que falta. Não foi feito aqui porque
`USER` sozinho **quebra produção**: `/app/uploads` e `/app/backups` são
volumes **nomeados** (`uploads_data`, `backups_data`) que já existem no VPS
pertencendo ao root, e o Docker só aplica dono/permissão da imagem quando o
volume nasce vazio. Usuário não-root perderia a escrita — upload de documento
e o backup agendado das 02h00 parariam no primeiro deploy.

Fechar exige PR próprio, com build de container exercitado:
1. `useradd` + `chown -R` de `/app/uploads` e `/app/backups` na imagem;
2. `chown` único dos volumes existentes no VPS, no runbook de deploy;
3. conferir que `pg_dump`/`rclone` do job de backup ainda escrevem.

---

## Prova de que o gate continua reprovando

Não basta o scan sair verde — ele precisa continuar vermelho para código
ruim. Verificado inserindo temporariamente em `backend/app/routers/`:

```python
async def _sonda(db, request):
    nome = request.query_params.get("nome")
    return await db.execute(text(f"SELECT * FROM cases WHERE title = '{nome}'"))
```

`semgrep scan --config=auto --error .` reprovou (exit 1), apontando
`formatted-sql-query` e `sqlalchemy-execute-raw-query` na linha. O trecho foi
removido em seguida e **não** está em nenhum commit.

---

## Quando reavaliar

- **`.semgrepignore`, bloco 1 (padrões da ferramenta):** não mexer sem medir.
  Um `.semgrepignore` no raiz **substitui** a lista embutida do semgrep. Foi
  medido: sem `test/`+`tests/`, `backend/tests/` entra no scan e aparecem 24
  achados que o gate nunca reprovou.
- **`docs/arquivo/`:** se voltar a existir `.github/workflows/`, a exclusão
  **não** acompanha — workflow vivo tem de passar no gate.
- **`backend/alembic/versions/`:** se uma migration passar a ler entrada
  externa (env var, arquivo, argumento) e interpolá-la em SQL, o achado vira
  verdadeiro. A exclusão é por caminho, e não por linha, porque CLAUDE.md §5
  proíbe editar migration já aplicada em produção — e as 14 atingidas já
  rodaram lá.
- **Cada `# nosemgrep`:** vale para aquela linha e aquela regra. Mudou o
  código da linha, a justificativa ao lado tem de ser reconferida — não
  arrastada.
- **Versão do semgrep:** o CI fixa `1.172.0`; esta triagem rodou em `1.176.1`.
  `--config=auto` busca as regras do registry a cada execução, então regra
  nova pode acrescentar achado sem que ninguém tenha mexido no código. Achado
  novo no gate não é necessariamente regressão do PR — confira a categoria
  contra esta tabela antes de culpar o diff.
