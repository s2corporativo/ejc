# OmniRoute — gateway de manutenção do EJC

Integração opcional para ferramentas de desenvolvimento e manutenção (Codex, Claude Code, Antigravity e clientes compatíveis). **Não substitui** `backend/app/services/ai_gateway.py` e não participa das chamadas de IA do runtime jurídico do EJC.

## Exceção de governança registrada (escopo: engenharia)

`CLAUDE.md` §3 (regra inegociável) exige que **toda chamada de IA do produto**
passe por `backend/app/services/ai_gateway.py` — nada aqui altera isso. Esta
integração é a **exceção explícita, registrada e delimitada** para as
ferramentas de engenharia/mantenedores (Codex, Claude Code, Antigravity)
operarem fora do produto, conforme formalizado em `ENGINEERING_BOUNDARY.md`
(§"Exceção de governança"): escopo exclusivo de manutenção, sem tráfego de
funcionalidades jurídicas, sem sobreposição ao gateway institucional. Qualquer
uso do OmniRoute pelo runtime do produto segue sendo mudança arquitetural
separada.

## Limite arquitetural

- serviço independente do `docker-compose.yml` principal;
- bind padrão somente em `127.0.0.1:20128`;
- sem Nginx, Cloudflare, túnel público ou porta aberta para a internet;
- sem mount de `/opt/ejc`, checkout Git, `.env`, `~/.codex`, `~/.claude` ou diretórios de credenciais;
- dados do OmniRoute persistem apenas no volume Docker `ejc-omniroute-data`;
- endpoint keys, OAuth/refresh tokens e credenciais de providers são segredos e nunca devem ser versionados, copiados para Issue/PR ou registrados em logs de CI.

## Subir a stack

A partir de um workspace seguro, fora de `/opt/ejc`:

```bash
cp infra/omniroute/.env.example infra/omniroute/.env
docker compose \
  -p ejc-omniroute \
  -f infra/omniroute/docker-compose.yml \
  --env-file infra/omniroute/.env \
  config >/dev/null
docker compose \
  -p ejc-omniroute \
  -f infra/omniroute/docker-compose.yml \
  --env-file infra/omniroute/.env \
  up -d
```

O `config >/dev/null` valida o compose **sem imprimir** a configuração
interpolada — a saída expandida contém o `JWT_SECRET` resolvido e não deve
ever ser exibida em terminal capturado ou log de CI.

O `.env` local desta pasta é ignorado pelo Git. O compose usa versão + digest
fixos para evitar atualização implícita. Antes do `up`, gere um `JWT_SECRET`
forte conforme `SECURE_BOOTSTRAP.md` — o compose falha de forma segura com
valor vazio ou placeholder, e `verify-boundary.sh` recusa subir nesse estado.

## Acesso remoto seguro

Na VPS, a interface fica acessível apenas por loopback. Para abrir o dashboard de uma estação autorizada, prefira túnel SSH local:

```bash
ssh -L 20128:127.0.0.1:20128 USUARIO@VPS
```

Depois, abra `http://127.0.0.1:20128` no navegador local. Não altere `OMNIROUTE_BIND_HOST` para `0.0.0.0` em servidor exposto sem uma decisão específica de segurança.

## Providers e custo

Cadastre providers apenas pelo dashboard/local helper do OmniRoute. Priorize providers gratuitos ou planos já disponíveis e use o modelo lógico `auto` quando o fluxo exigir fallback. Provider pago deve ser habilitado deliberadamente; o OmniRoute não transforma uma API paga em gratuita.

As credenciais e endpoint keys ficam fora do repositório. O volume `/app/data` deve ser tratado como sensível porque pode conter configuração de providers e autenticação.

## Codex

Depois de criar uma endpoint key no OmniRoute:

```bash
export OPENAI_BASE_URL="http://127.0.0.1:20128/v1"
export OPENAI_API_KEY="<endpoint-key-do-omniroute>"
```

Use o modelo `auto` quando suportado pela integração. A chave acima é segredo operacional: não gravar em arquivos versionados.

## Claude Code

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:20128"
export ANTHROPIC_AUTH_TOKEN="<endpoint-key-do-omniroute>"
export ANTHROPIC_MODEL="auto"
export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1
```

A base Anthropic usa a raiz do gateway, sem `/v1`.

## Antigravity

Quando o Antigravity estiver na máquina local, mantenha o OmniRoute alcançável pelo túnel SSH acima. Configuração/autenticação de provider deve permanecer no OmniRoute; não transportar refresh tokens para o repositório nem para prompts de agentes.

## Verificação operacional

```bash
docker compose -p ejc-omniroute -f infra/omniroute/docker-compose.yml ps
curl -fsS http://127.0.0.1:20128/ >/dev/null
```

Para diagnóstico, inspecione somente logs técnicos do container e evite colar logs que contenham headers ou credenciais em Issues/PRs.

## Versão e atualização

A implantação inicial foi validada em 13/09/2026 com `diegosouzapw/omniroute:3.8.50`, cujo `package.json` dentro da imagem retornou `3.8.50`. O compose também fixa o digest `sha256:085c57adf499a8aaa9f35ccde95c0df9c11bd9ecd18d6c9edbf3b68b8079ba9d`, evitando confiar apenas em uma tag mutável.

Houve falhas no publish inicial do 3.8.50 em 26/08/2026; por isso a validação desta integração exige conferir o artefato real, não somente a existência da tag. Atualizações devem ocorrer em PR separado, com versão interna, digest, release notes, `docker compose config`, health-check e smoke local novamente verificados.

## Rollback

Pare a camada sem apagar os dados:

```bash
docker compose -p ejc-omniroute -f infra/omniroute/docker-compose.yml down
```

Não use `down -v` no ciclo normal. A remoção do volume é destrutiva e exige decisão explícita porque elimina configuração e credenciais persistidas do OmniRoute.

## Relação com outras frentes

Esta integração evita sobreposição com o PR #1616 (regras/workflows de Antigravity) e com o PR #1624 (`ops/agents/**` + OpenAI Agents SDK). Ela fornece somente o gateway externo de modelos; governança, sandbox, handoffs, guardrails, testes, PRs e deploy continuam sendo responsabilidade das camadas próprias do EJC.
