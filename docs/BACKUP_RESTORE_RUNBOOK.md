# EJC — Runbook de Backup e Restauração

## Objetivo

Estabelecer um procedimento verificável para backup, retenção, recuperação e evidência de continuidade do EJC.

## Princípios obrigatórios

1. Banco e uploads devem ser cifrados antes de sair da VPS.
2. A chave `BACKUP_ENCRYPTION_KEY` não pode existir apenas na VPS.
3. Logs, relatórios e tickets não podem conter a chave ou a senha do banco.
4. Backup sem teste de restauração não constitui prova suficiente de continuidade.
5. Alterações destrutivas exigem backup recente, restauração comprovada e rollback definido.

## Backup de produção

O serviço `backend/app/services/backup_service.py` executa:

1. `pg_dump -Fc` do PostgreSQL;
2. empacotamento dos uploads em `tar.gz`;
3. cifragem Fernet;
4. envio para a pasta configurada no Google Drive;
5. rotação limitada aos arquivos com prefixo `ejc_backup_`;
6. persistência de estado e alerta em caso de falha.

A ativação idempotente é feita por:

```bash
cd /opt/ejc
bash scripts/backup/ativar_backup.sh
```

O script não deve regenerar uma chave válida. A chave precisa ser copiada para um cofre externo seguro antes de qualquer incidente.

## Diagnóstico

Use:

```bash
bash scripts/backup/diagnostico_backup.sh
```

E confira o endpoint administrativo de status do backup. Um resultado parcial não é equivalente a sucesso integral quando banco ou uploads estiverem ausentes.

## Prova automática de restauração

O workflow `Continuity and UI Gates` executa `scripts/backup/restore_drill.py` em PostgreSQL efêmero.

A prova realiza:

1. criação de marcador temporário de integridade;
2. dump em formato custom;
3. cifragem com o mecanismo do backup do EJC;
4. exclusão do dump claro;
5. decifragem controlada;
6. criação de banco vazio com nome aleatório;
7. `pg_restore --exit-on-error`;
8. comparação da versão Alembic;
9. comparação da quantidade de tabelas públicas;
10. validação do marcador;
11. exclusão do marcador da origem e remoção do banco temporário.

O relatório `restore-drill-report.json` é anexado ao workflow e não contém credenciais.

## Execução manual do restore drill

Somente em banco de teste ou ambiente descartável:

```bash
cd /opt/ejc/backend
RESTORE_DRILL_ALLOW=1 \
DATABASE_URL_SYNC='postgresql://usuario:senha@host:5432/banco_teste' \
PYTHONPATH=. \
python ../scripts/backup/restore_drill.py
```

O flag explícito impede execução acidental.

## Prova com artefato real externo

A certificação operacional exige, periodicamente:

1. selecionar um par recente de arquivos `*_db.dump.enc` e `*_uploads.tar.gz.enc` no armazenamento externo;
2. baixar os artefatos para ambiente isolado;
3. conferir hash, tamanho e origem;
4. decifrar usando a cópia externa da chave;
5. restaurar o banco em instância vazia;
6. extrair uploads em diretório temporário;
7. executar smoke funcional e consultas de integridade;
8. registrar data, duração, responsável, RPO observado, RTO observado e resultado;
9. destruir de forma segura os artefatos claros temporários.

Essa prova depende das credenciais reais do armazenamento e não pode ser simulada pelo CI.

## RPO e RTO

Até aprovação administrativa formal, use como alvo técnico provisório:

- RPO técnico: até 24 horas, considerando backup diário;
- RTO técnico: medir em cada restore drill e registrar, sem prometer valor não comprovado.

O acceptance gate só deve ser marcado como concluído após os valores serem formalmente aprovados e comprovados com artefato real.

## Falhas e resposta

Quando o backup falhar:

1. preservar logs e estado;
2. não apagar o último backup íntegro;
3. verificar credencial dedicada, pasta, quota, rede, `pg_dump` e chave;
4. repetir a prova integral somente após corrigir a causa;
5. registrar o incidente e a recuperação;
6. avaliar se houve violação do RPO.

## Critérios de aceite

- artefatos cifrados existem no destino externo;
- banco e uploads estão presentes;
- chave externa recuperável;
- restore drill automatizado verde;
- restauração real periódica comprovada;
- RPO e RTO medidos;
- rollback de deploy documentado e testado.
