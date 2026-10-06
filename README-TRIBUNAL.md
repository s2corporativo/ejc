# JuridIA — Cérebro Jurídico Multi-Agente (Tribunal)

**Data de exportação:** 2026-10-06
**Branch:** main
**Commit:** 0a577d3
**Tarball:** `juridia-tribunal-multiragente-20261006.tar.gz` (17 MB, 1.395 arquivos)

## O que é

Aplicação Next.js 16 com o **Tribunal Multi-Agente** — três personas distintas
(Advogado + Juiz + Promotor) debatem entre si a partir dos mesmos fatos em
até 5 turnos, simulando o contraditório processual antes do protocolo.

## Como rodar localmente

```bash
tar -xzf juridia-tribunal-multiragente-20261006.tar.gz
cd juridia-fixes
cp ENV.example .env  # editar com suas chaves
npm install
npm run db:push     # cria SQLite com 25 modelos
npm run dev         # http://localhost:3000
```

## Como popular a base doutrinária

```bash
# Após npm run dev, em outro terminal:
curl -X POST http://localhost:3000/api/admin/seed-doctrine \
  -H "x-seed-token: dev"
# Resposta esperada: { ok: true, total: 50, inserted: 50, updated: 0 }
```

## Áreas jurídicas cobertas

Civil · Processo Civil · Consumidor · Trabalhista · Previdenciário ·
Penal · Processo Penal · Tributário · Administrativo · **Ambiental** · **Digital (LGPD/MCI)**

## Como usar o Tribunal

1. Abra a aba **3. Tribunal** (atalho: `t`)
2. Informe:
   - Parte autora / Parte ré (use `[NOME_1]`, `[CPF_1]` — pseudonimização automática)
   - Ramo jurídico
   - Advogado defende: autor ou réu
   - Fatos do caso
3. Clique **Iniciar debate** (executa turno 1 — Advogado)
4. Avance pelos turnos:
   - **T1 Advogado** (tese) → **T2 Promotor** (contrário) → **T3 Juiz** (admissibilidade) →
   - **T4 Advogado** (réplica) → **T5 Juiz** (sentença)
5. Baixe cada peça em .md e submeta à revisão humana (art. 1º EOAB)

Se o Juiz inadmitir no turno 3, o debate encerra automaticamente.

## Sanitização e LGPD

- **debate_*_penal** → `LOCAL_COMPLETO` (fail-closed sem Ollama local)
- **debate_* (demais áreas)** → `EXTERNO_PSEUDONIMIZADO`
- Pseudonimização reversível (`[NOME_1]`, `[CPF_1]`) antes de cada chamada LLM
- Reidratação após retorno
- `ensureDraftMarker` em todo artefato (marcador de rascunho)

## Citações e Citation Gate

- Citações vêm da `LegalDoctrine` (base curada local) OU de `web_search` (cache 7d)
- Cada citação carrega `verified: true` (local) ou `verified: false` (web)
- URL oficial incluída quando disponível (Planalto, STF, STJ, TST, ANPD)

## Estrutura

```
src/
├── lib/
│   ├── personas.ts              # 3 personas + DEBATE_TURNS
│   ├── doctrine_base.ts         # TF-IDF search na base curada
│   ├── websearch_live.ts        # web_search + cache 7d
│   ├── advocate.ts              # runAdvocateTurn()
│   ├── prosecutor.ts            # runProsecutorTurn()
│   ├── judge_turn.ts            # runJudgeTurn() — admissibilidade + sentença
│   ├── debate_orchestrator.ts   # máquina de estados 5 turnos
│   └── debate_audit.ts          # persistência Prisma
├── app/api/
│   ├── debate/
│   │   ├── start/route.ts       # POST: cria debate + turno 1
│   │   ├── next/route.ts        # POST: avança para próximo turno
│   │   ├── [id]/route.ts        # GET: debate + turns
│   │   └── list/route.ts        # GET: debates por caseId
│   └── admin/seed-doctrine/     # POST: popula base curada
└── components/app/tribunal.tsx  # UI
```

## Aviso OAB (art. 1º EOAB)

Esta ferramenta **NÃO** constitui aconselhamento jurídico nem promessa de
resultado. Produz **minutas para revisão humana**. O advogado habilitado
deve revisar cada peça antes do protocolo.

## Commits principais

- `c8d6f8b` — P0+P1 (auditoria inicial: 49→34 rotas, 25→23 libs, dead code removido)
- `0a577d3` — Tribunal Multi-Agente (3 personas, 5 turnos, base curada, web cache)
