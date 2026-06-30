# EJC — Ecossistema Jurídico Clovis (v3.x)

Sistema de gestão jurídica do escritório **De Paula Teixeira Sociedade de Advogados** (Betim/MG).
Stack: **FastAPI + React/TypeScript + PostgreSQL/pgvector + Docker + Nginx**. IA local-first via **Groq**.

---

## 🚀 Deploy rápido na VPS Contabo (Ubuntu)

```bash
# 1. Pré-requisitos no servidor
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER   # relogar após este comando

# 2. Clonar/enviar o projeto e configurar ambiente
cd /opt && git clone <SEU_REPO> ejc && cd ejc   # ou enviar o ZIP e descompactar
cp .env.example .env
nano .env    # PREENCHER: SECRET_KEY, senha do Postgres, GROQ_API_KEY, domínio, SMTP

# 3. Subir os containers
docker compose up -d --build

# 4. Aplicar migrations + seed inicial (primeira vez)
docker compose exec backend alembic upgrade head
docker compose exec backend python seeds/seed_all.py

# 5. Acessar
# https://ejc.depaulateixeira.adv.br  → login: gerenciar credenciais pelo painel de usuarios
#                        (o sistema FORÇA a troca no 1º login)
```

### Nginx + SSL (Let's Encrypt)
```bash
# O nginx/ejc.conf já vem pronto. Ajuste o server_name e rode:
sudo certbot --nginx -d ejc.depaulateixeira.adv.br
```

---

## ⚙️ Variáveis de ambiente essenciais (`.env`)

| Variável | Descrição |
|----------|-----------|
| `SECRET_KEY` | Chave JWT — gere com `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | Senha do banco |
| `GROQ_API_KEY` | Chave da IA (groq.com) — sem ela, recursos de IA ficam off |
| `FRONTEND_URL` | URL pública (ex.: `https://ejc.depaulateixeira.adv.br`) — usada nos e-mails |
| `ZAPI_*` | WhatsApp (Z-API): instância, token, Client-Token |

### E-mail (Gmail) — para reset de senha e alertas
```env
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu-email@gmail.com
SMTP_PASSWORD=     # SENHA DE APP (não a senha normal!)
```
> Gmail: ative a verificação em 2 etapas → "Senhas de app" → gere uma senha de 16 dígitos
> em https://myaccount.google.com/apppasswords e cole em `SMTP_PASSWORD`.

### Web Push (alertas no celular) — opcional
```bash
docker compose exec backend python scripts/gen_vapid.py
# cole VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY no .env e defina PUSH_ENABLED=true
```

### Busca semântica (RAG) — opcional
```bash
docker compose exec backend pip install -r requirements-ml.txt
# defina EMBEDDINGS_ENABLED=true no .env, reinicie e rode:
docker compose exec backend python seeds/gerar_embeddings.py
```

### Captura automática de intimações (DJEN)
Cada advogado configura sua **OAB** no menu do avatar → "Minha OAB". O sistema
consulta o DJEN/CNJ diariamente às 06h30 e cria notificações automáticas.

---

## 📦 Módulos

**Operação:** Clientes/CRM · Casos · Prazos (cálculo automático) · Documentos · Peças ·
Honorários · Tarefas (kanban) · Timesheet · Ambiental · Auditoria · Usuários · Lixeira

**Inteligência (Groq):** Análise de caso · Detector de teses ocultas · Auditor de peças ·
Preparação de audiência · Base RAG · Pós-Mortem (aprendizado por caso encerrado)

**Portal do Cliente:** acesso externo isolado — processos, financeiro, assinatura eletrônica

**Integrações:** DataJud/CNJ (movimentos) · DJEN (intimações) · Banco Central (correção
monetária) · ViaCEP/BrasilAPI (cadastro) · Z-API (WhatsApp → leads) · Google Calendar (ICS)

**Segurança:** JWT + refresh rotativo · 2FA TOTP · troca de senha obrigatória ·
anti-brute-force · alerta de novo dispositivo · reset por e-mail · soft-delete + auditoria ·
sanitização LGPD antes de qualquer chamada à IA · HITL obrigatório em peças de IA

---

## 🔧 Jobs automáticos (scheduler — `ENABLE_SCHEDULER=true`)
- Alertas de prazo (7/3/1 dias) · 06h00
- Captura DJEN por OAB · 06h30
- Sincronização DataJud dos casos ativos · 08h45 e 16h45
- Relatório gerencial mensal (PDF) · dia 1, 07h30

> ⚠️ Rode com **`--workers 1`** (já configurado no Docker) — o scheduler não pode
> duplicar entre workers.

---

## 🧪 Testes
58 cenários E2E cobrindo auth, portal, IA, integrações e segurança.
```bash
docker compose exec backend pytest          # se incluir testes pytest
```

## 💾 Backup
```bash
# Configurado em scripts/backup.sh (retenção 14 dias + offsite opcional via rclone)
0 2 * * * cd /opt/ejc && bash scripts/backup.sh
```

---

## 🆕 Atualização jun/2026 — Blocos A–E

**A. Infraestrutura de ingestão RAG** (`app/services/ingestion_service.py`)
UPSERT idempotente por `chave_origem` + SHA-1 (re-embeda só se mudou), chunking
com overlap, controle por fonte (`fontes_ingestao`). Migration `006`.

**B. Ingestores automáticos** (`app/services/ingestors/`) — jobs diários/semanais:
- `planalto` — 10 códigos-núcleo (CF, CC, CPC, CLT, CDC, CP, CPP, ECA, L14.133, CTN)
- `stj` — jurisprudência (CKAN espelhos-de-acórdãos)
- `camara` / `senado` — monitor legislativo (ementas de proposições)

**C. Calculadoras** (`app/services/calc/` · rotas `/calculadoras`)
INSS e IRRF 2026 (tabelas oficiais conferidas) · verbas rescisórias (CLT) ·
correção monetária (BCB ao vivo) · prescrição/decadência (14 prazos curados) ·
custas TJMG (UFEMG + isenção verificadas). Toda saída é **minuta (HITL)**.

**D. Indicadores de gestão** (`app/services/` · rotas `/analytics`)
Case Health Score · Jurimetria (com tamanho de amostra) · Taskscore ·
Funil de leads · Rentabilidade (migration `007`: `users.custo_hora`) · Onboarding.
Cada indicador respeita o controle de acesso por advogado.

**E. IA aplicada**
Análise de contratos (`/ai/analisar-contrato`, Groq+RAG+sanitização LGPD) ·
Monitor legislativo (`/rag/monitor-legislativo`, radar Câmara+Senado).

> Princípio transversal: **nada é inventado**. Tabelas tributárias/custas são de
> fonte oficial conferida; lacunas (ex.: redutor parcial IRPF, faixas de custas
> TJMG) são sinalizadas para conferência, nunca preenchidas por suposição.

---

*HITL é inegociável: toda peça gerada por IA exige revisão humana antes de uso (Provimento OAB 205/2021).*
*Sem dependência de licitações. Dados de clientes nunca deixam a infraestrutura sem sanitização LGPD.*
