# Governança de agentes de IA no EJC

> **Documento canônico.** `CLAUDE.md`, `AGENTS.md` e os demais documentos de processo
> traduzem estas regras para cada agente. Em caso de divergência, este arquivo prevalece.

Versão: 2.0 — 2026-08-05.

## 1. Princípio

A governança do EJC existe para proteger produção, dados, validade jurídica e rastreabilidade.
Ela **não pode impedir diagnóstico, auditoria, revisão ou correção autorizada pelo titular**.

O GitHub é a fonte permanente de verdade do projeto. Pedido direto do titular por chat é
autorização válida para começar; a decisão, os achados e as mudanças devem ser registrados no
GitHub até o encerramento do trabalho, por Issue, Pull Request, comentário de review ou documento
versionado.

A governança deve ser aplicada de forma proporcional ao risco:

- leitura e diagnóstico têm ampla liberdade;
- escrita exige branch, rastreabilidade e testes;
- mudança irreversível exige decisão humana específica;
- produção, segredos e dados reais permanecem fora do alcance operacional dos agentes.

## 2. Papéis definidos pela tarefa, não pelo modelo

ChatGPT, Claude Code, Codex ou outro agente podem atuar como **auditor**, **executor**,
**revisor** ou **verificador**, conforme a tarefa e a autorização do titular. Nenhum fornecedor
de IA fica permanentemente impedido de implementar ou revisar.

| Papel da tarefa | Responsabilidade | Limite principal |
|---|---|---|
| **Titular** | Define objetivo, prioridade, decisões jurídicas e autorização de merge/deploy | Não precisa revisar código linha a linha |
| **Auditor** | Lê todo o escopo necessário, executa diagnóstico, testes e produz achados verificáveis | Não altera produção nem apresenta hipótese como fato |
| **Executor** | Implementa correções ou funcionalidades, escreve testes e registra decisões | Não faz merge/deploy sem autorização humana |
| **Revisor independente** | Revisa diff, segurança, LGPD, validade jurídica, UX e regressão | Não aprova por confiança; exige evidência |
| **CI/GitHub** | Mantém histórico e executa controles automáticos | Não substitui homologação humana |

O mesmo agente pode auditar e implementar quando isso for expressamente autorizado, desde que
registre as duas etapas e submeta o resultado a revisão independente quando o risco justificar.

## 3. Modos de trabalho

### 3.1 Auditoria ou revisão somente leitura

Pode começar imediatamente, sem Issue e sem branch. O auditor pode:

- ler todo o repositório, documentação, histórico e PRs abertos;
- examinar arquivos já tocados por outras branches;
- executar buscas, lint, testes, builds, análise estática e inspeção de dependências;
- comparar código, documentação, rotas, banco, UX, segurança e regras jurídicas;
- produzir relatório em chat, Issue, comentário de PR ou documento versionado.

A sobreposição com outro PR **não impede leitura nem diagnóstico**.

### 3.2 Auditoria corretiva ampla

Quando o titular pede “pente fino”, “corrija tudo”, “auditoria completa com correção” ou comando
equivalente, o pedido autoriza um escopo sistêmico. O trabalho pode usar uma **Issue-guarda-chuva**
e um ou mais PRs organizados por dependência técnica, risco ou facilidade de revisão.

Achados podem ser corrigidos no mesmo trabalho quando forem:

1. confirmados por evidência;
2. relacionados ao objetivo sistêmico;
3. necessários para que a correção principal funcione, seja testável ou não deixe regressão;
4. documentados no PR, com impacto e rollback.

Achado sem relação causal ou que aumente materialmente o risco deve ser registrado para
continuidade, mas não precisa interromper o trabalho atual.

### 3.3 Desenvolvimento focal

Para funcionalidade ou bug específico, permanece o fluxo normal:

