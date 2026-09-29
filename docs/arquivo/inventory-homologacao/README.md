# Baterias de homologação m01..m36 (arquivadas em 28/09/2026)

Cada `mXX_*_tests.py` era uma bateria HTTP executada à mão contra
`http://127.0.0.1:8000` com `EJC_QA_PASSWORD`, nunca coletada pelo pytest.
28 das 33 baterias foram cobertas por `backend/tests/` (m01–m32, agosto/2026).

Cinco continuam **ativas** em `scripts/inventory/` por não terem equivalente
em `backend/tests/`: `m05_tenant_tests` (isolamento multi-tenant), `m18_templates_tests`,
`m27_chat_juridico_tests`, `m31_risco_tests`, `m36_timesheet_tests`. Abrir testes
pytest para esses cinco é a forma de fechar o buraco e encerrar `scripts/inventory/`.

Os `debug_*`, `mXX_probe_*` e utilitários (`env_shell`, `prep_local_env`,
`summarize_drift`, `openapi_movimentos`, `gen_test_files`, `run_m22_lowmem`) foram
sonda de depuração de uma execução e não têm consumidor.

`backend/tests/test_inventory_qa_scripts.py` continua validando estaticamente
todos estes arquivos (AST) a partir dos dois caminhos.
