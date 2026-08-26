"""Testa `qa/e2e/rbac_matrix.py` — a derivação estática da matriz RBAC
usada pela suíte E2E (Issue #700).

Roda com pytest normal (`pytest tests/test_rbac_matrix.py`), com todas as
deps do backend instaladas — por isso pode importar `app.core.security` e
`app.core.auth_middleware` diretamente para comparar contra o espelho
mantido em `qa/e2e/rbac_matrix.py` (que, por sua vez, evita essa importação
para ficar leve na hora de rodar a suíte contra homologação, sem instalar o
backend inteiro).
"""
from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "qa" / "e2e"))

import rbac_matrix as rm  # noqa: E402

from app.core.auth_middleware import (  # noqa: E402
    AuthMiddleware,
    _path_casa_prefixo_publico,
)
from app.core.security import EQUIPE_JURIDICA as BACKEND_EQUIPE_JURIDICA  # noqa: E402
from app.core.security import ROLE_LEVEL as BACKEND_ROLE_LEVEL  # noqa: E402

ROUTERS_DIR = ROOT / "backend" / "app" / "routers"
MAIN_PY = ROOT / "backend" / "app" / "main.py"


# ── O espelho não pode divergir do original ──────────────────────────────────


def test_role_level_espelha_backend():
    """Se alguém mudar a hierarquia em security.py sem atualizar o espelho,
    a matriz calcularia resultado esperado errado sem avisar — é exatamente
    o tipo de lista que envelhece em silêncio que a Issue #700 quer evitar."""
    assert rm.ROLE_LEVEL == BACKEND_ROLE_LEVEL


def test_equipe_juridica_espelha_backend():
    """Mesma razão de `test_role_level_espelha_backend`, para a allowlist da
    Issue #694: os routers importam EQUIPE_JURIDICA de security.py, então o
    espelho de `rbac_matrix.py` é o que decide se a matriz enxerga o gate.
    Divergir em silêncio faria a matriz prever 403 para quem passa (ou 200
    para quem é barrado) em 15 arquivos da superfície jurídica."""
    assert set(rm.EQUIPE_JURIDICA) == set(BACKEND_EQUIPE_JURIDICA)


def test_gate_compartilhado_equipe_juridica_nao_e_piso_hierarquico():
    """`financeiro` (nível 4) está ACIMA de `estagiario` (3) em ROLE_LEVEL e
    mesmo assim NÃO pertence à equipe. Se `_GATES_COMPARTILHADOS` registrasse
    requer_equipe_juridica como `local_level` (piso) em vez de
    `local_membership` (allowlist), a matriz daria financeiro como permitido —
    exatamente o defeito que a Issue #694 corrigiu no backend."""
    kind, roles, level = rm._GATES_COMPARTILHADOS["requer_equipe_juridica"]
    assert kind == "local_membership"
    assert "financeiro" not in roles
    assert rm.ROLE_LEVEL["financeiro"] > level  # acima do nível, fora da lista


def test_casa_prefixo_publico_bate_com_auth_middleware():
    """`_casa_prefixo` (rbac_matrix.py) precisa concordar com
    `_path_casa_prefixo_publico` (auth_middleware.py) para os mesmos casos —
    senão a matriz prevê 200/403 diferente do que o middleware real decide."""
    casos = [
        ("/api/auth/login", "/api/auth/"),
        ("/api/portal/dashboard", "/api/portal/"),
        ("/api/portal-admin/dashboard", "/api/portal/"),
        ("/api/users/me", "/api/users/me"),
        ("/api/users/me/totp-qr", "/api/users/me"),
        ("/api/users/", "/api/users/me"),
        ("/api/health", "/api/health"),
        ("/api/health/ready", "/api/health"),
        ("/api/cases/", "/api/portal/"),
    ]
    for path, prefixo in casos:
        assert rm._casa_prefixo(path, prefixo) == _path_casa_prefixo_publico(
            path, prefixo
        ), (path, prefixo)