```
pedido/Issue → branch → implementação → testes → PR → revisão → homologação → merge autorizado
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

Para escrita, PR aberto no mesmo arquivo é um **risco a administrar**, não uma proibição absoluta.
Antes de editar, o executor deve verificar o diff concorrente e escolher uma destas opções:

1. trabalhar em trechos ou funções independentes e registrar a sobreposição;
2. coordenar a ordem de merge e rebase;
3. consolidar as mudanças numa única branch;
4. adiar somente a parte que realmente conflita.

A tarefa só deve parar quando a concorrência produzir duas soluções incompatíveis para o mesmo
comportamento ou risco concreto de perda de trabalho.

### Migrations

O repositório deve chegar ao merge com **head único e cadeia linear**. Mais de uma branch pode
analisar ou preparar mudança de banco, mas somente uma migration é integrada por vez. A branch
seguinte deve atualizar a base, conferir o head, ajustar número e `down_revision` e repetir os
testes antes de ficar pronta para merge.

## 6. Regras de execução

1. Não alterar, commitar ou empurrar diretamente na `main`/`master`.
2. Não fazer merge nem deploy de produção sem autorização humana expressa.
3. Toda escrita ocorre em branch identificável e termina registrada em PR.
4. Auditoria ampla pode usar Issue-guarda-chuva; não é obrigatório criar uma Issue por achado.
5. Escopo pode ser ampliado para achados relacionados, desde que a ampliação seja registrada.
6. Correção de bug deve ter teste de regressão quando tecnicamente possível.
7. Regra jurídica exige fonte oficial, vigência, versão e revisão humana.
8. Migration exige conferência do head, reserva e validação da cadeia antes do merge.
9. Não versionar credencial, token, senha, PII real ou documento de cliente.
10. Não usar comandos destrutivos ou atalhos que eliminem controles de permissão.
11. Toda entrega de escrita termina com arquivos, comandos, testes, riscos, limitações e rollback.
12. Chamadas de IA passam pelo gateway; HITL, gate de citações, sanitização de PII e kill-switch
    não podem ser contornados incidentalmente.
13. Rota nova nasce protegida; endpoint público exige justificativa registrada.

## 7. Proteções não negociáveis

Permanecem proibidos:

- operar em `/opt/ejc` ou contra banco de produção;
- `git push --force`, `git reset --hard`, `git clean -fd`, `rm -rf` fora de área temporária,
  `docker compose down -v`, `docker volume rm`, `dropdb`, `alembic downgrade base`;
- `claude --dangerously-skip-permissions`;
- expor segredo, credencial ou PII em código, log, teste, prompt ou provedor externo;
- desligar silenciosamente RBAC, isolamento de dados, HITL, citation gate, sanitização de PII ou
  controles de auditoria;
- usar massa real de cliente em teste ou homologação.

Mudança deliberada de política de segurança pode ocorrer somente por pedido explícito do titular,
com risco, justificativa, teste e rollback documentados.

## 8. Controle de migrations

Antes de uma migration ficar pronta para merge:

1. atualizar a base da branch;
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

O pedido direto do titular autoriza todas as ações **razoavelmente necessárias** ao objetivo,
inclusive alterar API, migration, autenticação, RBAC, CI/CD, Docker, dependência, rota ou código,
desde que a mudança:

- permaneça fora de produção;
- seja feita em branch;
- seja reversível ou tenha decisão humana específica quando irreversível;
- tenha testes e impacto documentados;
- não extrapole para assunto sem relação com o objetivo.

O agente não precisa pedir autorização repetida para cada arquivo, comando seguro, teste ou
refatoração necessária. Deve parar e pedir decisão apenas quando:

1. duas interpretações plausíveis produzirem resultados materialmente diferentes;
2. houver exclusão ou transformação irreversível de dado;
3. a mudança contrariar decisão permanente do titular;
4. a execução depender de credencial, produção ou dado real não disponibilizado com segurança.

Uma tarefa pode começar sem Issue. Auditoria somente leitura pode terminar em relatório; tarefa
com escrita deve terminar vinculada a Issue ou Issue-guarda-chuva e PR.

## 11. Decisões permanentes do titular

Decisão permanente só é reaberta por novo pedido explícito do titular.

| Decisão | Estado | Observação |
|---|---|---|
| **2FA — não implementar por padrão** | Vigente desde 2026-07-26 | `TWO_FACTOR_AUTH_ENABLED` permanece desligado por padrão e o kill-switch é preservado. Auditoria pode registrar o risco, mas não tratá-lo como correção obrigatória contra a decisão do titular. |

## 12. Exceção de bot de manutenção de dependências

O step “Descricao do PR preenchida” de `.github/workflows/governanca.yml` é pulado somente quando
o autor original do PR **e** o ator do evento pertencem à lista fechada abaixo:

```json
["dependabot[bot]"]
```

A exceção dispensa apenas Issue vinculada e preenchimento manual do template. Não dispensa
controle de migration, segredo, branch ou demais verificações. A lista do workflow e deste
documento deve coincidir exatamente. Ampliá-la exige decisão do titular.

## 13. Documentos relacionados

- `CLAUDE.md` — mapa técnico e instruções operacionais do executor;
- `AGENTS.md` — resumo comum aos agentes;
- `docs/FLUXO_DE_DESENVOLVIMENTO.md` — fluxos por modo de trabalho;
- `docs/CRITERIOS_DE_ACEITE.md` — critérios de auditoria do resultado;
- `docs/RELEASE_CHECKLIST.md` — controles de liberação;
- `backend/alembic/MIGRATION_RESERVATIONS.md` — coordenação de migrations;
- `docs/GOVERNANCA_FASE2.md` — automações de governança.
