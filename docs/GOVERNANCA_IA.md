# Governança de agentes de IA no EJC

> **Documento canônico.** `CLAUDE.md`, `AGENTS.md` e os demais documentos de processo
> traduzem estas regras para cada agente. Em caso de divergência, este arquivo prevalece.

Versão: 3.1 — 2026-08-09 — **fluxo autônomo local-first**: trabalho e validação não param por
indisponibilidade do GitHub; merge/deploy continuam condicionados aos gates e às exceções do §6-A.

## 1. Princípio

A governança do EJC existe para proteger produção, dados, validade jurídica e rastreabilidade.
Ela **não pode impedir diagnóstico, auditoria, revisão ou correção autorizada pelo titular**.

O GitHub permanece a fonte remota permanente de verdade e o destino final da rastreabilidade do
projeto. Ele, porém, **não é dependência operacional para preservar trabalho ou executar testes**.
Pedido direto do titular por chat é autorização válida para iniciar diagnóstico somente de leitura.
Antes de qualquer escrita deve existir registro do objetivo, achados e escopo:

- por Issue/Issue-guarda-chuva, quando o GitHub estiver disponível; ou
- por registro local de contingência, associado à branch e ao SHA, quando a indisponibilidade do
  GitHub for comprovada.

O registro local segue modelo **store-and-forward**: não substitui a rastreabilidade permanente e
deve ser sincronizado como Issue/PR assim que o GitHub voltar. Toda mudança de arquivo ocorre em
branch identificável; nenhum modo offline autoriza escrever diretamente em `main`/`master`.

As decisões, os achados e o escopo devem permanecer rastreáveis por Issue, comentário de revisão,
documento versionado ou, durante a contingência, artefato local protegido. Toda mudança deve
terminar registrada em Pull Request antes de integração permanente à `main`.

A governança deve ser aplicada de forma proporcional ao risco:

- leitura e diagnóstico têm ampla liberdade;
- escrita exige registro de tarefa, branch, rastreabilidade e testes;
- mudança irreversível exige decisão humana específica;
- produção, segredos e dados reais permanecem protegidos pelos controles desta governança.

## 2. Papéis definidos pela tarefa, não pelo modelo

ChatGPT, Claude Code, Codex ou outro agente podem atuar como **auditor**, **executor**,
**revisor** ou **verificador**, conforme a tarefa e a autorização do titular. Nenhum fornecedor
de IA fica permanentemente impedido de implementar ou revisar.

| Papel da tarefa | Responsabilidade | Limite principal |
|---|---|---|
| **Titular** | Define objetivo, prioridade, decisões jurídicas e decide as exceções do §6-A | Não intervém no ciclo normal: merge e deploy são automáticos com gates verdes |
| **Auditor** | Lê todo o escopo necessário, executa diagnóstico, testes e produz achados verificáveis | Não altera produção nem apresenta hipótese como fato |
| **Executor** | Implementa correções ou funcionalidades, escreve testes e registra decisões | Não força integração de mudança retida por exceção do §6-A |
| **Revisor independente** | Revisa diff, segurança, LGPD, validade jurídica, UX e regressão | Não aprova por confiança; exige evidência |
| **CI/GitHub** | Mantém histórico remoto e executa controles adicionais | Não substitui CI local, homologação ou contingência |

O mesmo agente pode auditar e implementar quando isso for expressamente autorizado, desde que
registre as duas etapas. Toda entrega de risco relevante ou significativo deve receber revisão
independente antes do merge.

## 3. Modos de trabalho

### 3.1 Auditoria ou revisão somente leitura

Pode começar imediatamente, sem Issue e sem branch. O auditor pode:

- ler todo o repositório, documentação, histórico e PRs abertos quando acessíveis;
- examinar arquivos já tocados por outras branches;
- executar buscas, lint, testes, builds, análise estática e inspeção de dependências;
- comparar código, documentação, rotas, banco, UX, segurança e regras jurídicas;
- produzir relatório em chat, Issue, comentário de PR, documento versionado ou artefato local.

