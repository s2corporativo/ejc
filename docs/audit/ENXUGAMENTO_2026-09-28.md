# Enxugamento do repositório EJC — 28/09/2026

Branch: `chore/enxugamento-profundo-20260928` (6 commits sobre `7034f2bb`).
Método: grafo graphify de `backend/app` (9.428 nós, 455 comunidades) cruzado com
seis auditorias de leitura sobre backend, testes, docs, scripts/infra, frontend e
raiz/marcas/segurança. Nenhuma alteração em runtime, migrations, RBAC ou IA.

## Resultado

| Métrica | Antes | Depois |
|---|---:|---:|
| Bytes versionados nas pastas tocadas | ≈ 71 MB | ≈ 0,5 MB |
| Arquivos rastreados | 2.805 | 2.783 |
| Documentos fora de `docs/arquivo/` | 221 | 150 |
| `UI.tsx` (linhas) | 2.569 | 1.764 |
| Linhas de código (py/ts/tsx/sh/css/mjs) | 499.951 | 498.552 |

O ganho de linhas é pequeno de propósito: o peso estava em artefatos gerados
(70 MB) e em arquivo de documentação (≈ 80 documentos movidos, não apagados).

## O que foi feito

1. **Artefatos tirados do Git** — `docs/audit/inventory/architecture_inventory.{json,csv}`
   e `classification_review.csv` (≈ 68 MB, gerados por `generate_architecture_inventory.py`,
   lidos por ninguém em runtime; o CI regenera em diretório temporário) e o grafo
   antigo `docs/arquivo/auditoria-grafo/`. Entram no `.gitignore`; o histórico
   preserva o conteúdo, o clone novo não carrega mais.
2. **Documentação** — relatórios de auditoria 06/08→09/09, planos, pareceres,
   apêndices de IA e evidência de homologação movidos para `docs/arquivo/`
   e `qa/arquivo/`. Referências em código, runbooks, `docker-compose.yml`,
   `.env.example` e `config.py` atualizadas uma a uma. `docs/arquivo/README.md`
   passou a ser o índice do arquivo.
3. **Frontend** — 17 primitivos de `UI.tsx` sem nenhum importador real removidos
   (2.569 → 1.764 linhas) e `dashboard-canonical.css`, camada nunca importada.
   Verificado: `tsc --noEmit` limpo, 12 testes de UI verdes, governança CSS 12/12.
4. **Assets** — 4 imagens sem referência (`logo-white.png`, `de-paula-teixeira-logo.jpg`
   no frontend, `sidebar-betim/ponte.jpg`, `backend/app/assets/logo.png`).
5. **Scripts** — baterias de homologação `mXX_*` já cobertas por `backend/tests/`
   e sondas `debug_*`/`probe_*` arquivadas; as 5 sem equivalente ficaram ativas.
   SQL pontual de 01/07 e one-offs de saneamento arquivados.
6. **Testes** — 11 arquivos com data no nome renomeados para nome estável.
7. **Referências mortas** — mensagens de `inventario-repo.sh` e
   `ci-local-governanca.sh` apontavam para `.github/workflows/governanca.yml`,
   que não existe desde 31/08 (o CI é Woodpecker).

## O que foi decidido NÃO fazer (e por quê)

- **Migrations** (154 arquivos): intocáveis por AGENTS.md/CLAUDE.md. O plano
  render **zero** migration alterada. Nota: 126 das 154 têm `downgrade` vazio —
  dívida estrutural do schema, que se corrige com migration nova, não com limpeza.
- **`backend/tests/`** (718 arquivos): nenhum import quebrado, nenhum teste
  duplicado além de 7 cópias de gates de rate limit. **Alerta:** 98
  `@pytest.mark.skip` em 97 arquivos — a maior dívida da suíte; cada skip
  precisa de motivo e data de revisão.
- **`docs/biblioteca_juridica/`** (42 arquivos): nenhum código a lê; é conteúdo
  de dado, não documentação. Decisão de arquitetura pendente (fonte do RAG).
- **`legal_brain/`, `api_contract.py`, `inlabs_parser.py`, `legal_graph.py`**
  (≈ 2.300 linhas): candidatos reais a arquivo, mas dependem de decisão de
  produto (o `legal_brain` tem 10 testes próprios).
- **Histórico Git** (31,6 MiB, já comprimido): reescrever com `filter-repo`
  invalidaria 549 branches remotas para ganhos pequenos. Não recomendado.
- **Playfair 600/700**: byte-a-byte idênticos ao 500; os pesos 600/700 renderizam
  o desenho do 500. Corrigir re-baixando as fontes, não apagando arquivos.
- **Branches remotas**: 549 branches, 72 mergeadas. Poda é operação remota,
  fora do escopo deste pedido.

## Pendências conhecidas (não feitas aqui)

- Design tokens: `--ejc-primary` é azul em `ejc-tokens.css` e ouro em
  `tailwind.config.js` (o último bloco vence). `bg-primary-700` renderiza ouro.
  Documentos de design: 4 concorrentes (`DESIGN_SYSTEM_EJC`, `design-system`,
  `FRONTEND_DESIGN_SYSTEM`, `LEGAL_TECH_PREMIUM`).
- 14 componentes `Guia*.tsx` (≈ 5.200 linhas) são quase idênticos e são o maior
  ganho de consolidação do frontend (≈ 4.400 linhas), mas exigem refactor de
  `RamoBase` com teste de regressão por ramo.
- 5 buracos de cobertura: tenancy, templates, chat jurídico, risco, timesheet.
- `.env.example` (1.086 linhas, 300 chaves) e 13 variáveis do compose ausentes dele.

## Como revisar

O trabalho está em um worktree isolado (`%TEMP%\ejc-limpeza`, branch
`chore/enxugamento-profundo-20260928`). Ele parte de `7034f2bb` (igual a
`main` no momento da análise); se a `main` andou, sincronize antes de abrir o PR.
Há sobreposição de arquivos com a branch `design/onda0-3-correcao-camada-css`
(`main.tsx`, `css-governance.json`, `LayoutReference.test.ts`): resolver na
frente, não aqui.
