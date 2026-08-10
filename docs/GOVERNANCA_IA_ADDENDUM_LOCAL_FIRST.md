# Adendo à Governança de IA — operação local-first

Data da decisão do titular: **2026-08-09**  
Registro: **Issue #1000**

## Precedência

Este adendo registra decisão posterior do titular e, até a consolidação textual em `docs/GOVERNANCA_IA.md`, **prevalece somente sobre cláusulas que transformem GitHub, GitHub Actions, runner, PR/check remoto ou disponibilidade do serviço GitHub em requisito operacional para continuar desenvolvimento, validação ou deploy**.

Nenhuma outra proteção da governança é reduzida.

## Regra permanente

O EJC passa a operar em modelo **local/VPS-first**:

1. GitHub é repositório remoto, espelho, histórico e meio de colaboração quando disponível.
2. GitHub **não é dependência operacional**.
3. Falha de GitHub, Actions, runner, API, PR ou check remoto não interrompe a tarefa.
4. O agente deve procurar e executar autonomamente o caminho local seguro antes de reportar bloqueio.
5. O gate técnico obrigatório de código é `scripts/ci-local.sh`.
6. O fluxo canônico de publicação é `scripts/operacao-local-first.sh deploy <worktree>`, que executa snapshot, CI local e `scripts/deploy_vps_safe.sh` com backup pré-deploy obrigatório.
7. A identidade da versão pode ser SHA Git local ou fingerprint `local-<hash>`; não depende de GitHub.
8. Sincronização de Issue/commit/PR/review com GitHub pode ocorrer posteriormente, sem bloquear a execução já validada localmente.

## Fallback obrigatório

Quando uma operação GitHub falhar:

```text
GitHub/Actions falhou
  → não esperar
  → continuar em worktree/cópia isolada
  → snapshot sem segredos/PII
  → CI local
  → revisão/testes locais
  → backup obrigatório
  → deploy seguro local
  → health/readiness
  → rollback automático se necessário
  → sincronizar GitHub quando voltar
```

Se a alternativa local também falhar, o agente tenta o próximo mecanismo seguro disponível. Só existe bloqueio real quando a execução depende de credencial/produção não acessível com segurança, decisão jurídica humana, operação irreversível sem rollback, ou falha local persistente que não possa ser diagnosticada com os recursos disponíveis.

## Controles que permanecem obrigatórios

- branch/worktree/cópia isolada para escrita;
- teste de regressão para correção de bug;
- fonte oficial e vigência para regra jurídica;
- backup antes de mudança de produção;
- migration não destrutiva ou com estratégia específica de rollback;
- `docker compose config --quiet`;
- healthcheck/readiness e prova da versão publicada;
- rollback automático;
- RBAC e mínimo privilégio;
- HITL, citation gate, sanitização de PII e kill-switch;
- logs sem segredo/PII;
- nenhuma exposição pública de Postgres, Redis ou Ollama;
- nenhuma operação destrutiva proibida pela governança principal.

## Relação com GitHub

A indisponibilidade do GitHub é um problema de sincronização/auditoria remota, **não um problema de validade do código**. Resultado de CI local, snapshot, fingerprint, logs de deploy e healthchecks constituem a evidência operacional primária durante a indisponibilidade.

Quando o GitHub retornar, o histórico local deve ser sincronizado sem reescrever a história e sem `force push`.
