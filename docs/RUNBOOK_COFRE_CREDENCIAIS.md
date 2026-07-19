# Runbook — Cofre de Credenciais do EJC

Procedimento operacional do Cofre de Credenciais (tabela
`integration_credentials`, migration 108). Referências de código:

- Criptografia: `backend/app/services/vault_crypto.py` (MultiFernet).
- Serviço: `backend/app/services/credential_vault_service.py`.
- Catálogo de campos: `backend/app/services/credential_registry.py`.
- API: `backend/app/routers/credential_vault.py` (prefixo `/cofre-credenciais`).
- Rotação da chave-mestra: `backend/scripts/vault_rotate_master_key.py`.

Conceito central do plano (`docs/PLANO_COFRE_CREDENCIAIS.md`): o `.env` continua
sendo o **fallback**; o cofre **sobrepõe** o `.env` para os campos cadastrados;
credencial **revogada** vira `""` (sem cair de volta no `.env`). A chave-mestra
vive **fora do banco**, só no `.env`.

Todas as rotas de `/cofre-credenciais` exigem papel **superadmin** e as
operações mutadoras exigem **step-up**: `senha_atual` (+ `codigo_totp` de 6
dígitos se o superadmin tiver 2FA ativo).

---

## 1. Gerar `VAULT_MASTER_KEYS` (primeiro provisionamento)

A chave-mestra é uma chave Fernet dedicada AO COFRE — nunca reusar
`SECRET_KEY`, `PII_ENCRYPTION_KEY` ou `BACKUP_ENCRYPTION_KEY`.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- Coloque o valor em `VAULT_MASTER_KEYS` no `.env` do VPS (CSV — no início, uma
  única chave).
- **Guarde uma cópia offline** (cofre físico/gerenciador de segredos fora do
  VPS), mesma disciplina do `BACKUP_ENCRYPTION_KEY`. **Perder a chave = perder
  o cofre** (ver seção 7).

## 2. Primeiro deploy

O boot **falha alto** em `APP_ENV=production` se `VAULT_MASTER_KEYS` estiver
ausente, com placeholder (`TROCAR...`) ou com chave Fernet malformada
(`backend/app/core/config.py`). Isso é intencional — a falha aparece no deploy,
não no primeiro uso de uma credencial.

Checklist:
1. `VAULT_MASTER_KEYS` definido no `.env` **antes** de subir a stack.
2. Subir backend + worker (ambos leem o mesmo `.env`).
3. Confirmar que a aplicação iniciou (sem `ValueError` de boot no log).

Em desenvolvimento (`APP_ENV != production`), se `VAULT_MASTER_KEYS` estiver
vazio o boot gera uma chave **efêmera** com `warnings.warn` — credenciais
cifradas com ela se perdem no próximo restart.

## 3. Importar credenciais do `.env` para o cofre

Depois que a app está de pé com a chave-mestra, migre os segredos que hoje
vivem no `.env`:

```
POST /cofre-credenciais/importar-env
{ "senha_atual": "<senha do superadmin>", "codigo_totp": "<6 dígitos, se 2FA>" }
```

- Idempotente: importa só os campos do catálogo com valor não-vazio no
  `Settings` e **sem** linha ativa (origem `env_import`); rodar de novo não
  duplica.
- A resposta traz `{provider, field, last4}` — **nunca** o valor.

### 3.1 Remover os segredos em claro do `.env` (checklist MANUAL)

O import **não** apaga nada do `.env` (por segurança, é passo manual e
revisável). Depois de confirmar o import e testar as conexões (seção 4):

1. Liste o cofre (`GET /cofre-credenciais`) e confira `last4`/`origem` de cada
   campo esperado.
2. Teste cada provider (seção 4) e confirme estado `configurada`.
3. **Só então** comente/remova as linhas em claro correspondentes no `.env` do
   VPS (mantendo `VAULT_MASTER_KEYS` e demais chaves de infraestrutura).
4. Reinicie app/worker e revalide os testes de conexão.

> Mantenha o `.env` original em backup seguro durante a transição — enquanto
> ele ainda tiver os valores, há caminho de recuperação (seção 7).

