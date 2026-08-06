# AGENTS.md — regras comuns aos agentes de IA no EJC

Aplica-se a ChatGPT, Codex, Claude Code e a qualquer agente que leia ou escreva neste
repositório.

## Fonte canônica

As regras prevalentes estão em `docs/GOVERNANCA_IA.md`. Este arquivo é um resumo operacional.
Em caso de divergência, siga o documento canônico e registre a necessidade de harmonização.

Leitura recomendada conforme a tarefa:

1. `docs/GOVERNANCA_IA.md` — autonomia, modos de trabalho e proteções;
2. `CLAUDE.md` — mapa técnico do repositório;
3. `docs/FLUXO_DE_DESENVOLVIMENTO.md` — fluxo por tipo de tarefa;
4. `docs/CRITERIOS_DE_ACEITE.md` — critérios de revisão;
5. pedido do titular, Issue ou PR que originou o trabalho.

## Modos de trabalho

### Auditoria ou revisão somente leitura

Pode começar sem Issue e sem branch. O agente pode ler todo o repositório e PRs abertos,
comparar branches, executar buscas, lint, testes, builds e produzir relatório. Arquivo tocado
por outro PR **não fica proibido para leitura ou diagnóstico**.

### Auditoria corretiva ampla

Pedido do titular para “pente fino”, “corrigir tudo”, “auditoria completa com correção” ou
comando equivalente autoriza o diagnóstico sistêmico. Antes de criar branch de implementação,
alterar arquivo ou produzir commit, crie uma Issue-guarda-chuva e organize um ou mais PRs por
dependência, risco ou facilidade de revisão.

Achado confirmado e relacionado ao objetivo pode ser corrigido no mesmo trabalho, desde que o
PR registre evidência, impacto, testes e rollback. Achado sem relação causal deve ser reportado,
mas não interrompe o que já foi autorizado.

### Desenvolvimento focal

Para bug ou funcionalidade específica, use branch própria, testes e PR vinculado ao pedido ou
Issue. Uma Issue pode gerar mais de um PR; um PR pode fechar Issues tecnicamente inseparáveis.

## Papéis

O papel é definido pela tarefa, não pelo modelo. Qualquer agente autorizado pode auditar,
implementar, revisar ou verificar. O mesmo agente pode auditar e corrigir quando autorizado,
mas toda entrega de risco relevante ou significativo deve receber revisão independente antes do
merge.

## Regras de escrita

- Nunca alterar a `main`/`master` diretamente.
- Toda escrita exige Issue ou Issue-guarda-chuva, ocorre em branch e termina registrada em PR.
- Verificar PRs concorrentes antes de editar.
- Não modificar, em outra branch, arquivo que pertença a PR ativo. Quando houver sobreposição,
  consolide o trabalho na mesma branch, aguarde a integração ou adie somente a parte incompatível.
- Escopo pode ser ampliado para correções relacionadas ou necessárias ao objetivo sistêmico.
- Correção de bug deve ter teste de regressão quando tecnicamente possível.
- Entrega termina com arquivos, comandos, testes, evidências, riscos, limitações, rollback e
  decisões que exigem ação humana.
- Mudança sensível envolvendo autenticação, permissões, uploads, CI/CD ou configuração exige
  execução e registro do `security-auditor` antes da finalização e do merge.

## Proteções que nenhum agente ultrapassa

1. Não fazer merge ou deploy de produção sem autorização humana.
2. Não operar em `/opt/ejc` nem contra banco de produção.
3. Não versionar segredo, credencial, token, senha, PII ou documento real de cliente.
4. Não usar `git push --force`, `git reset --hard`, `git clean -fd`, `rm -rf` fora de área
   temporária, `docker compose down -v`, `docker volume rm`, `dropdb`,
   `alembic downgrade base` ou `--dangerously-skip-permissions`.
5. Não editar migration aplicada para mudar schema; criar nova migration.
6. Não desligar silenciosamente RBAC, isolamento, HITL, gate de citações, sanitização de PII ou
   kill-switch de IA.
7. Não apresentar hipótese jurídica ou técnica como fato sem evidência.
8. Não executar operação SQL `DROP`, migration destrutiva ou transformação irreversível sem
   backup prévio, verificável, restauração testada e decisão humana registrada.
9. Toda chamada de IA passa pelo gateway institucional; rota nova nasce protegida e endpoint
   público exige justificativa registrada.

## Migrations

Mais de uma branch pode analisar mudança de banco, mas apenas uma migration é integrada por vez.
Antes de ficar pronta para merge, a branch deve atualizar a base, conferir `alembic heads`,
ajustar reserva/número/`down_revision`, validar upgrade e rollback aplicável e demonstrar head
único. Migration destrutiva exige backup e teste de restauração antes do merge.

## Validade jurídica

Regra jurídica exige fonte oficial, vigência, versão, teste, rastreabilidade do fundamento e aviso
de revisão humana. Ferramenta não homologada pode apoiar análise, mas não deve gerar documento
formal automaticamente.

## Decisão e dúvida

Decida e siga sem pedir autorização repetida para arquivos, testes, refatorações ou comandos
seguros necessários ao objetivo. Pare diante de ambiguidade material, alteração irreversível,
produção, credencial, segredo, dado real ou conflito com decisão permanente do titular.
