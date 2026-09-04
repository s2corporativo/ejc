# Adendo à Governança de IA — operação local-first

> **CONSOLIDADO** em 2026-08-25 no §6-B de `docs/GOVERNANCA_IA.md` v4.0 (Issue #1286), como
> este adendo previa ("até a consolidação textual"). Este arquivo permanece como registro
> histórico da decisão; o texto vigente é o da governança principal.

Data da decisão do titular: **2026-08-09**  
Registro: **Issue #1000**

## Precedência

Este adendo registra decisão posterior do titular e, até a consolidação textual em `docs/GOVERNANCA_IA.md`, prevalece somente sobre cláusulas que transformem GitHub, GitHub Actions, runner, PR/check remoto ou disponibilidade do serviço GitHub em requisito para **continuar desenvolvimento e validação**.

Nenhuma proteção de produção, segurança, LGPD, RBAC, HITL, backup ou rollback é reduzida.

## Regra permanente

O EJC passa a adotar execução **local-first para desenvolvimento e CI**:

1. GitHub é repositório remoto, espelho, histórico e meio de colaboração quando disponível.
2. Falha de GitHub, Actions, runner ou API não interrompe edição, checkpoint e validação.
3. O agente procura e executa autonomamente o caminho local seguro antes de reportar bloqueio.
4. O gate técnico local é `scripts/ci-local.sh`.
5. O workspace deve ser branch/worktree/cópia isolada e nunca `/opt/ejc`.
6. A identidade local é SHA Git quando a árvore está limpa ou fingerprint `local-<hash>` quando necessário.
7. Sincronização remota ocorre oportunisticamente, sem force-push, reset destrutivo ou rewrite automático.
8. Produção continua exclusivamente pela esteira de deploy já endurecida; este adendo não cria deploy paralelo a partir de worktree.

## Fallback obrigatório

Quando uma operação GitHub falhar:

```text
GitHub/Actions falhou
  → classificar infraestrutura x código
  → não insistir em runner morto
  → continuar em worktree/cópia isolada
  → checkpoint sem segredos/PII
  → CI local
  → correção + revisão/testes locais
  → commit local
  → sync não destrutiva quando origin voltar
  → confirmação remota/integração
  → deploy pela esteira produtiva existente
```

Falha transitória remota não exige nova autorização do titular. Só existe bloqueio real quando a execução depende de segredo/credencial não acessível com segurança, decisão jurídica humana, operação irreversível sem rollback, conflito material de escopo ou falha local persistente sem mecanismo seguro de diagnóstico.

## Controles que permanecem obrigatórios

- branch/worktree/cópia isolada para escrita;
- teste de regressão para correção de bug;
- fonte oficial e vigência para regra jurídica;
- backup antes de mudança de produção;
- migration não destrutiva ou com estratégia específica de rollback;
- `docker compose config --quiet` na esteira de deploy;
- healthcheck/readiness e prova da versão publicada;
- rollback automático;
- RBAC e mínimo privilégio;
- HITL, citation gate, sanitização de PII e kill-switch;
- logs sem segredo/PII;
- nenhuma exposição pública de Postgres, Redis ou Ollama;
- nenhuma operação destrutiva proibida pela governança principal;
- nenhum `.env` copiado, linkado ou versionado em worktree para contornar deploy.

## Relação com GitHub

A indisponibilidade do GitHub é um problema de sincronização/auditoria remota, **não um problema de validade do código**. Resultado de CI local, checkpoint, fingerprint e commits locais preservam o trabalho até a sincronização.

Quando o GitHub retornar, o histórico local deve ser sincronizado sem reescrever a história e sem `force push`. Se a branch remota avançou/divergiu, o agente reconcilia em branch segura; não sobrescreve o remoto.

## Produção

Este adendo não transforma worktree em diretório produtivo. `scripts/operacao-local-first.sh` recusa `/opt/ejc` como workspace e não possui comando de deploy. A publicação continua por `scripts/deploy_vps_safe.sh`/esteira canônica já existente, após a versão validada estar sincronizada/integrada.
