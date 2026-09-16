"""Gates estruturais + rate limit de /api/ia-governanca (Fase 8, onda 1-B).

Antes da onda 1, os 13 endpoints de governança da IA faziam a checagem
admin/sócio no CORPO do handler (`_require_admin_socio(cu)`): funcional, mas
invisível para o inventário RBAC (que lê a assinatura — reportava ONLY_AUTH) e
fácil de esquecer num handler novo. A onda 1 promove a checagem para a
dependency `_req_admin_socio` e adiciona rate limit aos 4 mutantes da
prioridade 1.

Este teste trava, lendo o app montado:
1. toda rota de /api/ia-governanca resolve `cu` via `_req_admin_socio`
   (nenhuma dependência de `get_current_user` puro);
2. os 4 mutantes carregam as closures de rate_limit com nome/limite
   esperados (mesma técnica de test_ai_rate_limit_cobertura.py);
3. `_require_gestao` e `_require_admin_socio` continuam semanticamente
   idênticos (regressão do superadmin barrado em 29/08/2026).
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from fastapi.params import Depends

import app.routers.ia_governanca as gov
from app.core.rate_limit import rate_limit as _rate_limit_factory

_PREFIXO = "/api/ia-governanca"

# (path, method) -> (nome esperado, limite máximo/minuto)
_ALVOS_RATE_LIMIT = {
    ("/api/ia-governanca/rag-curadoria/{doc_id}", "PATCH"): ("ia-gov-curadoria", 30),
    ("/api/ia-governanca/fontes/tjmg/coletar", "POST"): ("ia-gov-coleta-tjmg", 5),
    ("/api/ia-governanca/jurisprudencia-mg", "POST"): ("ia-gov-import-juris-mg", 10),
    ("/api/ia-governanca/jurisprudencia-mg/extrair-url", "POST"): ("ia-gov-extrai-juris-mg", 5),
}


def _rotas_do_app() -> dict[tuple[str, str], object]:
    from app.main import app

    saida = {}
    for r in app.routes:
        path = getattr(r, "path", None)
        metodos = getattr(r, "methods", None) or set()
        if path is None or not path.startswith(_PREFIXO):
            continue
        for m in metodos:
            saida[(path, m)] = r
    return saida


def test_todas_as_rotas_usam_o_gate_estrutural():
    """Nenhuma rota de /api/ia-governanca pode voltar a depender só de
    get_current_user — o gate admin/sócio é dependency, não corpo."""
    rotas = _rotas_do_app()
    assert len(rotas) >= 13, f"rotas de ia-governanca mudaram: {sorted(rotas)}"
    for chave, rota in sorted(rotas.items()):
        endpoint = getattr(rota, "endpoint", None)
        assert endpoint is not None, f"rota sem handler: {chave}"
        params = inspect.signature(endpoint).parameters
        cu = params.get("cu")
        assert cu is not None, f"{chave}: handler sem parâmetro cu"
        dep = cu.default
        assert isinstance(dep, Depends), f"{chave}: cu não é Depends"
        assert dep.dependency is gov._req_admin_socio, (
            f"{chave}: gate estrutural removido — cu resolve via "
            f"{getattr(dep.dependency, '__name__', dep.dependency)}"
        )


def _fechamento_do_rate_limit(rota):
    referencia = _rate_limit_factory("sonda", 1)  # mesmo formato de closure
    for dep in getattr(rota, "dependencies", []) or []:
        fn = getattr(dep, "dependency", None)
        if fn is None or fn.__code__ is not referencia.__code__:
            continue
        limite, nome = (c.cell_contents for c in fn.__closure__)
        return nome, limite
    return None


@pytest.mark.parametrize(
    "chave,esperado", sorted(_ALVOS_RATE_LIMIT.items()), ids=[f"{k[1]} {k[0]}" for k, _ in sorted(_ALVOS_RATE_LIMIT.items())]
)
def test_mutantes_p1_tem_rate_limit(chave, esperado):
    rota = _rotas_do_app().get(chave)
    assert rota is not None, f"rota sumiu do app: {chave}"
    achado = _fechamento_do_rate_limit(rota)
    assert achado == esperado, f"rate_limit divergente em {chave}: {achado}"


def test_nomes_de_rate_limit_sao_unicos():
    nomes = [nome for nome, _ in _ALVOS_RATE_LIMIT.values()]
    assert len(nomes) == len(set(nomes)), nomes


def test_require_gestao_e_admin_socio_sao_o_mesmo_conjunto():
    """`_require_gestao` delega ao gate canônico — os dois nomes não podem
    voltar a divergir (superadmin barrado no pente fino de 29/08/2026)."""
    from types import SimpleNamespace

    user = SimpleNamespace(role=SimpleNamespace(value="advogado"))
    with pytest.raises(HTTPException) as e1:
        gov._require_admin_socio(user)
    with pytest.raises(HTTPException) as e2:
        gov._require_gestao(user)
    assert e1.value.status_code == e2.value.status_code == 403
