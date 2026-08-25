# Relatório Global — Auditoria, Consolidação e Correção

**Estado:** EM EXECUÇÃO — levantamento global concluído e primeira onda de consolidação executada.  
**Data-base:** 2026-08-24 (BRT)  
**Branch de controle:** `audit/global-repositories-20260824`

> Este é um relatório vivo. Só será marcado como FINAL quando cada repositório tiver estado objetivo, evidência e pendências residuais classificadas.

## Resumo executivo

- **Repositórios encontrados:** 9
- **Ativos:** 8
- **Arquivados:** 1 (`s2corporativo/Anifarm-`)
- **Repositórios adicionais por colaboração/organização:** 0 na conexão atual
- **Principais repos com backlog ativo:** EJC, S2, Verdelimp, CuidarVet
- **Branch sprawl observado:** EJC ~370; S2 61; Verdelimp 33; CuidarVet 41
- **Produção documentalmente mapeada:** EJC e S2; Verdelimp com divergência de domínio a reconciliar; CuidarVet sem URL canônica comprovada
- **Validação HTTP externa:** inconclusiva por limitação de resolução DNS do ambiente de consulta; não usada para declarar indisponibilidade
- **PRs fechadas como supersedidas nesta auditoria:** EJC #1199 e #1229
- **Nova PR central de governança:** EJC #1284
- **Nova PR de correção reconstruída sobre main atual:** EJC #1285
- **PRs convertidas para draft por divergência/blockers:** S2 #160/#161; Verdelimp #132/#149/#169; CuidarVet #49
- **Operações destrutivas, migrations de produção e deploys realizados:** 0

## Resultado por repositório — estado atual da execução

| Repositório | Sistema | Branch/PR | Correções / consolidações executadas | Testes/CI | Produção | Estado |
|---|---|---|---|---|---|---|
| `s2corporativo/ejc` | EJC | #1284, #1285 e backlog existente | #1199 saneada no HEAD e fechada; #1229 substituída; bridge reconstruído sobre main atual | Actions/gates ainda insuficientes para certificar publicação | documentada; deploy bloqueado por continuidade/gates | corrigido parcialmente; P0/P1 e CI externos ativos |
| `s2corporativo/s2licit` | S2 | #159/#160/#161 | três frentes protegidas como draft; sobreposição/migrations registrada | Actions sem runner; gates locais devem ser repetidos após reconciliação | domínio documentado | consolidando; aguardando reconstrução sobre main |
| `s2corporativo/verdelimpclaude` | Verdelimp | #132/#144/#149/#169/#170 | PRs antigas e #169 protegidas como draft; blockers P1/P2 documentados | 13 gates locais são a contingência oficial, mas precisam ser repetidos após novas correções | DNS/secrets/recovery externos | consolidando; sem deploy autorizado nesta auditoria |
| `s2corporativo/cuidar-vet-plataforma` | CuidarVet | #47/#49 | #49 convertida draft; colisão explícita de migration 0020 registrada; execução real bloqueada | Actions sem runner; cadeia Drizzle precisa reconstrução | não certificada | consolidando; migration/importação não executadas |
| `s2corporativo/anifarm` | Anifarm | `main` | nenhuma correção crítica comprovada necessária nesta onda | não aprofundado | não comprovada | auditado em triagem; P3 |
| `s2corporativo/Anifarm-` | Anifarm legado | `main` | nenhum conteúdo único que justifique reativação comprovado | n/a | n/a | arquivado/obsoleto com justificativa |
| `s2corporativo/clovis-fitness-tracker` | Fitness | default `claude/...` | comparação confirmou default branch e main idênticas no snapshot | não aprofundado | não comprovada | auditado; pendência administrativa de default branch |
| `s2corporativo/openai-agents-python` | fork OpenAI Agents | `main` | confirmado como fork externo, não sistema proprietário | n/a | n/a | auditado como dependência/referência P3 |
| `s2corporativo/skills-manus` | auxiliar | `master` | nenhuma frente de PR ativa | não aprofundado | n/a | auditado em triagem P3 |

## P0 — estado

### EJC — continuidade/backup

Issues #378/#1236 continuam impedindo certificação de deploy: backup offsite/restauração não foram comprovados. Nenhum gate foi contornado.

### EJC — credencial QA previamente exposta

