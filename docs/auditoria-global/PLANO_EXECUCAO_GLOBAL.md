# Plano de Execução Global

**Branch de controle:** `audit/global-repositories-20260824`  
**Data-base:** 2026-08-24 (BRT)

Este plano deriva do inventário e da matriz de riscos. A execução deve ser serializada quando houver estado compartilhado (migrations, auth, CI/CD, branch principal) e paralelizada apenas entre repositórios realmente independentes.

## Onda 1 — Segurança e continuidade

### EJC

1. Manter bloqueio de deploy enquanto backup offsite/restauração não estiverem comprovados (#378/#1236).
2. Não considerar credencial QA previamente exposta como saneada até rotação/desativação runtime (#1186).
3. Não reativar ou alterar workflows de recuperação SSH sem resolver pinagem de host key/sudoers/User (#1261/#1262).
4. Preservar fail-closed de RAG/HITL e priorizar PRs canônicas que corrigem #983/#984/#985/#986.
5. Não publicar merges recentes classificados como integrados porém não certificados.

### S2

1. Confirmar que correção recente de tenant leakage permanece em `main` após drift concorrente.
2. Impedir merge acidental do PR #159 enquanto migrations/lógica estiverem sobrepostas ao #158 já integrado.
3. Preservar credenciais externas apenas no cofre e manter CAPTCHA/2FA como gate humano.

### Verdelimp

1. Não substituir banco/volumes para contornar bloqueio de produção.
2. Comprovar recuperação de dados (#147) antes de qualquer limpeza.
3. Manter secrets/DNS/SSH como bloqueios externos explicitamente registrados (#139).

### CuidarVet

1. Manter `db:generate` protegido enquanto snapshots da cadeia Drizzle não forem reconstruídos.
2. Não executar importação definitiva do NuvemVet sem banco correto, dry-run/pré-validação e reconciliação.
3. Não promover sistema como substituto operacional sem RBAC/multi-clínica/fluxos críticos homologados.

## Onda 2 — Consolidação Git

### EJC

- classificar PRs abertas em: canônica, empilhada, supersedida, Dependabot, bloqueada por infraestrutura, bloqueada por decisão jurídica/operacional;
- fechar apenas PRs comprovadamente supersedidas, preservando branch/histórico;
- não deletar as ~370 branches em lote;
- usar Issue #909 e documentação de governança como referências de sequenciamento.

### S2

- #159: comparar diferenças únicas após merge #158; converter em draft/bloquear integração se necessário;
- #160: preservar quatro correções órfãs e reconciliar sobre `main` sem reutilizar migration conflitante;
- #161: manter como frente funcional independente até gates suficientes.

### Verdelimp

- revisar #132/#144/#149/#169/#170 por dependência, mergeability e gates locais registrados;
- não integrar feature antes de hardening obrigatório quando o próprio PR/issue declare dependência.

### CuidarVet

- #47: auditoria/RBAC permanece draft até critérios de isolamento e migrations;
- #49: código de importação pode evoluir, mas execução contra dados reais permanece operação separada.

## Onda 3 — Banco, backend e integrações

1. **EJC:** uma migration Alembic por vez, sempre a partir do head atual; nenhuma destrutiva sem backup/rollback.
2. **S2:** reconciliar Drizzle migrations após merges concorrentes e confirmar journal/ordem real.
3. **Verdelimp:** schema Prisma apenas com Postgres de homologação, migrate/validate/rollback e gates de ownership.
4. **CuidarVet:** reconstruir snapshots Drizzle antes de liberar geração automática; testar vazio + existente.
5. Integrações externas nunca devem transformar indisponibilidade em resultado vazio/sucesso falso.

## Onda 4 — Frontend e experiência operacional

- corrigir páginas/fluxos somente após backend/canonical service estarem definidos;
- evitar segunda implementação visual de entidade já canônica;
- preservar compatibilidade de URLs/adapters enquanto houver consumidores;
- testar loading/erro/vazio, RBAC de UI e comportamento responsivo;
- funcionalidades publicadas devem ser confrontadas com o commit realmente implantado.

## Onda 5 — Testes, CI/CD e produção

### Regra de CI

`startup_failure`, `jobs=[]`, ausência de steps/logs = **infraestrutura**, não falha funcional e não aprovação.

- S2/Verde/Cuidar: usar contingência local apenas conforme regra versionada de cada repo, registrando comandos/resultado/SHA.
- EJC: não converter validação local em certificação de produção onde a governança exigir gates oficiais/executor segregado.

### Regra de deploy

Antes de qualquer promoção:

1. commit/PR exato identificado;
2. revisão e testes adequados ao risco;
3. backup válido/restaurável quando aplicável;
4. migration compatível e rollback conhecido;
5. deploy pelo workflow autorizado;
6. health/readiness/smoke;
7. commit publicado comprovado;
8. logs sanitizados e ausência de regressão crítica.

## Critério de conclusão por repositório

Cada repo deve terminar em um dos estados:

- auditado e regular;
- corrigido e validado;
- consolidado com implementação canônica;
- PR criada/atualizada;
- aguardando CI;
- aguardando autorização/credencial externa indispensável;
- arquivado/obsoleto com justificativa;
- sem acesso com comprovação.

Itens não aplicáveis devem ser marcados explicitamente. Não usar “parece”, “provavelmente” ou “push = concluído”.

## Restrições desta conexão

A execução GitHub pode criar branches/files/PRs, revisar/atualizar/mesclar PRs e consultar checks/logs disponíveis. Não há, nesta sessão, acesso direto ao computador do titular, banco/VPS, painel de DNS, billing Actions, cofre de secrets ou controles administrativos completos de workflows/rulesets. Esses itens são bloqueios externos objetivos, não justificativa para interromper os demais repositórios.
