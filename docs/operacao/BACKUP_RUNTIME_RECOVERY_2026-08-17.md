# Correção de continuidade — 17/08/2026

## Escopo

Correção operacional do backup pré-deploy após incidente em que o backend entrou em restart loop durante a aplicação da migration 145.

## Causa confirmada

1. `scripts/backup.sh` considerava a presença do nome do container em `docker ps` suficiente para usar `docker exec`; um container em `restarting` também aparecia nessa listagem e recusava `exec`.
2. O runtime instalava `rclone` pelo pacote do Debian. A versão observada em produção não conseguia mais autenticar no remote configurado, enquanto a mesma configuração funcionou com rclone 1.75.0.
3. O caller `scripts/deploy_vps_safe.sh` ainda continha uma via permissiva que registrava `offsite_ok=false` como aviso e poderia prosseguir. O fluxo foi endurecido para bloquear antes de qualquer mutação.

## Arquivos alterados

- `backend/Dockerfile` — rclone 1.75.0 proveniente da imagem oficial e fixado no runtime.
- `scripts/backup.sh` — seleção por `State.Status`, com fallback efêmero fora do estado `running`.
- `scripts/deploy_vps_safe.sh` — confirmação explícita `offsite_ok=true`; `offsite_ok=false` ou ausente bloqueia o deploy.
- `scripts/post_deploy_check.sh` — valida backend, banco, frontend, worker e Redis em execução, além de `/api/health` e `/api/health/ready` local e público.
- `scripts/tests/test_backup_wrapper.sh` — regressões do restart loop, caller fail-closed, JSON compacto e pin exato do rclone.
- este relatório operacional.

## Evidências verificáveis

- deploy inicial do design: run `32047072436` bloqueado antes de mutação por falha do backup obrigatório;
- diagnóstico no runner `ejc-vps`: backend em restart loop por drift parcial da migration 145; banco, Redis, worker e frontend permaneceram operacionais;
- backup de recuperação: run `32048715351`, `status=sucesso`, banco e uploads cifrados e transferência ao remote concluída (`offsite_ok=true`) usando rclone 1.75.0;
- recuperação controlada da migration 145: run `32048913939`, com segundo backup cifrado e transferência offsite concluída imediatamente antes da mutação, schema final na revisão 145 e `/api/health` + `/api/health/ready` aprovados;
- build real do backend com o Dockerfile corrigido: run `32049515527`, imagem construída e `rclone v1.75.0` verificado dentro da imagem;
- PR #1191: Release Gate, validação de backup e CI completo executados sobre a correção.

`offsite_ok=true` é evidência de **transferência concluída para o remote**, não de política de retenção do provedor nem de restauração bem-sucedida. O ciclo de recuperação deste incidente não executou restauração integral do artefato enviado. Retenção e restauração permanecem controles externos separados e devem ser comprovados em exercício periódico próprio.

As evidências acima registram IDs e estados, sem copiar credenciais, conteúdo de clientes, parâmetros SQL ou dados pessoais para o repositório.

## Comandos e fluxos validados

- `bash scripts/backup.sh` com backend `running` e com backend `restarting` (fallback efêmero);
- `docker compose run --rm --no-deps -T backend ...` para execução isolada;
- `python -m alembic upgrade head` na recuperação controlada da revisão 145;
- `curl -fsS http://127.0.0.1:8000/api/health` e `/api/health/ready`;
- build real de `backend/Dockerfile` e `rclone version` dentro da imagem;
- `bash scripts/tests/test_backup_wrapper.sh`, `bash scripts/tests/test_deploy_rollback.sh` e `bash -n` dos scripts de backup/deploy.

## Testes e resultados esperados

- backend `running`: wrapper usa `docker exec`;
- backend `restarting`: wrapper não tenta `exec` e usa container efêmero;
- falha do motor: wrapper retorna código diferente de zero;
- `offsite_ok=false` mesmo com exit 0 do wrapper: caller de deploy retorna não zero antes de `docker compose build/up`;
- JSON compacto `"offsite_ok":false`: produz o mesmo bloqueio fail-closed;
- rclone no bloco `apt-get install`: teste falha;
- ausência ou alteração da linha de pin `rclone v1.75.0`: teste falha;
- backup promovível: exige banco cifrado, uploads cifrados e transferência offsite confirmada pelo motor;
- pós-deploy real: exige backend, banco, frontend, worker e Redis em execução, além de `/api/health` e `/api/health/ready` local e público.

### Cobertura específica do rollback

`test_deploy_rollback.sh` substitui deliberadamente `post_deploy_check.sh` por um stub para isolar e provar a lógica transacional de captura/restauração das imagens e a execução do rollback. Esse teste **não** é a prova funcional de worker, Redis ou readiness. A prova funcional desses requisitos pertence ao `scripts/post_deploy_check.sh`, agora endurecido para checá-los de forma real durante o deploy. No incidente, `/api/health/ready`, worker, banco e Redis também foram verificados diretamente no runner de produção antes da retomada.

## Segurança

- nenhuma credencial foi versionada ou alterada;
- o backup continua exigindo cifragem e confirmação de transferência offsite antes do deploy;
- não há alteração de RBAC, autenticação, dados de clientes ou contratos de API;
- o deploy é fail-closed quando não existe confirmação de envio fora da VPS;
- a retenção do remote rclone é executada pelo próprio ciclo, limitada ao prefixo
  `ejc_backup_` e a `BACKUP_RETENTION_DAYS`; o teste de restauração permanece um
  controle separado de continuidade.

## Riscos residuais e limitações

- backend e worker ainda executam como root no container. A migração para usuário dedicado é transversal (volumes, migrations, uploads, caches, rclone e Celery) e foi isolada na Issue #1192 para implantação própria, sem misturá-la a este hotfix;
- a credencial service-account dedicada encontrada no mount operacional não está utilizável; o destino offsite funcional neste incidente é o remote rclone existente. Corrigir a service account deve ocorrer separadamente, sem copiar segredo para Git;
- o pin do rclone reduz variação de runtime, mas futuras atualizações precisam repetir build e prova de transferência offsite;
- este hotfix prova criação, cifragem, envio offsite e rotação segura do backup. **Não prova restauração integral**; esse controle exige exercício de restore em ambiente isolado.

## Critérios de validação da recuperação

A recuperação operacional só é considerada válida quando: Alembic está na revisão esperada; backend não está em restart loop; `/api/health` e `/api/health/ready` respondem; worker, banco e Redis permanecem operacionais; e o backup prévio contém artefatos cifrados de banco e uploads com transferência offsite confirmada (`offsite_ok=true`). A validação de continuidade completa ainda requer, em ciclo separado, comprovação da política de retenção e teste de restauração.

## Rollback

O patch de runtime não altera schema nem dados. Se o novo runtime falhar, o rollback é a reversão do PR e restauração das imagens anteriores pelo fluxo transacional de `deploy_vps_safe.sh`. Após a restauração, `scripts/post_deploy_check.sh` deve aprovar containers essenciais, `/api/health`, `/api/health/ready`, frontend e endpoint público antes de considerar o rollback operacionalmente válido. Não executar rollback de schema destrutivo automaticamente.

## Decisões humanas pendentes

- priorizar e agendar a Issue #1192 (runtime não-root) em janela própria;
- decidir a correção ou substituição da credencial service-account dedicada do backup;
- definir periodicidade e executar teste real de restauração offsite em ambiente isolado.
