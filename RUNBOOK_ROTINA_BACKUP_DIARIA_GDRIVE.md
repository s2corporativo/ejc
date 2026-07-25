# Rotina de Backup Diário Cifrado do EJC no Google Drive

**Status:** código implementado; ativação e prova real dependem da credencial do
ambiente e são rastreadas na issue #378.

A rotina salva diariamente:

1. o banco PostgreSQL em formato customizado `pg_dump -Fc`;
2. todo o `UPLOAD_DIR`, incluindo peças, provas, PDFs, assinaturas e documentos
   enviados pelo Portal;
3. ambos cifrados com Fernet antes de sair da VPS.

O backup somente é considerado operacional depois de uma restauração integral
em ambiente descartável. Upload sem restauração comprovada não conclui o gate
G7 do EJC.

---

## 1. Arquitetura e controles

| Controle | Implementação |
|---|---|
| Agendamento | Scheduler do backend, diariamente em `BACKUP_HORA_UTC`. |
| Opt-in | A rotina só agenda com `BACKUP_ENABLED=true`. |
| Banco | `pg_dump -Fc`, com timeout e limite de tamanho configuráveis. |
| Documentos | `tar.gz` de todo o `UPLOAD_DIR`. |
| Criptografia | Fernet com `BACKUP_ENCRYPTION_KEY`, antes do upload. |
| Autenticação Drive | Identidade exclusiva `BACKUP_GOOGLE_DRIVE_*`; recomendado `service_account`. |
| Retenção | Remove somente arquivos do EJC além de `BACKUP_RETENCAO_DIAS`. |
| Concorrência | Um ciclo por vez; execuções simultâneas não duplicam o backup. |
| Telemetria | Estado em `/admin/backup/status` e alerta de falha. |
| Restauração | Manual, verificável e nunca executada pelo scheduler. |

O RAG permanece com credencial somente leitura. O backup não deve ampliar essa
credencial para escrita.

### Nomes exatos dos artefatos

Cada ciclo usa o mesmo timestamp UTC nos dois arquivos:

```text
ejc_backup_AAAAmmddTHHMMSSZ_db.dump.enc
ejc_backup_AAAAmmddTHHMMSSZ_uploads.tar.gz.enc
```

O par deve ter timestamp idêntico. Misturar banco e uploads de ciclos
diferentes invalida a prova.

---

## 2. Variáveis obrigatórias

As variáveis ficam no cofre ou no `.env` da VPS. Nunca devem entrar no
repositório, issues, logs ou histórico do shell.

```env
BACKUP_ENABLED=true
BACKUP_ENCRYPTION_KEY=<chave-fernet-exclusiva>
BACKUP_DRIVE_FOLDER_ID=<id-da-pasta>
BACKUP_GOOGLE_DRIVE_AUTH_MODE=service_account
BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE=/run/secrets/ejc-backup-drive.json
```

Alternativamente, o JSON da service account pode ser fornecido por
`BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`, desde que injetado pelo cofre de
segredos.

Variáveis operacionais com valores padrão:

```env
BACKUP_HORA_UTC=05:00
BACKUP_RETENCAO_DIAS=14
BACKUP_UPLOADS_MAX_MB=512
BACKUP_DB_MAX_MB=2048
BACKUP_PG_DUMP_TIMEOUT=600
UPLOAD_DIR=/app/uploads
```

### Gerar a chave Fernet

Gere uma única vez e custodie uma cópia fora da VPS:

