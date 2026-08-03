# Histórico — relatórios, planos e laudos datados

Material **de leitura, não de procedimento**. São registros de ciclos já
encerrados: auditorias, estabilizações, planos de fase e laudos. Ficavam na
raiz do repositório (40 arquivos, contra 9 de procedimento vivo), o que
tornava impossível distinguir à primeira vista o que ainda se executa do que
apenas se consulta.

**Não use nada daqui como procedimento.** Números, migrations, contagens de
rota e nomes de arquivo envelheceram. Procedimento vivo está em:

| Assunto | Onde |
|---|---|
| Ciclo de desenvolvimento | `docs/FLUXO_DE_DESENVOLVIMENTO.md` |
| Governança de IA | `docs/GOVERNANCA_IA.md` |
| Critérios de review | `docs/CRITERIOS_DE_ACEITE.md` |
| Release | `docs/RELEASE_CHECKLIST.md` |
| Deploy / backup / monitoramento | `RUNBOOK_*.md` na raiz |
| Backlog de higienização | `docs/HIGIENIZACAO_BACKLOG*.md` |
| Auditoria externa (jul/2026) | `docs/auditoria/` |

## Índice

### Ciclo de junho/2026 — contenção e auditoria forense

- `AUDITORIA_MESTRE_CHECKLIST_EJC.md` (2026-06-25)
- `RELATORIO_EXECUCAO_PROMPT_MESTRE_EJC_2026-06-25.md`
- `LAUDO_AUDITORIA_FORENSE_EJC_2026-06-29.md`
- `RELATORIO_FASE0_CONTENCAO_2026-06-29.md`
- `RELATORIO_FASE2_BANCO_2026-06-29.md`
- `RELATORIO_FASE3A_OWNERSHIP_2026-06-29.md`
- `RELATORIO_FASE3B_RAG_2026-06-29.md`
- `RELATORIO_FASE4_EXECUCAO_2026-06-29.md`
- `RELATORIO_FASE5_HIGIENE_2026-06-29.md`
- `RELATORIO_LAUDO_IA_RAG_2026-06-29.md`

### Ciclo de julho/2026 — correção, estabilização e go-live

- `AUDIT_FIXES.md` (rastreamento dos 24 bugs da auditoria funcional)
- `RELATORIO_ETAPA_1_SEGURANCA_E_DIAGNOSTICO.md`
- `RELATORIO_ETAPA_2_GRAPHIFY_MAPEAMENTO.md`
- `RELATORIO_ETAPA_3_AUDITORIA_COMPLETA.md`
- `RELATORIO_ETAPA_6_BANCO_DE_DADOS.md` e `6B`/`6C`/`6D`
- `PLANO_ETAPA_4_CORRECAO_SEGURA_EJC.md`
- `RELATORIO_EXECUCAO_CORRECAO_TOTAL_EJC_2026-07-06.md`
- `RELATORIO_EXECUCAO_BLOCO6_TESTES_EJC_2026-07-06.md`
- `RELATORIO_AUDITORIA_ESTABILIZACAO_EJC_2026-07-06.md`
- `RUNBOOK_DEPLOY_CORRECAO_EJC_2026-07-06.md` (deploy pontual, já executado)
- `RELATORIO_AUDITORIA_GO_LIVE_2026-07-12.md`
- `RELATORIO_AUDITORIA_IA_EJC_2026-07-17.md`
- `RELATORIO_PENTE_FINO_EJC_2026-07-18.md`
- `RELATORIO_USABILIDADE_LEIGO_EJC_2026-07-18.md`
- `RELATORIO_AUDITORIA_FUNCIONAL_MODULOS_EJC_2026-07-19.md`
- `RELATORIO_MELHORIA_GERAL_EJC_2026-07-22.md` (origem da P0 H01–H15 de `qa/homologacao/`)
- `RELATORIO_CONSOLIDACAO_AUDITORIA_EJC_2026-07-29.md`

### Mapeamento por grafo (graphify)

- `RELATORIO_GRAPHIFY_EJC_2026-07-02.md`
- `RELATORIO_ANALISE_AGENTES_GRAPHIFY_EJC_2026-07-02.md`
- `RELATORIO_AUDITORIA_INCREMENTAL_GRAPHIFY_EJC_2026-07-02.md`
- `RELATORIO_AUDITORIA_GRAPHIFY_EJC_2026-07-04.md`
- `RELATORIO_CONSOLIDACAO_GERAL_EJC_2026-07-04.md`
- `RELATORIO_VALIDACAO_FUNCIONAL_EJC_2026-07-04.md`

O grafo navegável que esses relatórios citam (`auditoria-grafo/`) era um
snapshot de 2026-07-04 versionado por engano. O grafo vivo é regenerado por
`graphify update .` em `graphify-out/`, que não é versionado.

### Arquitetura de IA e produto

- `MAPA_PROMPTS_IA03.md` — mapa da arquitetura de prompts (citado em comentários
  de `backend/app/routers/ia_extra.py` e nos testes de blindagem de prompts)
- `PLANO_IA04_AGENTES_NATIVOS_E_EFICIENCIA.md`
- `PLANO_FASE4_CONSOLIDACAO.md`
- `RELATORIO_ESTADO_PRODUTO.md`
