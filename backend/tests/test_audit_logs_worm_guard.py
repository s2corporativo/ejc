"""Issue #699 — trava de VARREDURA (não enumeração) contra rota de mutação
sobre `audit_logs`.

A imutabilidade real vive no banco (trigger `trg_audit_logs_bloqueia_mutacao`,
migration `131_audit_logs_worm`). Este arquivo é a segunda linha de defesa,
mais barata: reprova em CI — sem precisar de Postgres — qualquer PR que
registre uma rota HTTP de mutação sobre a entidade de auditoria, ANTES de
chegar a produção e esbarrar no trigger.

Estilo inspirado no invariante de `test_areas_atuacao_onda2.py`
(`test_invariante_toda_ferramenta_tem_metadados_ou_selo`): varre o app REAL
(ou o código-fonte real) por padrão, em vez de checar uma lista fixa de rotas
conhecidas — o objetivo é pegar o que ainda NÃO existe.
"""
from __future__ import annotations

import inspect
import re

import pytest

_METODOS_DE_MUTACAO = {"POST", "PUT", "PATCH", "DELETE"}

# Segmento de path que identifica a ENTIDADE audit_logs — não a substring
# "audit" (que também aparece em rotas legítimas e sem relação, como
# /api/ai/auditar-peca ou /api/.../auditoria-pre-producao). Casa "/audit",
# "/audit_logs"/"/audit-logs"/"/audit_log"/"/audit-log" como segmento
# INTEIRO do path.
_SEGMENTO_AUDIT_LOGS = re.compile(r"^audit([_-]logs?)?$")


def _e_rota_de_audit_logs(path: str) -> bool:
    segmentos = [s for s in path.lower().split("/") if s and "{" not in s]
    return any(_SEGMENTO_AUDIT_LOGS.fullmatch(s) for s in segmentos)


def test_nenhuma_rota_registrada_muta_audit_logs():
    """Varre TODAS as rotas montadas em `app.main.app` (não uma lista fixa).

    Qualquer rota cujo path tenha "audit"/"audit_logs" como SEGMENTO e
    responda a um método de mutação reprova — não importa em qual
    router/arquivo ela tenha sido registrada. Isso cobre tanto uma rota nova
    em `app/routers/audit.py` quanto um router futuro montado em outro
    prefixo que também mexa em `audit_logs`. Não usa substring solta porque
    "audit" também aparece em rotas sem relação (`/ai/auditar-peca`,
    `/.../auditoria-pre-producao`) — falso positivo derrubaria a confiança
    na trava e convidaria a ignorá-la.
    """
    from app.main import app

    achadas = []
    total_rotas_audit = 0
    for rota in app.routes:
        path = (getattr(rota, "path", "") or "")
        if not _e_rota_de_audit_logs(path):
            continue
        total_rotas_audit += 1
        metodos = set(getattr(rota, "methods", None) or set())
        mutantes = sorted(metodos & _METODOS_DE_MUTACAO)
        if mutantes:
            achadas.append((path, mutantes))

    # Guarda contra falso-positivo por varredura vazia (path não encontrado
    # por erro de digitação, módulo não importado etc.) — precisa achar pelo
    # menos a rota de leitura que hoje existe.
    assert total_rotas_audit > 0, (
        "a varredura não encontrou NENHUMA rota com 'audit' no path — "
        "verifique se app.routers.audit segue montado em app/main.py"
    )
    assert not achadas, (
        f"rota(s) de MUTAÇÃO sobre a entidade de auditoria: {achadas}\n"
        "audit_logs é WORM (Issue #699, migration "
        "131_audit_logs_worm) — o banco vai rejeitar em runtime (trigger "
        "trg_audit_logs_bloqueia_mutacao), mas a rota não deve nem existir. "
        "Se isto é a implementação da via de expurgo da #582, ela precisa de "
        "decisão explícita do controlador/encarregado — não adicione aqui."
    )


def test_router_de_audit_so_declara_metodos_get():
    """Varredura por REGEX no código-fonte de `app/routers/audit.py` — trava
    dupla independente da introspecção de `app.routes` acima: mesmo que o
    router deixe de ser montado em `app.main`, este teste ainda reprova um
    `@router.post/put/patch/delete` escrito no arquivo.
    """
    from app.routers import audit as audit_router

    fonte = inspect.getsource(audit_router)
    decoradores = re.findall(r'@router\.(get|post|put|patch|delete)\(', fonte)

    assert decoradores, "nenhum @router.<metodo> encontrado — varredura furou"
    mutantes = [m for m in decoradores if m != "get"]
    assert not mutantes, (
        f"app/routers/audit.py declara método(s) de mutação: {mutantes} — "
        "audit_logs é somente-leitura por rota (Issue #699)."
    )


@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_nenhum_router_do_app_expoe_mutacao_no_prefixo_audit(metodo):
    """Varredura mais ampla: nenhum arquivo de `app/routers/` pode registrar
    `@<qualquer_router>.<metodo>("/audit...")` — cobre um router NOVO que
    decida se automontar sob o mesmo prefixo em vez de estender audit.py.
    """
    import pathlib

    # Mesma restrição de segmento da varredura em app.routes: exige que
    # "audit"/"audit_logs" seja o segmento INTEIRO logo após a barra, não
    # uma substring (evita falso positivo em /auditar-peca, /auditoria-x).
    padrao = re.compile(
        r'@\w+\.' + metodo
        + r'\(\s*["\'](/audit([_-]logs?)?(?:/[^"\']*)?)["\']',
        re.IGNORECASE,
    )
    routers_dir = pathlib.Path(__file__).parents[1] / "app" / "routers"
    achadas = []
    for arquivo in routers_dir.glob("*.py"):
        fonte = arquivo.read_text(encoding="utf-8")
        for m in padrao.finditer(fonte):
            achadas.append(f"{arquivo.name}:{m.group(1)}")
    assert not achadas, (
        f"rota .{metodo}(\"/audit...\") encontrada fora do esperado: {achadas}"
    )
