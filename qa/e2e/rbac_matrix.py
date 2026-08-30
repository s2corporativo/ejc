"""Deriva a matriz RBAC (papel × rota) a partir do código REAL do backend.

Issue #700: a suíte E2E autenticava com uma única conta e nunca provava que
`financeiro`, `secretaria`, `estagiario` e `cliente_externo` são barrados
onde deveriam. Uma lista escrita à mão para cobrir isso envelheceria a cada
PR que mexe em `require_roles(...)` — exatamente o defeito que a Issue #694
documenta (27 gates frouxos que nenhum teste pegaria). Este módulo não
mantém lista nenhuma: faz *parsing estático* (stdlib `ast`, sem importar o
FastAPI app — não precisa de banco nem de settings) dos routers em
`backend/app/routers/*.py` e recalcula a matriz a cada execução da suíte.

Reproduz as MESMAS duas camadas de decisão do backend, nesta ordem:

1. `AuthMiddleware` confina `cliente_externo` a poucos prefixos
   (`backend/app/core/auth_middleware.py:190-198` — hoje efetivamente
   191-204 após correções anteriores; ver `PORTAL_PREFIXES_CLIENTE_EXTERNO`
   e `_cliente_externo_confinado`, que espelham `_path_casa_prefixo_publico`
   linha a linha).
2. Dentro disso, o gate do router decide por HIERARQUIA de nível
   (`backend/app/core/security.py::require_roles` — a checagem real é
   `ROLE_LEVEL[papel] >= min(ROLE_LEVEL[r] for r in allowed)`; pertencer à
   lista `allowed` não é exigido se o nível já for suficiente, e é
   exatamente essa hierarquia que a Issue #694 explora).

Além de `require_roles`/`require_admin`, o parser reconhece os padrões REAIS
encontrados rodando a suíte contra um backend local (Issue #700 — cada um
tinha ao menos uma rota que "sumia" da amostra ou aparentava sem gate antes
de o padrão ser suportado):
- checagem inline no corpo do handler (`if ROLE_LEVEL... < ROLE_LEVEL[...]:
  raise 403`, sem passar por `requer_advogado()`);
- helper local de PERTENCIMENTO ESTRITO (`if papel not in {...}: raise 403`
  — ao contrário de `require_roles`, NÃO tem a hierarquia: um papel de nível
  maior mas fora do conjunto continua negado; ex.: `clients.py::_req_clientes`);
- guarda de IGUALDADE a um único papel (`if cu.role != UserRole.X: raise
  403` — o padrão inverso, "só X passa"; ex.: `portal.py::_exigir_cliente`,
  que exclui a própria equipe interna);
- helper booleano (`def _pode_editar(cu): return ROLE_LEVEL... >= ...`),
  chamado como `if not _pode_editar(cu): raise 403`;
- alias de módulo (`_gestores = require_roles([...])`, usado depois como
  `Depends(_gestores)`) e `require_roles`/`require_admin` importados com
  outro nome (`from ...security import require_roles as _rr`);
- gate do ROUTER INTEIRO (`APIRouter(..., dependencies=[Depends(x)])`),
  combinado (AND lógico) com o gate de cada rota individual.

Limitações conhecidas (documentadas, não escondidas):
- só GET é derivado para a matriz ao vivo (métodos mutantes não são
  seguros para sondar negativamente sem side effect: ver `run_fictitious_smoke.py`);
- GET com query param OBRIGATÓRIO cujo gate é verificado no CORPO do handler
  (não em `Depends()` de assinatura) não é sondável: o FastAPI valida query
  ANTES de rodar o corpo, então falta o param → 422 para QUALQUER papel,
  permitido ou negado, sem o gate nunca executar. `run_fictitious_smoke.py`
  trata esse caso como inconclusivo (não reprova, fica marcado); gates
  declarados via `Depends()` de assinatura NÃO têm este problema — o
  FastAPI resolve sub-dependências antes de path/query;
- `requer_advogado(...)` e os padrões acima são detectados por presença em
  QUALQUER ponto do corpo da função (via `ast.walk`), inclusive dentro de
  `if` condicional a um campo do payload — pode gerar falso positivo de
  "protegido" (a rota aparenta MAIS restrita do que é na prática, nunca
  MENOS: não esconde um gate frouxo real);
- combinação de checagem hierárquica (`ROLE_LEVEL`) com exceção de papel
  único no MESMO `if` (`if nível < X and papel != "Y": raise` — ex.:
  `export.py::export_honorarios`, achado real) não é reconhecida; a rota
  cai em "nenhum" (permite todos) e a sondagem ao vivo reporta uma
  DIVERGÊNCIA (não uma aprovação falsa — divergência é falha, só não é
  rotulada GATE FROUXO);
- rotas cujo `require_roles([...])` recebe uma lista não resolvível
  estaticamente (comprehension, concatenação de listas em runtime) ficam
  como `gate_kind="indeterminado"` e são excluídas da amostra ao vivo — não
  silenciosamente: `discover_gates` as retorna, `selecionar_amostra_get` as
  descarta e o chamador reporta a exclusão.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# Espelha app/core/security.py::ROLE_LEVEL. Divergir daqui é o mesmo bug que
# a duplicação de "socio" já causou uma vez (ver comentário no arquivo
# original) — o teste `test_rbac_matrix.py::test_role_level_espelha_backend`
# compara os dois dicionários lendo o arquivo fonte, então uma mudança em um
# lado sem o outro quebra o CI em vez de divergir em silêncio.
ROLE_LEVEL: dict[str, int] = {
    "superadmin": 9,
    "admin": 8,
    "socio": 7,
    "advogado": 6,
    "advogado_auxiliar": 5,
    "financeiro": 4,
    "estagiario": 3,
    "secretaria": 2,
    "cliente_externo": 1,
}

# Espelha app/core/security.py::EQUIPE_JURIDICA — allowlist EXATA da superfície
# jurídica (Issue #694). NÃO é um piso hierárquico: `financeiro` (nível 4) fica
# ACIMA de `estagiario` (3) em ROLE_LEVEL e mesmo assim NÃO pertence à equipe.
# Diferente das constantes de `_module_role_constants`, esta é IMPORTADA pelos
# routers (`from app.core.security import EQUIPE_JURIDICA`), então não aparece
# como atribuição de módulo no arquivo que a usa — sem registrá-la aqui, todo
# gate `... in EQUIPE_JURIDICA` ficaria irresolvido e a rota apareceria como
# "sem gate" na matriz. `test_rbac_matrix.py::test_equipe_juridica_espelha_backend`
# compara os dois lados para que uma mudança em security.py quebre o CI em vez
# de divergir em silêncio.
EQUIPE_JURIDICA: tuple[str, ...] = (
    "superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario",
)

# Constantes de papel IMPORTADAS de app.core.security que os routers usam como
# container de pertencimento. Semeiam `_module_role_constants` por arquivo; uma
# atribuição de módulo com o mesmo nome, se existir, sobrescreve (o arquivo
# local é sempre mais específico que o default importado).
_CONSTANTES_DE_PAPEL_IMPORTADAS: dict[str, list[str]] = {
    "EQUIPE_JURIDICA": list(EQUIPE_JURIDICA),
}

# Gates COMPARTILHADOS de app/core/security.py chamados direto no corpo do
# handler (`requer_advogado(cu)`, `requer_equipe_juridica(cu, "...")`). O
# `raise 403` mora na função importada, não no arquivo do router, então o
# parser não o encontra varrendo o corpo — precisa conhecê-los por nome.
# Chave = nome da função; valor = o gate que ela impõe.
_GATES_COMPARTILHADOS: dict[str, "GateInfo"] = {
    "requer_advogado": ("requer_advogado", ["advogado"], ROLE_LEVEL["advogado"]),
    # Allowlist exata, NÃO piso: min_level = estagiario (3) só descreve o menor
    # nível da lista; é `permite()` sobre `local_membership` que barra
    # financeiro (4), que está acima desse número e fora da equipe.
    "requer_equipe_juridica": (
        "local_membership", list(EQUIPE_JURIDICA), ROLE_LEVEL["estagiario"],
    ),
}

# Espelha app/core/auth_middleware.py::PREFIXOS_PUBLICOS filtrados para o
# ramo `cliente_externo` (bloco "if request.state.role == 'cliente_externo'").
PORTAL_PREFIXES_CLIENTE_EXTERNO: tuple[str, ...] = (
    "/api/portal/",
    "/api/auth/",
    "/api/health",
    "/api/notifications",
    "/api/signatures",
    "/api/users/me",
)


def _casa_prefixo(path: str, prefixo: str) -> bool:
    """Espelha auth_middleware.py::_path_casa_prefixo_publico."""
    if prefixo.endswith("/"):
        return path.startswith(prefixo)
    return path == prefixo or path.startswith(prefixo + "/")


def cliente_externo_confinado(path: str) -> bool:
    """True quando `AuthMiddleware` barraria cliente_externo nesta rota."""
    return not any(_casa_prefixo(path, p) for p in PORTAL_PREFIXES_CLIENTE_EXTERNO)


@dataclass(frozen=True)
class RouteGate:
    module_key: str
    method: str
    path: str
    gate_kind: str  # "nenhum" | "require_roles" | "local_membership" | "require_admin" | "requer_advogado" | "indeterminado"
    allowed_roles: tuple[str, ...]  # papéis citados no código (informativo p/ relatório)
    min_level: int  # nível mínimo REAL exigido — é isto que decide, não allowed_roles
    source_file: str
    source_line: int
    # True quando o gate DECISIVO (o que resultou em min_level/gate_kind acima,
    # após combinar rota+router) é resolvido via `Depends(...)` — de assinatura
    # OU de `dependencies=[...]` do router — e portanto roda ANTES da validação
    # de query do FastAPI. False quando o gate só existe DENTRO do corpo do
    # handler (checagem inline, ou chamada a um helper local que não passa por
    # Depends()) — nesse caso um 422 por query faltante pode chegar ANTES do
    # `raise 403`, e a rota nunca prova nada sobre RBAC para aquele papel.
    # Decide o achado #3 do review do PR #708: só gate via_depends=True pode
    # tratar um 422 em célula "negada" como bypass real (run_fictitious_smoke.py).
    via_depends: bool = True

    def permite(self, role: str) -> bool:
        if self.gate_kind == "local_membership":
            # Pertencimento ESTRITO (padrão `if papel not in {...}: raise 403`,
            # ex.: clients.py::_req_clientes) — SEM a hierarquia de
            # require_roles(). Um papel de nível superior mas ausente do
            # conjunto (ex.: financeiro fora de `_CLIENTES`) continua negado.
            return role in self.allowed_roles
        return ROLE_LEVEL.get(role, 0) >= self.min_level

    def resultado_esperado(self, role: str) -> int:
        """200 (permitido) ou 403 (negado) — combina as DUAS camadas reais."""
        if role == "cliente_externo" and cliente_externo_confinado(self.path):
            return 403
        return 200 if self.permite(role) else 403


# ── Parsing estático dos routers ─────────────────────────────────────────────

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _string_const(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_prefix(tree: ast.Module) -> str:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "router" for t in node.targets):
            continue
        if isinstance(node.value, ast.Call):
            for kw in node.value.keywords:
                if kw.arg == "prefix":
                    s = _string_const(kw.value)
                    if s is not None:
                        return s
    return ""


def _extract_router_level_deps(tree: ast.Module) -> list[ast.expr]:
    """Devolve as expressões dentro de `dependencies=[...]` do `router =
    APIRouter(...)` — dependências aplicadas a TODA rota do arquivo (padrão
    `dependencies=[Depends(_req_staff)]`, ex.: jurimetria_extra.py: achado
    real rodando a suíte localmente — `/jurimetria/ext/stats` não tinha
    NENHUM gate por função, só o do router inteiro). Cru; resolvido depois
    de `dep_registry` existir, em `discover_gates`."""
    deps: list[ast.expr] = []
    for node in tree.body:
        # Forma 1: APIRouter(..., dependencies=[Depends(...)]).
        if isinstance(node, ast.Assign):
            if not any(isinstance(t, ast.Name) and t.id == "router" for t in node.targets):
                continue
            if isinstance(node.value, ast.Call):
                for kw in node.value.keywords:
                    if kw.arg == "dependencies" and isinstance(kw.value, ast.List):
                        deps.extend(kw.value.elts)
            continue
        # Forma 2: router.dependencies.append(Depends(...)) fora do construtor
        # (padrão da consolidação de jurimetria_extra.py em jurimetria.py:441
        # — sem isto a matriz derivava "permitido" onde o app aplica 403).
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "append"
            and isinstance(node.value.func.value, ast.Attribute)
            and node.value.func.value.attr == "dependencies"
            and isinstance(node.value.func.value.value, ast.Name)
            and node.value.func.value.value.id == "router"
        ):
            deps.extend(node.value.args)
    return deps


def _resolver_gate_de_dependencia(
    dep_expr: ast.expr,
    constants: dict[str, list[str]],
    dep_registry: dict[str, GateInfo],
    aliases: dict[str, str] | None = None,
) -> GateInfo | None:
    """Resolve uma única entrada `Depends(...)` (de assinatura OU de
    `dependencies=[...]` do router) contra os papéis conhecidos."""
    if not (isinstance(dep_expr, ast.Call) and isinstance(dep_expr.func, ast.Name)
            and dep_expr.func.id == "Depends" and dep_expr.args):
        return None
    inner = dep_expr.args[0]
    direto = _match_role_call(inner, constants, aliases)
    if direto and direto[0] != "indeterminado":
        return direto
    if isinstance(inner, ast.Name):
        return dep_registry.get(inner.id)
    return None


def _combinar_gates(
    rota: GateInfo, rota_via_depends: bool, do_router: GateInfo | None
) -> tuple[GateInfo, bool]:
    """AND lógico entre o gate da ROTA e o gate do ROUTER inteiro — a
    requisição real precisa passar pelos DOIS. Sem rota própria, o do router
    vale sozinho; dois `local_membership` combinam por INTERSECÇÃO (AND
    exato); nos demais casos usa o de MAIOR min_level como aproximação
    (o mais exigente decide).

    Devolve também `via_depends`: o gate do ROUTER (`dependencies=[...]`) É
    SEMPRE via `Depends()` por construção (só é extraído por
    `_resolver_gate_de_dependencia`, que só reconhece `Depends(...)`) — roda
    antes da validação de query de QUALQUER rota do arquivo. Quando ele
    decide sozinho (rota="nenhum") ou vence por min_level, `via_depends` é
    True. Na intersecção de dois `local_membership`, um papel pode ser negado
    só pelo lado da ROTA (body, não Depends) — nesse caso a negação real só
    aconteceria DEPOIS da validação de query, então a combinação herda
    `rota_via_depends` (conservador: só True se os DOIS lados forem
    Depends())."""
    if do_router is None or do_router[0] in ("nenhum", "indeterminado"):
        return rota, rota_via_depends
    if rota[0] == "nenhum":
        return do_router, True
    if rota[0] == "local_membership" and do_router[0] == "local_membership":
        inter = [r for r in rota[1] if r in do_router[1]]
        level = min((ROLE_LEVEL.get(r, 0) for r in inter), default=0) if inter else 999
        return ("local_membership", inter, level), rota_via_depends
    if rota[2] >= do_router[2]:
        return rota, rota_via_depends
    return do_router, True


def _join(prefix: str, subpath: str) -> str:
    full = f"/api{prefix}{subpath}"
    if len(full) > 1 and full.endswith("/") and not subpath.endswith("/") and subpath != "":
        pass
    # Colapsa barras duplicadas (prefix="" + subpath="/" -> "/api/")
    while "//" in full:
        full = full.replace("//", "/")
    return full


def _decorator_route(dec: ast.expr) -> tuple[str, str] | None:
    """@router.get("/x") -> ("get", "/x"); ignora decorators que não são rota."""
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "router"):
        return None
    method = func.attr
    if method not in _HTTP_METHODS:
        return None
    if not dec.args:
        return None
    path = _string_const(dec.args[0])
    if path is None:
        return None
    return method, path


# GateInfo: (gate_kind, allowed_roles_ou_None, min_level). `gate_kind` decide
# a SEMÂNTICA de `permite()` em RouteGate — "local_membership" é
# pertencimento ESTRITO (sem hierarquia); os demais usam nível (>= min_level),
# espelhando require_roles() do backend.
GateInfo = tuple[str, "list[str] | None", int]

# Depends() cujo alvo NÃO é gate de papel — presença isolada não marca a rota
# como "indeterminado" (ficaria fora da amostra sem necessidade).
_DEPENDS_NEUTROS = {"get_current_user", "get_db"}


def _extract_roles_from_expr(node: ast.expr, constants: dict[str, list[str]]) -> list[str] | None:
    """Resolve o conjunto de papéis de uma expressão: lista/tupla/set literal
    `["a","b"]`/`("a","b")`/`{"a","b"}`, `frozenset({...})`/`set([...])`, ou
    nome de constante do MÓDULO (resolvido por `_module_role_constants` —
    padrão dominante no repo: `_EQUIPE`, `_GESTORES`, `_CLIENTES`,
    `GOVERNANCE_ROLES` etc.). Sem isto a maioria dos gates do backend ficaria
    "indeterminado" e fora da amostra ao vivo — o oposto do que a Issue #700
    pede."""
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        roles: list[str] = []
        for elt in node.elts:
            s = _string_const(elt)
            if s is None:
                return None
            roles.append(s)
        return roles or None
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("frozenset", "set") and node.args):
        return _extract_roles_from_expr(node.args[0], constants)
    return None


def _module_role_constants(tree: ast.Module) -> dict[str, list[str]]:
    """Varre atribuições de nível de módulo `NOME = [...]` / `{...}` / `(...)`
    para resolver referências por nome (ver `_extract_roles_from_expr`)."""
    out: dict[str, list[str]] = dict(_CONSTANTES_DE_PAPEL_IMPORTADAS)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        roles = _extract_roles_from_expr(node.value, {})
        if roles:
            out[node.targets[0].id] = roles
    return out


def _raises_403(node: ast.AST) -> bool:
    """True se, em algum ponto de `node`, um `raise HTTPException(403, ...)`
    (ou `status_code=403`/`status.HTTP_403_FORBIDDEN`) aparece — confirma que
    a condição encontrada é mesmo um GATE de autorização, não outra checagem
    qualquer que também usa `not in`/`<`."""
    for n in ast.walk(node):
        if not isinstance(n, ast.Raise) or n.exc is None or not isinstance(n.exc, ast.Call):
            continue
        exc = n.exc
        for kw in exc.keywords:
            if kw.arg == "status_code" and isinstance(kw.value, ast.Constant) and kw.value.value == 403:
                return True
        if exc.args:
            a0 = exc.args[0]
            if isinstance(a0, ast.Constant) and a0.value == 403:
                return True
            if isinstance(a0, ast.Attribute) and a0.attr == "HTTP_403_FORBIDDEN":
                return True
    return False


def _find_membership_check(body: list[ast.stmt], constants: dict[str, list[str]]) -> list[str] | None:
    """Acha `if <papel> not in <container>: raise ...403` (padrão de
    `_req_clientes`/`_req_clientes_leitura` em clients.py e afins) — checagem
    de PERTENCIMENTO ESTRITO, sem a hierarquia de require_roles()."""
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            container = None
            if (isinstance(test, ast.Compare) and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.NotIn)):
                container = test.comparators[0]
            elif (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
                    and isinstance(test.operand, ast.Compare) and len(test.operand.ops) == 1
                    and isinstance(test.operand.ops[0], ast.In)):
                container = test.operand.comparators[0]
            if container is None:
                continue
            roles = _extract_roles_from_expr(container, constants)
            if roles and _raises_403(node):
                return roles
    return None


def _role_level_subscript_literal(node: ast.expr) -> str | None:
    """`ROLE_LEVEL["socio"]` -> "socio"."""
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "ROLE_LEVEL":
        return _string_const(node.slice)
    return None


def _find_inline_level_check(body: list[ast.stmt]) -> int | None:
    """Acha `if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]: raise
    ...403` — padrão inline usado em vários routers (ex.: centro_custos.py)
    EM VEZ do helper `requer_advogado()`. Mesma ideia, sem o helper nomeado."""
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if not (isinstance(test, ast.Compare) and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.Lt)):
                continue
            papel = _role_level_subscript_literal(test.comparators[0])
            if papel and papel in ROLE_LEVEL and _raises_403(node):
                return ROLE_LEVEL[papel]
    return None


def _find_bool_return_gate(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, constants: dict[str, list[str]]
) -> GateInfo | None:
    """Reconhece helper booleano de UMA linha, usado depois via
    `if not <helper>(cu): raise 403`. Dois formatos observados no repo:
    - nível: `return ROLE_LEVEL.get(cu.role.value, 0) >= ROLE_LEVEL["advogado"]`
      (`data_room_v4.py::_pode_editar`);
    - pertencimento: `return _role_str(user) in _ATENDIMENTO_ROLES`
      (`atendimentos.py::_is_staff`)."""
    for stmt in fn.body:
        if not isinstance(stmt, ast.Return) or stmt.value is None:
            continue
        val = stmt.value
        if not (isinstance(val, ast.Compare) and len(val.ops) == 1):
            continue
        if isinstance(val.ops[0], ast.GtE):
            papel = _role_level_subscript_literal(val.comparators[0])
            if papel and papel in ROLE_LEVEL:
                return ("local_level", None, ROLE_LEVEL[papel])
        if isinstance(val.ops[0], ast.In):
            roles = _extract_roles_from_expr(val.comparators[0], constants)
            if roles:
                level = min((ROLE_LEVEL.get(r, 0) for r in roles), default=0)
                return ("local_membership", roles, level)
    return None


def _find_bool_helper_call_check(body: list[ast.stmt], bool_helpers: dict[str, GateInfo]) -> GateInfo | None:
    """Acha `if not <helper>(cu ...): raise ...403` onde `<helper>` é uma
    função já resolvida por `_find_bool_return_gate`."""
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
                    and isinstance(test.operand, ast.Call)
                    and isinstance(test.operand.func, ast.Name)):
                continue
            nome = test.operand.func.id
            if nome in bool_helpers and _raises_403(node):
                return bool_helpers[nome]
    return None


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    """`from app.core.security import require_roles as _rr` -> {"_rr":
    "require_roles"} — achado real (`dashboard.py`): sem isto, `Depends(_rr([
    ...]))` fica invisível ao parser porque `_rr` não é `require_roles`
    textualmente. Cobre os nomes de gate reconhecidos pelo parser, incluindo
    os compartilhados de `_GATES_COMPARTILHADOS` (`requer_equipe_juridica as
    _je_requer_equipe_juridica` em jurimetria.py — sem isto o gate do router
    inteiro ficava invisível e a matriz derivava "permitido" onde o app nega
    com 403)."""
    reconhecidos = ("require_roles", "require_roles_exact", "require_admin",
                    *_GATES_COMPARTILHADOS)
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            if alias.name in reconhecidos and alias.asname:
                aliases[alias.asname] = alias.name
    return aliases


def _string_from_role_attr(node: ast.expr) -> str | None:
    """`UserRole.cliente_externo` -> "cliente_externo" (o nome do membro do
    enum é IGUAL ao valor — ver app/models/user.py::UserRole)."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "UserRole":
        return node.attr
    return None