A sobreposição com outro PR **não impede leitura nem diagnóstico**.

### 3.2 Auditoria corretiva ampla

Quando o titular pede “pente fino”, “corrija tudo”, “auditoria completa com correção” ou comando
equivalente, o pedido autoriza o diagnóstico sistêmico. Antes de criar branch de implementação,
alterar arquivo ou produzir commit, deve existir uma **Issue-guarda-chuva** ou, se o GitHub estiver
indisponível, um **registro local de contingência** que será sincronizado posteriormente. O trabalho
pode usar um ou mais PRs organizados por dependência técnica, risco ou facilidade de revisão.

Achados podem ser corrigidos no mesmo trabalho quando forem:

1. confirmados por evidência;
2. relacionados ao objetivo sistêmico;
3. necessários para que a correção principal funcione, seja testável ou não deixe regressão;
4. documentados no PR ou no registro local de contingência, com impacto e rollback.

Achado sem relação causal ou que aumente materialmente o risco deve ser registrado para
continuidade, mas não precisa interromper o trabalho atual.

### 3.3 Desenvolvimento focal

Fluxo normal, com GitHub disponível:

```text
pedido/Issue → branch → implementação → testes locais → PR → gates automatizados verdes
            → merge automático → deploy automático (staging quando ativo → produção)
            → health-check + smoke → rollback automático em falha
```

Fluxo de contingência, com GitHub indisponível:

```text
pedido → registro local → branch local → checkpoint → implementação → CI local
      → checkpoint final → sync best-effort quando GitHub voltar → Issue/PR/gates remotos
      → integração/deploy pelo caminho seguro aplicável
```

Uma Issue pode originar mais de um PR quando a divisão reduzir risco, conflito ou tamanho do diff.
Um PR pode atender mais de uma Issue quando as correções forem tecnicamente inseparáveis.

## 4. Prioridades

| Nível | Significado | Efeito |
|---|---|---|
| **P0** | Segurança, LGPD, validade jurídica, perda de dado ou prova | Bloqueia release afetado e recebe prioridade máxima |
| **P1** | Integridade funcional, contrato divergente, regressão relevante | Bloqueia a funcionalidade afetada |
| **P2** | UX, desempenho, organização e dívida técnica | Planejamento normal |
| **P3** | Evolução futura | Backlog |

P0 aberto **não proíbe auditoria, correção ou trabalho independente em outra área**. Ele impede
apenas liberar mudança que dependa do risco não resolvido.

## 5. Concorrência e sobreposição

Leitura e auditoria podem ocorrer em paralelo sem restrição de arquivos.

Para escrita, arquivo pertencente a PR ativo **não deve ser modificado em outra branch**. Quando o
GitHub estiver acessível, o executor verifica PRs concorrentes antes de editar. Em contingência
sem acesso ao remoto, **bloqueia ou adia a alteração quando a titularidade (ownership) do arquivo
não puder ser confirmada remotamente**. Não escrever arquivo baseando-se apenas em informação local
sem metadata remota válida sobre propriedade/conflito. Exigir metadata remota válida OU estratégia
explícita de consolidação (merge/reconciliação) antes de escrever. Registrar a limitação de
conectividade no relatório/log.

Quando houver sobreposição confirmada, escolher uma destas opções:

1. consolidar a alteração na mesma branch do PR ativo;
2. aguardar a integração do PR ativo e atualizar a branch seguinte;
3. dividir o trabalho por arquivos sem sobreposição;
4. adiar somente a parte incompatível.

Não é permitido sobrescrever silenciosamente trabalho concorrente. A tarefa deve parar somente a
parte da escrita que alcançar arquivo de outro PR ativo e ainda não possuir estratégia explícita de
consolidação ou sequência.

### Migrations

O repositório deve chegar ao merge com **head único e cadeia linear**. Mais de uma branch pode
analisar ou preparar mudança de banco, mas somente uma migration é integrada por vez. A branch
seguinte deve atualizar a base, conferir o head, ajustar número e `down_revision` e repetir os
testes antes de ficar pronta para merge.

