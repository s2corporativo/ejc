# EJC 10/10 — Critérios objetivos de certificação

**Status atual:** NÃO CERTIFICADO 10/10 — congelamento de features decretado em 22/09/2026 para certificação (ver §2-A)  
**Data-base:** 20/07/2026 (original) · **Atualização de evidências:** 22/09/2026 (§2-A)  
**Fase atual:** ondas de absorção W1–W11 executadas e homologação de produção registrada (W12); certificação condicionada a G0 (proteção da main), rollback drill e RPO/RTO.  
**Regra:** o EJC somente pode receber a classificação 10/10 quando todos os gates abaixo estiverem comprovados por evidência automatizada e homologação humana.

## 1. Princípio de certificação

A classificação 10/10 não decorre da quantidade de módulos. Ela exige, cumulativamente:

1. correção funcional;
2. segurança e segregação de dados;
3. aderência jurídica e auditabilidade;
4. arquitetura coerente, sem duplicidades operacionais;
5. experiência de uso simples e contínua;
6. IA controlada, verificável e submetida a revisão humana;
7. banco e migrations íntegros;
8. observabilidade e recuperação de falhas;
9. CI/CD bloqueante e rastreável;
10. operação documentada e homologada por usuários reais.

## 2. Situação real verificada em 20/07/2026

### Integrado na `main`

- Onda 1 — API canônica `/api/v1`, aliases de compatibilidade, contratos de domínio, normalização de rotas e inventário arquitetural.
- Onda 2 — domínio canônico de Processos, com repositório, serviço, schemas, ownership, auditoria, processo principal/acessórios e compatibilidade temporária com `cases`.
- Estabilização pós-Onda 2: correção de serialização assíncrona, head Alembic 111, Prettier, integridade de links e CI integralmente verde.
- Hardening do núcleo de IA/RAG, resolução fail-closed, escopo de conhecimento, pseudonimização externa e proteção de marcadores estruturais do AILog.
- Feed cognitivo DataJud e governança da base de conhecimento.
- Segregação de agenda pessoal e de casos, restrição de atribuição a terceiros e censura do oráculo de conflito.
- Validação do comprovante de protocolo e titularidade das procurações, com testes negativos e trilha de auditoria.
- Auditoria de replay de refresh token após logout ou troca de senha.
- Enforcement duro de 2FA por papel: token temporário restrito, sem sessão plena de negócio antes da ativação TOTP.
- Autenticação de escrita do backup separada da credencial somente leitura do RAG, com service account/OAuth exclusivos e modos fail-closed.

### Evidências automatizadas recentes

#### Estabilização geral — PR #376

- head validado: `d0ca80a281837314bcd94e5e5031355040494ed1`;
- merge na `main`: `13b4381ab24c9f274a7d0c02e3bae8a8d70d4843`;
- CI backend, frontend e eval: **verde**;
- PostgreSQL 16 + pgvector, Ruff, Prettier, Vitest, TypeScript, Vite, `pip-audit`, `npm audit` e Alembic: **verdes**;
- `EJC Release Gate` e `Architecture Inventory`: **verdes**.

#### Isolamento da credencial do backup — PR #380

- head validado: `ecd9f550e959fccb86e2fe0c129cd6e30df3e6b6`;
- merge na `main`: `51983663234674c1a8586550d6806d5653557ae9`;
- CI backend, frontend e eval: **verde**;
- `EJC Release Gate` e `Architecture Inventory`: **verdes**.

### Não integrado

As seguintes ondas ainda precisam ser reaplicadas semanticamente sobre a `main` vigente, uma por PR e com revalidação integral:

- Onda 3 — consolidação de Data Room e Teses v4;
- ~~Onda 4 — Sala de Guerra canônica por caso~~ — substituída: o PR #489
  removeu as Salas de Guerra e consolidou a superfície na Sala Jurídica
  (`/sala-juridica`);
- Onda 5 — timeline única e saúde operacional do caso;
- Onda 6 — painel contextual de saúde/timeline no frontend;
- Onda 7 — saúde operacional da carteira no Dashboard.

