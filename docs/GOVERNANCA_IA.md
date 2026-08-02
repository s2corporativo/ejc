# Governança de agentes de IA no EJC

> **Documento canônico.** `CLAUDE.md`, `AGENTS.md` e os demais documentos de processo
> traduzem estas regras para cada agente; nenhum deles pode contrariá-las. Em caso de
> divergência entre qualquer instrução e este arquivo, **este arquivo prevalece** e a
> divergência deve ser registrada no PR.

Versão: 1.0 — 2026-07-27.

## 1. Princípio

O GitHub é a **fonte única da verdade** do EJC. Nenhuma decisão técnica, jurídica ou
operacional existe se não estiver em uma Issue, em um Pull Request, em um comentário de
review ou em um documento versionado do repositório. Conversas de chat não são registro:
são rascunho até virarem um desses quatro artefatos.

**Não há comunicação direta entre os papéis de governança.** ChatGPT, Claude Code e Codex
trocam informação exclusivamente por Issue, Pull Request, comentário de review e documento
versionado — nunca por canal privado entre si.

Isso **não** se aplica aos subagentes internos do repositório (`ejc`, `backend-fastapi`,
`frontend-react`, `db-migrations`, `security-auditor`, `qa-tests`, `code-reviewer`,
`verifier`, `simplifier`, listados em `CLAUDE.md`). Eles são **ferramentas do executor**, não
papéis de governança: o executor os aciona diretamente, e o resultado deles entra no PR sob a
responsabilidade do executor — quem responde pelo trabalho continua sendo um só.

## 2. Papéis

| Participante | Responsabilidade | O que **não** faz |
|---|---|---|
| **Clovis (titular)** | Define prioridades do escritório, valida o uso prático, autoriza merge e deploy | Não é revisor técnico de linha a linha |
| **ChatGPT (arquiteto/auditor)** | Especifica a tarefa, escreve a Issue e os critérios de aceite, revisa o PR (técnico, jurídico, segurança, LGPD, UX), aprova ou recusa | Não edita código diretamente na branch de execução |
| **Claude Code (executor)** | Implementa a Issue, escreve e roda testes, cria migrations, abre e atualiza o PR, corrige apontamentos | Não faz merge, não faz deploy, não altera escopo por conta própria |
| **Codex / revisor independente** | Auditoria técnica independente em entregas críticas | Não edita a branch sob revisão |
| **GitHub** | Guarda código, Issues, PRs, decisões, evidências e histórico | — |
| **GitHub Actions / CI** | Bloqueia merge quando testes, lint, schema, segurança ou gates de continuidade falham | — |
| **VPS staging** | Homologação com massa fictícia | Não recebe experimentação direta de agente |
| **VPS produção** | Somente releases aprovados pelo titular | Nunca é ambiente de trabalho de agente |

Detalhamento operacional dos agentes internos do repositório (`ejc`, `backend-fastapi`,
`frontend-react`, `db-migrations`, `security-auditor`, `qa-tests`, `code-reviewer`,
`verifier`, `simplifier`) está em `CLAUDE.md`; a hierarquia de papéis acima não muda por
causa deles — subagente é ferramenta do executor, não um papel de governança novo.

## 3. Fluxo canônico

```
Clovis  →  ChatGPT (Issue + critérios de aceite)  →  GitHub
        →  Claude Code (branch, código, testes, PR draft)
        →  ChatGPT (revisão registrada no PR)
        →  Claude Code (correções na MESMA branch e no MESMO PR)
        →  CI verde  →  homologação  →  autorização do titular  →  merge  →  deploy
```

Regra de forma: **uma Issue → uma branch → um PR**. O detalhamento passo a passo está em
`docs/FLUXO_DE_DESENVOLVIMENTO.md`.

## 4. Prioridades

