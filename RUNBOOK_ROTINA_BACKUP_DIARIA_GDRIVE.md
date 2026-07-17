# Rotina de Backup Diário do EJC no Google Drive

Rotina que, **todo dia automaticamente**, salva no Google Drive uma cópia
**cifrada** de:

1. **O sistema inteiro** — banco PostgreSQL via `pg_dump -Fc` (casos, clientes,
   prazos, honorários, usuários e os **metadados** de todos os documentos).
2. **Todos os documentos gerados e enviados** — o diretório `UPLOAD_DIR`
   (`/app/uploads`) inteiro, que é onde o EJC grava **peças, minutas, PDFs
   gerados, provas, anexos, assinaturas e documentos do portal do cliente**
   (`pdf_service`, `legal_docs`, `portal_documentos`, `provas`,
   `anexos_service`, `signatures`, `visual_law_files`).

Companion: `RUNBOOK_BACKUP.md` (caminho alternativo via script + cron no VPS) e
a skill `gestor-backup-recuperacao`.

> **A rotina já existe no código** (`backend/app/services/backup_service.py`,
> agendada pelo scheduler). Este runbook é o passo-a-passo para **ativá-la e
> operá-la**. Nada aqui expõe segredos.

---

## 1. O que a rotina faz (e por que é segura)

| Item | Comportamento |
|---|---|
| **Quando roda** | Diariamente às `BACKUP_HORA_UTC` (default **05:00 UTC**), via scheduler do backend. Gate: `BACKUP_ENABLED=true`. |
| **O que salva** | `pg_dump -Fc` do banco **+** `tar.gz` do `UPLOAD_DIR` (documentos gerados/enviados). |
| **Criptografia (LGPD)** | Todo artefato é cifrado com **Fernet** (`BACKUP_ENCRYPTION_KEY`) **antes** de sair do VPS. O dump carrega PII — sem a chave o backup não sobe. |
| **Onde salva** | Pasta do Google Drive `BACKUP_DRIVE_FOLDER_ID`, arquivos com prefixo `ejc_backup_…​.enc`. Reusa as credenciais Google já cadastradas para a curadoria de conhecimento (RAG), reescopadas para escrita. |
| **Retenção/rotação** | Mantém `BACKUP_RETENCAO_DIAS` (default **14**) dias. A rotação **só** apaga arquivos com o prefixo `ejc_backup_` — nunca toca outros arquivos da pasta. |
| **Concorrência** | Um backup por vez (guard síncrono). Um disparo em corrida retorna “em execução” sem duplicar. |
| **Falha** | Dump vazio/corrompido, erro de upload ou 403 do Drive disparam alerta e ficam registrados no `/admin/backup/status`. |

Limites de tamanho (protegem RAM/tempo): `BACKUP_UPLOADS_MAX_MB` (512),
`BACKUP_DB_MAX_MB` (2048), `BACKUP_PG_DUMP_TIMEOUT` (600s).

---

## 2. Ativar a rotina (uma vez, no VPS de produção)

Os valores abaixo vão no **`.env` do VPS** (nunca no repositório). Ver
`.env.example`.

1. **Gerar a chave de criptografia** (guarde-a FORA do servidor — perder a chave
   = perder os backups):
   ```bash
   python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```
2. **Criar a pasta no Google Drive** onde os backups vão morar e copiar o ID da
   pasta (o trecho final da URL `…/folders/<ID>`). A conta Google cadastrada
   precisa de permissão de **escrita** nessa pasta.
3. **Preencher o `.env`**:
   ```env
   BACKUP_ENABLED=true
   BACKUP_ENCRYPTION_KEY=<a chave gerada no passo 1>
   BACKUP_DRIVE_FOLDER_ID=<o ID da pasta do passo 2>
   # opcionais (têm default):
   BACKUP_HORA_UTC=05:00
   BACKUP_RETENCAO_DIAS=14
   ```
4. **Reiniciar o backend** para o scheduler reagendar:
   ```bash
   docker compose restart backend
   ```
5. **Validar a configuração** (logado como admin/superadmin):
   ```
   GET /admin/backup/status
   ```
   Confira `configuracao.enabled/chave_configurada/pasta_configurada/`
   `credencial_drive_configurada/pg_dump_disponivel` — todos **true**.
6. **Testar com um backup manual** (não espera o horário, mas exige chave+pasta):
   ```
   POST /admin/backup/executar      → 202 (roda em background)
   ```
   Acompanhe em `GET /admin/backup/status` até `em_execucao=false` e confirme na
   pasta do Drive um arquivo `ejc_backup_<data>…_db.enc` e outro `…_uploads.enc`
   com tamanho > 0.

Pronto: a partir daí a rotina roda sozinha todo dia no horário configurado.

---

## 3. Confirmar que os documentos gerados entram no backup

Os documentos gerados **não** vão para o banco — só os metadados vão. Os arquivos
vivem em `UPLOAD_DIR` (`/app/uploads`, volume Docker `uploads_data`). A rotina
empacota esse diretório **inteiro**, então cobre automaticamente qualquer módulo
novo que salve arquivo ali. Checagem rápida no VPS:

```bash
docker exec ejc_backend sh -c 'du -sh /app/uploads && find /app/uploads -type f | wc -l'
```

Se um módulo passar a gravar documentos **fora** de `/app/uploads`, esse caminho
**não** será coberto — mantenha todo storage de arquivos sob `UPLOAD_DIR`.