def _find_role_equality_check(body: list[ast.stmt]) -> list[str] | None:
    """Acha `<algo>.role != UserRole.X` num `if` que RAISE 403 — idioma de
    guarda EXCLUSIVA (só o papel X passa; usado em endpoints do Portal do
    Cliente que devem excluir a equipe interna, ex.: `portal_documentos.py
    ::_exigir_cliente` — `if cu.role != UserRole.cliente_externo or not
    cu.client_id: raise 403`). Diferente de `_find_membership_check`
    (`not in <conjunto>`): aqui é igualdade a um ÚNICO papel."""
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.If) or not _raises_403(node):
                continue
            achados: list[str] = []
            for comp in ast.walk(node.test):
                if (isinstance(comp, ast.Compare) and len(comp.ops) == 1
                        and isinstance(comp.ops[0], ast.NotEq)
                        and isinstance(comp.left, ast.Attribute) and comp.left.attr == "role"):
                    papel = _string_from_role_attr(comp.comparators[0])
                    if papel:
                        achados.append(papel)
            if achados:
                return achados
    return None


def _find_helper_call_gate(
    body: list[ast.stmt],
    helper_gates: dict[str, GateInfo],
    aliases: dict[str, str] | None = None,
) -> GateInfo | None:
    """Acha chamada a um helper JÁ conhecido como gate (`requer_advogado(cu)`,
    ou um helper local tipo `_require_admin_socio(cu)` resolvido por
    `_analisar_helpers_locais`) em qualquer ponto do corpo. `aliases` resolve
    import renomeado (`requer_equipe_juridica as _je_requer_equipe_juridica`,
    achado real em jurimetria.py) para o nome canônico antes de comparar."""
    aliases = aliases or {}
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                nome = aliases.get(node.func.id, node.func.id)
                if nome in helper_gates:
                    return helper_gates[nome]
    return None


