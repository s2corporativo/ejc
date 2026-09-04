# Governança de agentes de IA no EJC

> **Documento canônico.** `CLAUDE.md`, `AGENTS.md` e os demais documentos de processo
> traduzem estas regras para cada agente. Em caso de divergência, este arquivo prevalece.

Versão: 4.0 — 2026-08-25 — decisão do titular: **otimização para desempenho**. Consolida o
adendo local-first (Issue #1000, 2026-08-09) e institui a **verificação proporcional ao diff**
(Issue #1286). Nenhuma proteção de produção, dados, LGPD, validade jurídica ou rastreabilidade
foi reduzida; o que mudou foi o custo fixo por tarefa.

## 1. Princípio

A governança do EJC protege produção, dados, validade jurídica e rastreabilidade. Ela **não
pode impedir diagnóstico, auditoria, revisão ou correção autorizada pelo titular** — e também
não pode custar mais do que o risco que mitiga. Aplicação proporcional ao risco:

- leitura e diagnóstico têm ampla liberdade;
- escrita exige Issue, branch, rastreabilidade e testes proporcionais ao diff;
- mudança irreversível exige decisão humana específica;
- produção, segredos e dados reais permanecem fora do alcance operacional dos agentes.

O GitHub é o versionamento, o histórico e o meio de colaboração — **quando disponível**. A
operação é **local-first**: indisponibilidade de GitHub/Actions/runner é problema de
sincronização, não de validade do código, e nunca interrompe edição, checkpoint e validação
(ver §6-B). Toda mudança de arquivo ocorre em branch identificável e termina registrada em
Pull Request; decisões e achados permanecem rastreáveis por Issue, comentário de revisão ou
documento versionado.

## 2. Papéis definidos pela tarefa, não pelo modelo

Qualquer agente pode atuar como auditor, executor, revisor ou verificador, conforme a tarefa e
a autorização do titular.

| Papel | Responsabilidade | Limite principal |
|---|---|---|
| **Titular** | Objetivo, prioridade, decisões jurídicas e exceções do §6-A | Não intervém no ciclo normal com gates verdes |
| **Auditor** | Diagnóstico, testes e achados verificáveis | Não altera produção nem apresenta hipótese como fato |
| **Executor** | Implementa, testa e registra decisões | Não força integração de mudança retida pelo §6-A |
| **Revisor independente** | Diff, segurança, LGPD, validade jurídica, UX, regressão | Não aprova por confiança; exige evidência |
| **CI/GitHub** | Histórico e controles automáticos | Não substitui homologação humana |

O mesmo agente pode auditar e implementar quando autorizado, registrando as duas etapas.
Entrega de risco relevante recebe revisão independente antes do merge.

## 3. Modos de trabalho

- **Somente leitura** (auditoria, revisão, diagnóstico): começa imediatamente, sem Issue e sem
  branch. Pode ler tudo — inclusive arquivos de outros PRs —, executar buscas, lint, testes e
  builds, e reportar em chat, Issue, PR ou documento. Sobreposição com PR não impede leitura.
- **Auditoria corretiva ampla** ("pente fino", "corrija tudo"): o pedido autoriza o diagnóstico
  sistêmico; antes da primeira escrita deve existir **Issue-guarda-chuva**. Achado confirmado,
  relacionado ao objetivo e documentado pode ser corrigido no mesmo trabalho; achado sem relação
  causal é registrado para continuidade sem interromper o escopo atual.
- **Desenvolvimento focal**: `pedido/Issue → branch → implementação → testes proporcionais →
  PR → gates → merge → deploy pela esteira`. Uma Issue pode gerar mais de um PR; um PR pode
  fechar Issues tecnicamente inseparáveis.

## 4. Prioridades

| Nível | Significado | Efeito |
|---|---|---|
| **P0** | Segurança, LGPD, validade jurídica, perda de dado/prova | Bloqueia o release afetado; prioridade máxima |
| **P1** | Integridade funcional, contrato divergente, regressão relevante | Bloqueia a funcionalidade afetada |
| **P2** | UX, desempenho, dívida técnica | Planejamento normal |
| **P3** | Evolução futura | Backlog |

P0 aberto não proíbe trabalho independente em outra área; impede apenas liberar mudança que
dependa do risco não resolvido.

## 5. Concorrência e sobreposição

Leitura em paralelo é livre. Para escrita, arquivo de PR ativo funciona como **lock lógico**:
não se modifica em outra branch sem estratégia explícita — consolidar na branch do PR ativo,
aguardar a integração, dividir por arquivos sem sobreposição ou adiar só a parte incompatível.
Nunca sobrescrever silenciosamente trabalho concorrente.

**Migrations**: o repositório chega ao merge com head único e cadeia linear; somente uma
migration é integrada por vez. A branch seguinte atualiza a base, confere o head, ajusta
número/`down_revision` e repete os testes.

## 6. Regras de execução

1. Não alterar, commitar ou empurrar diretamente na `main`/`master`.
2. Merge e deploy são automáticos com todos os gates verdes e diff fora das exceções do §6-A;
   fora disso a integração espera decisão humana, que o agente jamais contorna.
3. Toda escrita ocorre em branch e termina em PR. Antes do push rodam os **portões locais
   proporcionais ao diff** (§6-B); teste que falhar é investigado e corrigido dentro do escopo.
4. Auditoria ampla exige Issue-guarda-chuva antes da primeira escrita; não é preciso uma Issue
   por achado.
5. Ampliação de escopo para achado relacionado é permitida e registrada no PR.
6. Correção de bug tem teste de regressão quando tecnicamente possível.
7. Regra jurídica exige fonte oficial, vigência, versão e revisão humana (§9).
8. Migration segue o §8 (head, reserva, cadeia validada).
9. Não versionar credencial, token, senha, PII real ou documento de cliente.
10. Não usar comandos destrutivos ou atalhos que eliminem controles de permissão.
11. **O PR com template preenchido é o relatório da entrega** — sem documento duplicado;
    acrescente ao corpo apenas o que o template não cobre (suposições, riscos residuais,
    decisões que exigem ação humana).
12. Chamadas de IA passam pelo gateway; HITL, gate de citações, sanitização de PII e
    kill-switch não podem ser contornados nem incidentalmente.
13. Rota nova nasce protegida; endpoint público exige justificativa registrada.
14. Mudança em autenticação, permissões, uploads, CI/CD ou configuração exige execução e
    registro do `security-auditor` antes da finalização e do merge.

## 6-A. Fluxo autônomo — gates e exceções

Decisão permanente do titular (2026-08-08): no ciclo normal, **nenhuma autorização
intermediária** é exigida para análise, Issue, branch, implementação, testes, commits, push,
PR, merge e deploy.

**Gates obrigatórios (todos verdes para integrar):**

1. portões locais proporcionais ao diff, executados antes do push (§6-B);
2. CI completa (backend + banco/migrations + frontend) — **enquanto o Actions estiver
   indisponível no nível da conta (estado desde ~22/08), este gate é substituído pela
   evidência local registrada no corpo do PR, e o merge é manual, do titular**; quando a
   esteira voltar, o fluxo automático retoma sem novo pedido;
3. travas de governança (`governanca.yml`) e release gate (`ci_guard.sh`) — mesma substituição
   temporária acima;
4. pós-merge: deploy com backup prévio, health-check com confirmação de SHA e smoke
   (`scripts/post_deploy_check.sh`); staging com gates próprios quando `STAGING_ENABLED=1`;
5. rollback automático para a última versão estável em falha de deploy.

**Exceções — intervenção humana obrigatória** (a automação retém e registra o motivo no PR):

1. migration destrutiva ou irreversível;
2. risco concreto de perda ou corrupção de dados;
3. alteração de credenciais ou segredos;
4. alteração crítica de autenticação/autorização;
5. impossibilidade de rollback seguro;
6. alteração estrutural cuja segurança não possa ser validada automaticamente — incluída
   qualquer mudança em workflows, governança, configuração de agentes, nginx, compose,
   `scripts/` (esteira executada na VPS), Dockerfiles, dependências (`requirements*.txt`,
   `package*.json`), núcleo `backend/app/core/`, middlewares, rotas de auth/usuários,
   `pii_crypto` e `ai_gateway`;
7. falha persistente que o agente não consiga resolver autonomamente.

**Rastreabilidade mínima por ciclo:** Issue, PR, commits, resultado de cada gate, artefato de
decisão de migration, SHA implantado, tags de rollback. Alterações pequenas e relacionadas
podem compartilhar Issue e PR — coerência prevalece sobre fragmentação.

## 6-B. Local-first e verificação proporcional ao diff

Consolida o adendo de 2026-08-09 (Issue #1000) como texto canônico.

**Local-first:**

1. Falha de GitHub, Actions, runner ou API não interrompe edição, checkpoint e validação; o
   agente executa o caminho local seguro antes de reportar bloqueio, sem insistir em runner
   morto e sem sondar o Actions — registra o estado uma vez e segue.
2. O gate técnico local de referência é `scripts/ci-local.sh`; workspace sempre em
   branch/worktree/cópia isolada, nunca `/opt/ejc`.
3. Sincronização remota é oportunista e não destrutiva: sem force-push, reset ou rewrite; se o
   remoto divergiu, reconcilia-se em branch segura.
4. Produção continua exclusivamente pela esteira endurecida; local-first não cria deploy
   paralelo nem copia/linka `.env` para contornar a esteira.

**Verificação proporcional** (tabela operacional no `CLAUDE.md`):

| Diff toca | Portão antes do push |
|---|---|
| Só documentação/comentários | Nenhum (declarar docs-only no PR) |
| Só frontend | lint + testes + build do frontend |
| Só backend sem banco | ruff + testes dirigidos na iteração; suíte backend completa uma vez antes do push |
| Banco/models/migrations/seeds | Acima + `alembic upgrade head` do zero em Postgres+pgvector local |
| Backend e frontend | As duas colunas |

Durante a iteração rodam-se só os testes da área em trabalho; o portão completo da linha
correspondente roda **uma vez, antes do push**. A suíte completa da área alterada permanece
obrigatória porque já capturou regressões invisíveis à análise estática; o que esta versão
elimina é o custo da área **não** tocada. O PR declara o que foi testado e o que não foi.

## 7. Proteções não negociáveis

Permanecem proibidos:

- operar em `/opt/ejc` ou contra banco de produção; apontar teste para banco de produção;
- `git push --force`, `git reset --hard`, `git clean -fd`, `rm -rf` fora de área temporária,
  `docker compose down -v`, `docker volume rm`, `dropdb`, `alembic downgrade base`;
- `claude --dangerously-skip-permissions`;
- expor segredo, credencial ou PII em código, log, teste, prompt ou provedor externo;
- desligar silenciosamente RBAC, isolamento de dados, HITL, citation gate, sanitização de PII
  ou controles de auditoria;
- usar massa real de cliente em teste ou homologação;
- expor publicamente Postgres, Redis ou Ollama.

Mudança deliberada de política de segurança ocorre somente por pedido explícito do titular,
com risco, justificativa, teste e rollback documentados.

## 8. Controle de migrations

Antes de ficar pronta para merge: atualizar a base; consultar PRs com migrations; executar
`cd backend && python -m alembic heads`; reservar/ajustar o identificador em
`backend/alembic/MIGRATION_RESERVATIONS.md`; confirmar `down_revision`, head único, upgrade e
rollback aplicável. Migration aplicada em produção não é reescrita — correção estrutural entra
em nova migration. Autogenerate não autoriza `DROP`; migration destrutiva exige backup, plano
de rollback e decisão humana registrada.

## 9. Regras jurídicas

Funcionalidade que produza prazo, cálculo, tese, orientação ou documento jurídico contém:
fonte oficial; vigência e versão; testes de caso normal, borda e exceção; aviso visível de
revisão humana; rastreabilidade do fundamento; linguagem não absoluta sob incerteza. Regra não
homologada pode apoiar análise, mas não vira documento formal automaticamente.

## 10. Autonomia operacional

O pedido direto do titular autoriza as ações de diagnóstico e leitura razoavelmente
necessárias ao objetivo. A escrita pode incluir API, migration, autenticação, RBAC, CI/CD,
Docker, dependência, rota ou código, desde que exista Issue ou Issue-guarda-chuva e a mudança
permaneça fora de produção, em branch, reversível (ou com decisão humana específica), com
testes e impacto documentados, sem extrapolar para assunto sem relação, e com
`security-auditor` quando tocar área sensível. Pedido que **implica** um desses itens já é a
autorização daquele item — e só dele.

Sem autorização repetida por arquivo, comando seguro, teste ou refatoração. Parar e perguntar
apenas quando: duas interpretações plausíveis produzem resultados materialmente diferentes;
há exclusão ou transformação irreversível de dado; a mudança contraria decisão permanente do
titular (§11); a execução depende de credencial, produção ou dado real não disponibilizado
com segurança. Fora disso: assumir a leitura mais provável, registrar a suposição no PR e
seguir. Tarefa com escrita começa vinculada a Issue e termina em PR — que, preenchido, **é**
o relatório (§6, regra 11).

## 11. Decisões permanentes do titular

Decisão permanente só é reaberta por novo pedido explícito do titular.

| Decisão | Estado | Observação |
|---|---|---|
| **Fluxo autônomo — merge/deploy automáticos com gates verdes** | Vigente desde 2026-08-08 | Exceções fechadas no §6-A. |
| **Operação local-first** | Vigente desde 2026-08-09 (Issue #1000) | Consolidada no §6-B desta versão. |
| **Verificação proporcional ao diff + relatório unificado no PR** | Vigente desde 2026-08-25 (Issue #1286) | Portões escalonados pelo que o diff toca; suíte completa apenas da área alterada. |
| **2FA — não implementar por padrão** | Vigente desde 2026-07-26 | `TWO_FACTOR_AUTH_ENABLED` desligado por padrão; kill-switch preservado. Auditoria registra o risco, sem tratá-lo como correção obrigatória. |

## 12. Exceção de bot de manutenção de dependências

O step "Descricao do PR preenchida" de `.github/workflows/governanca.yml` é pulado somente
quando o autor original do PR **e** o ator do evento pertencem à lista fechada:

```json
["dependabot[bot]"]
```

A exceção dispensa apenas Issue vinculada e preenchimento manual do modelo — nada mais. A
lista do workflow e deste documento devem coincidir; ampliá-la exige decisão do titular.

## 13. Documentos relacionados

- `CLAUDE.md` — mapa técnico e instruções operacionais do executor;
- `AGENTS.md` — resumo comum aos agentes;
- `docs/FLUXO_DE_DESENVOLVIMENTO.md` — fluxos por modo de trabalho;
- `docs/CRITERIOS_DE_ACEITE.md` — critérios de auditoria do resultado;
- `docs/RELEASE_CHECKLIST.md` — controles de liberação;
- `backend/alembic/MIGRATION_RESERVATIONS.md` — coordenação de migrations;
- `docs/GOVERNANCA_FASE2.md` — automações de governança;
- `docs/GOVERNANCA_IA_ADDENDUM_LOCAL_FIRST.md` — histórico; consolidado no §6-B.
