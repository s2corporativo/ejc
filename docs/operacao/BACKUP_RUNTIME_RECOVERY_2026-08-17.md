# Correção de continuidade — 17/08/2026

## Escopo

Correção operacional do backup pré-deploy após incidente em que o backend entrou em restart loop durante a aplicação da migration 145.

## Causa confirmada

1. `scripts/backup.sh` considerava a presença do nome do container em `docker ps` suficiente para usar `docker exec`; um container em `restarting` também aparecia nessa listagem e recusava `exec`.
2. O runtime instalava `rclone` pelo pacote do Debian. A versão observada em produção não conseguia mais autenticar no remote configurado, enquanto a configuração existente funcionou com rclone 1.75.0.

## Correção

- o wrapper de backup consulta `State.Status` e usa container efêmero quando o backend não está em estado `running`;
- o backend passa a copiar `rclone` 1.75.0 da imagem oficial, com versão fixada;
- teste de regressão cobre backend em restart loop e garante que o runtime não volte ao pacote apt defasado.

## Segurança

- nenhuma credencial foi versionada ou alterada;
- o backup continua exigindo cifragem e confirmação offsite;
- não há alteração de RBAC, autenticação, dados de clientes ou contratos de API;
- rollback do patch é a reversão do PR, sem migration.
