# AGENTS.md — regras comuns a qualquer agente de IA no EJC

Aplica-se a ChatGPT, Codex, Claude Code e a qualquer outro agente que leia ou escreva neste
repositório. As seções marcadas como **executor** valem apenas para quem implementa; as
marcadas como **revisor/auditor** valem para quem só lê e comenta. Os limites da seção
seguinte valem para todos.

## Fonte única

As regras canônicas estão em **`docs/GOVERNANCA_IA.md`**. Este arquivo é um resumo
operacional; se algo aqui parecer contrariar o documento canônico, o canônico prevalece e a
divergência deve ser corrigida por PR.

Leitura obrigatória antes de trabalhar:

1. `docs/GOVERNANCA_IA.md` — papéis, limites, segurança, migrations, regra jurídica;
2. `CLAUDE.md` — mapa técnico do repositório e regras do executor;
3. `docs/FLUXO_DE_DESENVOLVIMENTO.md` — o ciclo da tarefa;
4. `docs/CRITERIOS_DE_ACEITE.md` — o que será cobrado no review;
5. a Issue da tarefa, integralmente — ou, quando a tarefa chega por pedido direto do titular,
   a mensagem que a originou (`docs/GOVERNANCA_IA.md` §10, "Tarefa que chega sem Issue").

## Prioridade

- **P0** — segurança, LGPD e validade jurídica.
- **P1** — integridade funcional.
- **P2** — UX, desempenho e organização.
- **P3** — melhorias futuras.

## Processo

```
Issue → branch → implementação → testes → PR draft → auditoria → correções → CI → homologação → merge
```

Uma Issue, uma branch, um PR. Correção de review vai na mesma branch e no mesmo PR — nunca
em um PR novo.

## Limites que nenhum agente ultrapassa

1. Não commitar, empurrar nem alterar a `main` diretamente.
2. Não fazer merge e não executar deploy de produção.
3. Não trabalhar no diretório de produção nem contra o banco de produção.
4. Não versionar segredo, credencial, token, senha, PII ou documento real de cliente.
5. Não usar `git push --force`, `git reset --hard`, `git clean -fd`, `rm -rf`,
   `docker compose down -v`, `docker volume rm`, `dropdb`, `alembic downgrade base`, nem
   `claude --dangerously-skip-permissions`.
6. Não editar migration já aplicada em produção.
7. Não desligar HITL, gate de citações, sanitização de PII ou kill-switch de IA.
8. Não ampliar o escopo da Issue sem justificativa registrada no PR.
9. Não afirmar regra jurídica sem fonte oficial, vigência e teste.
10. Não editar arquivos que já estão sendo alterados por outro PR aberto — checar antes
    (`git diff --name-only origin/main...origin/<branch>` dos PRs em aberto).

## Antes de começar — **executor** (quem escreve código)

- [ ] `main` local atualizada.
- [ ] PRs abertos listados e conferidos quanto a sobreposição de arquivos.
- [ ] Head do Alembic verificado (`cd backend && python -m alembic heads`) e número reservado,
      se a tarefa mexe em banco — e nenhuma outra frente com migration em aberto.
- [ ] Problema reproduzido e diagnóstico registrado.
- [ ] Branch exclusiva criada a partir da `main` atualizada.

## Antes de começar — **revisor/auditor** (ChatGPT, Codex, qualquer agente que não implementa)

Não cria branch, não altera arquivo da branch sob revisão, não empurra commit. O trabalho é
somente leitura e o resultado vira comentário no PR.

- [ ] Issue e PR lidos por inteiro, incluindo o relatório do executor.
- [ ] Diff conferido contra o código (`git diff origin/main...origin/<branch>`), não contra a
      descrição do PR.
- [ ] Cinco camadas de `docs/CRITERIOS_DE_ACEITE.md` aplicadas.
- [ ] Achado registrado como comentário de review, com arquivo, linha e evidência.

## Ao terminar — executor

Relatório obrigatório, no PR:

- arquivos criados e modificados;
- comandos executados e resultado dos testes;
- migrations criadas e o head resultante;
- evidências (saída de teste, captura, log);
- impacto jurídico e impacto LGPD;
- riscos residuais e limitações;
- o que exige decisão humana.

## Divergência entre agentes

Registrada no PR, decidida por evidência. Assunto jurídico sobe para o titular; assunto de
segurança resolve-se pelo lado mais restritivo; empate sem evidência para o trabalho e sobe
para o titular. Detalhes em `docs/GOVERNANCA_IA.md`, seção 5.
