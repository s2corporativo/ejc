# RUNBOOK — Acesso SSH à VPS: recuperação e rotação de senha

> Produção: VPS Contabo · `APP_DIR=/opt/ejc` · domínio `ejc.depaulateixeira.adv.br`
> Escopo: recuperar o acesso quando a senha root não funciona mais, rotacionar a
> senha sem downtime e eliminar o ponto único de falha do acesso.

Este runbook não contém host, usuário, senha nem chave. Todos os valores reais
ficam em `vps-tools/.env` (fora do versionamento) e nos segredos do GitHub.

---

## 0. Antes de tudo: a senha está mesmo errada?

Antes de resetar pelo painel — que exige reboot e derruba o EJC — descarte as
causas baratas. Em ordem de custo:

1. **Arquivo local de ambiente.** Abra `vps-tools/.env` e confira `VPS_PASSWORD`.
   Teste sem alterar nada:
   ```bash
   node vps-tools/run.js "id -un && hostname"
   ```
   Respondeu? Então o acesso existe e o problema era o valor digitado à mão.

2. **Segredo do GitHub.** Se `vps-tools/.env` falha, veja se a esteira ainda
   entra. Em *Actions*, rode `Recover self-hosted runner` (`workflow_dispatch`)
   e leia o log do passo de SSH:

   | O que aparece no log | Significado |
   |---|---|
   | `Permission denied, please try again.` | O servidor **ofereceu** senha e **recusou** a credencial → a senha está errada mesmo. |
   | `Permission denied (publickey).` | O servidor **não aceita senha**; só chave. Não adianta resetar senha. |
   | `Connection timed out` / `No route to host` | Problema de rede ou firewall, não de credencial. |
   | `Host key verification failed` | `known_hosts` divergente — o host pode ter sido reinstalado. |

3. **Chave SSH.** Se `VPS_SSH_KEY_PATH` estiver configurado, a chave é tentada
   antes da senha. Uma chave válida torna o reset desnecessário.

Só siga para o passo 1 se nenhuma dessas vias entrar.

---

## 1. Recuperar acesso pelo painel do provedor

Necessário apenas quando **nenhuma** credencial funciona — sem senha e sem chave
não existe caminho remoto de entrada.

1. Entre no painel do Contabo com a conta titular.
2. Vá em **Your Services**, selecione a VPS do EJC.
3. Abra a gestão de senha do servidor (a opção fica junto de *rescue mode* e
   *reinstall*; o rótulo já mudou entre versões do painel).
4. Defina a nova senha e confirme.

⚠️ **O reset normalmente só passa a valer após reinício do servidor.** Isso
derruba a stack. Trate como janela de manutenção:

- Agende fora do horário de atendimento do escritório.
- Rode um backup antes (`RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md` ou
  `scripts/backup.sh`), porque um reboot pode expor migration pendente.
- Depois que o servidor voltar, confirme a stack:
  ```bash
  node vps-tools/run.js "cd /opt/ejc && docker compose ps"
  node vps-tools/run.js "cd /opt/ejc && EJC_DOMAIN=ejc.depaulateixeira.adv.br bash scripts/post_deploy_check.sh"
  ```

---

## 2. Rotacionar a senha sem reboot (caminho normal)

Com o acesso funcionando, **nunca** use o painel para trocar a senha — não há
motivo para pagar um reboot. Use:

```bash
node vps-tools/trocar-senha-root.js
```

O script:

- pede a senha nova **duas vezes, com entrada oculta**;
- exige no mínimo 12 caracteres e recusa quebra de linha (que permitiria
  injetar uma segunda entrada no `chpasswd`);
- entrega a senha ao `chpasswd` pelo **stdin da sessão SSH**, nunca na linha de
  comando — assim ela não aparece em `ps`, no histórico do shell remoto nem nos
  logs de auditoria de comando;
- abre uma **conexão nova** com a senha nova para provar que funciona;
- só então grava `VPS_PASSWORD` em `vps-tools/.env`, com permissão `0600`;
- nunca imprime a senha na tela.

Se qualquer etapa falhar, nada é gravado localmente e a senha antiga continua
valendo — o script falha fechado.

### Depois de rotacionar, atualize o segredo do GitHub

O `deploy-vps.yml` e o `recover-selfhosted-runner.yml` usam o segredo
`VPS_PASSWORD`. Trocar a senha no servidor sem atualizar o segredo **quebra a
esteira de deploy** — e a falha aparece como um `Permission denied` genérico,
difícil de associar à rotação.

*Settings → Secrets and variables → Actions → `VPS_PASSWORD`.*

---

## 3. Eliminar o ponto único de falha: cadastrar chave SSH

Enquanto o acesso depender só de senha, perder a senha significa reboot de
produção. Uma chave remove isso.

Na sua máquina:

```bash
ssh-keygen -t ed25519 -C "ejc-operacao" -f ~/.ssh/ejc_vps
ssh-copy-id -i ~/.ssh/ejc_vps.pub <usuario>@<host>
```

Sem `ssh-copy-id` (Windows), com o acesso por senha ainda ativo:

```bash
node vps-tools/run.js "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '<conteudo-de-ejc_vps.pub>' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

Depois aponte o toolkit para a chave, em `vps-tools/.env`:

```
VPS_SSH_KEY_PATH=~/.ssh/ejc_vps
```

O `ssh-config.js` passa a tentar a chave primeiro e mantém a senha como
fallback. Valide antes de confiar:

```bash
node vps-tools/run.js "id -un"
```

Cadastre também a **chave privada** no segredo `VPS_SSH_KEY` do GitHub. Os
workflows já preferem chave a senha quando ele está preenchido — hoje esse
segredo está vazio, e é por isso que uma senha errada basta para bloquear
totalmente a esteira.

---

## 4. Ordem de execução em bloqueio total

```
senha local falha
      │
      ├─ segredo do GitHub funciona? ──► use a esteira, corrija o .env local. Fim.
      │
      ├─ chave SSH cadastrada? ────────► entre por chave, rode trocar-senha-root.js. Fim.
      │
      └─ nada funciona
             │
             ├─ 1. backup
             ├─ 2. reset no painel (janela de manutenção, com reboot)
             ├─ 3. subir e validar a stack (post_deploy_check.sh)
             ├─ 4. cadastrar chave SSH  ◄── impede a repetição
             └─ 5. atualizar VPS_PASSWORD e VPS_SSH_KEY nos segredos do GitHub
```

---

## 5. Higiene

- Senha nunca em chat, ticket, commit ou mensagem de PR. Se vazou em algum
  desses canais, rotacione pelo passo 2 — é barato e não exige reboot.
- `vps-tools/.env` fica em `0600` e fora do versionamento (`.gitignore`).
  O `scripts/ci_guard.sh` bloqueia `.env` versionado, mas não confie nele como
  única barreira.
- Rotacione após qualquer saída de pessoa com acesso à operação.
- Nenhum arquivo versionado deve conter host, IP, senha ou instance ID
  (`README.md`, seção de VPS).
