# Verdelimp — consolidação de PRs antigas — 2026-08-25 BRT

## Estado de referência

`main`: `0e5dda3fe063908c292cc8b39091d3a21745a43b` (pós-#169/#170).

## PRs antigas encerradas sem merge

### #132 — auditoria de dependências

Encerrada como supersedida. A branch estava 71 commits atrás e adicionava um segundo workflow `ubuntu-latest` + lockfile antigo. O verificador oficial atual `scripts/verificar.sh` já cobre `security:scan`, `npm audit --omit=dev --audit-level=high`, estrutura, inventário, build e, com `--db`, migrations/drift/seed/integração em PostgreSQL descartável.

### #149 — recovery self-hosted

Encerrada como implementação obsoleta, **não como recuperação concluída**. A branch estava 49 commits atrás e usava o script anterior + runner `ejc-vps`. A `main` atual possui recovery v2 com preflight/SSH/evidências. A issue #147 continua canônica e registra `audit_failed`/estado não comprovado.

### #144 — hardening de Aptidão/dossiê

Encerrada após decomposição completa. A branch estava 53 commits atrás.

Sucessora **#173 — `fix(aptidao): reconciliar core e dossie sobre a main atual`**:

- 8 arquivos;
- 0 commits atrás da `main` no momento da reconciliação;
- core determinístico como fonte única;
- endpoints individual/lote/dossiê/opções;
- validação de data civil;
- resultados completos no lote;
- status APTO/NAO_APTO/INDETERMINADO;
- SST estruturado;
- escape de HTML;
- headers defensivos;
- RBAC de backend/testes alinhado ao cargo COORDENADOR introduzido pela #170;
- sem migration/schema.

A PR #173 permanece draft até `npm run verificar -- --db` aprovar 13/13 no SHA exato.

Resíduo **#174 — P1 página de Aptidão**:

A página React atual evoluiu depois da auditoria e não foi sobrescrita. O issue exige reconciliação preservando query string e corrigindo papéis locais, data civil, botão “amanhã”, contexto congelado do dossiê e tipos SST.

## Produção

Nenhuma destas ações comprova publicação. A produção pós-#170 continua não comprovada enquanto o agente/self-hosted/deploy oficial não produzir execução e health verificáveis.