| Nível | Significado | Efeito |
|---|---|---|
| **P0** | Segurança, LGPD, validade jurídica, perda de dado ou de prova | Bloqueia release; entra na frente de qualquer outra frente |
| **P1** | Integridade funcional — fluxo quebrado, contrato divergente, regressão | Bloqueia release da funcionalidade afetada |
| **P2** | UX, desempenho, organização de código | Entra no planejamento normal |
| **P3** | Evolução e melhoria futura | Só depois de P0–P2 estabilizados |

Enquanto houver P0 aberto em uma área, **nenhuma nova funcionalidade daquela área é
iniciada**.

## 5. Um único executor por área

Dois agentes não editam o mesmo conjunto de arquivos ao mesmo tempo. Isso não é
preferência de estilo: os PRs 493–497 deste repositório provaram o custo (ver
`docs/MATRIZ_CONSOLIDACAO_P0.md`) — três implementações incompatíveis do mesmo gate,
duas migrations disputando o número 122 e dois desenhos opostos para o mesmo segredo do
Data Room.

**Proibido**

```
Claude → corrige autenticação
Codex  → refatora autenticação
Outro  → altera RBAC
```

**Correto**

```
Claude   → implementa
ChatGPT  → revisa
Claude   → corrige os apontamentos
Codex    → auditoria independente final, sem editar
ChatGPT  → autoriza o merge (com o titular)
```

### Critérios de paralelização

Duas frentes só podem correr em paralelo quando **todas** as condições valem:

1. os conjuntos de arquivos são disjuntos (conferido por `git diff --name-only`);
2. **nenhuma das duas cria migration** — frente com migration é sempre sequencial (ver abaixo);
3. não compartilham contrato de API (schema, rota, nome de campo);
4. não compartilham a mesma regra jurídica.

### Migration: uma frente por vez, sem exceção

Só uma frente com migration corre por vez. Não é preferência de processo — é o que o CI
permite: o job de backend roda `alembic upgrade head` antes dos testes, e uma migration que
aponta para uma revisão ainda não mesclada não encontra o arquivo do pai numa branch tirada
da `main`. O PR simplesmente não fica verde. A guarda
`backend/tests/test_migration_numbering_guard.py` recusa `down_revision` inexistente pela
mesma razão.

Na prática: reservar o número em `MIGRATION_RESERVATIONS.md` **garante o lugar na fila**, não
o direito de desenvolver em paralelo. A segunda frente espera o merge da primeira e rebaseia
sobre a `main` atualizada. Branch empilhada (partir da branch da primeira em vez da `main`)
não é suportada hoje e não deve ser improvisada.

Se qualquer condição falhar, as frentes são **sequenciais** — a segunda começa depois do
merge da primeira, rebaseada sobre a `main` atualizada.

### Protocolo de divergência entre agentes

1. A divergência é registrada no PR, com o argumento de cada lado e a evidência (arquivo,
   linha, teste, fonte legal).
2. Vence quem apresentar evidência verificável; opinião sem evidência não decide.
3. Divergência sobre **regra jurídica** vai para o titular — nenhum agente decide sozinho
   qual é a lei aplicável.
4. Divergência sobre **segurança** resolve-se pelo lado mais restritivo (fail-closed) até
   que a auditoria diga o contrário.
5. Empate sem evidência: o trabalho **para** e a decisão sobe para o titular. Não se
   resolve implementando os dois caminhos.

## 6. Regras de execução (todos os agentes)

1. Nunca alterar a `main` diretamente — nem commit, nem push, nem force push.
2. Nunca fazer merge. Nunca executar deploy de produção.
3. Verificar PRs abertos que tocam os mesmos arquivos **antes** de começar.
4. Uma branch por tarefa, com nome que diga o que ela faz: `tipo/NUMERO-descricao`
   (`fix/`, `feat/`, `chore/`, `docs/`, `test/`) quando há Issue. Sessões do Claude Code na
   web recebem a branch pronta, no formato `claude/<descricao>` — esse nome é imposto pela
   ferramenta e **é aceito**; o vínculo com a tarefa fica no corpo do PR. Regra real: uma
   tarefa, uma branch, um PR — o padrão do nome é secundário.
