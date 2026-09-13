# Host automation — gate Woodpecker

Este diretório contém a ponte segura entre CI e operações de produção sem GitHub Actions.

## Princípio

O Woodpecker continua **sem acesso privilegiado ao host de produção**. O pipeline de PR nunca recebe `/var/run/docker.sock`, `/opt/ejc`, `/opt/verdelimp-erp` ou segredos de produção.

Quando uma rotina host-level pretende implantar uma nova versão, ela:

1. obtém o SHA exato de `origin/main`;
2. chama `woodpecker-approved-sha.sh <repo> <sha>`;
3. o gate consulta a API do Woodpecker com token armazenado somente no host;
4. exige pipeline `push` da branch `main`, para o mesmo SHA, com `status=success`;
5. somente então o script específico do sistema pode tocar produção.

Isso separa claramente **aprovação do código** de **privilégio operacional**.

## Instalação

```bash
cd infra/host-automation
sudo bash install.sh
sudoedit /etc/s2-automation/woodpecker.env
sudo chmod 600 /etc/s2-automation/woodpecker.env
```

O token deve ser obtido no perfil do próprio servidor Woodpecker e nunca deve ser colocado no GitHub, em PR, Issue, Woodpecker secret de repositório ou log.

## Uso

```bash
sudo /opt/s2-automation/host/woodpecker-approved-sha.sh \
  s2corporativo/verdelimpclaude \
  <sha-de-40-caracteres>
```

Saída 0 significa que existe uma execução bem-sucedida de `push/main` para o SHA. Qualquer ausência, falha, resposta inválida, token ausente ou SHA fora do escopo bloqueia a operação.

## Regras

- Não aceitar branch de PR como prova para produção.
- Não aceitar pipeline `pending`, `failure`, `killed`, `blocked` ou `declined`.
- Não aceitar SHA aproximado/curto.
- O wrapper de deploy deve repetir/verificar o SHA após qualquer novo `git fetch`, para evitar TOCTOU.
- O gate não faz deploy; ele apenas decide se o SHA está autorizado.