def _match_role_call(
    node: ast.expr, constants: dict[str, list[str]], aliases: dict[str, str] | None = None
) -> GateInfo | None:
    """Reconhece `require_roles([...])` ou `require_admin` NUS — usados tanto
    dentro de `Depends(...)` quanto em alias de módulo (`_gestores =
    require_roles([...])`, padrão de system_modules.py e afins). `aliases`
    resolve import renomeado (`require_roles as _rr`, achado real em
    dashboard.py) para o nome canônico antes de comparar."""
    aliases = aliases or {}
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        nome_func = aliases.get(node.func.id, node.func.id)
        if nome_func in ("require_roles", "require_roles_exact"):
            if not node.args:
                return ("indeterminado", None, -1)
            roles = _extract_roles_from_expr(node.args[0], constants)
            if roles is None:
                return ("indeterminado", None, -1)
            level = min((ROLE_LEVEL.get(r, 0) for r in roles), default=0)
            kind = "local_membership" if nome_func == "require_roles_exact" else "require_roles"
            return (kind, roles, level)
    if isinstance(node, ast.Name) and aliases.get(node.id, node.id) == "require_admin":
        return ("require_admin", ["admin"], ROLE_LEVEL["admin"])
    return None


def _module_dep_aliases(
    tree: ast.Module, constants: dict[str, list[str]], aliases: dict[str, str] | None = None
) -> dict[str, GateInfo]:
    """`_gestores = require_roles(["superadmin", "admin", "socio"])` a nível
    de módulo, usado depois como `Depends(_gestores)` (system_modules.py)."""
    out: dict[str, GateInfo] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        gate = _match_role_call(node.value, constants, aliases)
        if gate:
            out[node.targets[0].id] = gate
    return out


