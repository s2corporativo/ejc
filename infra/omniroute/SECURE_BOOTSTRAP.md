# Bootstrap seguro do OmniRoute

O OmniRoute de manutenção fica isolado do runtime jurídico e exige autenticação própria. Nenhum segredo deve ser salvo no Git, em Issue, PR ou log de CI.

## 1. Preparar o `.env` local

Todos os comandos deste runbook partem da **raiz do checkout** do OmniRoute
(ex.: `/srv/ejc-omniroute`), que contém a pasta `infra/omniroute/`. Copie o
modelo e gere um `JWT_SECRET` aleatório sem imprimi-lo no terminal:

```bash
cp infra/omniroute/.env.example infra/omniroute/.env
python3 - <<'PY'
from pathlib import Path
import re
import secrets

path = Path('infra/omniroute/.env')
text = path.read_text()
gerado, n = re.subn(
    r'(?m)^OMNIROUTE_JWT_SECRET=.*$',
    'OMNIROUTE_JWT_SECRET=' + secrets.token_urlsafe(64),
    text,
)
if n != 1:
    raise SystemExit('OMNIROUTE_JWT_SECRET não encontrado no modelo')
path.write_text(gerado)
PY
chmod 600 infra/omniroute/.env
```

O `JWT_SECRET` protege a assinatura da sessão administrativa do dashboard. O
compose falha de forma segura se a variável estiver ausente, vazia ou com o
valor placeholder — e `verify-boundary.sh` (seção 2) recusa subir nesse estado.

## 2. Validar antes de subir

```bash
bash infra/omniroute/verify-boundary.sh
docker compose \
  -p ejc-omniroute \
  -f infra/omniroute/docker-compose.yml \
  --env-file .env \
  config >/dev/null
```

Não exiba o resultado expandido do compose em logs públicos, pois ele pode conter o segredo interpolado.

## 3. Subir/recriar somente o OmniRoute

```bash
docker compose \
  -p ejc-omniroute \
  -f infra/omniroute/docker-compose.yml \
  --env-file .env \
  up -d
```

A stack principal do EJC não deve ser reiniciada por este procedimento.

## 4. Criar a senha administrativa

Mantenha o serviço em loopback e abra um túnel SSH a partir de uma estação autorizada:

```bash
ssh -L 20128:127.0.0.1:20128 USUARIO@VPS
```

Abra `http://127.0.0.1:20128`, conclua o onboarding e defina uma senha administrativa forte. Não envie essa senha pelo chat nem a armazene no repositório.

## 5. Provider inicial

Após o onboarding, comece com **um** provider gratuito/no-auth documentado e validado. A recomendação inicial é OpenCode Free. Faça um smoke test com prompt sintético e sem dados de clientes antes de adicionar fallback.

Adicione no máximo um segundo provider inicialmente. O catálogo irrestrito de providers não faz parte da configuração recomendada do EJC.

## 6. Chave de inferência

Crie uma endpoint/API key própria do OmniRoute para os agentes. `REQUIRE_API_KEY=true` é o padrão desta integração. Armazene a chave apenas no ambiente local da ferramenta que a utilizar.

Nunca coloque a endpoint key em `.env` do EJC, banco de dados jurídico, PR ou arquivo versionado.

## 7. Smoke test

Valide, nesta ordem:

1. container `healthy`;
2. porta publicada somente em `127.0.0.1:20128`;
3. dashboard exige autenticação;
4. `/v1/*` rejeita chamada sem API key;
5. provider escolhido responde a uma pergunta sintética;
6. Codex/Claude/Antigravity conseguem usar o gateway somente pela configuração externa de engenharia.

Se qualquer teste indicar acoplamento com backend/frontend jurídico, interrompa a promoção e execute `bash infra/omniroute/verify-boundary.sh`.