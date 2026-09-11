"""Isolamento do RAG por cliente — Fase 3B.

Garante que o filtro fail-closed está presente e é aplicado nas consultas
(protege contra regressão do vazamento cruzado entre clientes).
"""
import inspect

import pytest

from app.services.ai_service import (
    _RESTRICTED_CATS,
    _FILTRO_ESCOPO_RAG,
    _FILTRO_ELIGIBILIDADE_RAG,
    _params_escopo_rag,
    buscar_contexto_rag,
)


@pytest.fixture(autouse=True)
def _busca_textual_sem_download(monkeypatch):
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)


def test_categorias_restritas():
    for c in ("peca_interna", "peca_escritorio", "precedente_interno"):
        assert c in _RESTRICTED_CATS


def test_fragmento_de_filtro():
    assert "base_rag::text" in _FILTRO_ESCOPO_RAG
    assert "kd.client_id IS NULL" in _FILTRO_ESCOPO_RAG
    assert "kd.case_id IS NULL" in _FILTRO_ESCOPO_RAG
    assert "kd.categoria <> ALL(:restr_cats)" in _FILTRO_ESCOPO_RAG
    assert "kd.client_id = NULLIF(:scope_cli, '')" in _FILTRO_ESCOPO_RAG
    assert "kd.case_id = NULLIF(:scope_case, '')" in _FILTRO_ESCOPO_RAG


def test_binds_de_escopo_sao_fail_closed():
    assert _params_escopo_rag(None, None) == {
        "restr_cats": _RESTRICTED_CATS,
        "scope_cli": "",
        "scope_case": "",
    }
    params = _params_escopo_rag("cliente-A", "caso-X")
    assert params["scope_cli"] == "cliente-A"
    assert params["scope_case"] == "caso-X"


def test_assinatura_tem_escopo():
    assert "scope_client_id" in inspect.signature(buscar_contexto_rag).parameters


def test_limiar_de_similaridade_rag04():
    # RAG-04: a busca semântica tem um teto de distância (= 1 - similaridade mínima).
    # A-2 (2026-07-17): o limiar virou CONFIGURÁVEL (RAG_MIN_SIM) via _rag_max_dist().
    from app.services.ai_service import _rag_max_dist, _RAG_MIN_SIM_DEFAULT
    from app.core.config import get_settings
    d = _rag_max_dist()
    assert 0.0 < d < 1.0
    sim = float(get_settings().RAG_MIN_SIM)
    assert d == pytest.approx(1.0 - sim, abs=1e-9)
    assert _RAG_MIN_SIM_DEFAULT == pytest.approx(0.55, abs=1e-9)  # default de fábrica


class _CaptureDB:
    """Captura o SQL/params da última consulta; retorna zero linhas."""
    def __init__(self):
        self.sql = ""
        self.params = {}

    async def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params or {}
        return []


async def test_consulta_aplica_escopo():
    db = _CaptureDB()
    # Sem embeddings (default) cai na busca textual — que deve conter o filtro.
    await buscar_contexto_rag(db, "consulta de teste sobre tese qualquer", limite=3)
    assert "kd.client_id = NULLIF(:scope_cli, '')" in db.sql
    assert "scope_cli" in db.params
    assert "scope_case" in db.params
    assert "restr_cats" in db.params
    # Fail-closed: sem escopo, ambos os binds são vazios e NULLIF vira NULL.
    assert db.params["scope_cli"] == ""
    assert db.params["scope_case"] == ""


# ── Bloco 5 — isolamento por cliente aplicado nas chamadas ────────────────────

class _ResultCaso:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _DBCaso:
    """Fake DB que devolve o client_id de um caso (ou None se inexistente)."""
    def __init__(self, client_id):
        self._cid = client_id

    async def execute(self, sql, params=None):
        return _ResultCaso((self._cid,) if self._cid is not None else None)


async def test_escopo_sem_caso_e_fail_closed():
    """Sem case_id, o escopo é None → RAG mantém fail-closed (nada restrito)."""
    from app.services.ai_service import _escopo_cliente_do_caso
    assert await _escopo_cliente_do_caso(_DBCaso("qualquer"), None) is None


async def test_escopo_deriva_client_id_do_caso():
    """Com case_id, o escopo é EXATAMENTE o client_id daquele caso."""
    from app.services.ai_service import _escopo_cliente_do_caso
    assert await _escopo_cliente_do_caso(_DBCaso("cliente-A"), "caso-1") == "cliente-A"


