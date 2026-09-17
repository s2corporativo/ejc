# Fronteira de IA: runtime jurídico x engenharia

Este documento é um contrato arquitetural da integração OmniRoute no EJC.

## Regra principal

O OmniRoute existe exclusivamente para **engenharia, manutenção e desenvolvimento** do EJC. Ele não é parte do runtime jurídico, não substitui o gateway institucional da aplicação e não deve receber tráfego originado de funcionalidades jurídicas do produto.

## Domínio A — IA jurídica do EJC

O domínio jurídico permanece sob a arquitetura da aplicação, incluindo `backend/app/services/ai_gateway.py`, RAG, pesquisa jurídica, banco de teses, análise de documentos, produção/revisão de peças e demais fluxos jurídicos.

Regras:

- não apontar `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL` ou configuração equivalente do backend/frontend para `127.0.0.1:20128`;
- não importar cliente, SDK ou configuração do OmniRoute no backend ou frontend do produto;
- não usar o modelo lógico `auto` do OmniRoute para escolher modelos em consultas jurídicas;
- não usar providers gratuitos de engenharia como fallback invisível do runtime jurídico;
- preservar os controles de contexto, RAG, auditoria, autorização e qualidade já definidos pela aplicação.

## Domínio B — IA de engenharia

O OmniRoute pode ser usado por ferramentas externas de manutenção, como Codex, Claude Code, Antigravity e agentes compatíveis, sempre fora do runtime do produto.

Usos permitidos:

- diagnóstico de código;
- análise de logs técnicos sem dados pessoais;
- correção de bugs;
- testes;
- lint/typecheck;
- geração e revisão de patches;
- análise de CI;
- documentação técnica;
- revisão de PR;
- tarefas de manutenção executadas em sandbox.

## Exceção de governança (escopo exclusivo de engenharia)

`CLAUDE.md` §3 exige que toda chamada de IA do produto passe pelo gateway
institucional (`backend/app/services/ai_gateway.py`). Esta seção registra a
**exceção explícita** concedida para a camada OmniRoute e o seu limite exato:

- **quem usa**: apenas ferramentas de engenharia/manutenção (Codex, Claude
  Code, Antigravity e clientes compatíveis do mantenedor);
- **o que usa**: diagnóstico, análise de código/logs técnicos, correção de
  bugs, testes, lint/typecheck, geração/revisão de patches, documentação
  técnica — o rol do §"Domínio B";
- **o que NÃO usa**: nenhum router, service, job ou fluxo do runtime jurídico
  do produto (frontend e backend do EJC não referenciam o OmniRoute — o
  `verify-boundary.sh` falha se encontrar acoplamento);
- **vigência**: enquanto esta camada existir de forma isolada; qualquer uso
  pelo produto exige mudança arquitetural separada (§"Mudanças futuras").

Com isso, a regra inegociável permanece intacta para o produto, e o uso
externo de engenharia passa a ter amparo documentado em vez de operar como
contorno informal.

## Dados proibidos no OmniRoute de engenharia

Não enviar a providers externos por esta camada:

- documentos reais de clientes;
- petições ou processos com dados pessoais reais;
- CPF, RG, endereço, telefone ou dados bancários;
- prontuários, dados de saúde ou outros dados pessoais sensíveis;
- `.env`, tokens, cookies, senhas, endpoint keys ou credenciais;
- dumps de banco de produção;
- logs contendo headers de autenticação ou segredos.

Para testes, usar dados sintéticos/fictícios.

## Política de custo e qualidade

A economia de custo vale para **engenharia**, não para degradar a inteligência jurídica do EJC.

Estratégia recomendada para agentes de manutenção:

1. tarefas mecânicas e de baixo risco: modelo gratuito/local validado;
2. tarefa que falhar ou exigir raciocínio maior: fallback para segundo modelo previamente aprovado;
3. alteração sensível: revisão independente e gates do repositório;
4. provider pago: somente quando deliberadamente habilitado.

O roteamento `auto` não significa autorização para qualquer provider. A lista de providers/modelos disponíveis deve ser intencionalmente limitada.

## Separação operacional

- OmniRoute: `/srv/ejc-omniroute`, porta loopback `127.0.0.1:20128`;
- EJC: permanece em sua stack própria;
- nenhum mount do checkout do EJC no container OmniRoute;
- nenhuma conexão do OmniRoute com PostgreSQL/Redis do EJC;
- nenhum proxy Nginx/Cloudflare público para o dashboard/API do OmniRoute;
- credenciais de providers permanecem no storage próprio do OmniRoute e fora do Git.

## Verificação

Execute na raiz do repositório:

```bash
bash infra/omniroute/verify-boundary.sh
```

O verificador falha se encontrar sinais de acoplamento do runtime (`backend/app`, `frontend/src` ou compose principal) ao OmniRoute.

## Mudanças futuras

Qualquer proposta para utilizar OmniRoute em funcionalidade jurídica deve ser tratada como **mudança arquitetural separada**, com análise de segurança, privacidade, qualidade jurídica e impacto sobre o gateway institucional. Não deve ocorrer incidentalmente em tarefas de manutenção.