5. Não ampliar o escopo da Issue. Um achado fora do escopo vira uma Issue nova, não um
   commit a mais.
6. Toda correção de bug entra com **teste de regressão**.
7. Toda regra jurídica exige **fonte oficial, vigência e teste** — sem isso, não entra.
8. Migration só depois de conferir o head atual e reservar o número (seção 8).
9. Nada de credenciais, tokens, senhas, dados pessoais reais ou documentos de cliente no
   repositório, em teste ou em log.
10. Comandos destrutivos nunca são autorizados de forma permanente: `git push --force`,
    `git reset --hard`, `git clean -fd`, `rm -rf`, `docker compose down -v`,
    `docker volume rm`, `dropdb`, `alembic downgrade base`. Não usar
    `claude --dangerously-skip-permissions`.
11. Encerrar toda tarefa com relatório: arquivos alterados, comandos executados, testes,
    riscos residuais, limitações e pontos que exigem decisão humana.
12. Chamadas de IA sempre pelo `services/ai_gateway.py`. HITL e o gate de citações não são
    contornáveis.
13. Rota nova nasce protegida. Endpoint público é exceção explícita e justificada no PR.

## 7. Segurança, LGPD e credenciais

- Segredos vivem no `.env` do ambiente e no cofre — nunca no git. O `scripts/ci_guard.sh`
  bloqueia, mas o guard é rede de proteção, não permissão para tentar.
- O agente trabalha em cópia de desenvolvimento, **nunca** no diretório de produção e
  **nunca** contra o banco de produção.
- PII (CPF/CNPJ, telefone, conteúdo de mensagem, dado de saúde, fato criminal) não vai
  para log, mensagem de erro, teste ou provedor externo sem sanitização.
- Mudança em autenticação, RBAC, upload, portal do cliente ou configuração exige o
  `security-auditor` antes de o PR ser considerado pronto. O relatório do auditor é
  insumo, não ordem: achado que contraria uma decisão permanente do titular (seção 11)
  vira risco aceito e registrado, não commit.
- Toda alteração de dado pessoal ou de retenção passa por avaliação LGPD registrada no PR.

## 8. Controle de migrations

O arquivo `backend/alembic/MIGRATION_RESERVATIONS.md` é obrigatório e a reserva vem
**antes** de escrever a migration. Nenhum agente escolhe um número novo sem:

1. atualizar a `main` local;
2. consultar os PRs abertos (inclusive drafts);
3. verificar o head atual do Alembic (`python -m alembic heads`);
4. reservar o próximo identificador na tabela;
5. confirmar as dependências (`down_revision` correto e linear).

Regras adicionais:

- head único — o repositório nunca tem dois heads;
- migration já aplicada em produção **não se edita**: corrige-se com uma nova;
- `alembic/env.py` tem guarda `include_name()` porque dezenas de tabelas existem só em SQL
  bruto: **nunca** aceitar `drop_table` de autogenerate sem conferência manual;
- migration destrutiva exige backup comprovado e plano de rollback aprovados antes.

## 9. Regras jurídicas

Uma funcionalidade jurídica (calculadora, prazo, tese, minuta) só é aceita com:

1. **fonte oficial** citada (lei, artigo, súmula, precedente vinculante);
2. **vigência** identificada (a partir de quando a regra vale; se mudou, o que mudou);
3. **versão da regra** registrada na resposta e no documento gerado;
4. **teste** cobrindo o caso normal, a borda e a exceção;
5. **aviso de revisão humana** visível ao usuário;
6. ausência de afirmação jurídica absoluta indevida ("com certeza", "sempre", "nunca").

Regra sem homologação do advogado responsável **não vira documento formal** — pode
calcular como apoio, não pode virar peça. Nenhum agente inventa, presume ou extrapola
regra jurídica.

## 10. Limites de autonomia do agente

Pode, sem perguntar: ler o repositório, rodar testes e lint, criar branch, implementar o
escopo da Issue, criar arquivo novo dentro do escopo, abrir PR draft, corrigir apontamentos
do review.