### Pendências confirmadas

- proteção administrativa da branch `main` ainda precisa ser comprovada com checks obrigatórios, PR obrigatório e bloqueio de push direto/force push;
- inserir na VPS uma credencial real e exclusiva de escrita do Google Drive;
- comprovar backup cifrado, download, descriptografia e restauração em banco vazio;
- definir e aprovar RPO/RTO;
- testar rollback da release;
- homologar os fluxos jurídicos E2E com dados fictícios e usuários reais do escritório;
- medir desempenho dos fluxos críticos;
- concluir as Ondas 3 a 7 sem reintroduzir redundâncias.

## 2-A. Situação verificada em 2026-09-22 — pente fino, congelamento e evidências

**Status desta data-base:** features **CONGELADAS** por decisão do Titular
(sistema em uso a partir de 23/09/2026). Nenhuma onda nova entra até a
certificação 10/10; apenas hotfix de segurança/produção com gate integral.

### Evidências frescas (2026-09-22)

**Produção** (verificada por HTTP público, sem acesso privilegiado):

- `/api/health` → `status ok`, commit `0cf3a429e` (= head main − 1; #1775
  aguardando janela de deploy), environment `production`;
- CSP efetiva: `img-src 'self' data: blob:` — hotfix de blob em produção
  confirmado no header real (o item ① do plano do Titular já está vivo);
- `/brand/sidebar-betim.jpg` → 200 (fundo Betim/MG do menu lateral em
  produção, com overlay navy — item ② também vivo);
- e2e de navegação `test:navegacao` contra produção com credenciais reais do
  Titular: **82 rotas OK, 0 tela branca, 0 pageerror, 0 5xx (4 puladas —
  rotas `:id` sem seed, disciplina sem mock)**.

**Frontend local (mesma ordem de gates do CI + suítes locais extras):**

- `tsc --noEmit` ✓ · `eslint src` ✓ · `vitest run` ✓ (148 arquivos) ·
  `vite build` ✓ · `audit:css:verificar` ✓ · `test:responsive` ✓ ·
  `test:premium-responsive` ✓ (7 viewports) · `test:navegacao` ✓ (acima).

**Backend local (gates estruturais + suíte completa sem PG):**

- `compileall app` ✓ · `alembic heads` ✓ — head único `161_fee_estornos` ·
  `pytest tests -q` → **7659 passed, 455 skipped, 0 falhas** (os 455 são os
  gates DB-level que se auto-pulam sem `RUN_DB_TESTS=1` e permanecem como
  deveriam no CI com PostgreSQL 16 + pgvector real);
- 1 falso negativo de ambiente investigado e descartado
  (`test_mensagem_erro_sem_coletor` — desalinhamento pyOpenSSL × cryptography
  do venv local; 8/8 após alinhamento; main não tem regressão).

**Backlog (docs/audit/BACKLOG_LIMPEZA_2026-09-20.csv):**

