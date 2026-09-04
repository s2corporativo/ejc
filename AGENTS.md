# AGENTS.md — regras comuns aos agentes de IA no EJC

Aplica-se a qualquer agente que leia ou escreva neste repositório. As regras prevalentes estão
em `docs/GOVERNANCA_IA.md` (v4.0 — local-first e verificação proporcional ao diff); este
arquivo é o resumo operacional. Em divergência, siga o canônico e registre a harmonização.

Leitura conforme a tarefa: `docs/GOVERNANCA_IA.md` → `CLAUDE.md` (mapa técnico e tabela de
portões) → `docs/FLUXO_DE_DESENVOLVIMENTO.md` → `docs/CRITERIOS_DE_ACEITE.md` → o pedido,
Issue ou PR que originou o trabalho.

## Modos de trabalho

- **Somente leitura**: começa sem Issue e sem branch; pode ler tudo (inclusive arquivos de
  outros PRs), rodar buscas, lint, testes e builds, e produzir relatório.
- **Auditoria corretiva ampla** ("pente fino", "corrija tudo"): diagnóstico autorizado pelo
  pedido; Issue-guarda-chuva antes da primeira escrita; achado confirmado e relacionado entra
  no mesmo trabalho, achado sem relação causal é registrado sem interromper.
- **Desenvolvimento focal**: branch própria, testes proporcionais ao diff, PR vinculado à
  Issue. Uma Issue pode gerar vários PRs; um PR pode fechar Issues inseparáveis.

## Regras de escrita

- Nunca alterar a `main`/`master` diretamente.
- Toda escrita: Issue (ou guarda-chuva) → branch → PR. Verificar PRs concorrentes antes de
  editar; arquivo de PR ativo é lock lógico — consolidar, aguardar ou dividir, nunca
  sobrescrever em silêncio.
- Portões locais **proporcionais ao diff** antes do push (tabela no `CLAUDE.md`): docs-only
  sem portão; suíte completa apenas da área alterada, uma vez, antes do push.
- Correção de bug tem teste de regressão quando tecnicamente possível.
- **O PR com template preenchido é o relatório da entrega** — sem documento duplicado;
  registrar ali suposições, riscos residuais e decisões que exigem ação humana.
- Mudança em autenticação, permissões, uploads, CI/CD ou configuração → `security-auditor`
  antes da finalização e do merge.

## Proteções que nenhum agente ultrapassa

1. Não fazer merge ou deploy de produção fora da esteira/autorização vigente.
2. Não operar em `/opt/ejc` nem contra banco de produção.
3. Não versionar segredo, credencial, token, senha, PII ou documento real de cliente.
4. Não usar `git push --force`, `git reset --hard`, `git clean -fd`, `rm -rf` fora de área
   temporária, `docker compose down -v`, `docker volume rm`, `dropdb`,
   `alembic downgrade base` ou `--dangerously-skip-permissions`.
5. Não editar migration aplicada para mudar schema; criar nova migration.
6. Não desligar silenciosamente RBAC, isolamento, HITL, gate de citações, sanitização de PII
   ou kill-switch de IA.
7. Não apresentar hipótese jurídica ou técnica como fato sem evidência.
8. Não executar `DROP`, migration destrutiva ou transformação irreversível sem backup
   verificável, restauração testada e decisão humana registrada.
9. Toda chamada de IA passa pelo gateway institucional; rota nova nasce protegida; endpoint
   público exige justificativa registrada.

## Migrations

Uma migration integrada por vez: atualizar a base, conferir `alembic heads`, ajustar
reserva/número/`down_revision`, validar upgrade e rollback, demonstrar head único. Migration
destrutiva exige backup e teste de restauração antes do merge.

## Validade jurídica

Regra jurídica exige fonte oficial, vigência, versão, teste, rastreabilidade do fundamento e
aviso de revisão humana. Ferramenta não homologada não gera documento formal automaticamente.

## Decisão e dúvida

Decida e siga sem autorização repetida para arquivos, testes, refatorações ou comandos seguros.
Pare apenas diante de ambiguidade material, alteração irreversível, produção, credencial,
segredo, dado real ou conflito com decisão permanente do titular. Fora disso, assuma a leitura
mais provável, registre a suposição no PR e siga.