Em modo offline, migration nova pode ser preparada somente após conferir o head local e deve ser
revalidada contra o head remoto atual antes de sincronização/merge. Nenhuma reserva local prevalece
sobre migration que tenha sido integrada remotamente durante a indisponibilidade.

## 6. Regras de execução

1. Não alterar, commitar ou empurrar diretamente na `main`/`master`.
2. Merge e deploy ocorrem **automaticamente** quando todos os gates aplicáveis estiverem verdes e
   o diff não alcançar exceção do §6-A. Fora dessas condições, a integração espera a decisão
   prevista pela governança; o agente jamais contorna os gates.
3. Toda escrita ocorre em branch identificável. Com GitHub disponível, termina registrada em PR.
   Em contingência, pode avançar em branch local com registro e checkpoints, mas deve sincronizar
   Issue/branch/PR antes de integração permanente à `main`. Testes locais são obrigatórios antes de
   qualquer publicação.
4. Auditoria ampla exige Issue-guarda-chuva ou registro local de contingência antes da primeira
   escrita; não é obrigatório criar uma Issue por achado.
5. Escopo pode ser ampliado para achados relacionados, desde que a ampliação seja registrada.
6. Correção de bug deve ter teste de regressão quando tecnicamente possível.
7. Regra jurídica exige fonte oficial, vigência, versão e revisão humana.
8. Migration exige conferência do head, reserva e validação da cadeia antes do merge.
9. Não versionar nem copiar para contingência credencial, token, senha, PII real ou documento de
   cliente.
10. Não usar comandos destrutivos ou atalhos que eliminem controles de permissão.
11. Toda entrega de escrita termina com arquivos, comandos, testes, riscos, limitações e rollback.
12. Chamadas de IA passam pelo gateway; HITL, gate de citações, sanitização de PII e kill-switch
    não podem ser contornados incidentalmente.
13. Rota nova nasce protegida; endpoint público exige justificativa registrada.
14. Mudança sensível envolvendo autenticação, permissões, uploads, CI/CD ou configuração exige
    execução e registro do `security-auditor` antes da finalização e do merge.
15. Falha de GitHub/DNS/Actions é tratada como falha de infraestrutura externa: criar checkpoint,
    marcar modo offline, continuar trabalho/testes locais e sincronizar posteriormente. Não repetir
    indefinidamente a mesma chamada remota nem pedir intervenção humana quando houver alternativa
    local segura.

## 6-A. Fluxo autônomo — gates e exceções

Decisões permanentes do titular:

- 2026-08-08: no ciclo normal de desenvolvimento, **nenhuma autorização intermediária é exigida**
  para análise, Issue, branch, implementação, testes, commits, push, abertura/atualização de PR,
  merge e deploy; exceções desta seção permanecem retidas;
- 2026-08-09: indisponibilidade temporária de GitHub/GitHub Actions **não deve interromper o
  desenvolvimento**. O executor escolhe automaticamente a alternativa local-first segura e
  sincroniza quando o serviço remoto voltar, sem reduzir controles de segurança.

O GitHub atua como versionamento remoto, auditoria e CI/CD — não como ponto de espera humana nem
como requisito para checkpoint ou CI local.

**Gates obrigatórios para integrar/liberar:**

1. testes locais executados sobre o SHA candidato;
2. CI completa equivalente (backend + banco/migrations + frontend), executada no GitHub quando
   disponível ou pelo `scripts/ci-local.sh` na contingência; quando o GitHub voltar antes da
   integração, seus gates remotos complementam a prova local;
3. travas de governança e release gate (`ci_guard.sh`) aplicáveis ao diff;
4. revisão independente para entrega de risco relevante/significativo;
5. deploy com backup prévio, health-check com confirmação de SHA e smoke test
   (`scripts/post_deploy_check.sh`), staging com gates próprios quando ativo;
6. rollback automático para a última versão estável em falha de deploy.

**Exceções — intervenção humana obrigatória** (o workflow `auto-integracao.yml`, quando disponível,
retém e registra o motivo no PR; em contingência o executor preserva a retenção local):

