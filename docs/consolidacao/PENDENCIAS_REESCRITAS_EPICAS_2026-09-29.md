# Reescrita das pendências — consolidação das 16 épicas #1877–#1892

**Data:** 2026-09-29
**Origem:** issues #1877–#1892 (épicas de consolidação) e as 210 issues
absorvidas por elas.
**Situação:** substitui as 16 épicas, fechadas em 2026-09-29.

---

## Por que fechar as épicas

As 16 épicas foram criadas em 2026-09-29 por um script de triagem
(`ONDA6_TRIAGEM_ISSUES_210.md`). Todas têm o mesmo formato: absorvem uma
lista de issues-membros **já fechadas** e apontam para um "Plano Mestre de
Correção Total" que não está versionado no repositório.

O problema é estrutural, não de conteúdo:

1. Uma issue-membro fechada não tem estado, responsável nem verificação. A
   épica herda zero rastreabilidade.
2. A épica não é executável: ninguém pode pegá-la e saber o que fazer.
3. Nada impede o fechamento da épica sem entrega — e foi exatamente o que
   aconteceu (ver seção "Achado de verificação").

Fechar as épicas **não apaga trabalho**: os P0 estão todos fechados, com código
correspondente em `main` no caso de três deles. O que se perde ao mantê-las é a
possibilidade de usá-las como instrumento de triagem.

Este documento substitui as épicas por um inventário verificável.

---

## Como foi verificado

Para cada P0 listado abaixo:

- **Existe código?** — busca no código em `main` (não no PR, não na branch).
- **Existe teste?** — busca em `backend/tests` / `frontend/src`.
- **Existe verificação externa?** — estado real do CI no GitHub.

`CLOSED` no GitHub significa apenas que alguém marcou a caixa. As três colunas
da tabela são o que distingue entregue de marcado.

---

## Achado de verificação

**Os 32 P0 estão fechados. Três não têm o código que a issue pedia.**

### 1. #1026 — CI do GitHub Actions (P0, declarado "COMPLETED")

A issue relatava que *todos* os workflows falhavam antes do primeiro step.

- Existe código? **Não.** `.github/workflows/` **não existe** na `main`. O
  único CI versionado é `.woodpecker.yml`.
- Existe verificação? **Sim, e continua quebrada.** Os últimos 5 runs
  (`CI`, 28/09) terminam em `failure` com **0 steps executados** — os jobs
  `Escopo`, `Guard` e `EJC Gate — Actions` morrem antes de qualquer passo.
- A migração está **em aberto** no PR #1871 (branch
  `infra/github-actions-coolify-20260928`).

**Leitura:** a issue foi fechada com o trabalho em andamento no PR. O sintoma
que ela descrevia é o estado atual do repositório.

### 2. #1351 — hard purge com outbox (P0, declarado "COMPLETED")

A issue pedia: purge durável com outbox/retry, sem perder arquivo nem deixar
órfão no storage.

- Existe código? **Não.** Nenhum `outbox` no backend — `grep -rl outbox
  backend/app` retorna apenas `services/event_bus.py` (event bus genérico, sem
  relação a purge).
- O que foi entregue é uma **contenção**, não a solução: `routers/trash.py:87`
  `_validar_purga_irreversivel_disponivel()` lança `HTTP 409` para
  `entidade == "documents"`. Aissue em si diz que a pendência é a #1359
  (também fechada, com o mesmo padrão).

**Leitura:** o risco de perda de dado foi **contido por bloqueio** (purga de
documentos indisponível) e não resolvido. A rota `POST /trash/{entidade}/{id}/purgar`
existe e executa hard delete para as demais entidades.

### 3. Escopo do hard delete fora de `documents` — verificado, sem risco residual

Auditei as demais entidades de `ENTIDADES` (`trash.py:27`) procurando coluna de
arquivo físico:

| Entidade | Campo de arquivo |
|---|---|
| `clients`, `cases`, `deadlines`, `fees`, `tasks` | nenhum |
| `legal_docs` | nenhum — `conteudo` (Text) no banco |
| `procuracoes` | nenhum — `document_id` é referência ao `Document` (bloqueado) |
| `environmental_cases` | nenhum |
| **`documents`** | **`filepath` (caminho no volume uploads)** + `sha256` |

**`documents` é a única entidade com arquivo físico**, e é exatamente a única
bloqueada com HTTP 409. O hard delete das demais entidades descarta apenas
linhas de banco, sem órfão de storage. **Não há risco residual de perda de
arquivo fora de `documents`** — a contenção cobre o conjunto certo.

Isto corrige a suposição inicial desta revisão, que tratava o escopo como
"não verificado".

### 4. #983 — invariante de rota IA (P0, declarado "COMPLETED")

A issue pedia um teste que **percorra as rotas** e prove que todo endpoint
gerador aplica `hitl_policy.aplicar` + `response_validator.validar`, para que
um endpoint novo que esqueça o gate não passe verde.

- Existe código? **Parcial.** `backend/app/routers/ai.py` aplica o gate
  (o próprio texto da issue registra "audiência em `routers/ai.py:451`").
- Existe teste? **Não, o que a issue pedia.** Os testes que mencionam
  `hitl_policy` (`test_ai_core_nucleo.py`, `test_hitl_critica_adversarial_alertas.py`,
  `test_peca_analise_validacao_hitl.py`) exercitam fluxos individuais — que é
  exatamente o problema descrito na issue. Não há varredura de rotas.

