"""Registro explícito e paridade da superfície OpenAPI do EJC.

O snapshot permanece a referência anterior às mudanças intencionais. Toda rota
nova/removida precisa aparecer nominalmente abaixo; não há wildcard por prefixo.
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
                "path": path,
                "method": metodo,
                "auth_deps": sorted(nomes),
                "endpoint": getattr(getattr(r, "endpoint", None), "__name__", None),
            })
    rotas.sort(key=lambda x: (x["path"], x["method"]))
    return rotas


ADICOES_INTENCIONAIS = {
    ("/api/architecture/uso-rotas", "GET"),
    ("/api/sala-juridica/{session_id}/conversao/preview", "GET"),
    ("/api/diagnostico/integridade", "GET"),
    ("/api/data-rooms/{room_id}/arquivos/{arquivo_id}/publicacao", "PATCH"),
    ("/api/legal-docs/{doc_id}/conferir-e-assinar", "POST"),
    ("/api/legal-docs/{doc_id}/pdf-minuta", "GET"),
    ("/api/entrada/analisar", "POST"),
    ("/api/entrada/{rascunho_id}/criar-caso", "POST"),
    ("/api/processo-eletronico/sincronizar", "POST"),
    ("/api/processo-eletronico/status/{case_id}", "GET"),
    ("/api/processo-eletronico/credenciais", "GET"),
    ("/api/processo-eletronico/credenciais", "POST"),
    ("/api/processo-eletronico/credenciais/{credencial_id}/testar", "POST"),
    # DPT Empresarial 360 — toda rota é declarada nominalmente.
    ("/api/dpt360/dashboard", "GET"),
    ("/api/dpt360/companies/{client_id}", "GET"),
    ("/api/dpt360/diagnostics/readiness/{client_id}", "GET"),
    ("/api/dpt360/radar/today", "GET"),
    ("/api/dpt360/reports/executive/{client_id}", "GET"),
    ("/api/dpt360/intake/opportunities", "POST"),
    ("/api/dpt360/actions", "POST"),
}

REMOCOES_INTENCIONAIS = {
    ("/api/diplomacia-v3/dossie-pressao", "POST"),
    ("/api/diplomacia-v3/analisar-magistrado", "POST"),
    ("/api/cases/{case_id}/resumo", "GET"),
    ("/api/cases/{case_id}/linha-do-tempo", "GET"),
    ("/api/cases/{case_id}/assistente-estrategico", "POST"),
    ("/api/cases/{case_id}/movimentos/{mov_id}/traduzir", "POST"),
    ("/api/casos/{case_id}/jornada", "GET"),
}


def _baseline() -> list[dict]:
    caminho = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "snapshots",
        "openapi_rotas_baseline.json",
    )
    with open(caminho, encoding="utf-8") as fh:
        return json.load(fh)


_MOVIDAS_ONDA2 = tuple(
    (r["path"], r["method"])
    for r in _baseline()
    if r["path"].startswith("/api/v1/")
)
REMOCOES_INTENCIONAIS |= set(_MOVIDAS_ONDA2)
ADICOES_INTENCIONAIS |= {
    ("/api" + path[len("/api/v1"):], metodo) for path, metodo in _MOVIDAS_ONDA2
}


def test_paridade_openapi_com_snapshot_anterior():
    from app.main import app

    atual = _extrair_rotas(app)
    base = _baseline()
    chaves_base = {(r["path"], r["method"]): r for r in base}
    chaves_atual = {(r["path"], r["method"]): r for r in atual}

    sumiram = sorted(set(chaves_base) - set(chaves_atual) - REMOCOES_INTENCIONAIS)
    surgiram = sorted(set(chaves_atual) - set(chaves_base) - ADICOES_INTENCIONAIS)
    assert not sumiram, f"{len(sumiram)} rota(s) DESAPARECERAM: {sumiram[:10]}"
    assert not surgiram, f"{len(surgiram)} rota(s) NOVAS não previstas: {surgiram[:10]}"

    ressuscitadas = sorted(REMOCOES_INTENCIONAIS & set(chaves_atual))
    assert not ressuscitadas, (
        f"rota(s) removida(s) por decisão do escritório voltaram: {ressuscitadas}"
    )

    divergentes = [
        (k, chaves_base[k]["auth_deps"], chaves_atual[k]["auth_deps"])
        for k in sorted(set(chaves_base) & set(chaves_atual))
        if chaves_base[k]["auth_deps"] != chaves_atual[k]["auth_deps"]
    ]
    assert not divergentes, f"dependências de auth alteradas: {divergentes[:5]}"
    assert len(base) == 826
    assert len(atual) == len(base) + len(ADICOES_INTENCIONAIS) - len(REMOCOES_INTENCIONAIS)


@pytest.mark.parametrize(
    "caminho,metodo",
    [
        ("/api/jurisprudencia-externa/precedentes/buscar", "POST"),
        ("/api/pecas/advogado-estilo/me", "GET"),
        ("/api/rag/governanca/saude", "GET"),
        ("/api/casos/{case_id}/andamentos/inteligencia", "GET"),
        ("/api/ia-governanca/provedores", "GET"),
    ],
)
def test_rotas_antes_dinamicas_seguem_montadas(caminho, metodo):
    from app.main import app

    montadas = {
        (getattr(r, "path", ""), m)
        for r in app.routes
        for m in (getattr(r, "methods", None) or [])
    }
    assert (caminho, metodo) in montadas


@pytest.mark.parametrize(
    "caminho,metodo",
    [
        ("/api/dpt360/dashboard", "GET"),
        ("/api/dpt360/companies/{client_id}", "GET"),
        ("/api/dpt360/diagnostics/readiness/{client_id}", "GET"),
        ("/api/dpt360/radar/today", "GET"),
        ("/api/dpt360/reports/executive/{client_id}", "GET"),
        ("/api/dpt360/intake/opportunities", "POST"),
        ("/api/dpt360/actions", "POST"),
    ],
)
def test_rotas_dpt360_sao_explicitas(caminho, metodo):
    from app.main import app

    montadas = {
        (getattr(r, "path", ""), m)
        for r in app.routes
        for m in (getattr(r, "methods", None) or [])
    }
    assert (caminho, metodo) in montadas


def test_modulos_de_servico_nao_montam_mais_rotas():
    import inspect

    from app.services import event_subscribers
    from app.services import datajud_cognitive_patch
    from app.services.ai import provider_metrics_runtime

    for modulo in (
        event_subscribers,
        datajud_cognitive_patch,
        provider_metrics_runtime,
    ):
        fonte = inspect.getsource(modulo)
        assert "include_router" not in fonte, (
            f"{modulo.__name__} voltou a montar rota por side effect — "
            "registre o router explicitamente em app/main.py"
        )
        assert ".router.routes.append(" not in fonte, (
            f"{modulo.__name__} voltou a anexar rotas diretamente em outro router"
        )


def test_registro_independe_da_ordem_de_import():
    from app.services import event_subscribers  # noqa: F401
    from app.services.ai import provider_metrics_runtime  # noqa: F401
    from app.main import app

    assert len(_extrair_rotas(app)) == (
        826 + len(ADICOES_INTENCIONAIS) - len(REMOCOES_INTENCIONAIS)
    )


def test_efeitos_colaterais_nao_de_rota_preservados():
    import inspect

    from app.services import datajud_cognitive_patch, event_subscribers
    from app.services.ai import provider_metrics_runtime

    fonte_ev = inspect.getsource(event_subscribers)
    assert "_patch_documents_background_analysis()" in fonte_ev
    assert "_install_ai_core_hardening()" in fonte_ev
    assert "_install_datajud_cognitive_feed()" in fonte_ev
    assert "@on(" in fonte_ev

    fonte_dj = inspect.getsource(datajud_cognitive_patch)
    assert "_instalar_wrappers()" in fonte_dj
    assert "_registrar_job()" in fonte_dj
    assert "_registrar_categoria_restrita()" in fonte_dj

    fonte_pm = inspect.getsource(provider_metrics_runtime)
    assert "_instalar_instrumentacao(gateway)" in fonte_pm


def test_movimentacao_onda2_preservou_as_dependencias_de_auth():
    from app.main import app

    atual = {(r["path"], r["method"]): r for r in _extrair_rotas(app)}
    divergentes = []
    for r in _baseline():
        antigo = r["path"]
        if not antigo.startswith("/api/v1/"):
            continue
        novo = "/api" + antigo[len("/api/v1"):]
        destino = atual.get((novo, r["method"]))
        assert destino is not None, f"{antigo} {r['method']} não reapareceu em {novo}"
        if destino["auth_deps"] != r["auth_deps"]:
            divergentes.append((antigo, novo, r["auth_deps"], destino["auth_deps"]))
    assert not divergentes, (
        "a mudança de prefixo alterou o gate de auth de "
        f"{len(divergentes)} rota(s): {divergentes[:3]}"
    )