async def test_escopo_caso_inexistente_e_fail_closed():
    """Caso inexistente/deletado → None (não vaza para escopo vazio de outro)."""
    from app.services.ai_service import _escopo_cliente_do_caso
    assert await _escopo_cliente_do_caso(_DBCaso(None), "caso-fantasma") is None


async def test_escopo_nao_vazio_propaga_ao_param_sql():
    """Prova a ponta final do elo: um escopo de cliente chega ao scope_cli do SQL
    (com o filtro já validado, isolamento = filtro correto + client_id correto)."""
    db = _CaptureDB()
    await buscar_contexto_rag(db, "consulta", limite=3, scope_client_id="cliente-A")
    assert db.params["scope_cli"] == "cliente-A"


# ── Isolamento por CASO via ownership persistido ─────────────────────────────

async def test_consulta_com_caso_usa_mesmo_contrato_de_ownership():
    db = _CaptureDB()
    await buscar_contexto_rag(
        db, "consulta de teste sobre tese qualquer", limite=3,
        scope_client_id="cli-1", scope_case_id="caso-1",
    )
    assert "kd.client_id = NULLIF(:scope_cli, '')" in db.sql
    assert "kd.case_id = NULLIF(:scope_case, '')" in db.sql
    assert db.params["scope_cli"] == "cli-1"
    assert db.params["scope_case"] == "caso-1"


async def test_consulta_sem_caso_mantem_bind_fail_closed_para_case_id():
    db = _CaptureDB()
    await buscar_contexto_rag(
        db, "consulta de teste sobre tese qualquer", limite=3,
        scope_client_id="cli-1",
    )
    assert "kd.case_id = NULLIF(:scope_case, '')" in db.sql
    assert db.params["scope_case"] == ""


def test_todas_as_pernas_usam_o_mesmo_contrato_de_escopo():
    from app.services import ai_service

    fonte = inspect.getsource(ai_service)
    # vetor, trigram, FTS e fallback textual compartilham o mesmo fragmento.
    assert fonte.count("{_FILTRO_ESCOPO_RAG}") == 4
    assert fonte.count("_params_escopo_rag(scope_client_id, scope_case_id)") >= 4
    assert "_FILTRO_CASO_RAG" not in fonte
    assert "_CASE_SCOPED_CATS" not in fonte


def test_call_sites_com_caso_repassam_o_escopo_de_caso():
    """Quem sabe em que caso está precisa dizer — senão o filtro nunca atua."""
    import inspect as _inspect

    from app.services import analise_estrategica, anexos_service, checklist_ia, peca_service
    from app.services.ai.core import context_builder

    for modulo in (context_builder, analise_estrategica, peca_service,
                   anexos_service, checklist_ia):
        assert "scope_case_id=" in _inspect.getsource(modulo), modulo.__name__



def test_base_caso_exige_case_id_no_contrato_elegivel():
    assert "base_rag::text" in _FILTRO_ELIGIBILIDADE_RAG
    assert "kd.client_id IS NOT NULL" in _FILTRO_ELIGIBILIDADE_RAG
    assert "<> 'caso' OR kd.case_id IS NOT NULL" in _FILTRO_ESCOPO_RAG
    assert "<> 'caso' OR kd.case_id IS NOT NULL" in _FILTRO_ELIGIBILIDADE_RAG


def test_callers_case_bound_propagam_case_id_explicitamente():
    """Regressão do P1 #1579: caso conhecido não pode ser descartado no RAG."""
    from app.core import veredito_ia
    from app.routers import ai, ai_skills, ai_tools, intake
    from app.services import ai_service, matriz_teses_service, validador_juridico_service

    checks = {
        "veredito": (inspect.getsource(veredito_ia), "scope_case_id=case_id"),
        "router_ai": (inspect.getsource(ai), "scope_case_id=case_id"),
        "ai_tools": (inspect.getsource(ai_tools), "scope_case_id=req.case_id"),
        "ai_skills": (inspect.getsource(ai_skills), "scope_case_id=escopo_caso"),
        "intake": (inspect.getsource(intake), "scope_case_id=case.id"),
        "matriz": (inspect.getsource(matriz_teses_service), "scope_case_id=case_id"),
        "validador": (
            inspect.getsource(validador_juridico_service),
            "scope_case_id=payload.case_id",
        ),
        "contrato": (inspect.getsource(ai_service.analisar_contrato), "scope_case_id=case_id"),
    }
    for nome, (fonte, marcador) in checks.items():
        assert marcador in fonte, f"{nome} perdeu propagação de case_id"


def test_ai_skills_helper_exige_escopo_de_caso():
    from app.routers.ai_skills import _buscar_contexto
    sig = inspect.signature(_buscar_contexto)
    assert "escopo_caso" in sig.parameters