def _analisar_helpers_locais(
    tree: ast.Module, constants: dict[str, list[str]], aliases: dict[str, str] | None = None
) -> dict[str, GateInfo]:
    """Analisa TODA função de nível de módulo (não só as decoradas como rota)
    em busca de um gate no PRÓPRIO corpo — cobre tanto helpers dedicados
    (`_req_clientes`, `_require_admin_socio`) quanto handlers de rota que
    fazem a checagem inline (`consolidado_geral` em centro_custos.py).
    Resolve booleanos (`_pode_editar`) numa segunda passada, já com o
    primeiro conjunto de helpers de raise disponível."""
    funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    helper_gates: dict[str, GateInfo] = {}
    bool_helpers: dict[str, GateInfo] = {}
    for fn in funcs:
        roles = _find_membership_check(fn.body, constants)
        if roles:
            level = min((ROLE_LEVEL.get(r, 0) for r in roles), default=0)
            helper_gates[fn.name] = ("local_membership", roles, level)
            continue
        level = _find_inline_level_check(fn.body)
        if level is not None:
            helper_gates[fn.name] = ("local_level", None, level)
            continue
        eq_roles = _find_role_equality_check(fn.body)
        if eq_roles:
            eq_level = min((ROLE_LEVEL.get(r, 0) for r in eq_roles), default=0)
            helper_gates[fn.name] = ("local_membership", eq_roles, eq_level)
            continue
        # Helper que só delega a um gate compartilhado de security.py
        # (`_req_staff` em jurimetria_extra.py chama requer_equipe_juridica).
        # O `raise 403` está na função importada, não neste arquivo, então
        # nenhuma das varreduras acima o encontra.
        compartilhado = _find_helper_call_gate(fn.body, _GATES_COMPARTILHADOS, aliases)
        if compartilhado:
            helper_gates[fn.name] = compartilhado
            continue
        bool_gate = _find_bool_return_gate(fn, constants)
        if bool_gate:
            bool_helpers[fn.name] = bool_gate

    # 2ª passada: funções que só chamam um bool_helper (`if not _pode_editar(cu)`)
    # — precisa dos bool_helpers já resolvidos da 1ª passada.
    for fn in funcs:
        if fn.name in helper_gates:
            continue
        gate = _find_bool_helper_call_check(fn.body, bool_helpers)
        if gate:
            helper_gates[fn.name] = gate

    return helper_gates


