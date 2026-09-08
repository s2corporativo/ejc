# RUNBOOK — Backup e Continuidade (EJC)

## Estado arquitetural

O EJC possui um **único fluxo operacional permitido** para novos backups:

`caller → backup_execution_service → backup_lock → backup_service → retenção local cifrada → destino offsite`

Banco, uploads e GED contêm dados jurídicos e pessoais. Artefato de backup em
claro **não é permitido** em retenção local, cron, diretório persistente ou
destino offsite.

A Issue #1030 consolidou a exclusão mútua dessa arquitetura. A remediação
INF-04/#1572 acrescenta a cópia local cifrada recuperável; ela não autoriza
ressuscitar os scripts históricos de dump em claro.

## Componentes

- `scripts/backup.sh` — wrapper operacional. Não implementa `pg_dump` próprio;
  chama a fachada Python exclusiva, que adquire o mutex compartilhado antes do
  motor canônico.
- `backend/app/services/backup_execution_service.py` — fachada única de
  execução administrativa, agendada e operacional.
- `backend/app/services/backup_lock.py` — `fcntl.flock` cross-process sobre o
  volume `BACKUP_DIR`/`backups_data`.
- `backend/app/services/backup_service.py` — motor de dump, cifragem, retenção
  local, envio, estado e auditoria.
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

## Criptografia e retenção local

`BACKUP_ENCRYPTION_KEY` deve existir fora do código e do repositório. Nunca
publique, copie para documentação ou registre a chave em logs.

O dump e o tar são criados em área temporária apenas pelo tempo necessário para
cifragem. Eles são removidos em claro antes da publicação da cópia persistente.
Somente arquivos canônicos `ejc_backup_*.enc` podem permanecer em `BACKUP_DIR`.

No contrato INF-04:

- `local_ok=true` significa que o conjunto cifrado foi efetivamente publicado
  no `BACKUP_DIR` e fsyncado;
- cada artefato promovível contém `local_persistido=true`;
- arquivos finais devem permanecer `0600` e o diretório de continuidade não
  pode ser gravável por grupo/outros nem ser symlink inseguro;
- `BACKUP_RETENTION_DAYS` precisa ser inteiro positivo; configuração inválida
  torna o ciclo de backup inválido, em vez de desativar silenciosamente a
  rotação;
- antes de escrever um novo conjunto, a rotação pode remover conjuntos
  expirados, mas preserva o conjunto canônico mais recente conhecido; depois
  da publicação do novo conjunto, uma segunda rotação pode remover o conjunto
  antigo se já estiver expirado. Isso evita o deadlock de disco cheio sem
  destruir a última cópia conhecida antes de a nova existir.

Dumps históricos em claro encontrados em storages legados **não** fazem parte
da rotação automática. Devem permanecer contidos por permissão e só podem ser
saneados depois de uma cópia cifrada nova + restore drill comprovado.

## Destino offsite

O motor suporta destino externo configurado pelo EJC. A credencial de backup
deve ser segregada da credencial de leitura do RAG.

A política normal do gate de pré-deploy é:

- ciclo do motor aprovado;
- artefato cifrado do banco persistido localmente;
- artefato cifrado de uploads persistido localmente;
- `local_ok=true` e `local_persistido=true` para o conjunto;
- `offsite_ok=true` **quando** `BACKUP_OFFSITE_OBRIGATORIO=true`.

Com `BACKUP_OFFSITE_OBRIGATORIO=false`, falha do destino externo gera estado
parcial/alerta, mas a cópia local cifrada persistente pode satisfazer o gate.
Isso não transforma offsite em dispensável: continuidade adequada exige que a
falha seja corrigida e monitorada.

### Compatibilidade do primeiro deploy da INF-04

Há um único caso de transição: o wrapper novo é sincronizado para o host antes
de o backend novo ser recriado. Nesse instante ele pode executar contra a
imagem anterior, na qual `local_ok` ainda significava apenas geração temporária
e os artefatos não possuíam `local_persistido`.

Para não criar um deploy impossível, o wrapper detecta a **ausência** desse
marcador e usa exclusivamente o contrato legado mais estrito:

- par cifrado banco + uploads gerado;
- ciclo `ok=true`;
- `offsite_ok=true`, independentemente de `BACKUP_OFFSITE_OBRIGATORIO`.

Essa compatibilidade não relaxa segurança e deixa de ser usada automaticamente
assim que o backend novo passa a emitir `local_persistido`.

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

Após promover a INF-04, o primeiro fechamento operacional exige confirmar no
host pelo menos:

1. novo conjunto `ejc_backup_<timestamp>_*.enc` em `BACKUP_DIR`;
2. arquivos `0600` e diretório com permissões seguras;
3. `local_ok=true` e marcadores `local_persistido=true`;
4. offsite conforme a política vigente;
5. restore drill aprovado em banco descartável.

Somente depois disso pode ser aberto saneamento destrutivo separado para dumps
históricos em claro.

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
- `local_ok`;
- `offsite_ok`;
- duração;
- próximo agendamento;
- restore drill mais recente.

Logs não devem conter chave de criptografia, senha do banco, token, path de
segredo, conteúdo de documentos, CPF/CNPJ ou dados de cliente.

## Checklist de continuidade

- [ ] `BACKUP_DIR` está montado no volume esperado e não é group/world-writable.
- [ ] `BACKUP_ENCRYPTION_KEY` configurada fora do repositório.
- [ ] `BACKUP_RETENTION_DAYS >= 1`.
- [ ] Credencial offsite dedicada configurada quando o destino a exigir.
- [ ] Apenas um job canônico de backup está agendado.
- [ ] Nenhum cron executa `pg_dump`/`tar` em claro.
- [ ] Endpoint administrativo usa `backup_execution_service`.
- [ ] Pré-deploy usa `backup_execution_service`.
- [ ] Segundo processo é recusado pelo mesmo `flock`.
- [ ] Falha/crash libera o lock pelo kernel.
- [ ] Par cifrado novo persiste localmente em `0600`.
- [ ] `local_ok=true` e `local_persistido=true` foram comprovados no runtime novo.
- [ ] Destino offsite confirmado conforme a política vigente.
- [ ] Restore drill recente aprovado.
- [ ] Dumps históricos em claro não foram removidos antes do restore drill.
- [ ] Restore produtivo cifrado permanece bloqueado até homologação específica.
