# Plano — Cofre de Credenciais do EJC

Status: **PR-1..PR-6 concluídos** — cofre completo em produção (fundação,
serviço + overlay, API, testadores, frontend, import do `.env` + rotação da
chave-mestra + runbook). Runbook operacional em
`docs/RUNBOOK_COFRE_CREDENCIAIS.md`.
Plano produzido em 19/07/2026 (agente Plan) e transcrito/expandido aqui.

## 1. Problema

Todos os segredos de integrações externas (DataJud, Groq, Anthropic, Maritaca,
Infosimples, Z-API/WhatsApp, SMTP, NuvemFiscal/NFS-e, Portal da Transparência,
Langfuse, VAPID/Web Push) vivem exclusivamente no `.env` do VPS. Consequências:

- trocar/revogar uma credencial exige acesso SSH + edição manual + restart;
- não há trilha de auditoria (quem trocou, quando, qual sufixo);
- não há teste de validade por integração nem visibilidade de expiração;
- o superadmin (usuário do sistema) não consegue operar credenciais pela UI.

O cofre traz as credenciais para o banco, **cifradas em repouso**, com
auditoria, versionamento, teste por integração e UI em Configurações —
mantendo o `.env` como fallback e a chave mestra fora do banco.

## 2. Arquitetura

### 2.1 Criptografia — MultiFernet com `VAULT_MASTER_KEYS`

- `VAULT_MASTER_KEYS` = CSV de chaves Fernet no `.env`; a **primeira cifra**
  (primária), **todas decifram** (`cryptography.MultiFernet`).
- Sem envelope encryption (KMS/data-keys): complexidade injustificada para um
  único VPS; MultiFernet dá rotação de mestra sem downtime com uma dependência
  que o projeto já usa (`cryptography`).
- **Rotação de mestra** = prepend da chave nova no CSV (a antiga segue
  decifrando o legado) + re-encrypt em background de cada token via
  `MultiFernet.rotate` (`vault_crypto.rotacionar`); só depois a antiga sai do
  CSV. Runbook no PR-6.
- A chave vive **fora do banco** (só `.env`), é **exclusiva do cofre** (não
  reusa `PII_ENCRYPTION_KEY`/`BACKUP_ENCRYPTION_KEY` — rotacionar uma não pode
  invalidar a outra) e **jamais deriva de `SECRET_KEY`** (trocar o SECRET_KEY
  desloga usuários; não pode também inutilizar credenciais).
- Boot: em `APP_ENV=production`, ausência/placeholder/chave malformada →
  `ValueError` no boot (mesma promessa "falha no deploy, não no primeiro uso"
  de PII/BACKUP; todas as chaves do CSV são validadas). Em dev, chave efêmera
  gerada com `warnings.warn` explícito.
- Falha alta: token inválido ou cifrado com chave fora do CSV →
  `ValueError` (mesma filosofia de `pii_crypto.decrypt`) — mascarar entregaria
  credencial errada a uma integração externa.

### 2.2 Persistência — tabela `integration_credentials` (migration 108)

| Coluna | Tipo | Notas |
|---|---|---|
| id | VARCHAR(36) PK | UUID string (padrão do projeto) |
| provider_key | VARCHAR(50) NOT NULL, index | chave do catálogo (ex.: `datajud`) |
| field_key | VARCHAR(80) NOT NULL | **nome EXATO do atributo em `Settings`** |
| tipo | VARCHAR(20) NOT NULL | `api_key\|token\|login\|senha\|oauth_client` |
| valor_encrypted | TEXT NULL | token MultiFernet; NULL quando versão substituída/revogada |
| last4 | VARCHAR(8) NULL | sufixo exibível na UI (nunca o valor) |
| versao | INTEGER NOT NULL DEFAULT 1 | versionamento por linha |
| ativo | BOOLEAN NOT NULL DEFAULT TRUE | vigência |
| origem | VARCHAR(20) NOT NULL DEFAULT 'manual' | `manual\|env_import` |
| expires_at | TIMESTAMPTZ NULL | expiração declarada |
| last_test_at / last_test_status / last_test_detail | TIMESTAMPTZ/VARCHAR(30)/TEXT | resultado do último teste (PR-4) |
| created_by / revoked_by | VARCHAR(36) FK users ON DELETE SET NULL | auditoria |
| created_at / updated_at / revoked_at | TIMESTAMPTZ | ciclo de vida |

- **Índice único parcial** `uq_integration_credentials_provider_field_ativo`
  em `(provider_key, field_key) WHERE ativo` — uma credencial vigente por
  campo, histórico ilimitado de versões desativadas (padrão
  `uq_users_email_active`, migration 075).
- **Substituição zera `valor_encrypted` da versão antiga** — o segredo antigo
  não fica de histórico; sobram `last4` + metadados para auditoria.
