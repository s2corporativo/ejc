# Runbook — acesso seguro à VPS do EJC

## Política atual

A VPS de produção deve operar com autenticação SSH por chave:

- `PasswordAuthentication no`;
- `PubkeyAuthentication yes`;
- `PermitRootLogin prohibit-password`.

Não reative login por senha para resolver incidente de acesso. Senha de conta não substitui chave SSH quando o `sshd` está em modo key-only.

## Caminho normal

Use chave privada mantida fora do repositório e protegida pelo sistema operacional/cofre local. O toolkit em `vps-tools/` aceita:

- `VPS_SSH_KEY_PATH` — recomendado para uso local;
- `VPS_SSH_KEY` — somente quando um cofre/CI injeta o conteúdo no ambiente;
- `VPS_SSH_PASSPHRASE` — quando a chave for cifrada.

Nunca registre chave, passphrase, senha, IP privado ou token em Issue, PR, README, shell history compartilhado ou log.

## Diagnóstico sem alterar o host

Diferencie as classes de falha antes de qualquer ação:

1. **timeout/refused** — rede, firewall, serviço SSH ou indisponibilidade do host;
2. **`Permission denied (publickey)`** — chave ausente, chave errada, usuário errado ou `authorized_keys`/permissões inválidos;
3. **host key changed** — não aceite automaticamente; valide a mudança por canal administrativo confiável antes de atualizar `known_hosts`;
4. **toolkit sem configuração** — confira apenas presença das variáveis/caminhos, nunca imprima seus valores.

## Recuperação quando nenhuma chave válida funciona

A recuperação deve ocorrer pelo console/painel administrativo do provedor ou outro canal out-of-band autorizado. O objetivo é restaurar uma chave pública autorizada e preservar o modo key-only.

Procedimento conceitual:

1. confirmar que o incidente é autenticação e não indisponibilidade geral;
2. usar o console administrativo autorizado do provedor;
3. preservar uma cópia do `authorized_keys` e da configuração SSH antes de editar;
4. inserir somente uma chave pública controlada pelo escritório;
5. validar permissões de `.ssh`/`authorized_keys`;
6. validar uma segunda sessão SSH por chave antes de encerrar o console;
7. registrar a ocorrência sem incluir material secreto;
8. revogar chave antiga se houver suspeita de comprometimento.

## Redundância recomendada

Mantenha pelo menos duas vias de recuperação administrativamente independentes:

- chave operacional principal;
- chave de emergência protegida em custódia segura e testada periodicamente;
- console do provedor como último recurso.

Redundância não significa habilitar senha root.

## Rollback

Qualquer mudança em `sshd` só deve ser considerada concluída depois de uma nova sessão SSH autenticada com sucesso. Mantenha a sessão administrativa existente aberta durante a validação. Em caso de falha, restaure o arquivo de configuração e `authorized_keys` preservados pelo canal out-of-band.