def _find_gate_in_signature(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    constants: dict[str, list[str]],
    dep_registry: dict[str, GateInfo],
    aliases: dict[str, str] | None = None,
) -> GateInfo | None:
    """Varre os `Depends(...)` da assinatura. Prioriza gate reconhecido
    diretamente (`require_roles`/`require_admin`); senão resolve por NOME via
    `dep_registry` (aliases de módulo + helpers locais); Depends "neutro"
    (`get_current_user`/`get_db`) é ignorado sem marcar indeterminado."""
    args = fn.args
    pares: list[ast.expr | None] = []
    posargs = args.posonlyargs + args.args
    defaults = list(args.defaults)
    offset = len(posargs) - len(defaults)  # defaults alinha-se ao FINAL de posargs
    for i in range(len(posargs)):
        pares.append(defaults[i - offset] if i >= offset else None)
    pares += list(args.kw_defaults or [])

    achou_indeterminado = False
    for default in pares:
        if default is None or not isinstance(default, ast.Call):
            continue
        func = default.func
        if not (isinstance(func, ast.Name) and func.id == "Depends") or not default.args:
            continue
        inner = default.args[0]
        direto = _match_role_call(inner, constants, aliases)
        if direto:
            return direto
        if isinstance(inner, ast.Name):
            if inner.id in dep_registry:
                return dep_registry[inner.id]
            if inner.id not in _DEPENDS_NEUTROS:
                achou_indeterminado = True
    return ("indeterminado", None, -1) if achou_indeterminado else None


