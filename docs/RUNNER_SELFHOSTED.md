# Runner self-hosted — CI do EJC na VPS

Mantém os checks de Pull Request do GitHub, mas executa a computação no VPS do
escritório. Os workflows continuam definidos no repositório e usam os labels
`self-hosted` e `ejc-vps`.

> O repositório é privado. Ainda assim, qualquer workflow executado no runner
> deve ser tratado como código com acesso ao host. Preserve branch protection,
> revisão de PR e mínimo privilégio.

## Instalação ou recuperação controlada

### 1. Obter token temporário

No GitHub: **Settings → Actions → Runners → New self-hosted runner → Linux**.
Copie o token de registro e use-o imediatamente. Não publique o token em issue,
commit, chat, documentação ou log.

### 2. Executar o instalador na VPS

```bash
cd /caminho/do/ejc
git pull
sudo RUNNER_TOKEN='<TOKEN_TEMPORARIO>' scripts/setup-selfhosted-runner.sh
```

O instalador é idempotente e executa, nesta ordem:

1. instala dependências nativas, Docker, Node e `rsync`;
2. cria ou atualiza o usuário `ghrunner`;
3. para e desinstala o serviço anterior;
4. remove o registro anterior ou limpa apenas credenciais locais inconsistentes;
5. registra novamente o runner com o mesmo nome;
6. instala e inicia o serviço systemd;
7. aguarda o serviço ficar realmente ativo;
8. imprime diagnóstico local se o serviço não iniciar.

O script não deve afirmar sucesso apenas porque `svc.sh start` foi chamado.

### 3. Confirmar saúde

No GitHub, o runner `ejc-vps` deve aparecer **online** e **ocioso**.

Na VPS:

```bash
cd /opt/actions-runner
sudo ./svc.sh status
sudo systemctl list-units 'actions.runner.*' --all
sudo journalctl -u 'actions.runner.*' -n 200 --no-pager
```

Valide também os recursos necessários:

```bash
free -h
df -h
docker info >/dev/null && echo 'Docker OK'
command -v node npm rsync psql
```

## Recuperação rápida de serviço parado

Quando o runner ainda estiver registrado e apenas o serviço estiver parado:

```bash
cd /opt/actions-runner
sudo ./svc.sh stop || true
sudo ./svc.sh start
sudo ./svc.sh status
```

Se continuar offline, não apague arquivos nem tokens manualmente. Obtenha um
novo token temporário e reexecute o instalador idempotente.

## Diagnóstico de jobs aguardando runner

Se os checks permanecerem em **queued** ou **waiting for runner**:

1. confirme se `ejc-vps` aparece online no painel do GitHub;
2. confira `journalctl` e espaço em disco;
3. confirme que não existe job antigo preso;
4. valide Docker, memória e acesso ao diretório de trabalho;
5. reexecute o instalador com token novo somente se necessário.

Não faça merge de PR com gates obrigatórios pendentes apenas porque o runner
está offline.

## Recursos da VPS

O CI pode executar simultaneamente:

- PostgreSQL 16 com pgvector em container efêmero;
- suíte completa do backend;
- auditoria de dependências;
- testes e build do frontend;
- Playwright/Chromium;
- prova de backup e restauração.

Monitore CPU, memória e disco. Quando não houver capacidade suficiente, use o
CI local sob demanda descrito em `docs/CI_SEM_GITHUB.md` até a normalização.

## Teste de regressão do instalador

```bash
bash scripts/tests/test_selfhosted_runner_setup.sh
```

O teste valida sintaxe, dependências, ordem de recuperação e prova de saúde sem
instalar um runner real ou exigir token.

## Reversão

- Para voltar ao GitHub-hosted, altere conscientemente `runs-on` para
  `ubuntu-latest` e confirme billing/disponibilidade.
- Para operar apenas com CI local, use o procedimento de
  `docs/CI_SEM_GITHUB.md`.
- Para remover o runner da VPS:

```bash
cd /opt/actions-runner
sudo ./svc.sh stop
sudo ./svc.sh uninstall
```

Depois remova o registro no painel do GitHub ou use um token temporário de
remoção diretamente na VPS. Nunca versione esse token.
