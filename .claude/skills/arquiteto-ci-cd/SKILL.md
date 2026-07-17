---
name: arquiteto-ci-cd
description: >
  Playbook de referência para MONTAR/evoluir pipelines de CI/CD do EJC no GitHub Actions (build/test/deploy, secrets, ambientes dev/staging/produção, deploy na VPS). Para DIAGNOSTICAR falha de CI o ponto de entrada canônico é o agente `ci-triage`; use este playbook ao construir ou alterar o pipeline. Não é roteador concorrente.
---

> Playbook de referência (montagem de pipeline). Diagnóstico de falha de CI: agente `ci-triage`. Consultado durante a tarefa — não roteia.

# Arquiteto CI/CD — EJC e Sistema-S2

## Contexto

```
FERRAMENTA: GitHub Actions (gratuito para repositórios públicos/privados — 2.000 min/mês free)
DESTINO DEPLOY: VPS Ubuntu (acessado via SSH)
SISTEMAS: EJC (FastAPI + React) | Sistema-S2 (TypeScript)
BRANCHES: main (produção) | develop (staging) | feature/* (apenas testes)
```

---

## 1. Pipeline EJC — Completo

```yaml
# .github/workflows/ejc.yml
name: EJC — CI/CD Pipeline

on:
  push:
    branches: [main, develop]
    paths:
      - "backend/**"
      - "frontend/**"
      - "docker-compose*.yml"
  pull_request:
    branches: [main, develop]

env:
  REGISTRY: ghcr.io
  IMAGE_BACKEND: ${{ github.repository }}/ejc-backend
  IMAGE_FRONTEND: ${{ github.repository }}/ejc-frontend

jobs:
  # ─────────────────────────────────────────
  test-backend:
    name: 🧪 Testes Backend (pytest)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: ejc_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt --break-system-packages
          pip install pytest pytest-asyncio pytest-cov httpx --break-system-packages
      - name: Run tests
        env:
          TEST_DATABASE_URL: postgresql://test_user:test_pass@localhost:5432/ejc_test
          SECRET_KEY: test-secret-key-ci
        run: |
          cd backend
          pytest tests/ --cov=app --cov-report=xml --cov-fail-under=70 -v
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with: {file: backend/coverage.xml, flags: backend}

  # ─────────────────────────────────────────
  test-frontend:
    name: 🧪 Testes Frontend (vitest)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {node-version: "18", cache: "npm", cache-dependency-path: frontend/package-lock.json}
      - name: Install and test
        run: |
          cd frontend
          npm ci
          npm run test -- --coverage --reporter=verbose
      - name: TypeScript check
        run: |
          cd frontend
          npm run build  # falha se houver erros TS

  # ─────────────────────────────────────────
  security-scan:
    name: 🔒 Varredura de Segurança
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Python security scan (bandit)
        run: |
          pip install bandit safety --break-system-packages
          cd backend
          bandit -r app/ -ll  # reporta apenas medium e high
          safety check -r requirements.txt
      - name: JS security scan (npm audit)
        run: |
          cd frontend
          npm audit --audit-level=high

  # ─────────────────────────────────────────
  build-and-push:
    name: 🏗️ Build e Push Docker
    runs-on: ubuntu-latest
    needs: [test-backend, test-frontend]
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_BACKEND }}:${{ github.sha }}
      - uses: docker/build-push-action@v5
        with:
          context: ./frontend
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_FRONTEND }}:${{ github.sha }}

  # ─────────────────────────────────────────
  deploy-production:
    name: 🚀 Deploy Produção
    runs-on: ubuntu-latest
    needs: build-and-push
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - uses: actions/checkout@v4
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/ejc

            # Backup do banco antes de deploy
            docker-compose exec -T db pg_dump -U $POSTGRES_USER $POSTGRES_DB > \
              /backups/ejc_$(date +%Y%m%d_%H%M%S).sql

            # Atualizar imagens
            export IMAGE_TAG=${{ github.sha }}
            docker-compose pull

            # Executar migrations
            docker-compose run --rm backend alembic upgrade head

            # Reiniciar serviços
            docker-compose up -d --no-deps backend frontend

            # Healthcheck
            sleep 10
            curl -f http://localhost:8000/health || exit 1
            echo "✅ Deploy EJC concluído: ${{ github.sha }}"

      - name: Notificar sucesso WhatsApp
        if: success()
        run: |
          curl -X POST "${{ secrets.ZAPI_URL }}/send-text" \
            -H "Client-Token: ${{ secrets.ZAPI_CLIENT_TOKEN }}" \
            -d '{"phone":"${{ secrets.WHATSAPP_CLOVIS }}","message":"✅ Deploy EJC concluído\nCommit: ${{ github.sha }}\nHora: '"$(date '+%d/%m/%Y %H:%M')"'"}'

      - name: Notificar falha WhatsApp
        if: failure()
        run: |
          curl -X POST "${{ secrets.ZAPI_URL }}/send-text" \
            -H "Client-Token: ${{ secrets.ZAPI_CLIENT_TOKEN }}" \
            -d '{"phone":"${{ secrets.WHATSAPP_CLOVIS }}","message":"🔴 FALHA no deploy EJC\nCommit: ${{ github.sha }}\nVerificar GitHub Actions"}'
```

