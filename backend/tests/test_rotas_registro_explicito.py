"""Paridade explícita da superfície FastAPI do EJC.

Mantém o snapshot histórico como baseline e exige declaração nominal de toda
adição/remoção ou mudança de autenticação deliberada.
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
    ("/api/architecture/semantic-audit", "GET"),
    ("/api/diario-oficial/status", "GET"),
    ("/api/sala-juridica/{session_id}/conversao/preview", "GET"),
    ("/api/diagnostico/integridade", "GET"),
    ("/api/data-rooms/{room_id}/arquivos/{arquivo_id}/publicacao", "PATCH"),
    ("/api/documents/{doc_id}/publicacao-portal", "PATCH"),
    ("/api/legal-docs/{doc_id}/conferir-e-assinar", "POST"),
    ("/api/legal-docs/{doc_id}/pdf-minuta", "GET"),
    ("/api/entrada/analisar", "POST"),
    ("/api/entrada/{rascunho_id}/criar-caso", "POST"),
    ("/api/processo-eletronico/sincronizar", "POST"),
    ("/api/processo-eletronico/status/{case_id}", "GET"),
    ("/api/processo-eletronico/credenciais", "GET"),
    ("/api/processo-eletronico/credenciais", "POST"),
    ("/api/processo-eletronico/credenciais/{credencial_id}/testar", "POST"),
    ("/api/integracoes/cnj/tpu/versao", "GET"),
    ("/api/integracoes/cnj/tpu/pesquisar", "GET"),
    ("/api/integracoes/tcu/acordaos", "GET"),
    ("/api/integracoes/ibge/municipios/{uf}", "GET"),
    ("/api/integracoes/ibge/canonicalizar", "GET"),
    ("/api/integracoes/dados-publicos/{fonte}/recursos", "GET"),
    ("/api/integracoes/pgfn/divida-ativa/recursos", "GET"),
    ("/api/integracoes/querido-diario/{codigo_ibge}", "GET"),
    ("/api/integracoes/ide-sisema/camadas", "GET"),
    ("/api/integracoes/ide-sisema/feicoes", "GET"),
    ("/api/jurimetria/interno/stats", "GET"),
    ("/api/jurimetria/interno/benchmarks", "GET"),
    ("/api/jurimetria/interno/analise-prospectiva", "GET"),
    ("/api/jurimetria/analise-prospectiva", "POST"),
    ("/api/jurimetria/cobertura-rag", "GET"),
    ("/api/jurimetria/cobertura-mg-jec", "GET"),
    ("/api/cases/{case_id}/documentos/candidatos", "GET"),
    ("/api/cases/{case_id}/documentos/{document_id}/vincular", "POST"),
    ("/api/dpt360/dashboard", "GET"),
    ("/api/dpt360/companies/{client_id}", "GET"),
    ("/api/dpt360/diagnostics/readiness/{client_id}", "GET"),
    ("/api/dpt360/radar/today", "GET"),
    ("/api/dpt360/reports/executive/{client_id}", "GET"),
    ("/api/dpt360/intake/opportunities", "GET"),
    ("/api/dpt360/intake/opportunities", "POST"),
    ("/api/dpt360/actions", "POST"),
    ("/api/analytics/produtividade/export-event", "POST"),
    ("/api/dpt360/oportunidades/{batch_id}/ciclo-vida", "POST"),
    ("/api/signatures/{sig_id}/documento", "GET"),
    # #1199/#1220: peças avulsas de admissão vinculadas por client_id.
    ("/api/clients/{client_id}/pecas-geradas", "GET"),
    ("/api/clients/{client_id}/gerar-documentos", "POST"),
    ("/api/intelligence/radar/legislativo", "GET"),
    ("/api/intelligence/analise-impacto", "POST"),
    ("/api/teses/motor/async", "POST"),
    ("/api/teses/motor/async/{task_id}", "GET"),
    ("/api/cases/{case_id}/partes/{parte_id}", "PATCH"),
    ("/api/cases/{case_id}/movimentos/{movimento_id}", "PATCH"),
    ("/api/cases/{case_id}/movimentos/{movimento_id}", "DELETE"),
    ("/api/ia-governanca/prompts-sistema", "GET"),
    # #1215: consolidação canônica de honorários.
    ("/api/honorarios-oab/cases/{case_id}/provisionamento", "GET"),
    ("/api/honorarios-oab/cases/{case_id}/teto-etico", "GET"),
    ("/api/honorarios-oab/{fee_id}/rateio", "GET"),
    ("/api/honorarios-oab/{fee_id}/rateio", "POST"),
}

REMOCOES_INTENCIONAIS = {
    ("/api/diplomacia-v3/dossie-pressao", "POST"),
    ("/api/diplomacia-v3/analisar-magistrado", "POST"),
    ("/api/cases/{case_id}/resumo", "GET"),
    ("/api/cases/{case_id}/linha-do-tempo", "GET"),
    ("/api/cases/{case_id}/assistente-estrategico", "POST"),
    ("/api/cases/{case_id}/movimentos/{mov_id}/traduzir", "POST"),
    ("/api/casos/{case_id}/jornada", "GET"),
    ("/api/teses-v4/", "GET"),
    ("/api/teses-v4/", "POST"),
    ("/api/teses-v4/sugestao-ia", "GET"),
    ("/api/data-room-v4/", "GET"),
    ("/api/data-room-v4/", "POST"),
    ("/api/diplomacia-v3/calcular-acordo", "POST"),
    ("/api/document-templates/", "GET"),
    ("/api/document-templates/generate", "POST"),
    ("/api/veredito_ia/analisar", "POST"),
    ("/api/victory_vault/modelos", "GET"),
    ("/api/victory_vault/modelos", "POST"),
    ("/api/victory_vault/teses", "GET"),
    ("/api/victory_vault/teses", "POST"),
    ("/api/intelligence-v3/radar/legislativo", "GET"),
    ("/api/intelligence-v3/analise-impacto", "POST"),
    ("/api/search/", "GET"),
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

    AUTH_ALTERACOES_INTENCIONAIS = (
        (("/api/rag/docs", "GET"), ["HTTPBearer", "get_current_user", "get_db"]),
        (("/api/ai/analisar-caso", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/resumir-documento", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/teses-ocultas", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/auditar-peca", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/preparar-audiencia", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/casos/{case_id}/assistente", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/casos/{case_id}/dual", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/caso/{case_id}/visual-law", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/caso/{case_id}/estrategia", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/analisar-contrato", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/detectar-prazos", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ia-defensiva/analisar", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        # #1215 shims 308 deliberados; destino canônico reautentica.
        (("/api/prompts-biblioteca/", "GET"), []),
        (("/api/prompts-biblioteca/", "POST"), []),
        (("/api/prompts-biblioteca/{prompt_id}/executar", "POST"), []),
        (("/api/honorarios-calc/cases/{case_id}/provisionamento", "GET"), []),
        (("/api/honorarios-calc/cases/{case_id}/teto-etico", "GET"), []),
        (("/api/honorarios-exito/{fee_id}/rateio", "GET"), []),
        (("/api/honorarios-exito/{fee_id}/rateio", "POST"), []),
    )

    divergentes = [
        (k, chaves_base[k]["auth_deps"], chaves_atual[k]["auth_deps"])
        for k in sorted(set(chaves_base) & set(chaves_atual))
        if chaves_base[k]["auth_deps"] != chaves_atual[k]["auth_deps"]
        and not any(
            k == chave and deps == chaves_atual[k]["auth_deps"]
            for chave, deps in AUTH_ALTERACOES_INTENCIONAIS
        )
    ]
    assert not divergentes, f"dependências de auth alteradas: {divergentes[:5]}"
    assert len(base) == 826
    assert len(atual) == (
        len(base) + len(ADICOES_INTENCIONAIS) - len(REMOCOES_INTENCIONAIS)
    )


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
        ("/api/dpt360/intake/opportunities", "GET"),
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
            f"{modulo.__name__} voltou a montar rota por side effect"
        )
        assert ".router.routes.append(" not in fonte


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
    assert (
        "_install_document_analysis_hook()" in fonte_ev
        or "_patch_documents_background_analysis()" in fonte_ev
    )
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
        novo = "/api" + antigo[len("/api/v1") :]
        destino = atual.get((novo, r["method"]))
        assert destino is not None, f"{antigo} {r['method']} não reapareceu em {novo}"
        if destino["auth_deps"] != r["auth_deps"]:
            divergentes.append((antigo, novo, r["auth_deps"], destino["auth_deps"]))
    assert not divergentes, (
        "a mudança de prefixo alterou o gate de auth de "
        f"{len(divergentes)} rota(s): {divergentes[:3]}"
    )