def test_permitidos_cliente_externo_extraidos_do_codigo_fonte_do_middleware():
    """Em vez de confiar que alguém mantém `PORTAL_PREFIXES_CLIENTE_EXTERNO`
    sincronizado à mão, este teste EXTRAI a tupla `permitidos` de dentro do
    código-fonte real de `AuthMiddleware.dispatch` (ast) e compara com o
    espelho — qualquer PR que mude o confinamento do cliente_externo sem
    atualizar `rbac_matrix.py` quebra aqui, não em produção."""
    source = textwrap.dedent(inspect.getsource(AuthMiddleware.dispatch))
    tree = ast.parse(source)
    extraidos: list[str] | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "permitidos" for t in node.targets)
            and isinstance(node.value, ast.Tuple)
        ):
            extraidos = [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)]
    assert extraidos, "não encontrou a tupla `permitidos` em AuthMiddleware.dispatch"
    assert set(extraidos) == set(rm.PORTAL_PREFIXES_CLIENTE_EXTERNO)


# ── Confinamento de cliente_externo ──────────────────────────────────────────


def test_cliente_externo_confinado_em_rota_de_staff():
    assert rm.cliente_externo_confinado("/api/cases/") is True
    assert rm.cliente_externo_confinado("/api/clients/") is True


def test_cliente_externo_liberado_em_rota_de_portal():
    assert rm.cliente_externo_confinado("/api/portal/dashboard") is False
    assert rm.cliente_externo_confinado("/api/users/me") is False
    assert rm.cliente_externo_confinado("/api/health") is False


def test_cliente_externo_nao_ganha_prefixo_amplo_por_semelhanca_textual():
    """`/api/users/me` libera só o subcaminho — `/api/users/` (lista de
    usuários) continua confinada. Prova que a checagem não vira um
    `startswith` genérico demais."""
    assert rm.cliente_externo_confinado("/api/users/") is True


# ── Hierarquia de nível — a lógica que a Issue #694 explora ─────────────────


def test_hierarquia_admite_papel_de_nivel_superior_mesmo_fora_da_lista():
    """Reproduz o achado da Issue #694: um gate escrito como
    `require_roles(["estagiario", ...])` (min_level=3) deveria negar
    `financeiro`? NÃO — pela hierarquia real de `require_roles`, qualquer
    papel com nível >= min_level passa, mesmo que não esteja em `allowed`.
    Este teste documenta que o comportamento é esse MESMO (é o backend que
    decide assim); é o `resultado_esperado` que precisa refletir isso para a
    matriz não prever 403 onde a resposta real é 200."""
    gate = rm.RouteGate(
        module_key="teste", method="GET", path="/api/exemplo",
        gate_kind="require_roles", allowed_roles=("estagiario",),
        min_level=rm.ROLE_LEVEL["estagiario"],
        source_file="teste.py", source_line=1,
    )
    assert gate.permite("financeiro") is True  # nível 4 >= 3
    assert gate.permite("secretaria") is False  # nível 2 < 3
    assert gate.resultado_esperado("financeiro") == 200
    assert gate.resultado_esperado("secretaria") == 403


def test_resultado_esperado_aplica_confinamento_antes_do_gate_do_router():
    """cliente_externo é barrado pelo AuthMiddleware ANTES de qualquer gate
    de router — mesmo numa rota sem require_roles nenhum (min_level=1, que
    sozinho deixaria QUALQUER papel passar)."""
    gate = rm.RouteGate(
        module_key="cases", method="GET", path="/api/cases/",
        gate_kind="nenhum", allowed_roles=(), min_level=1,
        source_file="cases.py", source_line=1,
    )
    assert gate.permite("cliente_externo") is True  # o gate do router, isolado, permitiria
    assert gate.resultado_esperado("cliente_externo") == 403  # mas o middleware confina antes
    assert gate.resultado_esperado("secretaria") == 200


# ── Parsing estático contra o código real ────────────────────────────────────


