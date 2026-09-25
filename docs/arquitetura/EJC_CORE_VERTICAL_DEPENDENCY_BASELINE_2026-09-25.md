# Baseline de dependências — EJC Core x Verticais

**Data:** 2026-09-25  
**Issue:** #1843  
**ADR:** `docs/decisoes/ADR_EJC_CORE_VERTICAIS_2026-09-25.md`

## Finalidade

Este documento registra a dívida de acoplamento encontrada na `main` antes do
desacoplamento. A baseline não legitima essas dependências como arquitetura
permanente: ela apenas impede que novas arestas Core → vertical sejam criadas
durante a migração.

O contrato executável está em:

`backend/tests/test_ejc_core_vertical_boundaries.py`

A regra é monotônica:

- remover dependência conhecida: permitido;
- mover dependência para dentro da própria vertical: permitido;
- criar novo importador Core → vertical: CI deve falhar;
- ampliar a baseline: exige decisão arquitetural explícita vinculada à #1843.

## DPT360

Importador externo conhecido:

- `backend/app/main.py`.

**Reduções já executadas na Onda 3:**

- `impacto_regulatorio.py` deixou de importar o radar DPT360; a taxonomia
  determinística foi movida para `services/regulatory_area_classifier.py`;
- `routers/teses.py` deixou de importar `dpt360.access_scope`; o ownership de
  alertas foi movido para `services/diario_oficial_scope.py`, com reexport no
  DPT para compatibilidade interna.

O bootstrap passa a ser a única aresta Core → DPT conhecida nesta baseline.

## EnvironmentalCase

Importadores Core conhecidos:

- `backend/app/models/__init__.py`;
- `backend/app/routers/compliance.py`;
- `backend/app/routers/trash.py`;
A própria vertical (`routers/environmental.py`, schema/model ambiental e
DPT360) fica fora da contagem do contrato.

**Redução executada na Onda 4:** `services/case_context.py` deixou de importar
`EnvironmentalCase` diretamente. A leitura de satélites passa pelo adapter
`modules/legacy_verticals/case_context_adapter.py`.

Risco funcional relevante: o fluxo ambiental cria `Deadline` de defesa. A
extração só pode ocorrer após preservar essa obrigação por contrato explícito.

## Models especializados por ramo

Importadores Core conhecidos de `app.models.especializado`:

- `backend/app/models/__init__.py`.

**Redução executada na Onda 4:** `services/case_context.py` não conhece mais
`EmpresarialCase`, `CivelCase`, `PenalCase`, `TrabalhistaCase`,
`AdminCase` ou `BancarioCase`. Esses models ficam confinados no adapter de
compatibilidade.

Os routers `ramos_*.py` e `schemas/areas_atuacao.py` são tratados como
parte da vertical durante a migração.

## Routers verticais montados no Core

Dependências conhecidas:

- `app.routers.ramos*` → `main.py`;
- `app.routers.environmental` → `main.py`;
- `app.routers.tributario_fiscal` → `main.py` e `routers/lgpd_registros.py`;
- `app.routers.ambiental_estrategia` → `main.py` e `routers/lgpd_registros.py`.

O `main.py` é propositalmente o último ponto a perder a montagem das
verticais, após compatibilidade, dados e rotas terem destino definido.

## O que este gate não faz

Ele não:

- apaga código;
- altera RBAC;
- altera banco;
- altera migrations;
- impede correção de bugs dentro das verticais;
- substitui testes funcionais;
- prova ausência de dependências dinâmicas ou relações ORM por string.

Esses pontos permanecem no inventário da #1843 e serão tratados nas ondas
seguintes.


## Adapter de contexto legado

A Onda 4 introduz uma única aresta explícita:

- `services/case_context.py` → `modules/legacy_verticals/case_context_adapter.py`.

O adapter implementa o contrato neutro de
`services/legal_case_context.py::SpecializedCaseContext`. Essa aresta é
temporária e substitui dependências diretas do Core em sete families de models.
Novas regras de negócio não devem ser adicionadas ao adapter.


## LGPD e dados sensíveis de verticais

A Onda 5 remove a dependência direta
`services/client_anonimizacao.py -> models.especializado.TrabalhistaCase`.

A limpeza de CID permanece obrigatória e com a mesma semântica, mas passa por:

- `modules/legacy_verticals/lgpd_adapter.py`.

O adapter mantém as salvaguardas existentes:
- somente cliente PF;
- somente polo reclamante;
- inclui casos soft-deleted;
- não toca CID que possa pertencer a terceiro;
- retorna contagem para AuditLog e resposta.

Os testes DB-level já existentes continuam sendo o gate funcional dessa regra.


## Lixeira e entidades verticais

A Onda 6 remove a dependência direta
`routers/trash.py -> models.environmental.EnvironmentalCase`.

O Core passa a carregar entidades legadas de lixeira pelo registro:

- `modules/legacy_verticals/trash_entities.py`.

Listagem, restauração, purga, RBAC e AuditLog da lixeira permanecem no Core;
apenas o conhecimento do model ambiental fica atrás do adapter de compatibilidade.


## Dependência legada descoberta pelo próprio gate

A execução inicial do gate revelou uma aresta pré-existente omitida do primeiro
inventário:

- `routers/peca_geracao.py` → `routers/ramos.py`.

Peças usa dois contratos de proveniência das calculadoras:
`CAMINHOS_FERRAMENTAS_VALIDOS` e `VERSAO_REGRA_ATUAL`.

A aresta integra a baseline histórica, mas não autoriza novos imports Core →
Ramos. O destino é mover esses contratos para uma camada neutra preservando os
gates de homologação e proveniência dos demonstrativos.
