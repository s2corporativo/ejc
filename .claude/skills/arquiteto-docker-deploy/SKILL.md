---
name: arquiteto-docker-deploy
description: >
  Diagnose and fix Docker, Docker Compose, VPS deployment, Nginx, environment variables, CORS, and production build issues for web applications including EJC. Use whenever the user needs to: fix Docker Compose that fails to start; diagnose why the system is not accessible externally after VPS deploy; fix backend listening only on localhost instead of 0.0.0.0; configure Nginx as reverse proxy; fix CORS blocking frontend API calls; set up persistent Docker volumes; configure environment variables; fix production builds not being served; open firewall ports; set up SSL/HTTPS with Certbot; or create a complete deploy guide. Stack: FastAPI Python, React, PostgreSQL, Docker, Nginx, Ubuntu VPS. Always diagnose before fixing. Give exact commands. Trigger on: Docker nao sobe, sistema nao abre externamente, CORS bloqueando, porta nao acessivel, VPS deploy, Nginx configurar, backend localhost, variavel ambiente, volume Docker, producao nao funciona, SSL HTTPS, firewall VPS, build nao servido.
---

# Arquiteto Docker e Deploy — EJC e Sistemas Web

## Premissas Absolutas

- Nunca assumir o problema sem diagnosticar — perguntar ou pedir logs primeiro
- Sempre dar comandos exatos para rodar — não apenas descrições
- Testar uma coisa por vez — não mudar tudo ao mesmo tempo
- Backup antes de alterações em produção
- Nunca expor senhas ou secrets em arquivos públicos (usar .env)
- Backend deve escutar em 0.0.0.0 — nunca apenas em 127.0.0.1

---

## 1. Diagnóstico Inicial

### Sequência de Diagnóstico

```bash
# 1. VERIFICAR STATUS DOS CONTAINERS
docker-compose ps
docker ps -a

# 2. VER LOGS DO CONTAINER COM PROBLEMA
docker-compose logs backend
docker-compose logs frontend
docker-compose logs db

# 3. VERIFICAR PORTAS ABERTAS NO HOST
netstat -tlnp | grep -E '8000|5432|80|443|3000|5173'
ss -tlnp

# 4. VERIFICAR FIREWALL (Ubuntu/Debian)
ufw status
iptables -L -n

# 5. TESTAR CONECTIVIDADE INTERNA
docker-compose exec backend curl http://localhost:8000/health
docker-compose exec backend ping db

# 6. VERIFICAR VARIÁVEIS DE AMBIENTE
docker-compose exec backend env | grep -E 'DATABASE|SECRET|CORS|HOST'
```

---

## 2. Problemas Mais Comuns

### Backend não acessível externamente

```
SINTOMA: backend sobe mas não responde em http://IP_DO_SERVIDOR:8000

CAUSA MAIS COMUM: backend escutando em 127.0.0.1 ao invés de 0.0.0.0

DIAGNÓSTICO:
docker-compose logs backend | grep "Uvicorn running"

SE MOSTRAR: "Uvicorn running on http://127.0.0.1:8000"
→ PROBLEMA CONFIRMADO

CORREÇÃO no Dockerfile ou docker-compose.yml:

# FastAPI / Uvicorn — corrigir comando de start
# ERRADO:
CMD ["uvicorn", "main:app", "--port", "8000"]

# CORRETO:
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# OU no docker-compose.yml:
command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### CORS bloqueando frontend

```
SINTOMA: frontend carrega mas chamadas de API falham com erro CORS no console

ERRO TÍPICO:
Access to fetch at 'http://API_URL/api/v1/...' from origin 'http://FRONTEND_URL'
has been blocked by CORS policy

DIAGNÓSTICO: verificar configuração CORS no backend FastAPI

CORREÇÃO (FastAPI):
# main.py ou cors.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://SEU_DOMINIO.com",
        "https://SEU_DOMINIO.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# VIA VARIÁVEL DE AMBIENTE (melhor prática):
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, ...)

# .env:
CORS_ORIGINS=http://localhost:3000,https://ejc.seudominio.com.br
```

### Banco de dados não conecta

```
SINTOMA: backend sobe mas retorna erro de conexão com banco

ERRO TÍPICO:
asyncpg.exceptions.CannotConnectNowError ou
sqlalchemy.exc.OperationalError: could not connect to server

DIAGNÓSTICO:
docker-compose logs db | tail -20
docker-compose exec backend nc -zv db 5432

CAUSAS E CORREÇÕES:

1. Banco ainda não subiu (race condition):
   CORREÇÃO no docker-compose.yml:
   backend:
     depends_on:
       db:
         condition: service_healthy

   db:
     healthcheck:
       test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
       interval: 5s
       timeout: 5s
       retries: 10

2. String de conexão incorreta:
   ERRADO: DATABASE_URL=postgresql://user:pass@localhost:5432/ejc
   CORRETO: DATABASE_URL=postgresql://user:pass@db:5432/ejc
   (usar o nome do serviço Docker como host — não 'localhost')