1. migration destrutiva ou irreversível;
2. risco concreto de perda ou corrupção de dados;
3. alteração de credenciais ou segredos;
4. alteração crítica de autenticação/autorização;
5. impossibilidade de rollback seguro;
6. alteração estrutural cuja segurança não possa ser validada automaticamente — incluída qualquer
   mudança em workflows, governança, configuração de agentes, nginx, compose, `scripts/` (esteira
   executada na VPS), Dockerfiles, dependências (`requirements*.txt`, `package*.json`), núcleo
   `backend/app/core/`, middlewares, rotas de auth/usuários, `pii_crypto` e `ai_gateway`;
7. falha persistente que o agente não consiga resolver autonomamente.

Pedido explícito do titular que decide conscientemente uma dessas exceções constitui a decisão
humana exigida **para aquela mudança e escopo**, mas não autoriza bypass de testes, revisão,
backup, rollback ou proteção de produção.

**Concorrência:** segue o §5 — dois agentes não alteram os mesmos arquivos sem estratégia explícita
de consolidação. Em outage, a falta de visibilidade remota é registrada e a reconciliação é
obrigatória antes de integração.

**Rastreabilidade mínima por ciclo:** Issue ou registro local pendente, branch, checkpoints/commits,
resultado de cada gate, PR antes da integração permanente, artefato de decisão de migration quando
aplicável, SHA implantado (`.deployed_sha`), tags/imagens de rollback e versão anterior.

Nada neste modo reduz backup, rollback, integridade de banco, proteção de segredos, HITL,
citation gate, sanitização de PII ou isolamento entre ambientes.

## 7. Proteções não negociáveis

Permanecem proibidos:

- desenvolver diretamente no checkout de produção ou operar contra banco de produção fora dos
  scripts/esteiras explicitamente autorizados e auditados;
- `git push --force`, `git reset --hard`, `git clean -fd`, `rm -rf` fora de área temporária,
  `docker compose down -v`, `docker volume rm`, `dropdb`, `alembic downgrade base`;
- `claude --dangerously-skip-permissions`;
- expor segredo, credencial ou PII em código, checkpoint, bundle, log, teste, prompt ou provedor
  externo;
- desligar silenciosamente RBAC, isolamento de dados, HITL, citation gate, sanitização de PII ou
  controles de auditoria;
- usar massa real de cliente em teste ou homologação;
- usar indisponibilidade do GitHub como justificativa para force-push, bypass de revisão, cópia
  manual para produção ou alteração direta de `.env`/banco.

Mudança deliberada de política de segurança pode ocorrer somente por pedido explícito do titular,
com risco, justificativa, teste e rollback documentados.

## 8. Controle de migrations

Antes de uma migration ficar pronta para merge:

1. atualizar/reconciliar a base da branch com a fonte remota atual quando acessível;
2. consultar PRs com migrations;
3. executar `cd backend && python -m alembic heads`;
4. reservar ou ajustar o identificador em `backend/alembic/MIGRATION_RESERVATIONS.md`;
5. confirmar `down_revision`, head único, upgrade e rollback aplicável.

Migration aplicada em produção não é reescrita para mudar schema. Correção estrutural entra em
nova migration. Alteração puramente não funcional em migration histórica deve ser excepcional,
justificada e demonstrada como incapaz de alterar `upgrade()`/`downgrade()`.

Autogenerate não autoriza `DROP`. Migration destrutiva exige backup, plano de rollback e decisão
humana registrada.

## 9. Regras jurídicas

Funcionalidade que produza prazo, cálculo, tese, orientação ou documento jurídico deve conter:

1. fonte oficial;
2. vigência e versão da regra;
3. testes de caso normal, borda e exceção aplicável;
4. aviso visível de revisão humana;
5. rastreabilidade da origem do cálculo ou fundamento;
6. linguagem não absoluta quando houver incerteza ou dependência fática.

Regra não homologada pode apoiar análise, mas não deve virar documento formal automaticamente.

## 10. Autonomia operacional

