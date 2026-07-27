"""Onda 3 §4.1 — registro EXPLÍCITO dos routers antes montados por side effect.

Cinco grupos de rotas (precedentes, advogado_estilo, rag_governance,
datajud_intelligence, ia_provider_metrics) eram anexados aos routers-pais dentro
de app/services/event_subscribers.py, datajud_cognitive_patch.py e
ai/provider_metrics_runtime.py — o que tornava a superfície da API dependente da
ORDEM de import. Agora são registrados em app/main.py como os demais.

Este arquivo trava a PARIDADE: o snapshot em tests/snapshots/ foi capturado com
o código ANTERIOR à mudança; qualquer divergência de path, método ou dependência
de auth falha aqui.
"""
from __future__ import annotations

import json
import os

import pytest


def _extrair_rotas(app) -> list[dict]:
    def deps_flat(dep, out, depth=0):
        if dep is None or depth > 6:
            return
        for d in getattr(dep, "dependencies", []) or []:
            c = getattr(d, "call", None)
            if c is not None:
                out.add(getattr(c, "__name__", type(c).__name__))
            deps_flat(d, out, depth + 1)

    rotas = []
    for r in app.routes:
        path = getattr(r, "path", None)
        if not path:
            continue
        nomes: set[str] = set()
        deps_flat(getattr(r, "dependant", None), nomes)
        for metodo in sorted(getattr(r, "methods", None) or []):
            if metodo in ("HEAD", "OPTIONS"):
                continue
            rotas.append({
                "path": path, "method": metodo, "auth_deps": sorted(nomes),
                "endpoint": getattr(getattr(r, "endpoint", None), "__name__", None),
            })
    rotas.sort(key=lambda x: (x["path"], x["method"]))
    return rotas


# Adições INTENCIONAIS posteriores ao snapshot. O registro explícito (§4.1) não
# pode criar nem remover rota; qualquer outra novidade falha o teste.
ADICOES_INTENCIONAIS = {
    ("/api/architecture/uso-rotas", "GET"),   # telemetria de uso (Onda 3 §4.5)
}


def _baseline() -> list[dict]:
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "snapshots", "openapi_rotas_baseline.json")
    with open(caminho, encoding="utf-8") as fh:
        return json.load(fh)


def test_paridade_openapi_com_snapshot_anterior():
    """Path + método + dependências de auth idênticos ao estado pré-mudança."""
    from app.main import app

    atual = _extrair_rotas(app)
    base = _baseline()
    chaves_base = {(r["path"], r["method"]): r for r in base}
    chaves_atual = {(r["path"], r["method"]): r for r in atual}

    sumiram = sorted(set(chaves_base) - set(chaves_atual))
    surgiram = sorted(set(chaves_atual) - set(chaves_base) - ADICOES_INTENCIONAIS)
    assert not sumiram, f"{len(sumiram)} rota(s) DESAPARECERAM: {sumiram[:10]}"
    assert not surgiram, f"{len(surgiram)} rota(s) NOVAS não previstas: {surgiram[:10]}"

    divergentes = [
        (k, chaves_base[k]["auth_deps"], chaves_atual[k]["auth_deps"])
        for k in sorted(set(chaves_base) & set(chaves_atual))
        if chaves_base[k]["auth_deps"] != chaves_atual[k]["auth_deps"]
    ]
    assert not divergentes, f"dependências de auth alteradas: {divergentes[:5]}"
    assert len(base) == 826
    assert len(atual) == len(base) + len(ADICOES_INTENCIONAIS)


@pytest.mark.parametrize("caminho,metodo", [
    ("/api/jurisprudencia-externa/precedentes/buscar", "POST"),
    ("/api/pecas/advogado-estilo/me", "GET"),
    ("/api/rag/governanca/saude", "GET"),
    ("/api/casos/{case_id}/andamentos/inteligencia", "GET"),
    ("/api/ia-governanca/provedores", "GET"),
])
def test_rotas_antes_dinamicas_seguem_montadas(caminho, metodo):
    """Uma rota-testemunha de cada um dos cinco grupos."""
    from app.main import app

    montadas = {(getattr(r, "path", ""), m)
                for r in app.routes
                for m in (getattr(r, "methods", None) or [])}
    assert (caminho, metodo) in montadas


def test_modulos_de_servico_nao_montam_mais_rotas():
    """Regressão: nenhum dos três módulos volta a anexar router por side effect."""
    import inspect

    from app.services import event_subscribers
    from app.services import datajud_cognitive_patch
    from app.services.ai import provider_metrics_runtime

    for modulo in (event_subscribers, datajud_cognitive_patch, provider_metrics_runtime):
        fonte = inspect.getsource(modulo)
        assert "include_router" not in fonte, (
            f"{modulo.__name__} voltou a montar rota por side effect — "
            "registre o router explicitamente em app/main.py")
        assert ".router.routes.append(" not in fonte, (
            f"{modulo.__name__} voltou a anexar rotas diretamente em outro router")


def test_registro_independe_da_ordem_de_import():
    """Importar os módulos de serviço ANTES do app não altera a superfície."""
    from app.services import event_subscribers  # noqa: F401
    from app.services.ai import provider_metrics_runtime  # noqa: F401
    from app.main import app

    assert len(_extrair_rotas(app)) == 826 + len(ADICOES_INTENCIONAIS)


def test_efeitos_colaterais_nao_de_rota_preservados():
    """A remoção tocou APENAS a montagem de rota: subscribers de evento e
    patches de comportamento seguem no lugar."""
    import inspect

    from app.services import event_subscribers, datajud_cognitive_patch
    from app.services.ai import provider_metrics_runtime

    fonte_ev = inspect.getsource(event_subscribers)
    assert "_patch_documents_background_analysis()" in fonte_ev   # patch de comportamento
    assert "_install_ai_core_hardening()" in fonte_ev             # gate crítico de IA
    assert "_install_datajud_cognitive_feed()" in fonte_ev
    assert "@on(" in fonte_ev                                     # subscribers de evento

    fonte_dj = inspect.getsource(datajud_cognitive_patch)
    assert "_instalar_wrappers()" in fonte_dj                     # wrappers do datajud_service
    assert "_registrar_job()" in fonte_dj                         # job do scheduler
    assert "_registrar_categoria_restrita()" in fonte_dj

    fonte_pm = inspect.getsource(provider_metrics_runtime)
    assert "_instalar_instrumentacao(gateway)" in fonte_pm        # instrumentação do gateway
