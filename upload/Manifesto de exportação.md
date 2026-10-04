# Manifesto de exportação

Gerado em 2026-10-03T23:31:35Z

## Arquivos modificados ou criados na implementação
 [31mM[m backend/alembic/MIGRATION_RESERVATIONS.md
 [31mM[m backend/app/main.py
 [31mM[m backend/app/models/__init__.py
 [31mM[m backend/app/routers/ia_agente.py
 [31mM[m backend/app/schemas/ia_agente.py
 [31mM[m backend/app/services/ai/agent/loop.py
 [31mM[m backend/tests/test_alembic_single_head.py
 [31mM[m backend/tests/test_schema_dr_parity.py
 [31mM[m frontend/src/config/caseNav.ts
 [31mM[m frontend/src/pages/CasoDetalhe.tsx
[31m??[m EXPORT_MANIFEST.md
[31m??[m EXPORT_README_CASE_MAPPER.md
[31m??[m backend/alembic/versions/171_documental_hardening.py
[31m??[m backend/alembic/versions/172_grafo_juridico_p0.py
[31m??[m backend/alembic/versions/173_agent_runs_p1.py
[31m??[m backend/alembic/versions/174_case_mapper_skills.py
[31m??[m backend/app/models/agent_run.py
[31m??[m backend/app/models/case_graph.py
[31m??[m backend/app/models/case_mapper.py
[31m??[m backend/app/routers/case_mapper.py
[31m??[m backend/app/schemas/case_graph.py
[31m??[m backend/app/seeds/seed_case_mapper_skills.py
[31m??[m backend/app/services/agent_run_service.py
[31m??[m backend/app/services/ai/agent/case_mapper.py
[31m??[m backend/app/services/ai/agent/execution_orchestrator.py
[31m??[m backend/app/services/ai/core/skill_version_service.py
[31m??[m backend/app/services/case_evidence_service.py
[31m??[m backend/app/services/legal_graph_service.py
[31m??[m backend/tests/test_case_mapper_core.py
[31m??[m backend/tests/test_grafo_agent_runs_dblevel.py
[31m??[m docs/ESPECIFICACAO_NUCLEO_EJC_GRAFO_SKILLS.md
[31m??[m docs/ESPECIFICACAO_POSTGRES_GRAFO_JURIDICO.md
[31m??[m docs/FLUXO_PRIMEIRO_AGENTE_E_MODELO_SKILLS.md
[31m??[m docs/PLANO_TESTES_GRAFO_P0_E_AGENT_RUNS_P1.md
[31m??[m docs/REFERENCE_MINUTAIA_ANALYSIS.md
[31m??[m docs/superpowers/
[31m??[m frontend/src/pages/CasoDetalhe/TabInteligenciaVerificavel.tsx

## Testes
- Backend: 33 passed
- Frontend: lint, CasoDetalhe test e build aprovados
- Alembic head: 174_case_mapper_skills