- **P0 = 0 abertos** — SEC-02/SEC-05 executados (W5), SEC-03 verificado HOJE
  no código (PR #1763 já aplica binding fail-closed), SEC-04 verificado HOJE
  no GitHub (#1732/#1737/#1735 merged);
- P1: BE-04 executado HOJE (`test_regulatorio_digest.py` 8/8 — o único router
  sem teste do sistema passou a ter cobertura); W8.2 (504 de IA por timeout do
  nginx do host) preparado em branch `ops/w8.2-nginx-ai-timeout` com runbook
  de aplicação de 5 min no host;
- P1 restantes para pós-certificação: OPS-02/OPS-04 (consolidação de jobs,
  exigem dry-run 48h — NÃO executar na véspera do go-live), BE-11 (PII
  plaintext, depende de W11), LGPD-01 (ROPA — ação operacional anual).

### Congelamento e próximos passos para a certificação

1. Congelado o estado: nenhuma feature nova; PRs abertos pendentes só com
   correção/hotfix;
2. Aplicar W8.2 no host (RUNBOOK_W82_APLICACAO.md) — dor real em produção;
3. G0: proteção administrativa da `main` (checks obrigatórios, PR obrigatório,
   bloqueio de push/force) — segue o único gate de governança não comprovado;
4. Ensaio de rollback de release + backup restore drill (G1/G7) com evidence;
5. ROPA/PII (LGPD-01) e consolidação de jobs (OPS-02/04) após o go-live,
   dentro de ondas próprias com gate integral.

## 3. Gates obrigatórios

### G0 — Governança de merge e release

- [x] workflows `CI` e `EJC Release Gate` automáticos em PR;
- [x] Ruff, Prettier e auditorias de dependências configurados como bloqueantes;
- [ ] branch `main` protegida administrativamente;
- [ ] PR obrigatório para qualquer alteração;
- [ ] checks obrigatórios do workflow `CI` exigidos pela regra da branch;
- [ ] `P0 guard — conflitos e segredos` exigido pela regra da branch;
- [ ] branch desatualizada impedida de merge;
- [ ] conversa/revisão não resolvida impedida de merge;
- [ ] push direto e force push bloqueados, inclusive para administrador;
- [ ] deploy condicionado ao commit homologado.

### G1 — Backend e banco

- [x] instalação limpa de `requirements.txt`;
- [x] lint Ruff sem falhas;
- [x] suíte backend integral com PostgreSQL 16 + pgvector real;
- [x] zero falha no commit homologado dos PRs #376 e #380;
- [x] Alembic com head único;
- [x] `upgrade head` validado a partir de banco vazio no CI;
- [ ] `upgrade head` validado em cópia anonimizada do banco real;
- [ ] rollback documentado e testado para a release;
- [x] inventário arquitetural executado sem bloqueio nos commits homologados;
- [ ] auditoria final de SQL de negócio indevido em todos os routers.

### G2 — Frontend

- [x] Prettier sem divergências;
- [x] Vitest integral verde;
- [x] TypeScript sem erros;
- [x] build Vite verde;
- [x] integridade estática de rotas e links internos validada;
- [ ] ausência de telas, botões e fluxos mortos comprovada em homologação navegada;
- [ ] tratamento consistente de loading, vazio, erro e retry em todos os fluxos críticos;
- [ ] acessibilidade mínima WCAG AA nos fluxos principais.

### G3 — Segurança, sigilo e LGPD

- [ ] zero achado crítico ou alto em auditoria final consolidada;
- [ ] ownership comprovado por testes negativos em todos os módulos sensíveis;
- [ ] testes de IDOR completos por papel e entidade;
- [ ] segregação entre carteiras comprovada para todos os papéis;
- [x] 2FA efetivamente obrigatório para os papéis definidos;
- [x] gate automatizado de conflitos e segredos no repositório;
- [x] auditorias Python e Node sem vulnerabilidade alta/crítica nos commits homologados;
- [ ] trilha de auditoria imutável comprovada para todas as ações jurídicas e de IA;
- [ ] retenção, descarte e exportação de dados pessoais documentados e testados.

### G4 — IA jurídica e RAG

- [x] fail-closed sem provedor elegível;
- [x] indisponibilidade de IA não impede cadastro e operação básica nos fluxos desacoplados;
- [x] smoke dos gold sets e trajetória do agente aprovados nos commits homologados;
- [ ] pseudonimização comprovada por teste E2E contra todos os provedores externos habilitados;
- [ ] escopo RAG por cliente/caso comprovado por matriz completa de isolamento;
- [ ] citações jurídicas verificáveis, com fonte, tribunal, data e vigência, homologadas por área;
- [ ] gold sets representativos por área do Direito e tipo de tarefa;
- [ ] métricas mínimas aprovadas para precisão, completude e alucinação;
- [ ] HITL homologado antes de aplicar, protocolar ou comunicar conteúdo;
- [ ] custo, modelo, prompt sanitizado, resposta e decisão humana auditados de ponta a ponta.

### G5 — Fluxos jurídicos ponta a ponta

Devem existir testes automatizados e ata de homologação humana, no mínimo, para:

- [ ] documento → extração → novo caso → revisão → confirmação;
- [ ] cadastro manual simples de caso;
- [ ] cliente → atendimento → documentos pendentes → retorno;
- [ ] caso → processo principal/acessório → movimentação;
- [ ] intimação → prazo → tarefa → agenda → conclusão;
- [ ] documento/prova → estratégia → tese → peça → revisão;
- [ ] audiência → roteiro → ata → providências;
- [ ] honorários → parcelas → pagamento → conciliação;
- [ ] Raio-X avulso → análise → conversão em caso;
- [ ] DataJud → atualização → impacto cognitivo controlado;
- [ ] portal do cliente com segregação e trilha;
- [ ] backup → restauração → retomada operacional.

### G6 — Arquitetura e simplificação

- [x] Caso adotado como workspace central nos fluxos principais;
- [x] separação canônica entre Caso e Processo integrada pela Onda 2;
- [ ] uma única fonte de verdade por entidade em todos os domínios;
- [ ] Data Room e Teses consolidados pela Onda 3;
- [x] Sala de Guerra consolidada — concluído de outra forma: substituída pela
      Sala Jurídica no PR #489 (superfícies antigas removidas, redirects ativos);
- [ ] timeline e saúde operacional consolidadas pelas Ondas 5 a 7;
- [ ] módulos legados restritos a adaptadores temporários com telemetria;
- [ ] ausência de dupla escrita não controlada;
- [ ] aliases com prazo de retirada e rollback;
- [ ] menus e rotas sem redundância operacional comprovados em homologação;
- [ ] nenhuma exclusão física antes de backfill, telemetria e validação.

### G7 — Observabilidade e continuidade

- [ ] health checks de aplicação, banco, filas, scheduler, IA e integrações validados em produção;
- [ ] logs estruturados com correlação por requisição/caso homologados;
- [ ] alertas testados para falha de jobs, prazos, backups, integrações e IA;
- [ ] métricas aprovadas de erro, latência, fila, custo de IA e disponibilidade;
- [x] código de backup cifrado e autenticação de escrita exclusiva integrados;
- [ ] backup offsite real comprovado;
- [ ] restauração periódica comprovada;
- [ ] plano de recuperação com RPO/RTO definidos;
- [ ] rollback de deploy testado.

### G8 — Operação e usabilidade

- [ ] modo simples validado por advogado não técnico;
- [ ] modo avançado sem duplicar módulos;
- [ ] dashboard orientado a risco, prazo, pendência e próxima ação;
- [ ] saúde operacional por caso e carteira;
- [ ] timeline única e confiável;
- [ ] ajuda contextual e manual vivo por módulo;
- [ ] tempo de execução aceitável nos fluxos críticos;
- [ ] zero bloqueador em homologação real do escritório.

## 4. Critério final de aprovação

O EJC será certificado 10/10 somente quando:

- todos os itens G0 a G8 estiverem concluídos;
- CI e Release Gate estiverem verdes no commit exato da release;
- não houver issue P0/P1 aberta sem aceite formal de risco;
- os fluxos ponta a ponta tiverem evidência automatizada e ata de homologação;
- a release tiver rollback e restauração testados;
- o responsável técnico e o titular do produto aprovarem o checklist final.

## 5. Ordem de execução remanescente

1. configurar e comprovar a proteção administrativa da `main`;
2. configurar a service account exclusiva do backup na VPS;
3. comprovar backup, descriptografia, restauração, RPO e RTO;
4. reaplicar as Ondas 3 a 7, uma por PR, sem reutilizar branches obsoletas;
5. executar auditoria final consolidada de segurança, RBAC, ownership, IDOR e LGPD;
6. homologar os fluxos jurídicos ponta a ponta conforme roteiro formal;
7. medir desempenho, testar deploy e rollback;
8. emitir a ata de homologação e a certificação interna da release.
