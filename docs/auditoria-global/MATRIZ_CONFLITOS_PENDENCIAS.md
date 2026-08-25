# Matriz Global de Conflitos e Pendências

**Snapshot inicial:** 2026-08-24 (BRT)  
**Regra:** prioridade = maior impacto comprovado; ausência de CI não equivale a verde nem vermelho de código quando o job não chegou ao primeiro step.

## Matriz executiva

| Sistema | Repositório | Produção | Branch principal | PRs abertas | Conflitos / duplicações | Segurança | CI/CD | Banco | Prioridade |
|---|---|---|---|---:|---|---|---|---|---|
| EJC | `s2corporativo/ejc` | documentada; defasada/bloqueada por gates | `main` | 27 | alta: ~370 branches, pilhas de PRs, implementações históricas concorrentes | credencial QA previamente exposta ainda requer rotação; riscos HITL/RAG/SSH | Actions sem alocação; deploy bloqueado; gates administrativos parcialmente desligados segundo issue | Alembic sensível; migrations destrutivas/históricas exigem guarda e backup | **P0/P1** |
| S2 | `s2corporativo/s2licit` | domínio documentado | `main` | 3 | PR #159 ficou divergente/sobreposto após merge #158; #160 contém correções órfãs | correção de tenant leakage foi integrada durante auditoria; homologações externas pendentes | Actions sem runner desde ~22/08; validação local é contingência oficial | Drizzle/MySQL; migrations concorrentes exigem reconciliação | **P1/P2** |
| Verdelimp | `s2corporativo/verdelimpclaude` | evidência histórica; domínio atual não certificado | `main` | 5 | branches/agentes e ondas antigas; schema gates ainda pendentes | secrets de produção ausentes no GitHub segundo issue; não expor valores | Actions com falha pré-step; deploy/DNS/SSH pendentes | Prisma/PostgreSQL; recuperação de dados e schema exigem prova | **P1/P2** |
| CuidarVet | `s2corporativo/cuidar-vet-plataforma` | não certificada | `main` | 2 | branches de agentes; migration numbering/snapshots exigem disciplina | RBAC em auditoria; dados clínicos requerem isolamento multi-clínica | Actions sem runner; gates locais documentados | cadeia Drizzle recente sem snapshots; geração direta é deliberadamente bloqueada | **P1/P2** |
| Anifarm | `s2corporativo/anifarm` | não comprovada | `main` | 0 | repo legado separado arquivado | sem incidente crítico comprovado no snapshot | não auditado profundamente | Drizzle/MySQL | P3 |
| Anifarm legado | `s2corporativo/Anifarm-` | n/a | `main` | 0 | duplicidade nominal, mas já arquivado | n/a | n/a | n/a | P3 / regular como legado |
| Fitness | `s2corporativo/clovis-fitness-tracker` | não comprovada | branch `claude/...` | 0 | default branch não canônica; conteúdo idêntico à main | sem incidente comprovado | não auditado profundamente | conforme projeto | P3 |
| OpenAI Agents fork | `s2corporativo/openai-agents-python` | n/a | `main` | 0 | fork externo desatualizado | herda risco de dependência/fork | sem PR local | n/a | P3 |
| Skills Manus | `s2corporativo/skills-manus` | n/a | `master` | 0 | auxiliar | sem incidente comprovado | não auditado profundamente | n/a | P3 |

## Achados P0

### P0-01 — EJC: backup/restauração de produção não comprovados

- **Evidência:** Issues #378, #441 e #1236.
- **Impacto:** deploy permanece corretamente bloqueado enquanto backup offsite/restauração não forem comprovados.
- **Causa:** credencial do destino offsite/rclone/OneDrive inválida ou não reautorizada; issue histórica também exige drill de restauração.
- **Correção:** reautorizar destino externo, validar backup cifrado, restaurar em ambiente isolado, comprovar RPO/RTO; depois liberar deploy canônico.
- **Dependência externa:** sim — autenticação/painel/ambiente de produção.
- **Teste de aceite:** backup offsite verde + restauração completa + health de cópia restaurada.
- **Risco da mudança:** alto se o gate for contornado; **não contornar** `REQUIRE_PREDEPLOY_BACKUP`.

### P0-02 — EJC: credencial QA previamente exposta ainda não rotacionada/desativada

- **Evidência:** Issue #1186.
- **Estado:** segredo removido do código atual, mas credencial exposta deve ser tratada como comprometida até rotação/desativação e invalidação de sessões.
- **Impacto:** risco residual de acesso indevido a dados jurídicos/pessoais.
- **Correção:** rotação/desativação operacional, revogar sessões/tokens e comprovar que a credencial antiga falha.
- **Dependência externa:** sim — runtime/produção/credenciais.
- **Regra:** não reproduzir valor antigo nem novo em relatório, comando ou commit.

### P0-03 — EJC: riscos jurídicos/RAG/HITL ainda abertos

- **Evidência:** Issues #983, #984, #985, #986 e relacionadas.
- **Impacto:** possibilidade de saída de IA juridicamente não governada, norma sem vigência correta, ou endpoint sem gate uniforme.
- **Correção:** seguir PRs/branches canônicas de hardening, sem reabrir implementações paralelas.
- **Aceite:** testes-invariantes + citation/HITL + fontes oficiais + revisão humana.

### P0-04 — EJC: prazos/DJEN e assinatura/portal possuem backlog P0 jurídico-operacional

- **Evidência:** Issues #968, #970, #1075.
- **Impacto:** perda de prazo, aceite de documento sem acesso ao conteúdo, integridade/prova de assinatura.
- **Correção:** reconstrução sequenciada no head Alembic vigente, com migrations isoladas quando indispensáveis.

