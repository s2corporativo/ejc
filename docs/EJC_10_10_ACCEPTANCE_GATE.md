# EJC 10/10 — Critérios objetivos de certificação

**Status atual:** NÃO CERTIFICADO 10/10  
**Data-base:** 20/07/2026  
**Fase atual:** código estabilizado; governança administrativa, continuidade real e homologação operacional ainda pendentes.  
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
- [x] ownership comprovado por testes negativos em módulos sensíveis¹;
- [x] testes de IDOR por papel e entidade¹;
- [ ] segregação entre carteiras comprovada para todos os papéis;
- [x] 2FA efetivamente obrigatório para os papéis definidos;
- [x] gate automatizado de conflitos e segredos no repositório;
- [x] auditorias Python e Node sem vulnerabilidade alta/crítica nos commits homologados;
- [ ] trilha de auditoria imutável comprovada para todas as ações jurídicas e de IA;
- [x] retenção, descarte e anonimização de dados pessoais documentados e testados¹.

### G4 — IA jurídica e RAG

- [x] fail-closed sem provedor elegível;
- [x] indisponibilidade de IA não impede cadastro e operação básica nos fluxos desacoplados;
- [x] smoke dos gold sets e trajetória do agente aprovados nos commits homologados;
- [x] pseudonimização comprovada por teste dedicado contra provedores externos habilitados¹;
- [x] escopo RAG por cliente/caso comprovado por teste de isolamento¹;
- [x] citações jurídicas verificáveis, com fonte/tribunal/data/vigência, com gate automatizado testado¹ — homologação por área ainda pendente;
- [ ] gold sets representativos por área do Direito e tipo de tarefa (apenas exemplo/template presente — ver adendo);
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

## 6. Adendo — verificação de evidência em 27/07/2026 (commit `1befdf0f`)

**Motivo:** este documento tinha data-base de 20/07/2026; 270 commits foram aplicados à `main` desde então (Sala Jurídica substituindo Sala de Guerra — PR #489; ondas de pente fino #486–#491). Esta seção registra verificação independente de evidência real, sem alterar o histórico acima — apenas soma contexto.

### CI reproduzido localmente (Postgres 16 + pgvector real, Node 22)

- `pip install -r requirements.txt`: limpo.
- `ruff check app` (escopo exato do `ci.yml`): 0 falhas.
- `alembic upgrade head` em banco vazio (vector + pg_trgm + pgcrypto): OK até o head `121_sala_juridica_chat`.
- `pytest tests`: **3607 passed, 1 skipped, 77 subtests passed**, zero falha.
- Frontend: `prettier --check`: OK. `vitest run`: **225/225 passed**. `tsc --noEmit && vite build`: OK.

Conclusão: G1/G2 marcados `[x]` são precisos; CI passaria hoje no HEAD atual.

### ¹ Evidência específica para os itens G3/G4 recodificados acima

| Item | Evidência (arquivo) |
|---|---|
| Ownership / testes negativos | `tests/test_ownership.py`, `tests/test_hardening_ownership_2026_07.py`, `tests/test_context_builder_ownership.py` |
| IDOR por papel/entidade | `tests/test_idor_subrecursos_403_dblevel.py`, `tests/test_portal_idor_matrix.py`, `tests/test_portal_idor_matrix_dblevel.py`, `tests/test_idor_gates_migrados_dblevel.py` |
| Retenção/descarte/anonimização LGPD | `app/services/lgpd_service.py`, `app/services/client_anonimizacao.py`, `app/routers/lgpd_registros.py`, `tests/test_lgpd_registros.py`, `tests/test_client_anonimizacao_dblevel.py`, `tests/test_client_pii_cutover_dblevel.py` |
| Pseudonimização E2E | `app/services/client_anonimizacao.py`, `tests/test_p0_474_pseudonimizacao_externa.py`, `tests/test_pseudonymizer.py` |
| Escopo RAG por cliente/caso | migration `109_rag_scope_cliente`, `tests/test_rag_isolation.py`, `tests/test_rag_isolation_dblevel.py` |
| Citações jurídicas verificáveis | `app/services/citation_gate.py`, `tests/test_citation_gate.py`, `tests/test_citation_gate_hardening.py` |

**Ressalva importante:** "testes completos"/"matriz completa"/"homologação por área" nos itens acima descreve cobertura técnica automatizada comprovada por execução real — não substitui homologação humana formal (ata assinada pelo responsável técnico e titular do produto), que continua em aberto conforme a Seção 4.

### Item confirmado como genuinamente pendente (documento já estava correto)

- **Gold sets por área do Direito:** apenas `app/eval/gold_set.example.jsonl` (3 registros) e `app/eval/gold_set_pecas.example.jsonl` (10 registros) existem — arquivos de exemplo/template, não um gabarito curado real. `tests/test_hit_rate_e_mrr_acima_do_piso_de_regressao` já mede precisão/MRR contra um piso de regressão, mas não substitui gold sets completos por área homologados por advogado da área.

### Itens não verificáveis por código (configuração externa do GitHub — não alterados)

Proteção administrativa da branch `main`, checks obrigatórios, bloqueio de push direto/force-push — são configurações do GitHub (Settings → Branches), não observáveis a partir do código clonado. Seguem corretamente marcados como pendentes.