A auditoria encontrou uma cópia ainda presente no HEAD de uma branch antiga (#1199). O script foi removido no commit `a10f1eda36f66aff266985ca3bb6c64d2b0f061d`, a PR foi fechada sem merge e #1186 foi atualizada. O histórico não foi reescrito; portanto a credencial continua considerada comprometida até rotação/desativação runtime e invalidação de sessões/tokens.

### EJC — riscos jurídicos/RAG/HITL e prazos

#983–#986, #968, #970 e #1075 continuam compondo backlog P0/P1. Nenhuma implementação será promovida apenas porque está em branch ou possui testes parciais.

## Consolidação técnica executada

### 1. EJC — documentos automáticos de cliente

A PR #1199 foi encerrada como implementação supersedida. A frente v4 #1231 é a direção canônica porque usa vínculo persistente, mas ainda não está pronta: no refresh analisado estava 96 commits atrás e possuía P1/P2 de isolamento/RBAC/race/RAG não resolvidos. Resultado: **duplicação reduzida sem sacrificar histórico; merge da canônica ainda bloqueado**.

### 2. EJC — bridge temporário do Verdelimp

A PR #1229 estava 97 commits atrás e removia somente um workflow one-shot já consumido. Em vez de mesclar a branch antiga:

- foi criada `fix/remove-verdelimp-bridge-current-main-20260824` sobre a `main` atual;
- o workflow foi removido isoladamente no commit `b7f6f4537e08714a2a3036aca3404dfeaf8f9bcd`;
- foi aberta #1285;
- #1229 foi fechada sem merge.

A #1285 ainda precisa dos gates aplicáveis antes de integração.

### 3. EJC — Banco de Teses

A implementação paralela que criava um terceiro universo de teses foi corretamente abandonada em favor da fonte canônica `teses` / `tese_caso_links`. A cadeia de estabilização/evolução permanece empilhada (#1264 → #1267 → #1269 → #1275). Como #1264 ainda contém ADR único ausente da main, a cadeia foi preservada em draft em vez de fechada ou reescrita.

### 4. S2 — módulo 06 e FUNARBE

Merges concorrentes durante o levantamento mudaram a `main`. Resultado:

- #159: já draft; divergente e com migrations/lógica sobrepostas à implementação que entrou via #158;
- #160: convertida draft; quatro correções potencialmente úteis preservadas, mas requer reconciliação;
- #161: convertida draft; integração FUNARBE preservada, porém requer base atual e homologação externa.

Nenhuma dessas branches será integrada em bloco. Conteúdo único deverá ser extraído/reconstruído sobre a `main` atual e o journal Drizzle vigente.

### 5. Verdelimp — fornecedores e Coordenador

- #169 estava limpa contra `main` e declarava 13 gates locais verdes, mas revisão abriu blockers P1/P2 relevantes: regra de impedimento por sanção, confidencialidade GED, estado de certidão vencida, datas civis, backfill cronológico, mutações em fornecedor arquivado e outros. Foi convertida draft.
- #170 permanece draft e altera schema/RBAC/migration sobre os mesmos eixos. Deve ser reconciliada somente após a decisão sobre #169 e reexecutar todos os gates contra o schema resultante.
- #132/#144/#149 possuem drift expressivo; recovery não foi executado.

### 6. CuidarVet — migrations e NuvemVet

#47 e #49 nasceram de base antiga e usam `0020` para migrations diferentes. A cadeia atual avançou e o próprio repositório registra snapshots recentes ausentes. Resultado:

- #47 permanece draft;
- #49 foi convertida draft;
- não houve edição de journal por concatenação;
- não houve migration, reset, importação ou conexão ao banco real;
- conteúdo funcional do Arquivo NuvemVet deve ser preservado, mas a migration precisa ser reconstruída sobre o journal vigente e testada em banco vazio + existente.

## Segurança

### Segredos

- nenhum valor secreto foi incluído nos relatórios;
- segredo encontrado em branch antiga foi removido apenas do HEAD, sem `force push`/reescrita histórica;
- rotação externa permanece obrigatória para credencial previamente exposta.

### CI/CD

- workflows one-shot/privilegiados não são mantidos apenas por conveniência;
- `startup_failure`/ausência de runner não é interpretado como aprovação do código;
- no EJC, validação local não substitui gates oficiais de publicação quando a própria governança exige executor/backup/CI segregados;
- S2/Verde/Cuidar mantêm a contingência local documentada, mas os gates precisam ser executados novamente em cada SHA reconciliado.

## Pendências residuais reais

### EJC

1. **Backup/restauração offsite** — impacto: deploy não certificável; ação: reautorizar destino, executar backup e restore drill; responsável: operação/VPS; evidência: #378/#1236.
2. **Rotação da credencial QA exposta** — impacto: risco residual de acesso; ação: desativar/rotacionar no runtime, revogar sessões e provar rejeição do segredo antigo; responsável: operação/segurança; evidência: #1186.
3. **Runner/Actions/workflows administrativos** — impacto: HEADs integrados sem certificação; ação: regularizar runner/billing/workflows/rulesets; responsável: administração GitHub/VPS.
4. **#1231 e outras PRs canônicas** — impacto: P1/P2 de isolamento/RBAC; ação: corrigir threads e reconciliar base antes de ready.

### S2

1. **#159/#160/#161 divergentes** — ação: reconstrução sobre main e renumeração de migrations conforme journal atual.
2. **Portais externos** — ação: homologar credenciais, termos, CAPTCHA/2FA e confirmação final; não automatizar bypass.
3. **Actions sem runner** — ação administrativa externa ou gates locais oficiais por SHA.

### Verdelimp

1. **#169 blockers P1/P2** — corrigir antes de qualquer integração.
2. **#170 dependente da ordem de schema/RBAC** — rebase/reconciliação após decisão da #169.
3. **#147 recovery** — executar somente com backup, marker e VPS confirmados.
4. **#139 produção** — DNS/SSL/secrets/health externos.

### CuidarVet

1. **colisão 0020 / snapshots Drizzle** — reconstruir cadeia e validar em dois cenários de banco.
2. **RBAC/multi-clínica** — finalizar auditoria antes de substituição operacional.
3. **NuvemVet** — importação definitiva exige banco correto, pré-validação, autorização e reconciliação; merge de código não equivale a migração de dados.

### P3 / governança

1. Fitness: normalizar branch padrão para `main` quando a ação administrativa estiver disponível; não há divergência de código no snapshot.
2. `openai-agents-python`: confirmar dependência real antes de manter esforço de sincronização de fork.
3. `Anifarm-`: manter arquivado salvo evidência de conteúdo único.
4. Diretórios Git apenas locais: precisam de auditoria no computador; não são observáveis pela conexão GitHub desta sessão.

## Próximas ações da execução

- verificar checks/reviews/mergeability real da #1285;
- continuar a triagem de PRs com conteúdo único e drift alto, priorizando segurança e evitando terceira implementação paralela;
- atualizar este relatório após o próximo lote;
- não executar deploy, migration destrutiva ou recuperação real de dados enquanto os gates externos necessários não puderem ser comprovados.
