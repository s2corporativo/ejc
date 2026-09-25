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

Importadores externos conhecidos:

- `backend/app/main.py`;
- `backend/app/routers/teses.py`;
- `backend/app/services/impacto_regulatorio.py`.

Próximo objetivo: retirar primeiro os consumidores de negócio (`teses.py` e
`impacto_regulatorio.py`), deixando o bootstrap como último ponto de corte.

## EnvironmentalCase

Importadores Core conhecidos:

- `backend/app/models/__init__.py`;
- `backend/app/routers/compliance.py`;
- `backend/app/routers/trash.py`;
- `backend/app/services/case_context.py`.

A própria vertical (`routers/environmental.py`, schema/model ambiental e
DPT360) fica fora da contagem do contrato.

Risco funcional relevante: o fluxo ambiental cria `Deadline` de defesa. A
extração só pode ocorrer após preservar essa obrigação por contrato explícito.

## Models especializados por ramo

Importadores Core conhecidos de `app.models.especializado`:

- `backend/app/models/__init__.py`;
- `backend/app/services/case_context.py`;
- `backend/app/services/client_anonimizacao.py`.

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


## Dependência legada descoberta pelo próprio gate

A primeira execução do gate revelou uma aresta pré-existente que não havia
aparecido no inventário inicial:

- `routers/peca_geracao.py` → `routers/ramos.py`.

Peças usa hoje dois contratos de proveniência das calculadoras:
`CAMINHOS_FERRAMENTAS_VALIDOS` e `VERSAO_REGRA_ATUAL`.

Essa aresta existia antes da criação do gate e, por isso, integra a baseline
histórica. Ela **não** autoriza novos imports Core → Ramos.

Destino arquitetural: mover o registro/versão de ferramentas para contrato
neutro compartilhado e retirar esse import router→router em onda específica,
preservando os gates de homologação e proveniência da geração de demonstrativos.