## 4. Testar conexões

```
POST /cofre-credenciais/{provider_key}/testar
{ "senha_atual": "...", "codigo_totp": "..." }
```

Estados possíveis: `configurada | ausente | invalida | expirada |
sem_permissao | indisponivel`. O resultado é gravado nas linhas ativas do
provider (`last_test_status/at/detail`) e alimenta o painel de saúde das
integrações. O detalhe nunca contém segredo.

## 5. Rotação de uma credencial individual (substituir)

Quando um provedor emite uma nova chave/senha:

```
POST /cofre-credenciais/{provider_key}/{field_key}
{ "valor": "<novo segredo>", "tipo": "<api_key|token|login|senha|oauth_client>",
  "senha_atual": "...", "codigo_totp": "..." }
```

- Desativa a versão anterior, **zera** o `valor_encrypted` antigo (só `last4` +
  metadados sobrevivem) e cria a nova versão ativa (`versao = n+1`).
- Para desligar um campo sem substituto, use a revogação (`DELETE
  /cofre-credenciais/{provider_key}/{field_key}` com step-up): o atributo vira
  `""` no runtime, **sem** fallback ao `.env`.

## 6. Rotação da CHAVE-MESTRA (`VAULT_MASTER_KEYS`)

Rotaciona a chave que cifra o cofre inteiro, sem downtime. O MultiFernet cifra
com a **primeira** chave do CSV e decifra com **qualquer** uma — por isso a
rotação é em 3 passos (só o último é irreversível):

**(a) Prepend da chave nova.** Gere a chave nova (seção 1) e coloque-a na
FRENTE do CSV, mantendo a antiga:

```
VAULT_MASTER_KEYS=<NOVA>,<ANTIGA>
```

Reinicie app/worker. A partir daqui tudo que for cifrado usa a NOVA; o legado
ainda decifra com a ANTIGA. Guarde a NOVA offline (seção 1).

**(b) Re-encriptar o cofre.** Rode o script (dry-run primeiro):

```bash
cd backend
python scripts/vault_rotate_master_key.py --dry-run   # conta, não grava
python scripts/vault_rotate_master_key.py --yes        # efetiva
```

O script (via `credential_vault_service.rotacionar_todas`) recifra cada linha
com `valor_encrypted` não-nulo — ativas e históricas — usando
`vault_crypto.rotacionar` (`MultiFernet.rotate`: decifra com qualquer chave,
recifra com a primária = NOVA). É idempotente (rodar de novo não corrompe: o
valor decifrado é sempre o mesmo), loga só contagem/progresso (nunca valores) e
registra auditoria `COFRE_ROTATE_MASTER`. Se o CSV tiver **menos de duas
chaves**, o script aborta e ensina o procedimento (não há o que rotacionar com
segurança).

**(c) Remover a chave antiga.** Só depois de `--yes` concluir sem erro:

```
VAULT_MASTER_KEYS=<NOVA>
```

Reinicie app/worker. A partir daqui a ANTIGA não decifra mais nada — por isso
ela só sai quando nenhum token depende mais dela. Descarte a ANTIGA das cópias
offline.

## 7. Recuperação de desastre

- **Perda da chave-mestra** = perda do que está cifrado no cofre (não dos
  serviços em si). O caminho é reemitir cada credencial nos provedores e
  recadastrá-las (seção 5) sob uma nova chave-mestra (seção 1).
- **Enquanto o `.env` ainda tiver os valores em claro** (transição da seção 3
  ainda não concluída), há recuperação imediata: restaure os valores no `.env`,
  gere uma nova `VAULT_MASTER_KEYS`, suba a app e reimporte (seção 3). Por isso
  a remoção dos segredos do `.env` (3.1) só deve ocorrer após cópia da
  chave-mestra offline e testes de conexão OK.
- **Backup da chave-mestra**: trate `VAULT_MASTER_KEYS` com a mesma disciplina
  de `BACKUP_ENCRYPTION_KEY` — cópia fora do VPS, acesso restrito, rotação
  documentada (seção 6).
