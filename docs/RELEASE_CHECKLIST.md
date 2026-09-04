# Release checklist do EJC

Aplicável a cada merge na `main` e a cada deploy em produção. Regras canônicas em
`docs/GOVERNANCA_IA.md` (v4.0). O merge e o deploy são atos **humanos**, autorizados pelo
titular.

> **Enquanto o GitHub Actions estiver indisponível no nível da conta** (§6-B da governança),
> os itens de CI/gate remoto deste checklist são satisfeitos pela **evidência local
> proporcional ao diff registrada no corpo do PR** — portão a portão, commit e branch. CI
> ausente ou `startup_failure` não aprova nem bloqueia. Quando a esteira voltar, os itens
> voltam a valer literalmente.

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

Ordem real do `scripts/deploy_vps_safe.sh`:

```
backup (prova local cifrada + offsite) → build das imagens → alembic upgrade head
  → sobe o backend novo → health-poll em /api/health → worker → seeds
```

- [ ] `scripts/deploy_vps_safe.sh` executado (não fazer as etapas à mão).
- [ ] Migrations aplicadas sem erro; head confere com o esperado.
- [ ] Health check da API e do frontend respondendo.

> **A migration roda ANTES do health-poll.** Se o health check falhar, o rollback automático
> restaura as **imagens**, não o **schema** — o banco já está migrado. É por isso que toda
> migration precisa ser retrocompatível com a versão anterior do código: é a única coisa que
> torna o rollback seguro. Migration destrutiva ou incompatível transforma um rollback de
> rotina em restauração de backup.

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