def test_discover_gates_encontra_gates_conhecidos_no_backend_real():
    """Ancora a extração em rotas cujo gate é conhecido por inspeção manual —
    se o parser regredir (ex.: parar de resolver `Depends(require_admin)`),
    isto quebra."""
    gates = rm.discover_gates(ROUTERS_DIR)
    por_rota = {(g.method, g.path): g for g in gates}

    admin = por_rota.get(("GET", "/api/users/"))
    assert admin is not None, "GET /api/users/ não encontrada pelo parser"
    assert admin.gate_kind == "require_admin"
    assert admin.min_level == rm.ROLE_LEVEL["admin"]

    advogado = por_rota.get(("GET", "/api/environmental/"))
    assert advogado is not None
    assert advogado.gate_kind == "requer_advogado"
    assert advogado.min_level == rm.ROLE_LEVEL["advogado"]

    delete_caso = por_rota.get(("DELETE", "/api/cases/{case_id}"))
    assert delete_caso is not None
    assert delete_caso.gate_kind == "require_roles"
    assert delete_caso.min_level == min(
        rm.ROLE_LEVEL[r] for r in ("admin", "socio")
    )

    # M04 (homologação 2026-08-15): GET /cases ganhou o check em-body
    # `requer_equipe_juridica(cu)` (Issue #694) — o parser estático detecta a
    # allowlist como local_membership; antes da correção a rota estava sem gate.
    gate_casos = por_rota.get(("GET", "/api/cases/"))
    assert gate_casos is not None
    assert gate_casos.gate_kind in ("local_membership", "nenhum"), gate_casos
    if gate_casos.gate_kind == "local_membership":
        assert "financeiro" not in gate_casos.allowed_roles, gate_casos.allowed_roles


def test_discover_gates_resolve_constantes_de_modulo():
    """`require_roles_exact(_EQUIPE)` (constante do módulo, não lista literal)
    é o padrão da superfície jurídica; sem resolver a constante, a amostra ao
    vivo perderia a maior parte da cobertura real."""
    gates = rm.discover_gates(ROUTERS_DIR)
    alvo = next(
        (g for g in gates if g.method == "GET" and g.path == "/api/calculadoras/inss"),
        None,
    )
    assert alvo is not None
    assert alvo.gate_kind == "local_membership"
    assert alvo.allowed_roles, "constante do módulo não foi resolvida"
    assert alvo.permite("estagiario") is True
    assert alvo.permite("financeiro") is False


def test_selecionar_amostra_get_nunca_descarta_em_silencio():
    gates = rm.discover_gates(ROUTERS_DIR)
    amostra, excluidos = rm.selecionar_amostra_get(gates)
    total_get_unico = len(
        {(g.method, g.path) for g in gates if g.method == "GET"}
    )
    assert len(amostra) + len(excluidos) == total_get_unico
    assert len(amostra) > 50, "amostra caiu demais — parser pode ter regredido"
    # toda rota com gate explícito (hierarquia OU pertencimento estrito) e
    # sem parâmetro de path tem que estar na amostra, nunca amostrada por fora
    obrigatorias = {
        (g.method, g.path)
        for g in gates
        if g.method == "GET" and "{" not in g.path
        and g.gate_kind not in ("indeterminado", "nenhum")
    }
    presentes = {(g.method, g.path) for g in amostra}
    faltando = obrigatorias - presentes
    assert not faltando, f"rotas com gate explícito ficaram fora da amostra: {faltando}"


def test_discover_gates_resolve_helper_de_pertencimento_estrito():
    """`clients.py::_req_clientes_leitura` faz `if role not in _CLIENTES:
    raise 403` — pertencimento ESTRITO, sem hierarquia. Regressão real
    encontrada rodando a suíte contra um backend local: `estagiario`
    (nível 3) tem nível MAIOR que `secretaria` (nível 2, que está em
    `_CLIENTES`), mas não pode ser admitido por hierarquia aqui — só quem
    está literalmente no conjunto."""
    gates = rm.discover_gates(ROUTERS_DIR)
    alvo = next((g for g in gates if g.method == "GET" and g.path == "/api/clients/"), None)
    assert alvo is not None
    assert alvo.gate_kind == "local_membership"
    assert alvo.permite("secretaria") is True
    assert alvo.permite("estagiario") is False
    assert alvo.permite("financeiro") is False


