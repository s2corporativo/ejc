# Uptime Kuma — monitoramento S2

Substitui workflows de uptime do GitHub Actions por monitoramento contínuo self-hosted na VPS.

## Segurança adotada

- Interface exposta somente em `127.0.0.1:3001`; publicar externamente apenas via Nginx + TLS.
- Não montar `/var/run/docker.sock`. O monitoramento deve usar HTTP/TCP, evitando dar controle do Docker ao painel de uptime.
- Ativar 2FA na conta administrativa.
- Configurar notificações com credencial dedicada e de menor privilégio possível.

## Instalação

```bash
cd /opt/s2-automation/infra/monitoring/uptime-kuma
docker compose config --quiet
docker compose up -d
docker compose ps
```

Proxy recomendado: `https://status.depaulateixeira.adv.br` -> `http://127.0.0.1:3001`.

## Monitores iniciais verificados no código

1. Woodpecker CI — `https://ci.depaulateixeira.adv.br`
2. EJC API — `https://ejc.depaulateixeira.adv.br/api/health`
3. S2 Licit — `https://s2.s2corporativo.com.br/readyz`

Adicionar Studio, Verdelimp e Cuidar Vet somente depois de confirmar o domínio e o endpoint oficial de health de cada produção; não inventar rota de monitoramento.

Sugestão de parâmetros: intervalo de 60 s para health HTTP, timeout de 10 s, 3 tentativas antes de alerta e monitor de certificado TLS com aviso antecipado.

## Backup

O estado fica no volume `uptime-kuma-data`. Antes de atualização de versão, pare somente o Uptime Kuma e faça backup consistente do volume. Não usar `docker compose down -v`.