3. Credenciais incorretas:
   Verificar: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB no .env
   Comparar com DATABASE_URL
```

### Volume não persistente

```
SINTOMA: banco perde dados ao reiniciar container

DIAGNÓSTICO:
docker volume ls
docker inspect nome_do_container | grep Mounts

CORREÇÃO no docker-compose.yml:
services:
  db:
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
    driver: local

# NUNCA usar apenas ./data:/var/lib/postgresql/data sem declarar o volume nomeado
# Volumes nomeados sobrevivem ao docker-compose down
# Para apagar tudo incluindo dados: docker-compose down -v (CUIDADO)
```

### Frontend não acessível externamente

```
SINTOMA: frontend sobe mas não abre no navegador pelo IP/domínio

CAUSA 1: porta não publicada no docker-compose
CORREÇÃO:
  frontend:
    ports:
      - "80:80"      # se usando Nginx interno
      - "3000:3000"  # se usando servidor de dev
      - "5173:5173"  # se usando Vite dev

CAUSA 2: build de produção não configurado
O Vite dev server não serve em produção.
Em produção: buildar o React e servir com Nginx.

DOCKERFILE frontend para produção:
# Stage 1: Build
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve com Nginx
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

## 3. Nginx como Reverse Proxy

```nginx
# /etc/nginx/conf.d/ejc.conf (ou nginx.conf no container)

server {
    listen 80;
    server_name ejc.seudominio.com.br;  # ou IP do servidor

    # Frontend (React buildado)
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;  # SPA routing
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend docs (Swagger — opcional em produção)
    location /docs {
        proxy_pass http://backend:8000/docs;
        proxy_set_header Host $host;
    }
}
```

---

## 4. Docker Compose Completo — Referência EJC

```yaml
# docker-compose.yml — referência para EJC

version: '3.8'

services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"  # remover em produção se não precisar de acesso externo
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  backend:
    build: ./backend
    command: uvicorn main:app --host 0.0.0.0 --port 8000
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
      SECRET_KEY: ${SECRET_KEY}
      CORS_ORIGINS: ${CORS_ORIGINS}
    volumes:
      - uploads_data:/app/uploads
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  postgres_data:
  uploads_data:
```

---

## 5. .env.example — Referência

```env
# Banco de dados
POSTGRES_USER=ejc_user
POSTGRES_PASSWORD=TROCAR_POR_SENHA_FORTE
POSTGRES_DB=ejc_db

# Backend
SECRET_KEY=TROCAR_POR_CHAVE_ALEATORIA_LONGA_256bits
CORS_ORIGINS=http://localhost:3000,https://ejc.seudominio.com.br
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE_MB=50

# Frontend (variáveis para build)
VITE_API_URL=https://ejc.seudominio.com.br/api/v1
```

---

## 6. SSL/HTTPS com Certbot (VPS Ubuntu)

```bash
# Instalar Certbot
sudo apt update
sudo apt install certbot python3-certbot-nginx -y

# Obter certificado (domínio deve apontar para o IP)
sudo certbot --nginx -d ejc.seudominio.com.br

# Renovação automática (já configurada pelo certbot)
sudo systemctl status certbot.timer

# Verificar renovação
sudo certbot renew --dry-run
```

---

## 7. Firewall VPS (Ubuntu — UFW)

```bash
# Ver status
sudo ufw status

# Permitir portas necessárias
sudo ufw allow 22/tcp    # SSH — NUNCA fechar antes de configurar
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS

# Fechar porta do banco para acesso externo (produção)
sudo ufw deny 5432/tcp

# Ativar UFW
sudo ufw enable

# Ver regras detalhadas
sudo ufw status verbose
```

---

## 8. Comandos Úteis de Diagnóstico

```bash
# Reiniciar tudo
docker-compose down && docker-compose up -d

# Ver logs em tempo real
docker-compose logs -f backend

# Entrar no container
docker-compose exec backend bash
docker-compose exec db psql -U ejc_user -d ejc_db

# Verificar uso de recursos
docker stats

# Listar volumes
docker volume ls

# Remover tudo (CUIDADO — apaga dados)
docker-compose down -v

# Rebuild sem cache
docker-compose build --no-cache
docker-compose up -d

# Verificar healthcheck
docker inspect --format='{{json .State.Health}}' nome_do_container
```

---

## Acionamento

Frases que ativam este skill:
- "Docker não sobe", "container com erro"
- "sistema não abre externamente", "VPS deploy"
- "CORS bloqueando", "erro de CORS"
- "porta não acessível", "firewall VPS"
- "Nginx configurar", "reverse proxy"
- "backend em localhost", "0.0.0.0"
- "variável de ambiente", "arquivo .env"
- "volume Docker", "dados perdendo"
- "build não servido", "produção não funciona"
- "SSL HTTPS Certbot"
- Quando usuário cola erro de Docker e pede diagnóstico
- Quando sistema funciona localmente mas não em produção
