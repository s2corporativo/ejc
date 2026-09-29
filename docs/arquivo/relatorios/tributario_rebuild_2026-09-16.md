# Reconstrução tributária sobre a main atual

Base: `main@4f5d9218855db730d42d886757edc82fe606dde1`.

Objetivo desta branch: reaplicar semanticamente o núcleo PAF federal da frente tributária antiga sem reutilizar ancestry obsoleto.

## Incluído nesta primeira etapa

- serviço `tributario_paf.py` isolado;
- sub-router `ramos_tributario_paf.py` ainda não montado no agregador canônico;
- regressões isoladas da contagem temporal.

## Deliberadamente não promovido ainda

- substituição da rota histórica no agregador `ramos.py`;
- ampliação da matriz `FERRAMENTAS_NAO_HOMOLOGADAS`;
- selo de homologação nas demais calculadoras tributárias;
- Guia Tributário, prompt tributário e pré-auditoria XML/NF-e.

Esses itens serão integrados somente após o CI desta base reconstruída e revisão contra a `main` vigente. Nenhum endpoint novo fica ativo enquanto o sub-router não for montado.