Só com autorização explícita: alterar contrato público de API; criar ou alterar migration;
mexer em autenticação, RBAC ou permissões; alterar CI/CD, Docker ou deploy; excluir código,
rota ou tabela; alterar dependências; mudar política de IA ou de provedor.

**O que conta como autorização explícita.** A Issue que descreve a mudança, ou o pedido
direto do titular — inclusive por chat. Um pedido autoriza o que ele **implica**: "corrija o
cadastro de cliente" autoriza a migration que a correção exigir, e o PR registra a decisão.
Não se estende ao vizinho: autoriza o que o pedido pede, nunca o que o agente encontrou pelo
caminho. Na dúvida entre duas leituras do pedido que levam a resultados materialmente
diferentes, o agente pergunta antes de gastar trabalho.

**Tarefa que chega sem Issue.** O fluxo canônico continua sendo Issue → branch → PR. Quando o
titular pede direto — por chat, sem Issue prévia — o pedido **já é a autorização para começar**:
o agente não fica parado esperando alguém abrir a Issue. Mas o trabalho precisa terminar
registrado, e o registro tem duas partes obrigatórias:

1. **Issue de registro**, aberta pelo próprio executor se ninguém a abriu antes, com problema,
   escopo, fora do escopo e critérios de aceite;
2. **PR vinculado a ela** (`Closes #NNN`), com as decisões e suposições escritas no corpo.

Isso não é formalidade: a trava `Governança — travas de PR` (`.github/workflows/governanca.yml`)
reprova PR cujo corpo não referencia `#<numero>`. Documento e automação precisam dizer a mesma
coisa — regra escrita que o CI contradiz é a origem de metade da confusão que esta seção existe
para eliminar.

O que a governança não admite é trabalho sem artefato nenhum. Abrir a Issue depois de começar é
aceitável; terminar sem ela, não.

Nunca: merge, deploy de produção, acesso ao banco de produção, force push, apagar branch,
volume ou banco, versionar segredo, desligar HITL/citation gate/sanitização de PII.

## 11. Decisões permanentes do titular

Decisões já tomadas pelo titular. **Nenhum agente as reabre por conta própria** — nem como
"correção de segurança", nem como efeito colateral de outra tarefa. Mudar qualquer uma
exige pedido explícito do titular, registrado em Issue.

| Decisão | Estado | Observação |
|---|---|---|
| **2FA — não implementar** | Vigente desde 2026-07-26, reafirmada em 2026-07-27 | `TWO_FACTOR_AUTH_ENABLED` permanece como está: 2FA **desligado** por padrão e o kill-switch preservado. Não alterar `app/core/two_factor_policy.py` para forçar fail-closed, nem incluir 2FA em auditoria como bloqueador P0. Se uma auditoria apontar o fail-open, registre como **risco aceito pelo titular**, não como achado a corrigir. |

Histórico do porquê esta seção existe: os PRs #495 e #497 alteraram `two_factor_policy.py`
por iniciativa própria, com semânticas diferentes entre si, contra uma decisão já
comunicada (o #496 a respeitou explicitamente). Duas frentes gastaram trabalho e criaram
um conflito por causa de uma decisão que não estava escrita no repositório.

## 12. Documentos relacionados

- `CLAUDE.md` — regras operacionais do executor e mapa técnico do repositório.
- `AGENTS.md` — regras comuns a qualquer agente de IA.
- `docs/FLUXO_DE_DESENVOLVIMENTO.md` — o ciclo Issue → merge, passo a passo.
- `docs/CRITERIOS_DE_ACEITE.md` — as cinco camadas de auditoria de um PR.
- `docs/RELEASE_CHECKLIST.md` — o que precisa estar verde antes de um release.
- `docs/MATRIZ_CONSOLIDACAO_P0.md` — consolidação dos PRs 493–497.
- `backend/alembic/MIGRATION_RESERVATIONS.md` — reserva de numeração de migrations.