---

## 2. Pipeline Sistema-S2 (TypeScript)

```yaml
# .github/workflows/sistema-s2.yml
name: Sistema-S2 — CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    name: 🧪 Test TypeScript
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env: {POSTGRES_USER: s2user, POSTGRES_PASSWORD: s2pass, POSTGRES_DB: s2_test}
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 5s --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {node-version: "18", cache: "npm"}
      - run: npm ci
      - run: npm run typecheck  # tsc --noEmit
      - run: npm run lint       # eslint
      - run: npm test           # vitest ou jest
        env:
          DATABASE_URL: postgresql://s2user:s2pass@localhost:5432/s2_test

  deploy:
    name: 🚀 Deploy Sistema-S2
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/sistema-s2
            git pull origin main
            npm ci --production
            npx ts-node db/migrations/run_migrations.ts
            pm2 restart sistema-s2
            pm2 status
```

---

## 3. Secrets Necessários no GitHub

```
VPS_HOST          — IP ou domínio da VPS
VPS_USER          — usuário SSH (ex: ubuntu, deploy)
VPS_SSH_KEY       — chave privada SSH (sem senha)
ZAPI_URL          — URL da instância Z-API
ZAPI_CLIENT_TOKEN — token Z-API
WHATSAPP_CLOVIS   — número WhatsApp Dr. Clovis
POSTGRES_USER     — usuário banco de produção
POSTGRES_PASSWORD — senha banco de produção
```

### Gerar chave SSH para CI/CD
```bash
# Na sua máquina local
ssh-keygen -t ed25519 -C "github-actions-ejc" -f ~/.ssh/ejc_ci_deploy -N ""

# Adicionar chave pública na VPS
ssh-copy-id -i ~/.ssh/ejc_ci_deploy.pub usuario@VPS_IP
# OU adicionar manualmente em ~/.ssh/authorized_keys na VPS

# Adicionar chave PRIVADA como secret no GitHub:
# Settings → Secrets → Actions → New secret → VPS_SSH_KEY
cat ~/.ssh/ejc_ci_deploy  # copiar conteúdo completo
```

---

## 4. Status Badge para README

```markdown
![EJC CI/CD](https://github.com/SEU_USUARIO/ejc/actions/workflows/ejc.yml/badge.svg)
```

---

## 5. Regras do Pipeline

- Pull Request: apenas testes — nunca deploy automático
- Branch develop: deploy em staging automaticamente
- Branch main: deploy em produção com aprovação manual (GitHub Environment)
- Falha em teste: bloquear merge — nunca fazer merge com teste falhando
- Deploy falhou: notificar WhatsApp imediatamente + rollback automático
- Backup de banco: sempre antes do deploy em produção
- Healthcheck: verificar endpoint /health após deploy — reverter se falhar
