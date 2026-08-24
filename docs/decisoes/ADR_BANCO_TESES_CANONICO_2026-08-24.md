# ADR — Banco Nacional de Teses Jurídicas: fonte canônica e faseamento

**Status:** Decidido · **Data:** 24/08/2026
**Decisores:** Titular (s2corporativo), Claude Code
**Documentos relacionados:** `backend/alembic/MIGRATION_RESERVATIONS.md` (linha da
migração 148), PR [#1264](https://github.com/s2corporativo/ejc/pull/1264)

## Contexto

O PR #1264 nasceu para implementar um "Banco Nacional de Teses Jurídicas". A
primeira versão criou uma estrutura própria — tabelas `taxonomias`,
`teses_juridicas`, `precedentes`, `processos_vitoriosos`, `contrateses_tese`
(migração 148) e um router `teses_juridicas.py` — sem verificar se já existia
algo equivalente no repositório.

Auditoria completa do repositório (24/08/2026) encontrou que **já existe um
Banco de Teses canônico em produção**: a tabela `teses` + `tese_caso_links`
(`backend/app/models/tese.py`, migração 014), da qual dependem:

- Jurimetria (`app/routers/jurimetria.py`, `app/services/jurimetria.py`);
- Súmulas — `app/services/sumulas_ingestion.py` grava verbetes STF/STJ/TST
  **dentro** da tabela `teses` (`tipo='jurisprudencia'`) e `app/routers/sumulas.py`
  consulta via SQL cru `FROM teses WHERE tipo='jurisprudencia' AND status='ativa'`;
- o matcher tese↔caso (`app/services/tese_caso_matcher.py`) e o impacto
  regulatório (`app/services/impacto_regulatorio.py`);
- o aprendizado automático no encerramento de caso
  (`app/services/case_intel.py::aprendizado_encerramento`, que insere em `teses`);
- todo o frontend (`frontend/src/pages/BancoTeses.tsx`, `TabTeses.tsx`,
  `MotorTeses.tsx`, `moduleRegistry.tsx` key `banco-teses` → `/teses`).

A tabela paralela `teses_juridicas` da migração 148 duplicava esse domínio.
Pior: o router novo (`app/routers/teses_juridicas.py`) foi escrito contra um
modelo imaginado — `require_roles()` chamado com varargs quando a assinatura
real recebe uma lista única, papéis inexistentes com fail-open no fallback
hierárquico, colisão de prefixo `/teses` com o router canônico já registrado,
`selectinload()` sobre relationships que não existiam no model, e colunas
fantasma (`criada_em`, `revisada_em`, `vinculante`, `precedente_id`) — e
**derrubava o boot inteiro do backend** por erro no import do módulo.

O repositório já havia cometido e corrigido esse mesmo padrão de erro uma
vez: a migração `114_consolidar_dataroom_teses_v4.py` fundiu uma tabela
paralela `teses_juridicas_v4` de volta em `teses` (PR #1115). O model ORM
arquivado (`app/models/dataroom_teses_v4_compat.py`) documenta esse
precedente e continua registrado em `Base.metadata` só para o Alembic/gate de
schema não perder o histórico — nunca para uso ativo.

## Alternativas consideradas

| # | Alternativa | Avaliação |
|---|---|---|
| A | Manter `teses_juridicas` como nova fonte de verdade e migrar Jurimetria/Súmulas/matcher/frontend para o novo schema | Rejeitada — reescreveria módulos que já funcionam em produção, multiplicaria o raio de mudança de um PR que já teve dois P0 de conteúdo jurídico fabricado, e repetiria exatamente o erro que a migração 114 corrigiu. |
| B | Consolidar aditivamente na tabela canônica `teses`/`jurisprudencias_internas`, descartando o universo paralelo | **Escolhida.** Zero dados a migrar (os coletores da versão nova sempre retornaram lista vazia, após a correção de governança do commit `369d0ac`). Preserva tudo que já funciona; a extensão de schema fica isolada num PR próprio, revisável em separado da estabilização. |
| C | Reverter o PR inteiro e recomeçar do zero em um novo PR limpo | Rejeitada — descartaria a correção do boot já feita e validada (878 rotas, suíte de regressão verde), e o histórico de review (dois P0 + um P1) é exatamente o material que evita repetir os mesmos erros. |

## Decisão

1. **Fonte canônica única**: `teses` + `tese_caso_links`
   (`backend/app/models/tese.py`, migração 014). Nenhuma outra tabela de
   teses jurídicas deve ser criada; extensões ao domínio são colunas/tabelas
   satélite aditivas a partir daqui.
2. **`teses_juridicas` e todo o código que dependia dela foram removidos**
   do PR #1264 (commit `954ac3a`): router, schemas, model com classe ORM
   `TeseJuridica` (que colidia com `dataroom_teses_v4_compat.py`), coletores
   e seed correspondentes.
3. **Toda migração futura sobre `teses`/`jurisprudencias_internas` é
   aditiva** (`expand_only` no classificador
   `scripts/check_migration_compatibility.py`) — sem `DROP`, sem alterar o
   enum `tesetipo`/`tesestatus` existentes (dos quais depende o SQL cru de
   súmulas), sem `batch_alter_table` (o projeto roda só em Postgres; o modo
   batch existe para contornar limitações do SQLite e o classificador não
   reconhece seu corpo dinâmico).
4. **PR #1264 fica restrito à estabilização** (boot corrigido, universo
   paralelo removido, 878 rotas funcionando, regressão completa verde,
   esta decisão registrada). A evolução de schema (orientação
   ataque/defesa/ambos, contratese, distinguishing, força do precedente,
   status de validação, tabela de evidência jurídica, versionamento) e
   tudo o que vem depois entram em PRs subsequentes, cada um com sua
   própria Issue e review:

   - **PR 2** — Modelo jurídico e validação (schema aditivo; nenhuma tese
     populada em massa).
   - **PR 3** — Pipeline de coleta e validação (LexML, STF, STJ, TST, TJMG,
     TRT3, TRF6, ...), ciclo `coletada → normalizada → parcialmente_validada
     → validada → revisada`; nenhuma tese entra como validada por
     importação automática.
   - **PR 4** — Radar Jurisprudencial, matching em três camadas
     (identificadores jurídicos exatos → similaridade semântica/pgvector →
     IA como camada explicativa, nunca decisória) — sempre determinístico
     na decisão de status; IA nunca marca uma tese como superada sozinha.
   - **PR 5** — Cruzamento decisão → tese afetada → processo ativo → alerta.
   - **PR 6** — Integração com produção de peças (seleção de tese, checagem
     de atualidade antes de finalizar, contratese previsível).
   - **PR 7** — Busca semântica/RAG avançado, só depois do pipeline
     determinístico estar estável em produção.

## Justificativa técnica

- **Toda regra jurídica precisa de fonte oficial, vigência e teste**
  (governança do EJC) — popular milhares de teses não é tarefa de um PR de
  código; é um processo semiautomático contínuo (coleta → identificação de
  tema → extração candidata → fundamentos → precedentes → deduplicação →
  registro preliminar `NÃO VALIDADA` → verificação automática de referência
  → revisão jurídica humana → `VALIDADA`), com uma tabela de evidência
  jurídica dedicada (fonte, tribunal, número, URL oficial, data da consulta,
  hash/fingerprint, agente que coletou, revisor, última validação) para
  auditar cada afirmação jurídica até sua origem — desenhada no PR 2 e 3.
- **Migração aditiva reduz o risco de deploy**: o classificador de
  compatibilidade do próprio repositório (`check_migration_compatibility.py`)
  já reprova operações destrutivas por padrão; seguir esse contrato desde a
  primeira migração do domínio evita qualquer exceção `human_reviewed_drop`
  neste PR.
- **Reaproveitar reduz superfície de erro**: `tese_caso_matcher`,
  `impacto_regulatorio`, `verificador_jurisprudencia`, os importadores de
  jurisprudência (`juris_import/`, `jurisprudencia_externa.py`,
  `crawler_precedentes.py`), a Matriz de Teses (`matriz_teses.py`) e o
  radar legislativo (`radar_legislativo.py`, usado como template para o
  Radar Jurisprudencial do PR 4) já existem, testados, e não precisam ser
  reescritos — apenas conectados.

## Consequências

- Nenhuma tese populada em massa até que o pipeline de coleta com revisão
  humana (PR 3) exista; nenhuma tese entra com `status_validacao=validada`
  por importação automática.
- Todo PR desta série roda a suíte de regressão completa e a compatibilidade
  de migração antes de push, com o boot do backend (`from app.main import
  app`) como critério mínimo de aceite.
- Esta decisão pode ser revisitada se a Matriz de Teses (`matriz_teses.py`,
  por caso) e o Banco de Teses (`teses`, institucional) mostrarem
  sobreposição que justifique fusão — não identificado nesta auditoria, mas
  registrado como ponto de atenção para o PR 2.