def test_discover_gates_resolve_checagem_inline_de_nivel():
    """`centro_custos.py::consolidado_geral` faz
    `if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]: raise 403`
    DIRETO no corpo do handler — sem `Depends`, sem `requer_advogado()`."""
    gates = rm.discover_gates(ROUTERS_DIR)
    alvo = next(
        (g for g in gates if g.method == "GET" and g.path == "/api/centro-custos/consolidado"),
        None,
    )
    assert alvo is not None
    assert alvo.min_level == rm.ROLE_LEVEL["socio"]
    assert alvo.permite("advogado") is False
    assert alvo.permite("socio") is True


def test_discover_gates_resolve_alias_de_modulo_e_helper_booleano():
    """`system_modules.py`: `_gestores = require_roles([...])` a nível de
    módulo, usado como `Depends(_gestores)`. `data_room.py`:
    `_pode_editar(cu)` retorna bool comparando ROLE_LEVEL, chamado via
    `if not _pode_editar(cu): raise 403`."""
    gates = rm.discover_gates(ROUTERS_DIR)
    mapa = next((g for g in gates if g.method == "GET" and g.path == "/api/system-modules/mapa"), None)
    assert mapa is not None
    assert mapa.min_level == rm.ROLE_LEVEL["socio"]

    salas = next((g for g in gates if g.method == "GET" and g.path == "/api/data-rooms"), None)
    assert salas is not None
    assert salas.min_level == rm.ROLE_LEVEL["advogado"]


def test_discover_gates_resolve_helper_booleano_de_pertencimento():
    """`atendimentos.py::_is_staff` retorna `_role_str(user) in
    _ATENDIMENTO_ROLES` (pertencimento, não nível) e é chamado via
    `if not _is_staff(cu): raise 403` em `GET /atendimentos/meus`."""
    gates = rm.discover_gates(ROUTERS_DIR)
    alvo = next((g for g in gates if g.method == "GET" and g.path == "/api/atendimentos/meus"), None)
    assert alvo is not None
    assert alvo.gate_kind == "local_membership"
    assert alvo.allowed_roles, "não resolveu o conjunto de papéis do helper booleano"


def test_discover_gates_resolve_guarda_exclusiva_de_papel_unico():
    """`portal_documentos.py::_exigir_cliente` nega quando
    `cu.role != UserRole.cliente_externo` — guarda EXCLUSIVA (só o papel
    citado passa), o oposto do padrão usual (só a equipe interna passa)."""
    gates = rm.discover_gates(ROUTERS_DIR)
    alvo = next(
        (g for g in gates if g.method == "GET" and g.path == "/api/portal/solicitacoes-documentos"),
        None,
    )
    assert alvo is not None
    assert alvo.gate_kind == "local_membership"
    assert alvo.permite("cliente_externo") is True
    assert alvo.permite("socio") is False
    assert alvo.permite("advogado") is False


def test_discover_gates_resolve_gate_de_router_inteiro():
    """`jurimetria_extra.py`: `router = APIRouter(prefix=..., dependencies=
    [Depends(_req_staff)])` — gate aplicado a TODA rota do arquivo, sem
    NENHUM Depends de papel na assinatura de `ext_stats` em si. Achado real
    rodando a suíte localmente: sem este suporte, a rota aparentava
    "sem gate" (qualquer autenticado passa) quando na verdade nega
    secretaria/cliente_externo."""
    gates = rm.discover_gates(ROUTERS_DIR)
    alvo = next((g for g in gates if g.method == "GET" and g.path == "/api/jurimetria/por-area"), None)
    assert alvo is not None
    assert alvo.min_level == rm.ROLE_LEVEL["estagiario"]
    assert alvo.permite("secretaria") is False
    assert alvo.permite("estagiario") is True