---

## 4. Aviso por e-mail quando o backup falhar (nativo — recomendado)

**Já existe no EJC** (`backup_service._alertar_falha`): quando o backup diário
roda e falha, o sistema notifica automaticamente o(s) **admin/superadmin** por
**sino + e-mail** (assunto `[EJC] Backup automático FALHOU`). Roda no VPS junto
com o backup — **não depende de conector externo nem de agente de IA**. Para
ligar o canal de e-mail:

1. Configurar o envio no `.env` do VPS:
   ```env
   EMAIL_ENABLED=true
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=<conta de envio>
   SMTP_PASSWORD=<senha de app>
   ```
2. Garantir um usuário **admin/superadmin ativo com e-mail** (ex.:
   `adm@vetmg.com.br`) — é para ele que o alerta vai.

Teste: em ambiente de teste, force uma falha controlada (ex.:
`BACKUP_DRIVE_FOLDER_ID` inválido) e confirme o recebimento do e-mail; reverta.

> **Cobre “o backup rodou e falhou”.** Não cobre “o backup nem chegou a rodar”
> (backend caído). Para isso, adicione um monitor da idade do último backup:
> consulte `GET /admin/backup/status` (`ultimo_resultado`) e alerte se passar de
> 25h — ver skills `arquiteto-notificacoes` /
> `arquiteto-monitoramento-observabilidade`. Uma camada extra opcional, que
> confere direto na pasta do Drive, está no Apêndice A.

---

## 5. Restauração (disaster recovery — nunca automática)

Restaurar é destrutivo e manual. Resumo (detalhe em `RUNBOOK_BACKUP.md`):

1. Baixar do Drive o par `ejc_backup_<data>…_db.enc` + `…_uploads.enc`.
2. **Decifrar** com a `BACKUP_ENCRYPTION_KEY` (a mesma usada no backup).
3. `pg_restore` do dump no banco e extrair o `tar.gz` dos uploads em
   `/app/uploads`.
4. Se o dump for de schema anterior, rodar `alembic upgrade head`.

Teste a restauração periodicamente num banco descartável — backup que nunca foi
restaurado não é backup, é esperança.

---

## Apêndice A — Prompt da rotina de verificação diária (opcional, camada extra)

Camada **opcional**, além do alerta nativo da seção 4. Confere direto na pasta
do Drive se o backup do dia chegou. **Exige o conector Google Drive anexado à
rotina** — crie-a pela **UI de rotinas do claude.ai** (que permite anexar o
conector); rotinas criadas por outros meios podem rodar **sem** o conector e só
reportarão “Drive indisponível”. Ela **não** faz o backup — apenas verifica e
escala falhas.

```
Você é o operador de backup do EJC. Tarefa diária: confirmar que existe um
backup ÍNTEGRO de HOJE no Google Drive, cobrindo o sistema (banco) e os
documentos gerados (UPLOAD_DIR). Não reimplemente backup — verifique e, só se
faltar, dispare e reporte.

1. Leia GET /admin/backup/status (autenticado admin/superadmin). Se algum
   booleano de configuracao for false → é FALHA DE CONFIGURAÇÃO: não dispare,
   reporte qual booleano está false e escale.
2. Confirme na pasta do Drive (BACKUP_DRIVE_FOLDER_ID) os arquivos
   "ejc_backup_" de hoje: um de banco (_db.enc) e um de uploads (_uploads.enc),
   ambos com tamanho > 0. O status deve indicar dump verificado.
3. Se NÃO houver backup íntegro de hoje e a config estiver completa e não houver
   execução em andamento: dispare POST /admin/backup/executar (202) e faça
   polling do status até em_execucao=false; reconfirme os arquivos no Drive.
4. Verifique a retenção (BACKUP_RETENCAO_DIAS): antigos além da janela removidos,
   recentes preservados. Tamanho muito abaixo dos dias anteriores é suspeito —
   registre observação.
5. Reporte SEMPRE (Status OK|FALHA|CONFIG_INCOMPLETA|EM_EXECUCAO; data/hora UTC;
   banco presente/íntegro/tamanho; uploads presente/tamanho; arquivos no Drive
   sim/não; retenção; ações tomadas). Em falha, escale ao canal de alerta.

REGRAS DURAS: nunca imprima segredos (BACKUP_ENCRYPTION_KEY, senha do banco,
credenciais Google, .env) — só booleanos "*_configurada" e nomes/tamanhos/datas.
Nunca desligue a criptografia. Nunca apague na pasta do Drive nada sem o prefixo
"ejc_backup_". Nunca restaure banco/uploads nesta rotina (é manual). Se a falha
exigir mudança de infra/config, pare e escale para um humano.
```

## Apêndice B — Variáveis (`.env` / `.env.example`)

`BACKUP_ENABLED`, `BACKUP_ENCRYPTION_KEY`, `BACKUP_DRIVE_FOLDER_ID`,
`BACKUP_HORA_UTC`, `BACKUP_RETENCAO_DIAS`, `BACKUP_UPLOADS_MAX_MB`,
`BACKUP_DB_MAX_MB`, `BACKUP_PG_DUMP_TIMEOUT`, `UPLOAD_DIR`. Segredos nunca
aparecem em log/relatório — só os booleanos `*_configurada`.