```bash
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Perder a chave torna os artefatos irrecuperáveis. Expor a chave compromete todo
o histórico de backups produzido com ela.

---

## 3. Preparar a service account

1. Criar uma service account exclusiva para backup.
2. Guardar o JSON somente no cofre/ambiente da VPS.
3. Compartilhar apenas a pasta `BACKUP_DRIVE_FOLDER_ID` com o e-mail da service
   account como **Editor**.
4. Montar o arquivo no container backend como somente leitura.
5. Reiniciar o backend para recarregar a configuração.

Não reutilize a credencial OAuth `drive.readonly` da base de conhecimento. Um
refresh token concedido somente para leitura falha com `invalid_scope` quando
reconstruído para escrita.

---

## 4. Ativação e diagnóstico

### Recarregar o backend

```bash
docker compose restart backend
```

### Diagnóstico local

```bash
bash scripts/backup/diagnostico_backup.sh
```

O diagnóstico não deve imprimir chaves, senha do banco ou JSON da service
account.

### Estado administrativo

Com perfil `admin` ou `superadmin`:

```text
GET /admin/backup/status
```

Confirme:

- `enabled=true`;
- `chave_configurada=true`;
- `pasta_configurada=true`;
- `credencial_drive_configurada=true`;
- `credencial_dedicada_configurada=true`;
- `auth_mode=service_account`;
- `pg_dump_disponivel=true`.

### Disparo manual

```text
POST /admin/backup/executar
```

Resposta esperada: HTTP 202. Acompanhe o status até `em_execucao=false` e
confirme `ultimo_resultado.last_status` como `sucesso` ou `parcial` devidamente
justificado.

Na pasta do Drive devem existir os dois arquivos `.enc`, com o mesmo timestamp
e tamanho maior que zero.

---

## 5. Verificação da cobertura dos documentos

Os arquivos físicos não estão dentro do `pg_dump`. Eles vivem em `UPLOAD_DIR`.
Antes e depois do backup, registre apenas quantidade e tamanho, sem listar nomes
sensíveis em evidência pública:

```bash
docker exec ejc_backend sh -c 'du -sh /app/uploads && find /app/uploads -type f | wc -l'
```

Todo módulo que gerar arquivo persistente deve gravá-lo sob `UPLOAD_DIR`. Um
caminho externo exige inclusão explícita na política de backup.

---

## 6. Verificação criptográfica sem restauração

Baixe do Drive o par com o mesmo timestamp para um diretório restrito. Defina a
chave pelo ambiente ou por arquivo de chave com permissão somente leitura.

### Chave no ambiente

```bash
export BACKUP_ENCRYPTION_KEY='<chave-custodiada>'
python3 scripts/backup/validar_restauracao_cifrada.py \
  ./ejc_backup_20260720T210000Z_db.dump.enc \
  ./ejc_backup_20260720T210000Z_uploads.tar.gz.enc \
  --json-output ./evidencias/manifest-restauracao.json
unset BACKUP_ENCRYPTION_KEY
```

### Chave em arquivo montado

```bash
python3 scripts/backup/validar_restauracao_cifrada.py \
  ./ejc_backup_20260720T210000Z_db.dump.enc \
  ./ejc_backup_20260720T210000Z_uploads.tar.gz.enc \
  --key-file /run/secrets/ejc-backup-fernet.key \
  --json-output ./evidencias/manifest-restauracao.json
```

O modo padrão:

- verifica se os artefatos pertencem ao mesmo ciclo;
- decifra em diretório temporário;
- valida o dump com `pg_restore --list`;
- rejeita traversal, links e tipos especiais no `tar.gz`;
- calcula hashes e contagens;
- remove automaticamente os arquivos em claro;
- nunca inclui chave ou senha no manifesto.

---

## 7. Prova de restauração em banco descartável

Crie previamente um banco vazio cujo nome contenha `test`, `teste`, `homolog`,
`restore`, `restauracao` ou `dr`. O utilitário recusa:

- nomes que não aparentem ambiente descartável;
- alvo físico igual a `DATABASE_URL_SYNC` ou `DATABASE_URL`, mesmo com usuário
  diferente;
- senha na linha de comando.

Configure a URL somente no ambiente:

```bash
export RESTORE_TEST_DATABASE_URL='postgresql://usuario:senha@host:5432/ejc_restore_test'
export BACKUP_ENCRYPTION_KEY='<chave-custodiada>'
mkdir -p /tmp/ejc-restore-uploads

python3 scripts/backup/validar_restauracao_cifrada.py \
  ./ejc_backup_20260720T210000Z_db.dump.enc \
  ./ejc_backup_20260720T210000Z_uploads.tar.gz.enc \
  --restore-test \
  --uploads-output-dir /tmp/ejc-restore-uploads \
  --json-output ./evidencias/manifest-restauracao-real.json

unset RESTORE_TEST_DATABASE_URL
unset BACKUP_ENCRYPTION_KEY
```

A prova somente é aprovada quando o manifesto indicar:

- `status=restaurado_em_ambiente_descartavel`;
- objetos reconhecidos pelo `pg_restore`;
- tabelas no schema `public`;
- quantidade de uploads restaurados;
- hashes dos artefatos cifrados e decifrados;
- nenhum segredo.

Depois, inicialize uma instância de homologação sobre a cópia, execute migrations
quando necessário e valide login e consulta de dados fictícios. Registre tempo
total para definir RTO e a idade do backup para definir RPO.

---

## 8. Disaster recovery real

A recuperação de produção exige decisão humana, janela de indisponibilidade e
backup de segurança do estado atual.

Primeiro valide o par conforme as seções 6 e 7. Depois, para gerar arquivos em
claro deliberadamente:

```bash
mkdir -p /secure/ejc-restore
chmod 700 /secure/ejc-restore
export BACKUP_ENCRYPTION_KEY='<chave-custodiada>'

python3 scripts/backup/validar_restauracao_cifrada.py \
  ./ejc_backup_20260720T210000Z_db.dump.enc \
  ./ejc_backup_20260720T210000Z_uploads.tar.gz.enc \
  --export-clear-dir /secure/ejc-restore \
  --json-output ./evidencias/manifest-exportacao.json

