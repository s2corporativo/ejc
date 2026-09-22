# Runbook — W8.2: timeout de IA no nginx do host

## Objetivo

Evitar 504 em chamadas de IA que legitimamente duram mais de 120 s, sem ampliar
o timeout das demais APIs. O frontend usa o contrato público canônico
`/api/v1`, enquanto `/api` permanece como superfície legada. Como o middleware
de versão só reescreve o caminho depois do nginx, o host precisa cobrir ambos:

- `/api/v1/ai/*` → 300 s
- `/api/ai/*` → 300 s
- `/api/*` restante → 120 s

A mudança é somente de proxy do host. Não exige rebuild de containers, migration
ou alteração do backend/frontend.

## Pré-condições obrigatórias

1. A PR #1781 precisa estar mesclada na `main`.
2. O SHA a aplicar precisa ser exatamente o `origin/main` atual.
3. Esse SHA precisa possuir Woodpecker `push/main` verde.
4. O site ativo deve resolver para `/etc/nginx/sites-available/ejc.conf`.
5. O backup do arquivo ativo deve ser criado antes de qualquer substituição.

Não usar `git pull` como mecanismo para obter o arquivo do hotfix. Extraia
somente `nginx/ejc.conf` do SHA aprovado com `git show`.

## Aplicação segura

```bash
set -euo pipefail

APP_DIR=/opt/ejc
SHA="<SHA_MAIN_APROVADO>"
LIVE=/etc/nginx/sites-available/ejc.conf
CANDIDATE="/tmp/ejc.conf.$SHA"
BACKUP="${LIVE}.bak.$(date +%Y%m%d-%H%M%S)"

cd "$APP_DIR"
git fetch --prune origin main

test "$(git rev-parse origin/main)" = "$SHA"
/opt/s2-automation/host/woodpecker-approved-sha.sh s2corporativo/ejc "$SHA"

git show "$SHA:nginx/ejc.conf" > "$CANDIDATE"

ACTIVE="$(readlink -f /etc/nginx/sites-enabled/ejc.conf)"
test "$ACTIVE" = "$LIVE"

sudo cp -a "$LIVE" "$BACKUP"
sudo install -o root -g root -m 0644 "$CANDIDATE" "$LIVE"

if ! sudo nginx -t; then
  sudo cp -a "$BACKUP" "$LIVE"
  sudo nginx -t
  exit 1
fi

sudo systemctl reload nginx
sudo systemctl is-active --quiet nginx
curl -fsS --max-time 15 https://ejc.depaulateixeira.adv.br/api/health >/dev/null
```

## Verificação estrutural pós-reload

```bash
sudo nginx -T 2>/dev/null | grep -A22 -E 'location \^~ /api/(v1/)?ai/'
```

A saída deve mostrar as duas locations e `proxy_read_timeout 300s`.
O bloco genérico `location /api/` deve continuar em 120 s.

## Homologação funcional obrigatória

O teste precisa provar o problema que existia. Uma resposta inferior a 120 s
não valida o hotfix.

Critério de aceite:

1. executar uma chamada autenticada pela superfície canônica
   `POST /api/v1/ai/analisar-caso`;
2. a chamada real deve durar **mais de 120 s e menos de 300 s**;
3. resposta final HTTP 2xx, sem 504;
4. repetir pela tela `TabResumo` e confirmar que a resposta é renderizada;
5. conferir que existe um único AILog concluído para a execução, sem duplicação
   causada por retry do cliente.

Somente após esses cinco pontos o item W8.2 pode mudar de `PREPARADO` para
`EXECUTADO`.

## Rollback

Se `nginx -t`, reload, health ou homologação falharem:

```bash
sudo cp -a "$BACKUP" "$LIVE"
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl is-active --quiet nginx
curl -fsS --max-time 15 https://ejc.depaulateixeira.adv.br/api/health >/dev/null
```

O rollback restaura apenas a configuração do host; não altera containers,
banco, código da aplicação ou dados.