def test_amostra_inclui_gate_de_pertencimento_mesmo_com_min_level_baixo():
    """`portal.py::_exigir_cliente` só permite `cliente_externo` (nível 1) —
    `min_level` sozinho subestimaria a exigência (não é 'qualquer nível >= 1
    passa', é 'só ESTE papel'). Achado real: sem este tratamento a rota caía
    no balde 'sem gate' e só entrava na amostra por sorte da amostragem."""
    gates = rm.discover_gates(ROUTERS_DIR)
    amostra, _ = rm.selecionar_amostra_get(gates)
    caminhos = {(g.method, g.path) for g in amostra}
    assert ("GET", "/api/portal/financeiro") in caminhos
    assert ("GET", "/api/portal/meus-casos") in caminhos


def test_discover_gates_resolve_require_roles_importado_com_alias():
    """`dashboard.py`: `from app.core.security import require_roles as _rr`,
    usado como `Depends(_rr([...]))`. Achado real rodando a suíte localmente:
    sem resolver o alias, `/dashboard/relatorio-mensal` aparentava sem gate."""
    gates = rm.discover_gates(ROUTERS_DIR)
    alvo = next(
        (g for g in gates if g.method == "GET" and g.path == "/api/dashboard/relatorio-mensal"),
        None,
    )
    assert alvo is not None
    assert alvo.gate_kind == "require_roles"
    assert alvo.min_level == min(rm.ROLE_LEVEL[r] for r in ("superadmin", "admin", "socio"))
    assert alvo.permite("advogado") is False


def test_selecionar_amostra_get_inclui_ancoras_de_controle():
    gates = rm.discover_gates(ROUTERS_DIR)
    amostra, _ = rm.selecionar_amostra_get(gates)
    caminhos = {g.path for g in amostra}
    assert "/api/cases/" in caminhos
    assert "/api/users/me" in caminhos


# ── Achado #1 do review do PR #708: prefixo real de include_router() ────────


def test_router_mount_overrides_reflete_mount_canonico_datajud():
    """`router_mount_overrides` considera a primeira montagem do router
    canônico de cada módulo. Após o P3, `datajud_intelligence.router` monta
    diretamente em `API` e carrega seu próprio prefixo `/datajud/intelligence`;
    apenas `casos_router` permanece sob `API + '/casos'`. O teste ancora essa
    distinção para a matriz RBAC não reaplicar o prefixo legado a todas as
    rotas do módulo."""
    overrides = rm.router_mount_overrides(MAIN_PY)
    assert overrides["advogado_estilo"] == "/pecas"
    assert overrides["precedentes_jurisprudencia"] == "/jurisprudencia-externa"
    assert overrides["datajud_intelligence"] == ""
    # Router comum (prefix=API, sem sufixo) não deve ganhar sufixo indevido.
    assert overrides.get("clients", "") == ""


def test_discover_gates_deriva_o_path_real_de_advogado_estilo():
    """Exemplo LITERAL do comentário do review: `advogado_estilo.router` é
    montado sob `API + '/pecas'` (`backend/app/main.py`), então sua rota
    real é `/api/pecas/advogado-estilo/me` — não `/api/advogado-estilo/me`,
    que o parser produzia antes desta correção (e não existe no backend)."""
    gates = rm.discover_gates(ROUTERS_DIR)
    caminhos = {(g.method, g.path) for g in gates}
    assert ("GET", "/api/pecas/advogado-estilo/me") in caminhos
    assert ("GET", "/api/advogado-estilo/me") not in caminhos


def test_discover_gates_deriva_path_de_router_side_effect_antigo():
    """O caso remanescente de Onda 3 §4.1 em `precedentes_jurisprudencia`
    continua sob prefixo extra. DataJud agora possui router canônico próprio,
    enquanto as rotas de caso são preservadas separadamente em `casos_router`."""
    gates = rm.discover_gates(ROUTERS_DIR)
    caminhos = {(g.method, g.path) for g in gates}
    assert any(p.startswith("/api/jurisprudencia-externa/precedentes") for _, p in caminhos)
    assert any(p.startswith("/api/datajud/intelligence/") for _, p in caminhos)


