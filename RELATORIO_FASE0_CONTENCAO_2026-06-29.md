# Relatório — FASE 0: Contenção Crítica de Segredos (EJC)

**Data:** 2026-06-29 · **Escopo:** apenas contenção de segredos e redução de risco imediato.
**Regra cumprida:** nenhum arquivo apagado · nenhuma funcionalidade nova · IA/RAG/banco/layout/módulos intocados · nenhum valor sensível exibido neste relatório.

---

## 1. Resumo

Os segredos hardcoded foram **removidos do código versionado** e substituídos por leitura de variáveis de ambiente. O acesso à VPS agora depende de um arquivo local `vps-tools/.env` (não versionado). Documentação foi redigida. `.gitignore` criado e `.dockerignore` reforçado. Um artefato de backup foi movido para quarentena reversível.

> **Observação crítica:** remover o segredo do código **não desfaz a exposição já ocorrida**. A senha root esteve em texto puro em 5 arquivos locais e pode ter sido copiada/sincronizada/incluída em backups. **Ela deve ser tratada como COMPROMETIDA** — ver Seção 6 (rotação obrigatória).

---

## 2. Arquivos modificados (segredos externalizados)

| Caminho | O que foi feito |
|---------|------------------|
| `vps-tools/run.js` | Host/usuário/senha hardcoded → `require('./ssh-config')` |
| `vps-tools/upload.js` | idem |
| `vps-tools/sync.js` | Constante de IP + senha → `ssh-config` |
| `vps-tools/pull-file.js` | Host/usuário/senha → `ssh-config` |
| `vps-tools/deploy-rebrand.js` | Constante de IP + senha → `ssh-config` |
| `README.md` | Redigidos: IP da VPS, link do painel com instance-id, senha admin em texto puro, e-mail/projeto do Service Account do Drive |
| `.dockerignore` | Adicionados: `vps-tools/`, `*.tgz`, `*.bak/*.old/*.orig`, `_QUARENTENA/`, `_session_componentes_bronze/` |

## 3. Arquivos criados

| Caminho | Função |
|---------|--------|
| `vps-tools/ssh-config.js` | Carregador de credenciais via env (lê `vps-tools/.env` ou variáveis de ambiente). Falha com mensagem clara se faltarem — **não** conecta sem credenciais. Sem dependências novas. |
| `vps-tools/.env.example` | Template das variáveis `VPS_HOST/VPS_USER/VPS_PASSWORD/VPS_PORT` (sem valores reais) |
| `.gitignore` | Criado do zero (projeto não era repo git). Ignora `.env`, chaves, `*.tgz/*.bak`, `node_modules`, `.venv*`, `generated/`, `_session_componentes_bronze/`, `_QUARENTENA/`, etc. |
| `_QUARENTENA/README.md` | Documenta itens movidos (reversível) |
| `RELATORIO_FASE0_CONTENCAO_2026-06-29.md` | Este relatório |

## 4. Quarentena (movido, não apagado)

| Item | Origem → Destino | Contém segredo? |
|------|------------------|------------------|
| `ejc_frontend_current.tgz` | raiz → `_QUARENTENA/` | **Não** (verificado: 0 ocorrências) |

Restaurável a qualquer momento movendo de volta.

## 5. Verificações executadas

- ✅ Sintaxe Node OK nos 6 arquivos (`node --check`).
- ✅ `ssh-config.js` projetado para `exit(1)` antes de conectar quando faltam credenciais (a execução de teste do `run.js` foi corretamente bloqueada pelo classificador por ser comando contra a VPS de produção — não contornado).
- ✅ Re-varredura: **0 ocorrências** dos valores reais (IP, senha root, senha admin, projeto/instance-id) em `vps-tools/*.js`, `README.md`, `scripts/`, `backend/app`, `frontend/src`.

## 6. Itens NÃO alterados nesta fase (fora do escopo / outra fase)

- `backend/app/core/config.py` (linhas 29/31): default de dev `ejc_user:ejc_pass` no `DATABASE_URL`. **É placeholder de dev, sobrescrito por env em produção** — não é o segredo real e mexer nele é "banco" (fora da Fase 0). **Verificar na rotação** se o banco de produção realmente usa essas credenciais e, se sim, rotacionar.
- `docker-compose.yml`: **já estava correto** (usa `${POSTGRES_USER}/${POSTGRES_PASSWORD}` via env) — nenhuma mudança.
- `vps-tools/generated/`, `_session_componentes_bronze/`, `*.bak`, `backend/.venv-codex/`: **verificados, sem segredos reais**. Cobertos por `.gitignore`. Remoção/organização → **Fase 5 (Higiene)**.

---

## 7. ⚠️ ROTAÇÃO MANUAL OBRIGATÓRIA (ação do usuário na VPS/serviços)

A senha root vazada dava **acesso total ao servidor**. Portanto, **todo segredo armazenado nessa VPS deve ser considerado potencialmente comprometido** e rotacionado:

1. **Senha root da VPS (URGENTE, hoje):** conectar e trocar — `passwd root`. Recomendado migrar para **chave SSH** e desativar login por senha (`PasswordAuthentication no` no `sshd_config`). Depois preencher `vps-tools/.env` com as novas credenciais.
2. **Senha do admin da aplicação** (a que estava no README): redefinir via o procedimento de reset (agora usando `$NOVA_SENHA` em variável, não texto puro).
3. **Banco de dados:** rotacionar `POSTGRES_PASSWORD` (e confirmar que produção não usa o default `ejc_pass`); atualizar o `.env` real na VPS.
4. **`SECRET_KEY` (JWT):** gerar nova chave (`python3 -c "import secrets; print(secrets.token_urlsafe(64))"`) — todas as sessões/tokens atuais serão invalidados (efeito desejado).
5. **Chaves de API de IA:** rotacionar **Groq** (e **Anthropic**, se houver) no painel do provedor.
6. **SMTP** (Gmail/contato): trocar a senha de app.
7. **Google Drive Service Account:** revogar e gerar nova chave do SA; substituir o arquivo de credencial na VPS.
8. **Git:** o projeto **não é repositório git** — não há histórico público com segredos. Se em algum momento houve push/cópia para fora (ex.: backups, `.tgz`, pastas sincronizadas), considere esses destinos comprometidos.

> Após a rotação, valide que os scripts `vps-tools` funcionam com o novo `vps-tools/.env` e que a aplicação sobe com os novos segredos no `.env` da VPS.
