# P1/P2 — release, restore, observabilidade e hostnames

## P1

### Playwright obrigatório

O Woodpecker executa um gate Playwright sem segredos sobre o bundle real do
frontend. Ele valida:

- renderização da tela de login;
- responsividade desktop/mobile sem overflow;
- redirect fail-closed de rotas protegidas para `/login`;
- feedback pós-troca de senha;
- ausência de exceções JavaScript.

O E2E autenticado existente (`frontend/tests/e2e-homologacao.mjs`) permanece
para staging/produção controlada e **não** recebe credenciais versionadas.

### Evidência de release

`scripts/release_evidence.py` consolida em JSON sanitizado:

- SHA publicado;
- liveness/readiness;
- containers;
- Alembic;
- Nginx;
- resultado do serviço de deploy;
- saúde do backup;
- último restore drill off-site;
- espaço livre em disco.

Saída padrão: `/var/lib/ejc-release-evidence/`, permissões 0700/0600.

### Restore automático

O mecanismo canônico continua sendo
`ejc-restore-drill-offsite.timer`. Ele restaura o último backup cifrado em
banco temporário, compara Alembic/tabelas e remove o banco de teste.

Não criar segundo scheduler para a mesma tarefa.

## P2

### Observabilidade

`ejc-observability-snapshot.timer` roda a mesma evidência sanitizada a cada
15 minutos. Falha do probe deixa o oneshot em estado failed no systemd e mantém
`latest.json` para diagnóstico, sem reinício automático adicional.

### Separação Gitea/Woodpecker

Destino:

- `gitea.depaulateixeira.adv.br` → 127.0.0.1:8300
- `woodpecker.depaulateixeira.adv.br` → 127.0.0.1:8100

O arquivo `infra/nginx/ci-split-hostnames.conf.example` é deliberadamente
não habilitado enquanto DNS/certificados não existirem.

Ordem segura:

1. criar DNS dos dois hosts;
2. emitir certificados;
3. habilitar os novos vhosts e executar `nginx -t`;
4. validar Gitea e Woodpecker separadamente;
5. atualizar `WOODPECKER_HOST` e callbacks/webhooks;
6. confirmar pipeline push/main verde;
7. manter `ci.depaulateixeira.adv.br` como compatibilidade;
8. só depois converter o host legado em redirect.

Rollback: remover os novos vhosts e recarregar Nginx; o host `ci` permanece
intocado durante toda a migração.