def test_router_mount_overrides_e_falha_aberta_sem_main_py():
    """Sem `main.py` legível, o override fica vazio — `discover_gates` cai de
    volta no comportamento anterior a esta correção (só prefixo local),
    nunca em erro nem em path mais restritivo do que antes."""
    assert rm.router_mount_overrides(Path("/caminho/que/nao/existe/main.py")) == {}


# ── Achado #3 do review do PR #708: 422 só é inconclusivo fora de Depends() ──


def test_via_depends_true_para_gate_de_assinatura():
    """`require_admin`/`require_roles` em `Depends(...)` de assinatura rodam
    ANTES da validação de query do FastAPI — `via_depends` precisa refletir
    isso para `run_fictitious_smoke.py` não tratar um 422 como inconclusivo
    nesse caso (achado #3)."""
    gates = rm.discover_gates(ROUTERS_DIR)
    por_rota = {(g.method, g.path): g for g in gates}
    admin = por_rota[("GET", "/api/users/")]
    assert admin.via_depends is True


def test_via_depends_false_para_checagem_no_corpo_do_handler():
    """`environmental.py` (via `requer_advogado(cu)` chamado NO CORPO) e
    `centro_custos.py::consolidado_geral` (checagem inline no corpo) só
    executam DEPOIS que o FastAPI já validou path/query — um 422 aqui É
    inconclusivo de verdade, `via_depends` precisa ser False."""
    gates = rm.discover_gates(ROUTERS_DIR)
    por_rota = {(g.method, g.path): g for g in gates}
    advogado = por_rota[("GET", "/api/environmental/")]
    assert advogado.via_depends is False
    centro_custos = por_rota[("GET", "/api/centro-custos/consolidado")]
    assert centro_custos.via_depends is False


def test_via_depends_true_para_gate_de_router_inteiro():
    """`dependencies=[Depends(...)]` do ROUTER inteiro também é Depends() —
    roda antes da validação de query de toda rota do arquivo, mesmo quando a
    rota em si não declara Depends próprio (`despesas.py`)."""
    gates = rm.discover_gates(ROUTERS_DIR)
    alvo = next((g for g in gates if g.method == "GET" and g.path == "/api/despesas/resumo"), None)
    assert alvo is not None
    assert alvo.via_depends is True


def test_combinar_gates_local_membership_e_conservador_sem_depends_dos_dois_lados():
    """Intersecção de dois `local_membership` (rota + router) só é
    `via_depends=True` quando o lado da ROTA também vem de `Depends()` — se
    a rota nega só pelo corpo, um papel negado poderia estourar 422 antes de
    alcançar o `raise`, então tratar como conclusivo esconderia esse caso."""
    rota = ("local_membership", ["secretaria"], rm.ROLE_LEVEL["secretaria"])
    router = ("local_membership", ["secretaria", "financeiro"], rm.ROLE_LEVEL["financeiro"])
    combinado, via_depends = rm._combinar_gates(rota, False, router)
    assert combinado[0] == "local_membership"
    assert via_depends is False

    combinado2, via_depends2 = rm._combinar_gates(rota, True, router)
    assert via_depends2 is True


def test_combinar_gates_router_vence_e_e_sempre_via_depends():
    """Quando o gate do ROUTER decide sozinho (rota="nenhum") ou vence por
    min_level, o resultado é sempre `via_depends=True` — `dependencies=[...]`
    do router só existe via `Depends()` por construção."""
    nenhum = ("nenhum", [], 1)
    router_admin = ("require_admin", ["admin"], rm.ROLE_LEVEL["admin"])
    combinado, via_depends = rm._combinar_gates(nenhum, False, router_admin)
    assert combinado == router_admin
    assert via_depends is True