## Achados P1

### P1-01 — EJC: produção e merges recentes não certificados

Issues #1276, #1279, #1281 e outras registram merges em `main` sem execução real dos gates no HEAD final. O estado correto é **integrado, não certificado para publicação**.

### P1-02 — EJC: recuperação SSH/runner contém pendências de segurança

- Issues #1248, #1250, #1261 e #1262.
- Há ausência de redundância SSH, risco de TOFU via `ssh-keyscan`, necessidade de pinagem de host key e verificação de `User=`/sudoers na VPS.
- Não alterar segurança da VPS sem acesso real e evidência.

### P1-03 — EJC: workflows de governança administrativamente desligados

- Issue #1235 documenta `governanca.yml`, `continuity-ui-gates.yml`, `architecture-inventory.yml` e `auto-integracao.yml` em estados administrativos incompatíveis com a documentação.
- A conexão GitHub desta sessão não expõe ação administrativa de enable/disable workflow; portanto é bloqueio externo à API disponível.

### P1-04 — S2: PR #159 sobreposta/divergente após merge #158

- **Estado observado após refresh:** branch `feat/modulo06-pendencias` = 13 commits atrás e 4 à frente de `main`; mergeability negativa.
- **Risco:** duplicar migrations 0024/0025 e lógica de módulo já integrada.
- **Correção proposta:** impedir merge acidental, comparar conteúdo único e extrair apenas diferenças úteis sobre branch limpa da `main`.

### P1-05 — S2: correção de tenant leakage integrada durante a auditoria

- Commit recente de segurança entrou em `main` enquanto o snapshot era montado.
- **Estado:** corrigido no código remoto, mas ainda sujeito à certificação de testes/deploy por causa da indisponibilidade de Actions.

### P1-06 — Verdelimp: recuperação de dados e produção precisam comprovação

- Issue #147: auditoria pós-recovery do snapshot.
- Issue #139: produção depende de secrets/variables externos e DNS/SSL/health; não inventar ou copiar credenciais.

### P1-07 — CuidarVet: cadeia Drizzle com snapshots ausentes

- `CLAUDE.md` registra journal entries recentes sem snapshots e proíbe geração direta.
- O guard atual é correto: falhar antes de gerar DDL potencialmente destrutivo.
- **Correção:** reconstruir snapshots/cadeia em branch própria, validando banco vazio e banco existente antes de liberar `db:generate`.

### P1-08 — CuidarVet: RBAC/multi-clínica ainda em auditoria

- PR #47 é draft de auditoria/correção e o roadmap de homologação exige isolamento em cada query/mutation crítica.
- Não promover substituição do NuvemVet antes da homologação.

## Achados P2

### P2-01 — indisponibilidade de GitHub Actions

EJC, S2, Verdelimp e CuidarVet registram jobs que não chegam ao primeiro step (`startup_failure`, `jobs=[]` ou equivalente). Para S2/Verde/Cuidar, documentação recente adotou validação local como contingência; EJC mantém regras mais restritivas para publicação.

### P2-02 — sprawl de branches e PRs

- EJC ~370 branches;
- S2 61;
- Verdelimp 33;
- CuidarVet 41.

Não apagar branches em massa. Primeiro classificar: PR ativa, backup, Dependabot, agente, supersedida, conteúdo único ou referência histórica.

### P2-03 — S2 #160: correções órfãs úteis mas branch divergente

A branch mantém correções distintas (aviso de inatividade, sugestão de fornecedor, contador de fornecedores e backfill renumerado), porém está atrás da `main`. Requer reconciliação não destrutiva antes de merge.

### P2-04 — integrações externas S2

Issue #69: credenciais reais, termos, CAPTCHA/2FA, fornecedores e portais precisam homologação humana/externa. Não contornar controles de terceiros.

### P2-05 — Verdelimp: schema e comandos canônicos ainda incompletos

Issues #90/#91 registram Event Engine/Outbox, intake formal, origem/locação, uso e financeiro de locação como gates arquiteturais ainda não concluídos.

### P2-06 — CuidarVet: importação NuvemVet

PR #49 prepara import/archive, mas a transação definitiva não foi executada por falta de `DATABASE_URL`/pré-validação/autorização. Essa pendência é correta e não deve ser contornada.

## Achados P3

### P3-01 — Fitness: branch padrão com nome de agente

`claude/physiological-analysis-feedback-3w7q4f` é branch padrão, mas está bit a bit no mesmo commit da `main` no snapshot. Recomenda-se normalizar a default branch para `main` no painel/API administrativa quando disponível.

### P3-02 — fork `openai-agents-python`

Fork confirmado de `openai/openai-agents-python`, sem PR local, parado desde abril/2026 enquanto upstream continua ativo. Manter somente se houver dependência real; caso contrário, classificar como referência/fork, não produto proprietário.

### P3-03 — `Anifarm-`

Já está arquivado e tem conteúdo mínimo. Estado atual é coerente com legado/obsoleto; não reativar sem evidência de conteúdo único.

## Ordem global de execução

1. **Não desativar gates de backup/segurança.**
2. Persistir checkpoint global.
3. Bloquear/neutralizar PRs claramente não mergeáveis ou supersedidas sem apagar branches.
4. Extrair conteúdo único de implementações paralelas para branches limpas.
5. Reconstruir cadeias de migration somente em sequência e com testes.
6. Só promover merges com evidência adequada ao repositório.
7. Produção apenas quando backup, gates, health e commit publicado puderem ser comprovados.
