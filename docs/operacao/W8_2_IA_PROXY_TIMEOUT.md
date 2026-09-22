# W8.2 — timeout do proxy para IA

## Estado

O repositório não contém o `ejc.conf` do Nginx do host. Portanto, esta mudança não pode ser aplicada nem validada como reload de produção a partir do sandbox. O backend já possui o contrato de resposta e a PR #1786 adiciona smoke HTTP contra uvicorn, mas isso não prova o caminho Nginx externo.

## Alteração esperada no host

No bloco que encaminha `/api/ai/` para o backend, definir timeout compatível com a duração máxima aprovada para a operação síncrona. O valor recomendado inicial é 300 segundos, sempre acompanhado de `proxy_send_timeout` e `proxy_connect_timeout` coerentes. A alternativa preferível para chamadas acima desse limite é converter o fluxo para job assíncrono com polling/SSE, sem manter conexões HTTP longas indefinidamente.

## Procedimento seguro

Executar no host, preservando backup da configuração:

```bash
sudo nginx -T > /var/backups/nginx-ejc-$(date +%Y%m%d%H%M%S).conf
sudo nginx -t
sudo systemctl reload nginx
curl -fsS https://<host>/api/health
```

Depois, cronometrar uma chamada sintética de IA autorizada e confirmar que a resposta chega antes do novo limite. Não usar dados reais de clientes. Se `nginx -t`, health check ou smoke falhar, restaurar o arquivo salvo e recarregar o serviço.

## Critério de encerramento

W8.2 só deve ser marcado como executado após anexar: configuração efetiva do host, saída de `nginx -t`, horário do reload, health check e um curl sintético cronometrado. Até lá, o item permanece bloqueado por dependência operacional, não por falha de código.
