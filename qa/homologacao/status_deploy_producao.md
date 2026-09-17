> **DOCUMENTO HISTÓRICO.** Registra o estado de 17/08/2026 e não é runbook operacional. O deploy atual usa Woodpecker + host-automation ou `scripts/deploy_manual.sh`; não execute os comandos legados descritos abaixo.

# Status do Deploy em Produção — 17/08/2026 (verificação)

## Fatos verificados no repositório (GitHub)

| Item | Estado |
|---|---|
| Branch homologada | `homologacao-m07-2026-08-16` — commit `044c4e33` — PUSHED ao GitHub ✓ |
| Branch de produção | `main` (origin/main = `c4b75db4`) |
| Produção contém a homologação? | **NÃO** — homologação está em branch separada, sem PR aberto |
| Commits exclusivos da homologação pendentes de merge | `044c4e33`, `b9137aa5`, `5b4618f8`, `bb2df748`, `20d2d9b2` + M01-M36 (commits na branch) |
| Commits em main não presentes na homologação | ZERO (homologação parte de base igual ao main) |
| PR aberto para merge da homologação | Nenhum (gh pr list "homologacao" = vazio) |
| Último commit da main | `c4b75db4 fix(ci): corrigir parser do Deploy Staging (#1161)`; `5d4d065b feat(frontend): aplicar design claro, nova marca...` já está na main |
| Design do GPT (legal-tech-premium-design-72646) | Também em branch separada, NÃO mergeado — contém remoção do 2FA em auth.py (parecer emitido) |

## Mecanismo de deploy existente (scripts no repo)

- `scripts/deploy-vps.sh` — instalação inicial da VPS (Contabo), cria .env com segredos, docker compose up
- `scripts/atualizar-vps.sh` — **atualização de produção** (rodar DENTRO da VPS em `/opt/ejc`):
  1. pré-checagens (docker, .env, segredos)
  2. backup do banco ANTES de qualquer mudança
  3. `git reset --hard origin/main` — pinna produção na branch `main`
  4. fixes críticos, build sem cache, smoke tests (health, migrations, frontend HTTP 200)
- Produção roda Docker/Contabo VPS, deploy = merge em main + script na VPS (via runner self-hosted ou manual)
- GitHub Actions: CI staging deploy existe (#1161 corrigiu parser); runner self-hosted na VPS (`scripts/setup-selfhosted-runner.sh`)

## Conclusão do status

- **Código homologado**: publicado e sincronizado no GitHub ✓
- **Deploy em produção**: **NÃO REALIZADO** — a produção rastreia `origin/main` e a homologação nunca foi mergeada
- Bloqueio real: nenhum técnico; é decisão administrativa (merge + disparar atualização na VPS)

## Próximos passos para publicar

1. **Merge da branch homologada em main** (sem conflitos — base comum, zero divergência)
2. Na VPS Contabo: `cd /opt/ejc && git fetch && bash scripts/atualizar-vps.sh`
   (requer acesso SSH à VPS — credenciais NÃO armazenadas no sandbox; pedir takeover ou o usuário roda o script)
3. Smoke final: `/api/health`, `/api/health/ready`, frontend 200; retestar F-01/F-02 (500s apontados na auditoria, presumivelmente corrigidos pela versão homologada)

## Pontos de atenção antes do merge

- **F-03 (DJEN)**: contenção manual PJe/DJEN antes do deploy
- **auth.py**: o merge da homologação mantém o 2FA (bom); o design do GPT ainda remove — NÃO mesclar aquela branch sem decisão do usuário
- **Backups**: script de atualização já faz backup do banco; confirmar política (scripts/backup.sh)
- **M22/embeddings**: produção VPS precisa de ≥8GB RAM para o modelo e5-large (parecer entregue); com 4GB manter EMBEDDINGS_ENABLED=false
- F-06/F-07: dados de teste HOMOLOG em produção — expurgo recomendado antes/depois do deploy (usuário precisa aprovar)