unset BACKUP_ENCRYPTION_KEY
```

O diretório recebe `db.dump` e `uploads.tar.gz` com permissões restritas. Só
então execute a restauração guiada existente:

```bash
bash scripts/backup/restaurar_backup.sh \
  /secure/ejc-restore/db.dump \
  /secure/ejc-restore/uploads.tar.gz
```

O script solicita confirmação explícita do banco. Após validar a aplicação,
apague os artefatos em claro e o diretório temporário por procedimento seguro.
Nunca mantenha dump com PII em pasta compartilhada ou sem criptografia.

---

## 9. Alertas e monitoramento

Falhas do ciclo são registradas e notificadas ao primeiro admin/superadmin ativo
com e-mail quando o canal estiver configurado.

O monitor externo deve alertar quando:

- o último backup ultrapassar 25 horas;
- o status for `erro`;
- qualquer booleano de configuração obrigatório for falso;
- apenas um dos dois artefatos existir;
- houver redução anormal de tamanho ou contagem;
- a restauração periódica estiver vencida.

O monitor nunca deve executar restauração automaticamente.

---

## 10. Critério de encerramento da issue #378

A issue somente pode ser encerrada quando houver evidência sanitizada de:

1. upload dos dois artefatos cifrados;
2. hashes e tamanhos registrados;
3. decifragem com a chave custodiada;
4. `pg_restore` em banco descartável;
5. restauração e amostragem dos uploads;
6. aplicação de homologação iniciada sobre a cópia;
7. RPO e RTO aprovados;
8. descarte seguro dos arquivos em claro;
9. nenhum segredo exposto.

---

## 11. Destino OneDrive via rclone (`BACKUP_DESTINO=rclone`)

Alternativa offsite ao Google Drive quando a service account estiver
indisponível (contexto da issue #378). O ciclo local é idêntico: `pg_dump` +
`tar` de uploads, **sempre cifrados com Fernet antes de sair da VPS** —
`BACKUP_ENCRYPTION_KEY` continua obrigatória e nada é enviado em claro.

### 11.1 Instalar o rclone na VPS (se ausente)

```bash
command -v rclone || curl https://rclone.org/install.sh | sudo bash
rclone version
```

### 11.2 Configurar o remote OneDrive

```bash
rclone config
# n) New remote
# name> onedrive
# Storage> onedrive   (Microsoft OneDrive)
# client_id / client_secret: deixar em branco (defaults do rclone)
# Edit advanced config> n
# Use auto config> n   ← a VPS é headless, sem navegador
```

Como a VPS não tem navegador, o rclone pedirá um token. Em uma máquina COM
navegador (desktop) que também tenha rclone instalado, rode:

```bash
rclone authorize "onedrive"
```

Autorize a conta Microsoft no navegador, copie o bloco JSON exibido
(`config_token`) e cole no prompt `result>` da VPS. Escolha o tipo de conta
(OneDrive Personal/Business) e conclua com `y`.

### 11.3 Testar o remote

```bash
rclone lsd onedrive:
rclone mkdir onedrive:EJC-Backups   # pasta de destino dos artefatos
```

### 11.4 Ativar no EJC (`/opt/ejc/.env`)

```bash
BACKUP_DESTINO=rclone
BACKUP_RCLONE_REMOTE=onedrive:EJC-Backups
# BACKUP_RCLONE_TIMEOUT=300          # segundos por artefato, se o link for lento
# BACKUP_OFFSITE_OBRIGATORIO=false   # default: prova local sustenta o deploy
```

Reinicie o backend (`docker compose up -d backend worker`) e valide com
`bash scripts/backup.sh` — o JSON final deve trazer `"destino": "rclone"`,
`"local_ok": true` e `"offsite_ok": true`.

Observações:

- O container do backend precisa enxergar o binário `rclone` e o arquivo de
  configuração do remote. Se o backup roda dentro do container, monte
  `~/.config/rclone/rclone.conf` (somente leitura) e instale o rclone na
  imagem; alternativamente rode `scripts/backup.sh` pelo host.
- A rotação automática por `BACKUP_RETENCAO_DIAS` aplica-se apenas ao Google
  Drive. No remote rclone, faça a limpeza periódica manualmente, por exemplo:
  `rclone delete --min-age 14d --include "ejc_backup_*" onedrive:EJC-Backups`.
- Semântica do gate de deploy: falha do envio offsite com prova local cifrada
  presente gera status `parcial` (ok=true) e **AVISO GRAVE** no log/step
  summary; o deploy só é bloqueado se a prova LOCAL falhar. Para voltar ao
  comportamento fail-closed, defina `BACKUP_OFFSITE_OBRIGATORIO=true`.
- `BACKUP_ENCRYPTION_KEY` permanece obrigatória em qualquer destino — perder a
  chave = perder todos os backups. Custódia fora da VPS, como na seção 2.
