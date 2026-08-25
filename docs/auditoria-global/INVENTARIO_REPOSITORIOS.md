# Inventário Global de Repositórios

**Snapshot inicial:** 2026-08-24 (BRT)  
**Conta autenticada:** `s2corporativo`  
**Escopo:** todos os repositórios retornados pela instalação GitHub acessível nesta sessão.

## Método de descoberta

A descoberta foi feita em modo somente leitura antes de qualquer alteração de código, cruzando:

- repositórios por afiliação `owner`, com paginação até página vazia;
- afiliações `collaborator` e `organization_member`;
- organizações do usuário;
- instalação GitHub App e repositórios visíveis por essa instalação;
- busca de branches, PRs abertas, issues técnicas, commits recentes, manifests, workflows e documentação de produção.

Resultado: **9 repositórios acessíveis**, todos pertencentes a `s2corporativo`; **0** repositórios adicionais como colaborador; **0** organizações retornadas pela conexão atual. O conjunto retornado pela instalação coincide com o inventário por afiliação.

> Limitação objetiva: a conexão GitHub desta sessão não expõe o filesystem do computador do titular. Portanto, diretórios Git locais ainda não enviados ao GitHub não podem ser inventariados por esta conexão e permanecem como item de verificação local separada.

## Inventário

| Repositório | Visibilidade | Estado | Branch padrão | Branches observadas | PRs abertas no snapshot | Tamanho aprox. | Classificação inicial |
|---|---|---|---|---:|---:|---:|---|
| `s2corporativo/ejc` | privado | ativo | `main` | ~370 | 27 | ~25,9 MB | EJC / ecossistema jurídico; controle central da auditoria |
| `s2corporativo/s2licit` | privado | ativo | `main` | 61 | 3 | ~4,8 MB | S2 / licitações, cotações, propostas e portais |
| `s2corporativo/verdelimpclaude` | privado | ativo | `main` | 33 | 5 | ~4,4 MB | ERP Verdelimp |
| `s2corporativo/cuidar-vet-plataforma` | privado | ativo | `main` | 41 | 2 | ~8,8 MB | CuidarVet / plataforma clínica veterinária |
| `s2corporativo/anifarm` | público | ativo | `main` | 2 | 0 | ~4,4 MB | compêndio/dashboard veterinário Anifarm |
| `s2corporativo/Anifarm-` | público | **arquivado** | `main` | 1 | 0 | mínimo | repositório legado Anifarm; manter arquivado |
| `s2corporativo/clovis-fitness-tracker` | privado | ativo | `claude/physiological-analysis-feedback-3w7q4f` | 3 | 0 | ~1,5 MB | aplicativo fitness; pendência de governança da branch padrão |
| `s2corporativo/openai-agents-python` | público | ativo | `main` | 1 | 0 | ~28,2 MB | **fork** de `openai/openai-agents-python`; dependência/referência externa |
| `s2corporativo/skills-manus` | privado | ativo | `master` | 1 | 0 | ~4,0 MB | repositório auxiliar de skills; sem PR aberta |

## Observações por repositório

### EJC

- Stack documentada: FastAPI/Python, React/TypeScript/Vite, PostgreSQL + pgvector, Redis/Celery, Docker/Nginx.
- Domínio de produção documentado: `https://ejc.depaulateixeira.adv.br`.
- Há grande concentração de branches de agentes (`agent/`, `claude/`, `codex/`), Dependabot, backups e reconciliações.
- Há PRs empilhadas e dependentes, inclusive série do Banco de Teses.
- Há issues P0/P1/P2 de segurança, backup, CI, deploy, RAG, HITL e migrações.

### S2

- Manifesto identifica o projeto como `orcamento-fornecedores`.
- Stack: React 19, TypeScript, Vite, Express, tRPC, Drizzle/MySQL.
- Domínio oficial documentado: `https://s2.s2corporativo.com.br`.
- O termo de negócio `LicitaCore` **não foi encontrado** no código indexado; a correspondência técnica verificável é `s2corporativo/s2licit`.
- Durante o levantamento houve merges concorrentes de PRs, exigindo refresh antes das correções.

### Verdelimp

- Stack: Next.js 15, React 19, Prisma/PostgreSQL, NextAuth, Vitest.
- Operação de equipamentos/retroescavadeira aparece dentro deste repositório; não foi encontrado repositório autônomo de máquinas.
- Há divergência documental de domínio entre evidências históricas (`verdelimp.s2corporativo.com.br`) e a issue operacional mais recente (`erp.verdelimp.com.br`). A URL canônica de produção deve ser confirmada pela esteira/DNS antes de certificação.

### CuidarVet

- Stack: React 19, tRPC/Express, Drizzle/MySQL, Vite/TypeScript.
- O próprio roadmap do repositório ainda não classifica o sistema como substituto integralmente homologado do NuvemVet.
- A cadeia Drizzle possui entradas sem snapshots recentes; o comando de geração foi deliberadamente protegido para evitar DDL destrutivo.

### Anifarm

- O repositório ativo contém o compêndio/dashboard veterinário.
- `Anifarm-` está arquivado, possui conteúdo mínimo e deve permanecer legado até prova de conteúdo único ainda necessário.

### Fitness

- A branch padrão configurada tem nome de branch de agente, porém a comparação com `main` mostrou estado **idêntico (0 ahead / 0 behind)** no snapshot. O problema é de governança/nomenclatura, não divergência de código no momento.

### openai-agents-python

- Confirmado por metadata pública como fork de `openai/openai-agents-python`.
- O fork local estava sem PR própria e com histórico congelado desde abril/2026 enquanto o upstream segue ativo; não deve ser tratado como sistema proprietário de produção sem necessidade explícita.

## Itens não observáveis diretamente pela conexão atual

Os seguintes dados foram buscados por evidências em arquivos/PRs/issues, mas a API disponibilizada nesta sessão não expõe endpoints administrativos completos para todos os repositórios privados:

- inventário completo de secrets e environments no painel;
- rulesets/branch protection efetivos em todos os repos;
- lista administrativa completa de deployments/environments;
- runners no nível da conta/organização;
- diretórios Git locais do computador;
- estado real do banco de produção e filesystem das VPSs.

Nenhum desses itens será presumido. Quando houver evidência versionada ou issue operacional, ela é registrada como evidência indireta e marcada como tal.
