"""Migra os testes de rbac_matrix que referiam rotas de routers mortos
(data-room-v4, jurimetria_extra) para os routers canônicos equivalentes
(data_room.py, jurimetria.py). 12/08/2026."""
p = "/home/ubuntu/ejc/backend/tests/test_rbac_matrix.py"
s = open(p, encoding="utf-8").read()

# 1. test_discover_gates_resolve_alias_de_modulo_e_helper_booleano:
#    /api/data-room-v4/ (dead) → /api/data-rooms/ (canônico, mesmo _pode_editar)
s = s.replace(
    '    salas = next((g for g in gates if g.method == "GET" and g.path == "/api/data-room-v4/"), None)',
    '    salas = next((g for g in gates if g.method == "GET" and g.path == "/api/data-rooms/"), None)')
s = s.replace(
    '    """`system_modules.py`: `_gestores = require_roles([...])` a nível de\n'
    '    módulo, usado como `Depends(_gestores)`. `data_room_v4.py`:\n'
    '    `_pode_editar(cu)` retorna bool comparando ROLE_LEVEL, chamado via\n'
    '    `if not _pode_editar(cu): raise 403`."""',
    '    """`system_modules.py`: `_gestores = require_roles([...])` a nível de\n'
    '    módulo, usado como `Depends(_gestores)`. `data_room.py`:\n'
    '    `_pode_editar(cu)` retorna bool comparando ROLE_LEVEL, chamado via\n'
    '    `if not _pode_editar(cu): raise 403`."""')

# 2. test_via_depends_true_para_gate_de_router_inteiro:
#    jurimetria_extra stats (dead) → endpoint stats do jurimetria.py canônico
s = s.replace(
    '    rota em si não declara Depends próprio (`jurimetria_extra.py`)."""',
    '    rota em si não declara Depends próprio (`jurimetria.py`)."""')
s = s.replace(
    '    alvo = next((g for g in gates if g.method == "GET" and g.path == "/api/jurimetria/ext/stats"), None)',
    '    alvo = next((g for g in gates if g.method == "GET" and g.path == "/api/jurimetria/ext/stats"), None)')

open(p, "w", encoding="utf-8").write(s)
print("test_rbac_matrix.py migrado")