def _gate_from_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    constants: dict[str, list[str]],
    dep_registry: dict[str, GateInfo],
    aliases: dict[str, str] | None = None,
) -> tuple[GateInfo, bool]:
    """Retorna ((gate_kind, allowed_roles, min_level), via_depends), tentando
    nesta ordem:
    1) Depends() reconhecido/resolvido na assinatura — `via_depends=True`:
       o FastAPI resolve TODA sub-dependência (`Depends(...)`) ANTES de
       validar os parâmetros (path/query) da PRÓPRIA rota, então um `raise
       403` aqui sempre chega antes de um 422 de query faltante;
    2) auto-checagem da PRÓPRIA função — membership/nível inline, OU um
       helper booleano chamado com `if not _helper(cu): raise 403`
       (`dep_registry[fn.name]`, computado por `_analisar_helpers_locais`
       para TODA função do módulo, não só as decoradas como rota — cobre
       tanto handlers com checagem embutida quanto helpers dedicados) —
       `via_depends=False`: isto roda DENTRO do corpo do handler, só depois
       que o FastAPI já validou path/query — um 422 de query pode mascarar
       este `raise 403` para QUALQUER papel;
    3) chamada, no CORPO, a `requer_advogado(...)` ou a um helper local
       DIFERENTE já conhecido (ex.: handler que chama `_require_admin_socio(cu)`,
       cujo PRÓPRIO corpo tem o `raise`, não o do handler) — `via_depends=False`
       pelo mesmo motivo do item 2;
    4) "nenhum" — qualquer autenticado passa (cliente_externo tratado à
       parte pelo confinamento do AuthMiddleware) — `via_depends=False`
       (não há gate nenhum para "chegar antes" de coisa alguma)."""
    found = _find_gate_in_signature(fn, constants, dep_registry, aliases)
    if found and found[0] != "indeterminado":
        return found, True

    auto = dep_registry.get(fn.name)
    if auto:
        return auto, False

    chamada = _find_helper_call_gate(
        fn.body, {**dep_registry, **_GATES_COMPARTILHADOS}, aliases
    )
    if chamada:
        return chamada, False

    if found and found[0] == "indeterminado":
        return found, True
    return ("nenhum", [], 1), False  # qualquer autenticado (piso = cliente_externo, tratado à parte)


# ── Grafo real de include_router() em app/main.py ────────────────────────────
# Quase todo router é montado com `app.include_router(x.router, prefix=API)`
# — mas alguns (Onda 3 §4.1 de main.py: `precedentes_jurisprudencia`,
# `advogado_estilo`, `datajud_intelligence`) recebem um prefixo EXTRA
# (`prefix=API + "/pecas"` etc.), reproduzindo o path onde eram anexados por
# side effect antes da correção. Sem ler isto de `main.py`, o parser assumia
# sempre `/api` + prefixo local do próprio arquivo router — 404 espúrio
# (achado do review do PR #708).


def _extra_prefix_from_call(call: ast.Call) -> str | None:
    """Extrai o prefixo EXTRA de um `app.include_router(x.router,
    prefix=...)`: `""` quando `prefix=API` (sem sufixo), a string literal
    quando `prefix=API + "/algo"`. `None` quando o argumento `prefix` não é
    resolvível estaticamente (nome que não é `API`, concatenação não
    literal) — o chamador trata isso como "sem sufixo conhecido", igual ao
    comportamento de antes desta correção: nunca mais restritivo, só mais
    correto quando dá para resolver."""
    prefix_expr: ast.expr | None = None
    for kw in call.keywords:
        if kw.arg == "prefix":
            prefix_expr = kw.value
            break
    if prefix_expr is None and len(call.args) >= 2:
        prefix_expr = call.args[1]
    if prefix_expr is None:
        return ""
    if isinstance(prefix_expr, ast.Name) and prefix_expr.id == "API":
        return ""
    if (
        isinstance(prefix_expr, ast.BinOp)
        and isinstance(prefix_expr.op, ast.Add)
        and isinstance(prefix_expr.left, ast.Name)
        and prefix_expr.left.id == "API"
    ):
        sufixo = _string_const(prefix_expr.right)
        if sufixo is not None:
            return sufixo
    return None