- Migration **aditiva pura e idempotente** (raw SQL `CREATE ... IF NOT
  EXISTS`, padrão da 107); VARCHAR com domínio na aplicação em vez de ENUM
  nativo (trade-off consolidado nas migrations 073/084/107).

### 2.3 Catálogo — `services/credential_registry.py`

Dict estático `provider_key → campos` (`CampoCredencial(field_key, tipo,
rotulo, obrigatorio)`), fonte única para a UI, o import do `.env` e o gate de
escrita do router. **Contrato central**: `field_key` = nome exato do atributo
em `Settings`, validado por introspecção em `tests/test_vault_fundacao.py`.
Cobertura atual: datajud, groq, anthropic, maritaca, infosimples,
whatsapp_zapi (3 campos), smtp (2), nfse/NuvemFiscal (2, oauth_client),
transparencia, langfuse (2), push_vapid (2).

### 2.4 Overlay de runtime (PR-2)

- `aplicar_overlay` faz `setattr` **no singleton** `get_settings()`
  (`lru_cache` — mutação in-place propaga aos ~68 módulos que guardaram a
  referência). **Nunca `cache_clear()`** (criaria segundo objeto Settings e
  split-brain entre módulos).
- Worker Celery ressincroniza via número de versão + `task_prerun` com TTL
  ≤ 60s.
- Credencial **revogada** → atributo vira `""` **sem fallback ao `.env`**
  (revogação tem que revogar de verdade); credencial ausente do cofre →
  `.env` continua valendo (compatibilidade).

### 2.5 API (PR-3)

- Router `/cofre-credenciais` com `require_roles(["superadmin"])` em tudo.
- **Step-up por operação**: `senha_atual` (+ TOTP se 2FA ativo) — padrão
  `alterar_senha`.
- Response models **sem campo de valor** (só `last4`, datas, status) — o
  segredo nunca volta pela API depois de gravado.
- Auditoria `COFRE_*` via `criar_audit_log`, **sem segredo no log**.
- Rate limit (slowapi) nas operações de escrita/teste.

### 2.6 Testadores por integração (PR-4)

Estados: `configurada | ausente | invalida | expirada | sem_permissao |
indisponivel`. Estende o `integration_status` existente com campo
retrocompatível `credential_state`.

## 3. Decisões de segurança (resumo)

1. Chave mestra fora do banco; produção falha no boot sem ela (nunca autogera).
2. Nunca derivar de `SECRET_KEY`; chave exclusiva, não reusada de PII/backup.
3. Segredo cifrado com Fernet autenticado (AES-128-CBC + HMAC); falha alta em
   token inválido.
4. Substituição/revogação zera o ciphertext antigo (minimização — LGPD).
5. API nunca devolve o valor; UI só vê `last4`.
6. Superadmin + step-up (senha/TOTP) por operação sensível.
7. Auditoria completa sem vazar segredo.
8. Revogada → `""` sem fallback ao `.env`.

## 4. Sequência de PRs

| PR | Escopo | Estado |
|---|---|---|
| PR-1 | Fundação: `VAULT_MASTER_KEYS` + validators, `vault_crypto`, modelo + migration 108, `credential_registry`, testes. **Deploy inerte** (nada lê a tabela). | **feito** |
| PR-2 | `credential_vault_service` + overlay no singleton + ressincronização do worker Celery. | **feito** |
| PR-3 | Router `/cofre-credenciais` + step-up + auditoria `COFRE_*` + `POST /importar-env`. | **feito** |
| PR-4 | Testadores por integração + `credential_state` no integration_status. | **feito** |
| PR-5 | Frontend: aba Credenciais em Configurações (espelha `IntegrationHealthPanel`). | **feito** |
| PR-6 | Rotação da chave-mestra assistida (`scripts/vault_rotate_master_key.py` + `rotacionar_todas`) e runbook operacional (`docs/RUNBOOK_COFRE_CREDENCIAIS.md`). Import do `.env` já entregue no PR-3. | **feito** |

## 5. Riscos e mitigações

- **Perda da chave mestra** = perda das credenciais do cofre (não dos
  serviços — reemitir nos provedores). Mitigação: cópia da chave fora do VPS
  (mesmo runbook do BACKUP_ENCRYPTION_KEY).
- **Split-brain de Settings** se alguém usar `cache_clear()` — proibido;
  overlay é sempre mutação in-place do singleton.
- **Worker dessincronizado** — TTL ≤ 60s + versão em `task_prerun` (PR-2).
- **Deploy de produção após PR-1 exige definir `VAULT_MASTER_KEYS`** no
  `.env` antes de subir (boot falha alto por design). Comunicar no changelog
  do deploy.
- **Migração dupla .env/cofre** durante a transição: precedência clara
  (cofre > .env, exceto revogada = `""`), import assistido no PR-6.
