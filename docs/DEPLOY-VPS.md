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

## IA local com Ollama (opcional — profile `ia-local`)

O compose traz um serviço Ollama **opt-in** (o `up -d` padrão não o sobe).
Ligado, a análise de IA do dia a dia roda local com **custo zero por token**;
se o Ollama estiver fora do ar ou lento, a cadeia do gateway cai para
Anthropic/Groq **automaticamente** — ligar/desligar nunca quebra nada.

```bash
./scripts/subir-ia-local.sh        # sobe, baixa os modelos e confere
# ou, manualmente:
docker compose --profile ia-local up -d   # o one-shot ollama-init baixa os modelos
```

Requisitos de RAM (CPU, sem GPU): perfis prontos no `.env.example` —
VPS de 8 GB usa `llama3.2:3b` para tudo (~4 GB); servidor 16 GB+ usa os
modelos padrão (`deepseek-r1:8b`, `qwen2.5:14b`, `gemma3:9b`, até ~11 GB).
A lista de download vem de `OLLAMA_PULL_MODELS` no `.env` (fonte única —
mantenha em sincronia com os `OLLAMA_MODEL_*`). A porta 11434 **não** é
publicada no host: só o backend alcança o Ollama pela rede interna.

Verificação: `docker compose exec ollama ollama list` e, como admin,
`POST /api/ai/gateway/health` (status de cada provedor). Para subir o profile
de IA local use `./scripts/subir-ia-local.sh` (ele re-sobe sozinho nas
atualizações seguintes enquanto o container existir).

A extração de PII de documentos roda **só em modelo local (Ollama)** por LGPD —
se não houver Ollama, esse recurso específico falha fechado (o resto do sistema
funciona normalmente). Recursos de IA em nuvem (Groq) exigem `GROQ_API_KEY` no `.env`.

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
