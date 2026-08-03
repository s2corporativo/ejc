# RUNBOOK — Backup e Recuperação (EJC)

Estratégia de backup automatizado do EJC: banco PostgreSQL + arquivos de
upload/GED, com rotação, verificação de integridade e cópia offsite opcional.

## Scripts

- `scripts/backup/backup_diario.sh` — rotina diária (cron). `pg_dump -Fc` +
  `tar` dos uploads, verificação por `pg_restore --list`, rotação por contagem
  (7 diários + 4 semanais, configurável), offsite via rclone opcional.
- `scripts/backup/restaurar_backup.sh` — restauração guiada e destrutiva, com
  confirmação explícita e backup de segurança do estado atual antes.

Ambos detectam automaticamente se rodam com Docker (`ejc_db`/`ejc_backend`) ou
direto no host (`EJC_BACKUP_MODE=local`, com `PGHOST/PGUSER/PGPASSWORD/...`).

## Agendamento na VPS (cron)

```cron
# Backup diário às 02:00 (log dedicado). Ajuste o caminho do repo/deploy.
0 2 * * * cd /opt/ejc && bash scripts/backup/backup_diario.sh >> /var/log/ejc_backup.log 2>&1
```

Verifique o log no dia seguinte: linha final `Backup concluído com sucesso.`
(exit 0). Qualquer `FALHA(S)` sai com código != 0 — capture no monitoramento.

## Retenção

`KEEP_DAILY=7` diários + `KEEP_WEEKLY=4` semanais (cópia no domingo,
`WEEKLY_DOW=7`). A rotação é por **contagem** (`ls -t`), imune a relógio errado.
Destino local: `BACKUP_BASE_DIR` (default `/opt/ejc/backups/{diario,semanal}`).

## Offsite — OneDrive (fortemente recomendado)

**Destino oficial: OneDrive**, por decisão do titular em 2026-08-03. O Google
Drive continua funcionando e testado; é fallback, não o caminho padrão.

Defina `RCLONE_REMOTE` (ex.: `onedrive:EJC-Backups`) no ambiente do cron.
Requer `rclone` instalado e configurado (`rclone config`). Falha de upload
**não** derruba o backup local — apenas registra aviso. Sem offsite, um
incidente na VPS (disco, ransomware) leva os backups junto: trate como passo
obrigatório antes do go-live definitivo.

### Configurar o remote OneDrive na VPS

`rclone config` é **interativo e exige um navegador** para o consentimento
OAuth da Microsoft. Numa VPS sem interface, use a autorização remota: rode
`rclone authorize "onedrive"` numa máquina COM navegador, e cole o token no
prompt do `rclone config` da VPS (opção "N" para novo remote, tipo `onedrive`,
e responda **não** a "Use auto config?").

Confira antes de confiar:

```bash
rclone lsd onedrive:                      # lista pastas — prova que o remote responde
rclone mkdir onedrive:EJC-Backups         # cria a pasta raiz do backup
rclone touch onedrive:EJC-Backups/.ejc-ok # prova de ESCRITA (o que o backup precisa)
rclone delete onedrive:EJC-Backups/.ejc-ok
```

Use uma conta/aplicação **dedicada ao backup**, não a conta pessoal do titular:
o token do rclone dá acesso de escrita a tudo que a conta enxerga.

### Backup da aplicação (`backup_service.py`)

O backup embutido no backend é independente do cron acima e tem a própria
configuração. Para OneDrive:

```env
BACKUP_DESTINO=rclone                       # padrão desde 2026-08-03
BACKUP_RCLONE_REMOTE=onedrive:EJC-Backups
```

Os artefatos cifrados são gravados em `<remote>/AAAA/MM/` — o rclone cria as
pastas sozinho. Com backup diário e dois artefatos por ciclo, a raiz plana
passava de setecentos arquivos no primeiro ano; a hierarquia existe para quem
precisa achar o backup de uma data específica no meio de um incidente.

> **Atenção na virada.** Com `BACKUP_DESTINO=rclone` e `BACKUP_RCLONE_REMOTE`
> vazio, o envio offsite falha. Com `BACKUP_OFFSITE_OBRIGATORIO=false`
> (default) isso vira status `parcial` com aviso grave: a prova local cifrada
> continua sendo feita e o deploy não trava, mas **o backup deixa de sair do
> VPS**. Configure o remote antes de subir, ou mantenha `BACKUP_DESTINO=gdrive`
> até concluir.

### Retenção no OneDrive

A rotação automática existe **apenas** no destino Google Drive
(`_rotacionar_sync`). No destino rclone nada é apagado pelo ciclo — os
artefatos acumulam indefinidamente. Com as pastas `AAAA/MM`, a limpeza manual
é apagar o diretório de um mês inteiro:

```bash
rclone lsd onedrive:EJC-Backups/2026      # confere o que existe antes de apagar
rclone purge onedrive:EJC-Backups/2026/01 # remove o mês inteiro
```

Confira com `lsd` antes de cada `purge`: `purge` remove o diretório e todo o
conteúdo, sem confirmação.

## Restauração (disaster recovery)

```bash
cd /opt/ejc
# Lista os backups disponíveis
ls -lt /opt/ejc/backups/diario/

# Restaura banco + uploads (pede confirmação e oferece backup de segurança)
bash scripts/backup/restaurar_backup.sh \
  /opt/ejc/backups/diario/ejc_db_AAAAMMDD_HHMMSS.dump \
  /opt/ejc/backups/diario/ejc_uploads_AAAAMMDD_HHMMSS.tar.gz
```

Se o dump for de um schema anterior ao código atual, rode `alembic upgrade head`
após a restauração. Teste a recuperação periodicamente (restaurar num banco
descartável valida que os backups prestam) — validado neste repo restaurando
para um banco temporário.

## Checklist de primeiro dia

- [ ] `scripts/backup/backup_diario.sh` roda limpo na VPS (exit 0).
- [ ] Linha do cron instalada (`crontab -e`) e `/var/log/ejc_backup.log` criado.
- [ ] `RCLONE_REMOTE` configurado e primeiro upload offsite confirmado.
- [ ] Um teste de restauração em banco descartável concluído.
