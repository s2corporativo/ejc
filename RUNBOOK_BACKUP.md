# RUNBOOK — Backup e Continuidade (EJC)

## Estado arquitetural

O EJC possui um **único fluxo operacional permitido** para novos backups:

`caller → backup_execution_service → backup_lock → backup_service → destino cifrado`

Banco, uploads e GED contêm dados jurídicos e pessoais. Artefato de backup em
claro **não é permitido** em retenção local, cron, diretório persistente ou
destino offsite.

A Issue #1030 consolida essa arquitetura e elimina as rotas históricas
concorrentes.

## Componentes

- `scripts/backup.sh` — wrapper operacional. Não implementa `pg_dump` próprio;
  chama a fachada Python exclusiva, que adquire o mutex compartilhado antes do
  motor canônico.
- `backend/app/services/backup_execution_service.py` — fachada única de
  execução administrativa, agendada e operacional.
- `backend/app/services/backup_lock.py` — `fcntl.flock` cross-process sobre o
  volume `BACKUP_DIR`/`backups_data`.
- `backend/app/services/backup_service.py` — motor de dump, cifragem, envio,
  estado e auditoria.
- `scripts/backup/backup_diario.sh` — **shim de compatibilidade**. Não grava
  dump/tar em claro; apenas delega a `scripts/backup.sh`. Remova crons antigos
  após confirmar o scheduler canônico.
- `scripts/backup/restore_drill.py` — prova de recuperação em banco temporário,
  sem substituir produção.
- `scripts/backup/restaurar_backup.sh` — restore legado em claro **desativado**.

## Regra de agendamento

O scheduler da aplicação deve possuir **um único job de backup canônico**. Não
instale um segundo cron como arquitetura normal.

Se existir cron histórico chamando `scripts/backup/backup_diario.sh`, ele pode
permanecer temporariamente durante a migração porque o script agora é apenas um
shim para o mesmo motor/mutex. Depois de validar o job canônico do scheduler,
remova o cron legado para reduzir ruído operacional.

## Exclusão mútua

Todas as entradas produtivas devem usar `backup_execution_service`.

O lock é não bloqueante e compartilhado por processos/containers porque reside
no volume `BACKUP_DIR` (`/app/backups` no compose). Se já houver backup em
andamento, nova tentativa deve resultar em `status=em_execucao` e **não** iniciar
novo dump, tar, cifragem ou upload.

Falha ao abrir/validar o mutex é fail-closed (`erro_lock`). Redis e conexão longa
de banco não são dependências da trava de continuidade.

## Criptografia e destino

`BACKUP_ENCRYPTION_KEY` deve existir fora do código e do repositório. Nunca
publique, copie para documentação ou registre a chave em logs.

O motor suporta destino externo configurado pelo EJC. A credencial de backup
deve ser segregada da credencial de leitura do RAG.

### Estado transitório importante

No motor atual, `local_ok` significa que os artefatos cifrados foram gerados
durante o ciclo. Enquanto os `.enc` ainda forem criados dentro de
`TemporaryDirectory`, isso **não prova retenção local recuperável após o
retorno**.

Consequentemente, o gate de pré-deploy exige:

- artefato cifrado do banco gerado;
- artefato cifrado de uploads gerado;
- `offsite_ok=true`.

Essa exigência pode ser relaxada somente quando a Issue #1030 persistir e
validar uma cópia cifrada real em `BACKUP_DIR`, com retenção e restore
homologados.

## Validação de restore sem tocar produção

Use o restore drill controlado:

```bash
cd /opt/ejc
RESTORE_DRILL_ALLOW=1 python scripts/backup/restore_drill.py
```

O drill deve usar banco temporário aleatório, validar dump, cifragem/decifragem
e restauração e produzir relatório sem substituir o banco produtivo.

Nunca interprete `backup concluído` como prova suficiente: a continuidade só é
válida quando um restore drill recente também passa.

## Restore produtivo

O antigo `scripts/backup/restaurar_backup.sh` foi desativado porque aceitava
`*.dump`/`*.tar.gz` em claro e executava `pg_restore --clean` contra o banco
alvo.

Até existir ferramenta de restore cifrado homologada, a restauração produtiva é
uma **operação controlada** e não deve ser improvisada. Requisitos mínimos:

1. janela de manutenção aprovada;
2. identificação exata do artefato cifrado e sua origem;
3. validação de integridade antes do cutover;
4. backup pré-restauração recuperável;
5. restauração em ambiente temporário quando possível;
6. plano de rollback;
7. registro de auditoria;
8. validação pós-restore de banco, uploads, migrations, health/readiness e
   permissões.

Não decifre artefatos para diretórios persistentes compartilhados.

## Operação diária

Verifique pelo módulo administrativo/telemetria:

- último status;
- origem da execução;
- `mutex_status`;
- `offsite_ok`;
- duração;
- próximo agendamento;
- restore drill mais recente.

Logs não devem conter chave de criptografia, senha do banco, token, path de
segredo, conteúdo de documentos, CPF/CNPJ ou dados de cliente.

## Checklist de continuidade

- [ ] `BACKUP_DIR` está montado no volume esperado e não é group/world-writable.
- [ ] `BACKUP_ENCRYPTION_KEY` configurada fora do repositório.
- [ ] Credencial offsite dedicada configurada.
- [ ] Apenas um job canônico de backup está agendado.
- [ ] Nenhum cron executa `pg_dump`/`tar` em claro.
- [ ] Endpoint administrativo usa `backup_execution_service`.
- [ ] Pré-deploy usa `backup_execution_service`.
- [ ] Segundo processo é recusado pelo mesmo `flock`.
- [ ] Falha/crash libera o lock pelo kernel.
- [ ] Backup cifrado e destino offsite confirmados.
- [ ] Restore drill recente aprovado.
- [ ] Restore produtivo cifrado permanece bloqueado até homologação específica.