def router_mount_overrides(main_py: Path) -> dict[str, str]:
    """Deriva, por parsing estático de `app/main.py`, o prefixo EXTRA (além
    de `/api`) que cada módulo de router recebe em `app.include_router(...)`
    — chave = nome do módulo (`path.stem` em `backend/app/routers/`, o mesmo
    `module_key` usado por `discover_gates`).

    Resolve o alias de import (`from app.routers import api_keys as
    api_keys_router`) para o nome REAL do módulo antes de indexar — sem isto
    a única ocorrência de alias no repo (`api_keys_router`) ficaria sem
    entrada, mas por sorte esse módulo não tem prefixo extra hoje; ainda
    assim, resolver o alias é o que torna a função correta em geral, não só
    para os 3 casos conhecidos.

    Falha aberta (não fecha): se `main.py` não existir/não parsear, ou se o
    módulo simplesmente não aparecer no grafo de mounts, devolve `{}`/omite a
    chave — o chamador usa `.get(module_key, "")`, ou seja, sem override
    conhecido o comportamento é o de ANTES desta correção (só prefixo local
    do próprio router), nunca pior."""
    try:
        text = main_py.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text, filename=str(main_py))
    except (OSError, SyntaxError):
        return {}

    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.routers":
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name

    overrides: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "app"
        ):
            continue
        if not node.args:
            continue
        router_expr = node.args[0]
        # `x.router` ou `x.router_status` (ex.: ia_saude) — o que importa é o
        # módulo (`x`), o atributo é só QUAL router dentro dele.
        if not (isinstance(router_expr, ast.Attribute) and isinstance(router_expr.value, ast.Name)):
            continue
        module_local_name = router_expr.value.id
        module_key = aliases.get(module_local_name, module_local_name)
        extra = _extra_prefix_from_call(node)
        if extra is None:
            continue
        # Primeira ocorrência vence: no repo atual nenhum módulo é montado
        # duas vezes com prefixos EXTRA diferentes (só `ia_saude`, com o
        # mesmo prefixo "" nas duas linhas) — divergência real seria um
        # padrão novo, fora do escopo desta correção.
        overrides.setdefault(module_key, extra)
    return overrides