O pedido direto do titular autoriza todas as ações de diagnóstico e leitura **razoavelmente
necessárias** ao objetivo. A escrita pode incluir API, migration, autenticação, RBAC, CI/CD,
Docker, dependência, rota ou código, desde que exista Issue/Issue-guarda-chuva ou registro local de
contingência e a mudança:

- permaneça fora de produção durante desenvolvimento;
- seja feita em branch;
- seja reversível ou tenha decisão humana específica quando irreversível;
- tenha testes e impacto documentados;
- não extrapole para assunto sem relação com o objetivo;
- passe por `security-auditor` quando envolver autenticação, permissões, uploads, CI/CD ou
  configuração.

O agente não precisa pedir autorização repetida para cada arquivo, comando seguro, teste ou
refatoração necessária. Quando uma ferramenta/remoto falhar, deve procurar automaticamente uma
alternativa segura já disponível (checkout local, checkpoint, CI local, outro conector autorizado)
antes de interromper o trabalho.

Deve parar e pedir decisão apenas quando:

1. duas interpretações plausíveis produzirem resultados materialmente diferentes;
2. houver exclusão ou transformação irreversível de dado;
3. a mudança contrariar decisão permanente do titular sem novo pedido explícito;
4. a execução depender de credencial, produção ou dado real não disponibilizado com segurança e
   não existir canal alternativo já autorizado;
5. todas as alternativas seguras disponíveis tiverem falhado.

Toda tarefa deve terminar em relatório com arquivos alterados ou “nenhum”, comandos, testes,
evidências, riscos residuais, limitações, rollback e decisões que exigem ação humana. Tarefa com
escrita deve começar vinculada a Issue/Issue-guarda-chuva ou registro local de contingência e
terminar em PR antes de integração permanente.

## 11. Decisões permanentes do titular

Decisão permanente só é reaberta por novo pedido explícito do titular.

| Decisão | Estado | Observação |
|---|---|---|
| **Fluxo local-first — falha de GitHub não interrompe desenvolvimento** | Vigente desde 2026-08-09 | Checkpoint + CI local + store-and-forward; sincronização remota posterior. Não reduz gates de produção. |
| **Fluxo autônomo — merge/deploy automáticos com gates verdes** | Vigente desde 2026-08-08 | Ciclo normal sem intervenção humana; exceções fechadas no §6-A. Reverter exige novo pedido explícito do titular. |
| **2FA — não implementar por padrão** | Vigente desde 2026-07-26 | `TWO_FACTOR_AUTH_ENABLED` permanece desligado por padrão e o kill-switch é preservado. Auditoria pode registrar o risco, mas não tratá-lo como correção obrigatória contra a decisão do titular. |

## 12. Exceção de bot de manutenção de dependências

O step “Descricao do PR preenchida” de `.github/workflows/governanca.yml` é pulado somente quando
o autor original do PR **e** o ator do evento pertencem à lista fechada abaixo:

```json
["dependabot[bot]"]
```

A exceção dispensa apenas Issue vinculada e preenchimento manual do modelo. Não dispensa controle
de migration, segredo, branch ou demais verificações. A lista do workflow e deste documento deve
coincidir exatamente. Ampliá-la exige decisão do titular.

## 13. Documentos relacionados

- `CLAUDE.md` — mapa técnico e instruções operacionais do executor;
- `AGENTS.md` — resumo comum aos agentes;
- `docs/FLUXO_DE_DESENVOLVIMENTO.md` — fluxos por modo de trabalho;
- `docs/CRITERIOS_DE_ACEITE.md` — critérios de auditoria do resultado;
- `docs/RELEASE_CHECKLIST.md` — controles de liberação;
- `docs/OPERACAO_LOCAL_FIRST.md` — contingência GitHub/DNS/Actions e recuperação local;
- `docs/CI_SEM_GITHUB.md` — execução dos gates fora do GitHub Actions;
- `backend/alembic/MIGRATION_RESERVATIONS.md` — coordenação de migrations;
- `docs/GOVERNANCA_FASE2.md` — automações de governança.
