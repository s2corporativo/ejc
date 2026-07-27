# Release checklist do EJC

Aplicável a cada merge na `main` e a cada deploy em produção. Regras canônicas em
`docs/GOVERNANCA_IA.md`. O merge e o deploy são atos **humanos**, autorizados pelo titular.

## 1. Antes do merge do PR

- [ ] Issue vinculada e escopo cumprido — nada a mais, nada a menos.
- [ ] CI verde no **head exato** do PR: backend (pytest + schema/RAG com Postgres/pgvector),
      eval dos gold sets, frontend (testes + typecheck + build), ESLint/browser responsivo.
- [ ] `EJC Release Gate` (P0 guard — conflitos e segredos) verde.
- [ ] `Continuity and UI Gates` verde.
- [ ] `Architecture Inventory` verde quando a estrutura mudou.
- [ ] Migrations verificadas: head único, cadeia linear, número reservado em
      `backend/alembic/MIGRATION_RESERVATIONS.md`.
- [ ] Testes de regressão presentes para cada correção.
- [ ] Revisão técnica aprovada (`docs/CRITERIOS_DE_ACEITE.md`, camadas A, B, D, E).
- [ ] Revisão jurídica aprovada quando houver prazo, cálculo, tese ou peça (camada C).
- [ ] `security-auditor` executado quando o PR tocou auth, RBAC, upload, portal ou config.
- [ ] Teste funcional/homologação realizado em ambiente separado, com evidência anexada.
- [ ] Documentação atualizada (runbook, catálogo de APIs, docs de IA — o que for afetado).
- [ ] Rollback documentado para código, configuração **e** banco.
- [ ] Nenhuma colisão com outro PR aberto (arquivos, migrations, contratos de API).
- [ ] Autorização expressa do titular registrada.

## 2. Antes do deploy

- [ ] Backup íntegro e recente (`scripts/backup.sh` ou rotina diária), com prova local
      persistida e cópia offsite confirmada.
- [ ] Restore testado quando a release inclui migration estrutural.
- [ ] Variáveis de ambiente novas presentes no `.env` do servidor e documentadas no
      `.env.example` (sem valores reais).
- [ ] Flags de integrações novas em OFF por padrão.
- [ ] Janela de deploy acordada; ninguém em audiência ou prazo fatal na hora.
- [ ] Plano de rollback à mão (SHA anterior, `downgrade` das migrations, restauração).

## 3. Durante o deploy

- [ ] `scripts/deploy_vps_safe.sh` (backup → build → health-poll → migrations/seeds →
      rollback automático em erro).
- [ ] Health check da API e do frontend respondendo.
- [ ] Migrations aplicadas sem erro; head confere com o esperado.

## 4. Depois do deploy

- [ ] Smoke de homologação: login, cliente, caso, prazo, documento, IA, financeiro, portal.
- [ ] Logs sem erro novo recorrente nos primeiros minutos.
- [ ] Rotina de backup do dia seguinte confirmada.
- [ ] Issue fechada com o resultado; pendências viram Issues novas.
- [ ] Documento de release atualizado (o que entrou, o que ficou para depois, riscos).

## 5. Critérios de bloqueio absoluto

O release **não sai** se:

- há P0 de segurança, LGPD ou validade jurídica aberto na área tocada;
- o CI não está verde no head exato;
- existe migration destrutiva sem backup comprovado e plano de rollback aprovado;
- há segredo, credencial ou PII versionada;
- a mudança jurídica não tem fonte oficial, vigência e teste;
- HITL, gate de citações ou sanitização de PII foram enfraquecidos;
- o rollback não é viável.
