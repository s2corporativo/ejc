# Relatório Global — Auditoria, Consolidação e Correção

**Estado:** EM EXECUÇÃO — checkpoint inicial concluído; correções ainda em andamento.  
**Data-base:** 2026-08-24 (BRT)  
**Branch de controle:** `audit/global-repositories-20260824`

> Este arquivo é deliberadamente um relatório vivo. Ele só será marcado como FINAL quando cada repositório tiver estado objetivo, evidência e pendências residuais classificadas.

## Resumo executivo do checkpoint inicial

- **Repositórios encontrados:** 9
- **Ativos:** 8
- **Arquivados:** 1 (`s2corporativo/Anifarm-`)
- **Repositórios adicionais por colaboração/organização:** 0 na conexão atual
- **PRs abertas observadas:** 37 no snapshot mais recente
- **Principais repos com backlog ativo:** EJC, S2, Verdelimp, CuidarVet
- **Branch sprawl observado:** EJC ~370; S2 61; Verdelimp 33; CuidarVet 41
- **Produção documentalmente mapeada:** EJC e S2; Verdelimp com divergência de domínio a reconciliar; CuidarVet sem URL canônica comprovada
- **Validação HTTP externa desta sessão:** inconclusiva por limitação de resolução DNS do ambiente de consulta; não usada para declarar indisponibilidade

## Estado inicial por repositório

| Repositório | Sistema | Branch/PR | Correções já comprovadas | Testes/CI | Produção | Estado inicial |
|---|---|---|---|---|---|---|
| `s2corporativo/ejc` | EJC | `main`; 27 PRs abertas | consolidação do Banco de Teses já em andamento; diversos hardenings integrados | Actions sem execução real em vários HEADs; issues registram merges não certificados | documentada; deploy/backup bloqueados | auditado; P0/P1 ativos; correção em andamento |
| `s2corporativo/s2licit` | S2 | `main`; #159/#160/#161 | #127 e #158 integradas durante auditoria; tenant leakage corrigido em merge recente | Actions sem runner; contingência local documentada | domínio documentado | auditado; #159 divergente; correção em andamento |
| `s2corporativo/verdelimpclaude` | Verdelimp | `main`; 5 PRs | versão funcional recente e recuperação de dados possuem trilhas próprias | CI oficial com falha pré-step; gates locais robustos documentados | precisa reconciliação DNS/credenciais/health | auditado; bloqueios externos e PRs pendentes |
| `s2corporativo/cuidar-vet-plataforma` | CuidarVet | `main`; #47/#49 | guard contra geração destrutiva de migration já existe | Actions sem runner; validação local documentada | não certificada | auditado; RBAC/migrations/importação pendentes |
| `s2corporativo/anifarm` | Anifarm | `main`; 0 PR | — | não aprofundado | não comprovada | auditado em triagem; P3 |
| `s2corporativo/Anifarm-` | Anifarm legado | `main`; 0 PR | já arquivado | n/a | n/a | arquivado/obsoleto com justificativa inicial |
| `s2corporativo/clovis-fitness-tracker` | Fitness | default `claude/...`; 0 PR | branch default e main são idênticas no snapshot | não aprofundado | não comprovada | auditado em triagem; P3 governança |
| `s2corporativo/openai-agents-python` | fork OpenAI Agents | `main`; 0 PR | — | n/a para produtos internos | n/a | fork externo; P3 |
| `s2corporativo/skills-manus` | auxiliar | `master`; 0 PR | — | não aprofundado | n/a | auditado em triagem; P3 |

## P0 confirmados no checkpoint

1. **EJC — continuidade/backup:** restauração/offsite ainda não comprovados; deploy não deve contornar o gate (#378/#1236).
2. **EJC — segredo previamente exposto:** credencial QA removida do código atual, porém rotação/desativação runtime ainda não comprovada (#1186).
3. **EJC — riscos jurídicos de IA/RAG/HITL:** backlog P0 ativo (#983–#986 e correlatas).
4. **EJC — prazos/assinaturas/portal:** backlog P0 jurídico-operacional permanece aberto (#968/#970/#1075).

## P1 confirmados no checkpoint

- EJC possui merges recentes integrados sem certificação real do HEAD final.
- EJC possui pendências SSH/runner e workflows administrativos que requerem ação externa.
- S2 #159 tornou-se divergente e sobreposta após #158 ser integrada.
- Verdelimp precisa prova de recuperação de dados e reconciliação de deploy/DNS/credenciais.
- CuidarVet precisa reconstrução segura da cadeia de snapshots Drizzle e conclusão de RBAC/multi-clínica.

## Consolidação técnica já identificada

### Banco de Teses EJC

A primeira versão recente criou um terceiro universo paralelo de Banco de Teses. A auditoria do próprio repositório identificou a implementação canônica existente (`teses` / `tese_caso_links`) e a fase de estabilização passou a remover a implementação paralela, preservando a fonte canônica. Essa decisão é considerada correta e deve orientar as fases seguintes.

### S2 módulo 06

O merge do PR #158 alterou a base enquanto o PR #159 ainda estava aberto. Depois do merge, #159 ficou 13 commits atrás e 4 à frente, com migrations e lógica sobrepostas. Nenhum merge de #159 deve ocorrer sem extração explícita de conteúdo único.

### Anifarm

Há um repo ativo (`anifarm`) e um repo mínimo já arquivado (`Anifarm-`). Não há justificativa para reativar o legado neste snapshot.

### Fitness

A configuração da branch padrão é não canônica, porém não há divergência de código: default branch e `main` apontavam ao mesmo commit no snapshot.

## Bloqueios externos reais

- painel/billing/runner allocation do GitHub Actions;
- enable/disable administrativo de workflows/rulesets não exposto pela conexão;
- rotação de credenciais e sessões em produção;
- reautorização rclone/OneDrive/backup EJC;
- SSH/VPS/sudoers/systemd reais;
- DNS/SSL/secrets Verdelimp;
- credenciais/termos/CAPTCHA/2FA de portais S2;
- banco e autorização operacional da importação NuvemVet;
- inventário de repositórios Git existentes apenas no computador local do titular.

## Próxima atualização deste relatório

Após o checkpoint, serão registradas aqui as ações efetivamente executadas: PRs neutralizadas/fechadas, branches criadas, commits, reviews/checks, merges que possam ser comprovados e pendências que permaneçam externas.
