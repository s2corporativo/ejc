# Deploy do EJC na VPS (Docker Compose)

Guia para publicar o EJC (com o novo design) numa VPS Linux com Docker.
Sobe 3 serviços: **db** (Postgres 16 + pgvector), **backend** (FastAPI) e
**frontend** (Nginx servindo o SPA e fazendo proxy de `/api` → backend).

## Pré-requisitos na VPS

- Docker Engine + plugin Compose (`docker compose version` deve funcionar).
- Portas: **80** livre (frontend). O backend e o banco ficam na rede interna do
  Compose — não precisam de porta exposta.
- ~2 GB RAM livres para build/execução.

## Passo a passo

```bash
# 1) Clonar o repositório e entrar nele
git clone https://github.com/s2corporativo/ejc.git
cd ejc
#    (use a branch/commit que contém estes arquivos de deploy)

# 2) Criar o .env a partir do modelo e EDITAR os valores
cp .env.example .env
nano .env
```

No `.env`, preencha obrigatoriamente:

| Variável | Como gerar / o que pôr |
|---|---|
| `POSTGRES_PASSWORD` | senha forte do banco |
| `SECRET_KEY` | `python3 -c "import secrets;print(secrets.token_urlsafe(64))"` |
| `PII_ENCRYPTION_KEY` | `python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `PII_HASH_KEY` | `python3 -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `CORS_ORIGINS` / `FRONTEND_URL` | o domínio/IP público da VPS (ex.: `http://SEU_IP`) |
| `ADMIN_EMAIL` | e-mail real do admin (**não use `.local` — é rejeitado no login**) |
| `ADMIN_PASSWORD` | senha inicial do admin (troca obrigatória no 1º acesso) |

> As chaves `PII_*` são **obrigatórias em produção** — o app não as gera
> sozinho quando `APP_ENV=production`. Sem elas, os campos de CPF/CNPJ
> cifrados quebram. Guarde-as: se `PII_ENCRYPTION_KEY` mudar, os dados já
> cifrados ficam ilegíveis.

```bash
# 3) Subir tudo (build + up). O backend aplica migrations e cria o admin no boot.
docker compose up -d --build

# 4) Acompanhar a inicialização
docker compose logs -f backend
#   Espere por:
#     [entrypoint] Aplicando migrations (alembic upgrade head)...
#     [entrypoint] Semeando usuário admin (idempotente)...
#     [entrypoint] Iniciando uvicorn...
#   Se ADMIN_PASSWORD ficou vazio, a senha temporária é impressa AQUI (uma vez).
```

Acesse `http://SEU_IP` (ou o domínio) e faça login com `ADMIN_EMAIL` /
`ADMIN_PASSWORD`. No primeiro acesso o sistema exige troca de senha.

## Seeds opcionais (rodar UMA vez, após o `up`)

O admin e o schema já entram no boot. Para popular os dados do redesign
(ajuda contextual, matriz área→módulos, tipos de documento):

```bash
docker compose exec backend python -m app.seeds.redesign_seed
```

> A tabela OAB/MG (`oab_honorarios_seed`) **não** popula sozinha por segurança
> (nunca inventar valores sem a fonte oficial identificada) — cadastre pela tela
> de administração quando tiver o PDF/fonte.

## HTTPS (recomendado)

O Compose serve HTTP na porta 80. Para HTTPS, coloque um reverse proxy à frente
(Caddy, Traefik ou Nginx no host com certbot) apontando para a porta 80 do
container `frontend`, e ajuste `CORS_ORIGINS`/`FRONTEND_URL` para `https://...`.

## IA — provedores externos (Anthropic, Maritaca, Groq)

O EJC não tem provider de IA local: a cadeia do gateway é
Anthropic → Maritaca → Groq, com fallback automático entre eles. O conteúdo
enviado a qualquer provider externo passa por sanitização/pseudonimização de
PII (CPF/CNPJ/processo/etc.) antes do envio (LGPD, art. 33/46).

Verificação: como admin, `POST /api/ai/gateway/health` (status de cada
provedor). Requer `ANTHROPIC_API_KEY` (e opcionalmente `MARITACA_API_KEY`,
`GROQ_API_KEY`) no `.env`.

## Atualizar para uma nova versão

```bash
git pull
docker compose up -d --build   # migrations reaplicam automaticamente (idempotente)
```

## Verificação rápida

```bash
curl -fsS http://localhost/api/health        # {"status":"ok","database":true}
docker compose ps                             # db/backend healthy, frontend up
```
