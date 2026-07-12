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

## Offsite (fortemente recomendado)

Defina `RCLONE_REMOTE` (ex.: `gdrive:EJC-Backups`) no ambiente do cron. Requer
`rclone` instalado e configurado (`rclone config`). Falha de upload **não**
derruba o backup local — apenas registra aviso. Sem offsite, um incidente na
VPS (disco, ransomware) leva os backups junto: trate como passo obrigatório
antes do go-live definitivo.

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