def discover_gates(routers_dir: Path, main_py: Path | None = None) -> list[RouteGate]:
    """Varre `backend/app/routers/*.py` e deriva o gate de cada rota.

    `main_py` (default `routers_dir.parent / "main.py"`) é parseado UMA vez
    para achar o prefixo EXTRA que cada módulo recebe em `app.include_router(
    ..., prefix=...)` — ver `router_mount_overrides`. Sem isto o path
    derivado assumia sempre `/api` + prefixo LOCAL do próprio router, o que
    gera 404 espúrio para os poucos módulos montados com um prefixo adicional
    (achado do review do PR #708: `advogado_estilo.router` monta em
    `API + "/pecas"`, então sua rota real é `/api/pecas/advogado-estilo/me`,
    não `/api/advogado-estilo/me`)."""
    if main_py is None:
        main_py = routers_dir.parent / "main.py"
    mount_overrides = router_mount_overrides(main_py)

    gates: list[RouteGate] = []
    for path in sorted(routers_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "APIRouter" not in text:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        prefix = mount_overrides.get(path.stem, "") + _extract_prefix(tree)
        module_key = path.stem
        constants = _module_role_constants(tree)
        aliases = _import_aliases(tree)
        dep_registry: dict[str, GateInfo] = {}
        dep_registry.update(_module_dep_aliases(tree, constants, aliases))
        # Helpers locais (`_req_clientes`, `_require_admin_socio`, checagem
        # inline em handlers) resolvidos por ÚLTIMO: um alias de módulo com o
        # MESMO nome (raro) prevalece, mantendo a fonte mais explícita.
        for nome, gate in _analisar_helpers_locais(tree, constants, aliases).items():
            dep_registry.setdefault(nome, gate)

        # Gate do ROUTER INTEIRO (`APIRouter(..., dependencies=[Depends(x)])`)
        # — aplica-se a TODA rota do arquivo, mesmo quem não declara Depends
        # próprio. Primeiro reconhecido vence (múltiplas entradas de gate no
        # mesmo `dependencies=[...]` são incomuns neste repo).
        router_gate: GateInfo | None = None
        for dep_expr in _extract_router_level_deps(tree):
            resolvido = _resolver_gate_de_dependencia(dep_expr, constants, dep_registry, aliases)
            if resolvido and resolvido[0] not in ("nenhum", "indeterminado"):
                router_gate = resolvido
                break

        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                route = _decorator_route(dec)
                if not route:
                    continue
                method, subpath = route
                full_path = _join(prefix, subpath)
                rota_gate, rota_via_depends = _gate_from_function(node, constants, dep_registry, aliases)
                (kind, roles, level), via_depends = _combinar_gates(rota_gate, rota_via_depends, router_gate)
                gates.append(
                    RouteGate(
                        module_key=module_key,
                        method=method.upper(),
                        path=full_path,
                        gate_kind=kind,
                        allowed_roles=tuple(roles or ()),
                        min_level=level,
                        source_file=str(path.relative_to(routers_dir.parents[1])),
                        source_line=node.lineno,
                        via_depends=via_depends,
                    )
                )
    return gates


# ── Query mínima VÁLIDA por rota (pente fino 2026-08-30 §5.5) ────────────────
# GET com query param OBRIGATÓRIO responde 422 quando sondado sem parâmetros —
# o 422 até prova autorização quando o gate é via Depends() (ver via_depends),
# mas NUNCA exercita o handler. Este mapa dá a cada rota dessas uma query
# mínima VÁLIDA (valores fictícios inofensivos, conferidos ao vivo contra um
# backend local com token admin em 30/08/2026) para a sonda enviar. Para rota
# COBERTA pelo mapa, `run_fictitious_smoke.py` deixa de aceitar 422 em
# silêncio: um 422 ali significa mapa desatualizado (parâmetro renomeado/novo
# obrigatório) e REPROVA, em vez de virar "inconclusivo".


@dataclass(frozen=True)
class QueryMinima:
    """Query string mínima que faz o handler EXECUTAR (não só validar).

    `aceitos_alem_de_200`: códigos que, para papel PERMITIDO, também contam
    como handler exercitado — usados quando o handler exige um RECURSO
    existente que a sonda não tem como forjar (o motivo fica documentado em
    `motivo`, nunca implícito). Rotas de IA/fontes externas que degradam
    graciosamente (ex.: provedor ausente → 200 com aviso, ou 503 explícito do
    handler) também entram por aqui — nunca um 5xx genérico."""

    params: tuple[tuple[str, str], ...]
    aceitos_alem_de_200: tuple[int, ...] = ()
    motivo: str = ""

    def query_string(self) -> str:
        from urllib.parse import urlencode

        return urlencode(list(self.params))


QUERY_MINIMA_POR_ROTA: dict[str, QueryMinima] = {
    # calculadoras.py — Query(..., gt=0); qualquer valor positivo executa.
    "/api/calculadoras/inss": QueryMinima((("salario", "3000"),)),
    "/api/calculadoras/irrf": QueryMinima((("rendimento", "5000"),)),
    # jurisprudencia_externa.py — q: min_length=3. As buscas externas degradam
    # graciosamente DENTRO do serviço (exceções viram lista vazia → 200),
    # então 200 é o único código de sucesso mesmo sem rede.
    "/api/jurisprudencia-externa/buscar": QueryMinima((("q", "dano moral"),)),
    "/api/jurisprudencia-externa/buscar/lexml": QueryMinima((("q", "dano moral"),)),
    "/api/jurisprudencia-externa/buscar/tjmg": QueryMinima((("q", "dano moral"),)),
    # ficha_triagem.py — o handler exige caso EXISTENTE (verificar_acesso_caso
    # roda DEPOIS do gate `_exigir_piso`): com um case_id fictício o papel
    # permitido chega ao handler e recebe 404 "caso não encontrado" — isso JÁ
    # exercita gate + handler; a sonda não tem como forjar um caso real por
    # papel (mesma limitação documentada para paths com parâmetro).
    "/api/triagem/ficha": QueryMinima(
        (("case_id", "00000000-0000-0000-0000-000000000000"),),
        aceitos_alem_de_200=(404,),
        motivo=(
            "handler exige caso existente (verificar_acesso_caso); 404 com "
            "case_id fictício prova que gate e handler executaram"
        ),
    ),
    # ai.py::roteamento_preview — task_type é texto livre normalizado pelo
    # gateway; sem provedor a rota degrada graciosamente respondendo 200 com
    # `provider_elegivel=false` (nunca 5xx), conferido ao vivo.
    "/api/ai/roteamento/preview": QueryMinima((("task_type", "chat_juridico"),)),
    # consumidor_monitor.py — empresa é texto livre; fora da base interna o
    # handler responde 200 com avaliação genérica.
    "/api/consumidor-monitor/triagem-jec": QueryMinima(
        (("empresa", "Empresa Ficticia Exemplo"),)
    ),
    # previdenciario_beneficio.py — simulação stateless; idade/tempo dentro
    # dos ranges validados (ge/le) executam o cálculo completo.
    "/api/previdenciario/ferramentas/regras-transicao": QueryMinima(
        (("idade", "58"), ("tempo_contribuicao_anos", "30"))
    ),
}


# ── Seleção da amostra segura para sondagem ao vivo ──────────────────────────

# Paths com parâmetro de path (`{algo}`) exigem um ID real — sem ele o 404 de
# "não encontrado" se confunde com o 404 de rota ausente. Fora de escopo desta
# suíte (que não tem como forjar IDs válidos por papel); a amostra ao vivo
# cobre só paths sem parâmetro.
def _tem_parametro_de_path(path: str) -> bool:
    return "{" in path


# Rotas âncora sempre incluídas na fração "sem gate" quando existirem — cobrem
# o caso de controle mais importante (rota liberada ao papel de piso e à qual
# cliente_externo TEM acesso via AuthMiddleware) sem depender de sorte na
# amostragem determinística abaixo.
_ANCORAS_SEM_GATE = ("/api/cases/", "/api/clients/", "/api/users/me", "/api/health")


def selecionar_amostra_get(
    gates: list[RouteGate], max_sem_gate: int = 15
) -> tuple[list[RouteGate], list[RouteGate]]:
    """Retorna (amostra, excluidos) para a sondagem AO VIVO.

    `amostra` inclui TODA rota GET, sem parâmetro de path, com gate explícito
    — hierarquia (`min_level > 1`) OU pertencimento estrito
    (`gate_kind == "local_membership"`, mesmo com `min_level == 1`: um gate
    "só cliente_externo passa" tem min_level=1 porque cliente_externo É nível
    1, mas NEGA todo o resto — tratá-lo como "sem gate" pelo número sozinho
    seria o oposto do que essa classe de rota precisa provar; achado real
    desta suíte rodando localmente, ver `/api/portal/financeiro`). Testar
    todas, não uma fatia, porque cada uma pode ter um gate individualmente
    frouxo (é o padrão exato da Issue #694); amostrar aqui reproduziria o
    mesmo ponto cego que a suíte tinha antes desta correção.

    Rotas SEM gate (`min_level == 1`, qualquer autenticado passa) são
    controle — provam que a suíte não super-restringe. Amostradas (não
    todas: são ~180 e não agregam poder de detecção proporcional ao custo)
    de forma DETERMINÍSTICA (mesmo path -> mesma posição sempre, sem
    aleatoriedade) mais as âncoras de `_ANCORAS_SEM_GATE`.

    `excluidos` é reportado, nunca descartado em silêncio (mesma disciplina
    do achado AI-005 para `nao_coberto`)."""
    gated: list[RouteGate] = []
    sem_gate: list[RouteGate] = []
    excluidos: list[RouteGate] = []
    vistos: set[str] = set()
    for g in sorted(gates, key=lambda x: (x.path, x.method)):
        if g.method != "GET":
            continue
        chave = f"{g.method} {g.path}"
        if chave in vistos:
            continue
        vistos.add(chave)
        if g.gate_kind == "indeterminado" or _tem_parametro_de_path(g.path):
            excluidos.append(g)
            continue
        tem_gate = g.min_level > 1 or g.gate_kind == "local_membership"
        (gated if tem_gate else sem_gate).append(g)

    ancoras = [g for g in sem_gate if g.path in _ANCORAS_SEM_GATE]
    resto = [g for g in sem_gate if g.path not in _ANCORAS_SEM_GATE]
    faltam = max(0, max_sem_gate - len(ancoras))
    if resto and faltam:
        passo = max(1, len(resto) // faltam)
        amostrado = resto[::passo][:faltam]
    else:
        amostrado = []
    excluidos.extend(g for g in resto if g not in amostrado)

    amostra = gated + ancoras + amostrado
    return amostra, excluidos
