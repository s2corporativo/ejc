# Status da Execução Global

**Última atualização:** 2026-08-24 (BRT)  
**Branch de controle:** `audit/global-repositories-20260824`

## Estado geral

- [x] descobrir repositórios por afiliação e instalação, com paginação;
- [x] confirmar inexistência de repositórios adicionais de colaborador/organização na conexão atual;
- [x] inventariar 9 repositórios;
- [x] mapear branches dos sistemas principais;
- [x] mapear PRs abertas e issues técnicas prioritárias;
- [x] identificar stacks, comandos reais de validação e evidências de produção;
- [x] registrar conflitos/duplicações e classificar P0–P3;
- [x] persistir checkpoint inicial em branch e PR central (#1284);
- [x] iniciar onda de correções seguras pós-checkpoint;
- [x] neutralizar PRs divergentes ou com blockers críticos sem apagar histórico;
- [x] remover segredo do HEAD de branch EJC supersedida sem reescrever histórico;
- [x] fechar PRs EJC comprovadamente supersedidas (#1199 e #1229);
- [x] reconstruir remoção do bridge Verdelimp sobre a `main` atual (#1285);
- [ ] corrigir blockers de código remanescentes nas PRs canônicas;
- [ ] revalidar PRs após reconciliação;
- [ ] certificar CI/deploy/produção onde os gates externos permitirem;
- [ ] marcar relatório como final somente após estado objetivo por repositório.

## Snapshot inicial de PRs

| Repo | PRs abertas no snapshot | Observação |
|---|---:|---|
| EJC | 27 | forte presença de PRs empilhadas + Dependabot + infraestrutura |
| S2 | 3 | #159, #160, #161 após merges concorrentes de #127/#158 |
| Verdelimp | 5 | #132, #144, #149, #169, #170 |
| CuidarVet | 2 | #47, #49 |
| Demais 5 repos | 0 | sem fila de PR no snapshot |

**Total inicial observado:** 37. A contagem é um snapshot; houve atividade concorrente durante a auditoria e foram criadas as PRs EJC #1284/#1285 e fechadas #1199/#1229. Qualquer mutação continua exigindo refresh imediatamente antes da ação.

## Mudança concorrente detectada durante a auditoria

O S2 recebeu merges enquanto o snapshot era construído:

- PR #127 → `e8818663474d1bc0bc637381a7f92e2c046079ff`;
- PR #158 → `b718cd893af29b95a8965e76acb0448cf2f0771b`;
- correção de segurança/tenant leakage também entrou em `main` na mesma janela.

Consequência: #159/#160/#161 deixaram de representar a base atual e foram tratadas como frentes a reconciliar, não como PRs prontas.

## Correções pós-checkpoint executadas

### EJC

#### #1199 — fechada como supersedida

- a estratégia antiga vinculava documentos ao cliente por título/nome e foi substituída pela v4 #1231 com vínculo persistente;
- um script exclusivo da branch continha credencial QA em texto claro;
- o arquivo foi removido do HEAD da branch em `a10f1eda36f66aff266985ca3bb6c64d2b0f061d`;
- nenhum valor secreto foi reproduzido no relatório;
- o histórico não foi reescrito;
- #1199 foi fechada sem merge;
- #1186 foi atualizada: rotação/desativação runtime e invalidação de sessões continuam obrigatórias.

#### #1229 — substituída por reconstrução limpa

- branch antiga estava 97 commits atrás e removia somente o bridge one-shot do Verdelimp;
- criada `fix/remove-verdelimp-bridge-current-main-20260824` sobre a `main` atual;
- remoção isolada commitada em `b7f6f4537e08714a2a3036aca3404dfeaf8f9bcd`;
- aberta PR #1285;
- #1229 fechada sem merge como supersedida.

#### #1231 — canônica, mas ainda bloqueada

- permanece draft;
- observada 96 commits atrás da `main` no refresh analisado;
- revisão mantém P1/P2 não resolvidos de isolamento/RBAC/race/RAG;
- nenhuma promoção/merge foi executada.

#### Banco de Teses

- #1264 continua draft e contém ADR único ainda ausente da `main`;
- a cadeia #1264 → #1267 → #1269 → #1275 é empilhada e não será desmontada sem preservar dependências;
- a decisão canônica permanece `teses` / `tese_caso_links`, sem terceiro universo paralelo.

### S2

- #159 já estava draft; refresh confirmou divergência e sobreposição com #158 integrado;
- #160 convertida para draft: 4 commits à frente / 3 atrás no snapshot analisado;
- #161 convertida para draft: 4 à frente / 3 atrás;
- comentários persistentes registram necessidade de reconstrução sobre `main`, renumeração Drizzle a partir do journal vigente e repetição dos gates locais;
- nenhuma migration foi aplicada e nenhuma PR foi mesclada.

### Verdelimp

- #132 convertida para draft: branch 47 commits atrás; workflow de CVE deve ser reconstruído sem carregar lockfile antigo;
- #144 permanece draft: hardening relevante, porém 29 commits atrás;
- #149 convertida para draft: recovery de produção 25 commits atrás; nenhuma recuperação foi executada;
- #169 convertida para draft apesar de estar limpa contra `main` e ter 13 gates locais verdes, pois revisão mantém P1/P2 de regra jurídica, GED/confidencialidade, datas e certidões;
- #170 permanece draft: 1 commit atrás e sobreposição potencial de schema/RBAC/migrations com #169; deve ser revalidada somente após definição da ordem de integração.

### CuidarVet

- #47 permanece draft: 101 commits à frente / 18 atrás no snapshot analisado; não mesclar em bloco;
- #49 convertida para draft: 2 à frente / 18 atrás;
- conflito explícito: ambas usam migration `0020` para finalidades distintas;
- nenhuma migration foi executada e nenhuma importação NuvemVet foi iniciada;
- comentários persistentes exigem reconstrução da cadeia a partir do journal atual, banco vazio + existente e autorização separada para importação real.

## Bloqueios externos reais

### EJC

- rotação/desativação de credencial QA previamente exposta requer runtime/produção (#1186);
- backup offsite/restauração requer credencial/autorização externa (#378/#1236);
- SSH/VPS/runner depende de acesso/configuração reais (#1248/#1261/#1262);
- Actions/billing/runner allocation não é corrigível pelo código da aplicação (#1254/#1026);
- enable/disable administrativo de workflows não está disponível nesta conexão (#1235).

### S2

- homologação de portais/fornecedores depende de credenciais, termos, CAPTCHA/2FA e ambientes reais (#69);
- Actions sem alocação de runner exige regularização externa ou contingência oficial já documentada.

### Verdelimp

- secrets/variables de deploy e DNS/SSL são externos (#139);
- recuperação de dados precisa comprovação operacional (#147).

### CuidarVet

- importação definitiva do NuvemVet depende de banco correto, pré-validação/reconciliação e autorização operacional (#49).

### Conta / ambiente local

- a conexão atual não permite listar diretórios Git existentes somente no computador do titular;
- não expõe mudança de default branch, rulesets, secrets, environments, billing/runners nem painéis de DNS/VPS.

## Próximas ações automáticas

1. revisar checks/reviews da PR EJC #1285 e classificá-la como aguardando CI ou corrigível;
2. aprofundar PRs Verdelimp/Cuidar/EJC que contêm blockers de código ainda não resolvidos, evitando novas implementações paralelas;
3. fechar apenas duplicatas/supersedidas comprovadas;
4. preservar conteúdo único de branches antigas e reconstruí-lo sobre base atual quando tecnicamente seguro;
5. manter deploys e operações de dados bloqueados enquanto backup/credenciais/DB/runner não forem comprovados;
6. atualizar este arquivo e `RELATORIO_FINAL.md` após cada lote de mutações.

## Regra de atualização

Após cada mutação:

- registrar repo/PR/branch/SHA;
- informar teste/check disponível;
- não chamar de “concluído” se CI, integração ou produção ainda estiverem pendentes;
- não reproduzir segredos;
- manter estado remoto e relatório central sincronizados.