**Leitura:** a invariância é mantida por disciplina de código, não por
verificação. O gate pode ser omitido num endpoint novo sem ninguém perceber.

---

## Os 29 P0 restantes

Fechados, sem pendência estrutural observável a partir de `main`. Registrados
aqui para que o fechamento das épicas não os perca de vista.

| Épica | # | Título |
|---|---|---|
| 1877 | 552 | preservar fatos na conversão Sala Jurídica → Caso |
| 1877 | 841 | escopo de arquivos — validar antes do patch |
| 1877 | 843 | observação — sem alteração de corpus nesta fase |
| 1878 | 575 | `/rag/docs` resiliente e projeção ORM mínima |
| 1879 | 1397 | paridade real Woodpecker ↔ ci-local |
| 1879 | 848 | gates de regressão |
| 1880 | 837 | rollback — vigência RAG/citações |
| 1881 | 849 | review — pontos críticos CodeRabbit/CI |
| 1882 | 838 | observabilidade — motivos de bloqueio por vigência |
| 1882 | 842 | risco LGPD — não expor conteúdo em logs |
| 1882 | 986 | radares de Compliance (Senado, radar_poder, DOU) |
| 1884 | 826 | integrar vigência jurídica ao RAG e citation gate |
| 1884 | 835 | testes — vigência jurídica fail-closed |
| 1884 | 839 | compatibilidade — pesquisa histórica vs direito vigente |
| 1884 | 844 | distinguir status jurídico de flag técnica vigente |
| 1884 | 847 | não confundir pesquisa com fundamentação |
| 1886 | 852 | nota final de planejamento |
| 1886 | 1239 | abastecimento controlado do lote jurídico |
| 1887 | 1337 | Central só com o motor processual canônico |
| 1887 | 1338 | ownership de deadline avulso e validação de responsável |
| 1887 | 1553 | regras tributárias (PAF, CARF, TRF6, créditos) |
| 1888 | 845 | política — status aceitos |
| 1888 | 850 | documentação — política de vigência |
| 1888 | 851 | critérios de saída — sem falso status de conclusão |
| 1888 | 1204 | extrair correções úteis do PR #1185 |
| 1889 | 1031 | CI fallback — journal durável, recuperação idempotente |
| 1891 | 1072 | NFS-e — regime tributário e retenção de ISS |
| 1892 | 827 | gold set jurídico real e benchmark bloqueante |

---

## Pendências reais, reabertas

Substituem as épicas fechadas. Cada uma é verificável e cabe em um PR.

### PEND-1 — Recriar o CI no GitHub Actions (de #1026, #1871)

O repositório não tem `.github/workflows/`. O único CI versionado é
Woodpecker, e os runs do GitHub Actions falham com 0 steps.

- **Estado:** PR #1871 aberto, não mergeado.
- **Critério de saída:** um run do GitHub Actions completa com steps
  executados e o mesmo conjunto de gates-required que `ci-local.sh`.
- **Bloqueia:** merge automático (§6-A da governança) e o gate de
  branch protection.

### PEND-2 — Purga de documentos com outbox durável (de #1351, #1359)

Purga de `documents` está bloqueada com HTTP 409 como contenção. A solução
pedida (outbox/retry, sem perda de arquivo nem órfão no storage) não existe.

- **Estado:** contenção em `backend/app/routers/trash.py:87`. É a única
  entidade com arquivo físico, logo a contenção cobre o conjunto certo.
- **Critério de saída:** migration expand-only (após reconfirmar o head do
  Alembic), outbox com retry idempotente, validação server-side de retenção e
  legal hold, trilha de auditoria, e teste de crash entre as duas etapas.

### PEND-3 — Teste de invariante das rotas de IA (de #983)

Não existe varredura que prove que todo endpoint gerador aplica
`hitl_policy` + `response_validator`. Um endpoint novo que esqueça o gate
passa verde.

- **Estado:** gate aplicado em `routers/ai.py`; sem teste que o exija.
- **Critério de saída:** teste que percorra o registro de rotas de IA, falhe
  se um endpoint gerador não declarar o gate, e rode no portão de CI.

---

## Roadmap DPT 360 (#921, #933, #935)

Não são épicas de consolidação e permanecem **abertas**. São ondas de produto
declaradas em 09/08/2026, sem labels, sem decomposição e sem critérios de
saída:

- **#921** Onda 4 — Motor Jurídico e Modo Conselho (reusa
  `SingleAICoreOrchestrator`, registries e HITL existentes; protocolo de
  raciocínio auditável, nunca chain-of-thought livre).
- **#933** Onda 9 — compartilhamento aprovado no Portal/Data Room (somente
  conteúdo publicado; sem rascunho de IA exposto; sem portal paralelo).
- **#935** Onda 10 — entrada empresarial e integrações de sites.

Não são executáveis como estão. Cada uma precisa virar 2–3 tickets com
critério de saída verificável antes de entrar no fluxo.

---

## Reversão

Fechar as épicas não perdeu informação: os P0 estão listados nas duas tabelas
acima, e as issues-membros continuam acessíveis por número. Para reverter,
reabrir a épica correspondente.
