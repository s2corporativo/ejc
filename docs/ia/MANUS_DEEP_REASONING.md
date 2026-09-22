# Manus — Raciocínio Profundo no EJC

## Papel no sistema

Manus é uma ferramenta **explícita** do Assistente IA. Não participa do
roteamento automático Groq/Maritaca/Claude/Ollama e não é fallback de falha de
outro provider.

Fluxo:

1. advogado escolhe **Raciocínio profundo**;
2. EJC valida RBAC e eventual acesso ao caso;
3. conteúdo é pseudonimizado localmente;
4. segunda barreira rejeita PII residual;
5. EJC cria uma task privada na Manus API v2;
6. frontend consulta `task.listMessages` até conclusão;
7. Structured Output é exibido como **rascunho**, com revisão humana obrigatória.

## Segurança

- `MANUS_ENABLED=false` por padrão;
- `MANUS_AUTO_ROUTING_ENABLED=false` é obrigatório;
- nenhum conector Manus é enviado;
- nenhuma ação externa é confirmada automaticamente;
- tarefas com `Case.sigilo_reforcado=true` são bloqueadas;
- crimes sexuais e menores/infância também são bloqueados no uso avulso por
  sinais textuais de alta confiança;
- PII pseudonimizada não é reidratada nesta primeira versão;
- o mapa local de pseudônimos é descartado e nunca persistido;
- o task handle é HMAC, vinculado ao usuário e expira em 24h;
- fontes mencionadas pelo Manus são marcadas como **não verificadas**.

## Configuração

```env
MANUS_ENABLED=false
MANUS_AUTO_ROUTING_ENABLED=false
MANUS_API_BASE_URL=https://api.manus.ai
MANUS_API_KEY=
MANUS_AGENT_PROFILE=max
MANUS_CONNECT_TIMEOUT=10
MANUS_READ_TIMEOUT=30
MANUS_WRITE_TIMEOUT=30
MANUS_MAX_INPUT_CHARS=16000
```

A chave real nunca entra no Git. Um GitHub Repository Secret não é
automaticamente disponibilizado ao Woodpecker nem à VPS; produção precisa
receber o mesmo segredo no runtime por canal operacional próprio.

## Rotas

- `POST /api/manus/deep-reasoning` — cria task assíncrona;
- `GET /api/manus/deep-reasoning/{handle}` — lê status/resultado autorizado.

Não há migration, tabela ou webhook nesta versão. Isso mantém rollback simples:
desabilitar `MANUS_ENABLED` interrompe novas chamadas sem afetar o restante da
IA do EJC.
