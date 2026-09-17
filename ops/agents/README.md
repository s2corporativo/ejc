# EJC — agentes de manutenção

Camada operacional, fora do runtime de produção, para manutenção assistida do repositório com os recursos solicitados do OpenAI Agents SDK:

- `SandboxAgent`;
- agentes como ferramentas (`Agent.as_tool()`);
- handoffs;
- guardrails;
- tracing.

O runtime FastAPI de produção **não** importa este pacote e `backend/requirements.txt` permanece inalterado.

## Modelo de segurança

O runner:

1. cria um snapshot temporário contendo somente arquivos rastreados pelo Git;
2. exclui nomes comuns de arquivos com segredos (`.env*`, exceto exemplos, chaves privadas e arquivos típicos de credenciais);
3. recusa symlinks rastreados em vez de segui-los;
4. materializa somente `repo/` dentro de um container Docker dedicado, sem bind mount do checkout do host;
5. executa o container com `network_mode="none"`, sem portas publicadas;
6. usa uma imagem dedicada cujo usuário padrão é não-root (`agente`, UID/GID 10001);
7. não materializa `.git`, impedindo que o sandbox faça push, merge ou altere o histórico do repositório;
8. mantém a credencial do provider apenas no processo host; ela não é adicionada ao manifesto nem ao ambiente do container;
9. executa um guardrail de entrada bloqueante antes do primeiro turno do agente;
10. executa guardrail de saída no orquestrador e em todos os agentes capazes de produzir a resposta final;
11. exige por código um handoff real para o revisor de segurança em tarefas sensíveis;
12. registra tracing com `trace_include_sensitive_data=False` quando tracing remoto estiver habilitado.

O `SandboxAgent` ainda é recurso beta no SDK. A versão permanece fixada em `openai-agents[docker]==0.22.2` até revisão deliberada de compatibilidade.

## Papéis

- **Orquestrador de Manutenção EJC**: inspeciona e pode editar somente a cópia temporária do repositório e executar verificações proporcionais ao diff.
- **Revisor Independente EJC**: chamado como ferramenta para revisar resumo de alteração e evidências de teste antes da conclusão.
- **Revisor de Segurança EJC**: recebe handoff obrigatório quando a tarefa envolve autenticação, autorização, uploads, CI/CD, dependências, core/middlewares, migrations, segurança ou área próxima de produção.

## Instalação

Crie um ambiente Python separado do backend da aplicação:

```bash
python -m venv .venv-agents
. .venv-agents/bin/activate
pip install -r ops/agents/requirements.txt
```

Construa uma vez a imagem dedicada do sandbox:

```bash
docker build -t ejc-agents-sandbox:0.22.2 -f ops/agents/Dockerfile.sandbox .
```

A imagem traz Python 3, Node 22, Git e ripgrep para inspeção e verificações básicas. Dependências completas do backend/frontend continuam sendo validadas pela esteira oficial do EJC; o agente nunca pode apresentar como executado um teste que a imagem não suporte.

## Execução direta com OpenAI

O modelo não fica fixado no runner para permitir controle explícito de custo e capacidade por execução.

```bash
export OPENAI_API_KEY='...'
export OPENAI_AGENTS_MODEL='<nome-do-modelo>'
python -m ops.agents.runner "Analise e corrija o erro X; execute somente verificações proporcionais ao diff."
```

Também é possível selecionar a imagem e o modelo por argumento:

```bash
python -m ops.agents.runner \
  --modelo '<nome-do-modelo>' \
  --imagem 'ejc-agents-sandbox:0.22.2' \
  "Analise o problema X."
```

A credencial é usada apenas pelo processo host para as chamadas de modelo. O shell disponível ao agente fica dentro do container sem rede.

## Execução via OmniRoute

O launcher `ops.agents.omniroute` integra o Agents SDK ao gateway **somente para engenharia/manutenção**. Ele não altera `backend/app/services/ai_gateway.py`, o RAG ou qualquer fluxo jurídico do EJC.

Por padrão, aceita exclusivamente `http://127.0.0.1:20128/v1` e usa `auto/best-coding`. Um endereço público, outra porta ou outro path são recusados antes da chamada ao modelo.

```bash
export OPENAI_API_KEY='<endpoint-key-do-OmniRoute>'
export OPENAI_AGENTS_MODEL='auto/best-coding'  # opcional; este já é o padrão
python -m ops.agents.omniroute \
  "Analise e corrija o erro X; execute somente verificações proporcionais ao diff."
```

Se necessário, `EJC_OMNIROUTE_BASE_URL` ou `OPENAI_BASE_URL` podem ser definidos, mas o valor ainda precisa resolver exatamente para `http://127.0.0.1:20128/v1`.

O launcher configura o Agents SDK em `chat_completions` e cria um cliente OpenAI-compatible com `use_for_tracing=False`. A endpoint key do OmniRoute **nunca é reutilizada para exportar traces à OpenAI**. Sem uma credencial de tracing separada, o tracing remoto é desabilitado. Para habilitá-lo deliberadamente, use uma chave própria em `EJC_AGENTS_TRACING_API_KEY`; `trace_include_sensitive_data=False` continua obrigatório no runner.

A endpoint key permanece no processo host e não é enviada ao container sandbox. O OmniRoute também permanece fora da rede do sandbox: quem fala com o gateway é o SDK no host; as ferramentas shell/filesystem do agente continuam dentro do container com `network_mode="none"`.

## Testes determinísticos

Os testes abaixo não chamam modelo e não consomem créditos de API:

```bash
python -m unittest discover -s ops/agents/tests -v
```

Eles verificam, entre outros pontos:

- bloqueio de operações destrutivas e caminhos de produção;
- exclusão de arquivos sensíveis;
- identificação de tarefas que exigem revisão de segurança;
- `network_mode="none"` e ausência de portas publicadas;
- manifesto sem grants para caminhos externos;
- aceitação somente de handoff real para o revisor de segurança configurado;
- recusa de OmniRoute fora de `127.0.0.1:20128/v1`;
- separação entre endpoint key do OmniRoute e credencial de tracing.

## Limites deliberados

Esta primeira camada não:

- cria endpoint público;
- altera o AI Gateway institucional;
- faz merge ou deploy;
- toca `/opt/ejc` ou banco de produção;
- usa Sessions, Realtime, Voice, Skills, Memory ou outros módulos fora do escopo solicitado;
- exporta automaticamente alterações do sandbox para o checkout Git do host.

As alterações produzidas pelo sandbox são efêmeras nesta fronteira inicial. A promoção de uma correção revisada para uma branch Git continua sendo uma etapa separada e rastreável do fluxo de governança existente.
