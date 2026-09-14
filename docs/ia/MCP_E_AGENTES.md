# MCP e agentes - EJC

Este guia orienta a configuração do Antigravity para trabalhar no EJC com agentes especializados e conectores MCP, sem versionar credenciais nem expor dados jurídicos.

## Princípios

- Use MCP apenas com credenciais locais, temporárias ou de menor privilégio.
- Não grave tokens, senhas, URLs privadas, chaves, documentos, `.env` ou dados reais no repositório.
- Prefira acesso somente leitura para GitHub, banco, logs, documentos e observabilidade durante diagnóstico.
- Não conecte agente com permissão de escrita direta em produção.
- Toda chamada de IA deve respeitar o gateway institucional, HITL, gate de citações, sanitização LGPD e isolamento por perfil.
- Toda ação do agente deve deixar evidência no PR: modelo usado, comandos executados, resultado e risco residual.

## MCP recomendados

| Finalidade | Uso no dia a dia | Cuidados |
|---|---|---|
| GitHub | Ler issues, PRs, checks, diffs e criar PRs rastreáveis | Token com menor privilégio; sem bypass de proteção |
| Sistema de arquivos do workspace | Navegar pelo repositório aberto e anexar evidências locais | Limitar ao workspace; não expor arquivos pessoais |
| PostgreSQL local/homologação | Validar schema, migrations, pgvector e consultas controladas | Preferir read-only; nunca usar produção como teste |
| Docker local | Subir ambiente de desenvolvimento e serviços auxiliares | Evitar remoção de volumes; sem `down -v` sem decisão humana |
| Navegador/Playwright | Validar frontend, rotas, autenticação, estados e console | Usar usuários/dados fictícios |
| Observabilidade/logs | Investigar falhas recorrentes e regressões | Sanitizar logs; não copiar PII, documentos ou segredo |

## Agentes pertinentes

| Agente | Quando usar | Saída esperada |
|---|---|---|
| Coordenador de execução | Tarefa ampla, inventário ou estabilização | Plano curto, escopo, riscos e ordem dos PRs |
| Auditor de PR | Revisar PR aberto antes do merge | Classificação do PR, achados, testes faltantes e recomendação |
| Engenheiro frontend | Portal, rotas, estados, formulários e build | Correção mínima com teste ou validação visual |
| Engenheiro backend | FastAPI, serviços, schemas, permissões e jobs | Correção com teste de regressão e contrato preservado |
| Especialista banco/migrations | Alembic, PostgreSQL, pgvector e dados | Head único, upgrade/rollback e impacto documentado |
| Auditor segurança/LGPD | RBAC, ABAC, uploads, documentos, logs e secrets | Risco, evidência, mitigação e validação |
| Auditor jurídico/IA | Fluxos jurídicos, citações, HITL e revisão humana | Fonte, vigência, rastreabilidade e aviso de revisão humana |
| DevOps/CI | Workflows, builds, checks, deploy e rollback | Diagnóstico da falha e correção sem enfraquecer gates |

## Prompt base para o Antigravity

```text
Atue como agente senior do EJC. Antes de alterar, leia docs/GOVERNANCA_IA.md, CLAUDE.md, AGENTS.md, .agent/rules, docs/ia/README.md, docs/ia/PROBLEMAS_CONHECIDOS.md e escolha o modelo adequado em docs/ia/tarefas.

Confirme repositório, remoto GitHub, branch, estado do Git, PRs concorrentes e comandos reais disponíveis. Corrija apenas a causa comprovada, com a menor alteração segura. Preserve sigilo jurídico, LGPD, RBAC, documentos, HITL, gate de citações, gateway institucional de IA e isolamento de dados. Rode as validações proporcionais via .vscode/tasks.json ou comandos documentados em docs/ia/VALIDACOES_IDE.md.

Ao final, entregue causa, arquivos alterados, comandos executados, evidências sanitizadas, riscos residuais, rollback e recomendação de PR. Não faça merge ou deploy sem CI verde e autorização.
```

## Configuração MCP

Use `docs/ia/mcp_config.example.jsonc` como referência. Copie para o local de configuração do seu Antigravity apenas quando souber quais servidores MCP estão instalados na máquina e substitua os placeholders por variáveis de ambiente locais. Não commite a configuração real.
