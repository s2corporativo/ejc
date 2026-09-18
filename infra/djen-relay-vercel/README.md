# DJEN relay — Vercel São Paulo

Relay mínimo e dedicado para a API oficial Comunica/CNJ quando a VPS do EJC
possui egress fora do Brasil.

## Contrato de segurança

- execução fixada em `gru1` (São Paulo);
- aceita apenas `GET`;
- allowlist fechada dos parâmetros usados pelo Comunica;
- upstream fixo em `https://comunicaapi.pje.jus.br/api/v1/comunicacao`;
- autenticação Ed25519 por `x-ejc-timestamp` + `x-ejc-signature`;
- janela de validade de 120 segundos;
- a chave pública pode ser versionada; a chave privada nunca sai do ambiente do EJC;
- sem proxy genérico, sem destino arbitrário e sem interceptação TLS;
- respostas usam `Cache-Control: no-store`.

## Vercel Deployment Protection

O endpoint máquina-a-máquina precisa ter o domínio de produção público no
Vercel. Use **Standard Protection** para este projeto. Não use link temporário
de bypass como solução operacional.

A aplicação continua protegida pela assinatura Ed25519 mesmo com o domínio
público.

## Configuração EJC

Definir apenas no ambiente seguro de produção:

- `DJEN_RELAY_URL=https://<dominio-do-relay>/api/djen`
- `DJEN_RELAY_PRIVATE_KEY_B64=<segredo>`

A chave privada não deve aparecer em Git, logs, documentação ou tickets.

## Rollback

Remover `DJEN_RELAY_URL` e `DJEN_RELAY_PRIVATE_KEY_B64` faz o EJC voltar ao
proxy CONNECT configurado; sem proxy, volta à conexão direta.
