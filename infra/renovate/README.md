# Renovate self-hosted — S2

Substitui o Dependabot nos repositórios S2 sem usar GitHub Actions.

## Escopo

O runner central processa somente:

- `s2corporativo/ejc`
- `s2corporativo/studio`
- `s2corporativo/s2licit`
- `s2corporativo/cuidar-vet-plataforma`
- `s2corporativo/verdelimpclaude`

Cada repositório precisa conter `renovate.json`. O global `config.js` usa `onboarding: false` e `requireConfig: required`, portanto nenhum repositório sem configuração versionada será alterado.

## Segurança

1. Preferir GitHub App dedicada ao Renovate; PAT dedicado é fallback.
2. A credencial fica somente em `/etc/s2-automation/renovate.env`, `root:root`, modo `0600`.
3. Nunca inserir token em `config.js`, Issue, PR, log, `.env.example` ou Woodpecker.
4. `automerge` fica desabilitado. Atualizações major exigem aprovação explícita no Dependency Dashboard.
5. O manager `github-actions` fica desabilitado porque os workflows do Actions estão em processo de aposentadoria.

## Instalação na VPS

A partir do checkout revisado:

```bash
cd infra/renovate
sudo bash install.sh
sudoedit /etc/s2-automation/renovate.env
sudo systemctl start s2-renovate.service
sudo systemctl enable --now s2-renovate.timer
systemctl status s2-renovate.timer --no-pager
journalctl -u s2-renovate.service -n 100 --no-pager
```

O instalador se recusa a habilitar o timer enquanto `RENOVATE_TOKEN=TROCAR` permanecer.

## Agenda

O systemd inicia o Renovate diariamente por volta de 06:00 UTC, com atraso aleatório de até 20 minutos. Os `renovate.json` restringem a criação normal de PRs para sábado entre 02:00 e 07:00 em `America/Sao_Paulo`. Rodar diariamente permite ao bot reconciliar estado sem concentrar carga na VPS.

## Atualização do container

A imagem está fixada no `run.sh`. Alterar a versão exige PR, leitura das notas de release e uma execução manual bem-sucedida antes de manter o timer ativo.
