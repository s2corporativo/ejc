from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.modules.dpt360 import report_service
from app.modules.dpt360.schemas import (
    DptCompanyProfile,
)

_USER = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", role="socio")


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    """Devolve, em sequência, os resultados de cada `db.execute()`: casos,
    prazos, alertas — na mesma ordem chamada por build_executive_report."""

    def __init__(self, *result_sets):
        self._queue = list(result_sets)

    async def execute(self, *_a, **_kw):
        rows = self._queue.pop(0) if self._queue else []
        return _FakeResult(rows)


def _profile(client_id="c1") -> DptCompanyProfile:
    return DptCompanyProfile(
        id=client_id,
        nome="Empresa Teste Ltda",
        status="ativo",
        generated_at=datetime.now(timezone.utc),
        areas_com_casos=["tributario"],
        prazos_pendentes=0,
        documentos=0,
    )


def _case(i: int, client_id="c1"):
    return SimpleNamespace(
        id=f"case-{i}", client_id=client_id, titulo=f"Caso {i}", area="tributario",
        status="aberto", prioridade="critica", risco=None,
        proxima_acao=None, proxima_acao_prazo=None,
    )


def _deadline(i: int, case_id: str):
    return SimpleNamespace(
        id=f"deadline-{i}", case_id=case_id, titulo=f"Prazo {i}",
        data_prazo=date(2027, 1, 1), status="pendente", prioridade="alta",
        confirmado=True, deleted_at=None,
    )


def _dashboard(*, coverage="complete", notes=None):
    return SimpleNamespace(
        coverage=coverage, notes=notes or [],
    )


def _alerta(i: int) -> SimpleNamespace:
    # Sem termo de nenhuma área cadastrada: classify_area -> "geral" ->
    # impact_level sempre None -> nunca entra em "changes". Isola o teste no
    # teto de RAW ROWS buscadas, sem interferir no teto de 30 "mudanças".
    return SimpleNamespace(
        id=f"alerta-{i}", keyword_match=None, titulo="Publicação genérica",
        resumo=None, fonte="DOU", data_publicacao=None, link=None,
    )


def _patch_profile(monkeypatch, profile):
    async def fake(*_a, **_kw):
        return profile
    monkeypatch.setattr(report_service, "get_company_profile", fake)


def _patch_dashboard(monkeypatch, dashboard):
    async def fake(*_a, **_kw):
        return dashboard
    monkeypatch.setattr(report_service, "build_dashboard", fake)


async def test_cobertura_completa_quando_dashboard_e_secoes_dentro_do_teto(monkeypatch):
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(monkeypatch, _dashboard(coverage="complete"))
    resultado = await report_service.build_executive_report(_FakeDB([], [], []), _USER, "c1")
    assert resultado["cobertura"] == "completa"
    assert resultado["notas_cobertura"] == []


async def test_cobertura_incompleta_quando_dashboard_agregado_e_parcial(monkeypatch):
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(
        monkeypatch,
        _dashboard(coverage="partial", notes=["carteira truncada"]),
    )
    resultado = await report_service.build_executive_report(_FakeDB([], [], []), _USER, "c1")
    assert resultado["cobertura"] == "parcial"
    assert "carteira truncada" in resultado["notas_cobertura"]


async def test_cobertura_incompleta_por_truncamento_local_mesmo_com_dashboard_completo(monkeypatch):
    """Achado do review: mesmo com o dashboard inteiro marcado 'complete', uma
    empresa com mais de 30 casos tem a lista cortada pelo teto do PRÓPRIO
    relatório — isso também precisa zerar cobertura_completa, não só o teto
    global do dashboard."""
    muitos_casos = [_case(i) for i in range(35)]
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(monkeypatch, _dashboard(coverage="complete"))
    resultado = await report_service.build_executive_report(_FakeDB(muitos_casos, [], []), _USER, "c1")
    assert resultado["cobertura"] == "parcial"
    assert len(resultado["casos"]) == 30           # teto do relatório respeitado
    assert any("cortadas" in nota for nota in resultado["notas_cobertura"])


async def test_cobertura_completa_com_exatamente_500_alertas_no_periodo(monkeypatch):
    """Achado do review: 500 alertas pode ser o TOTAL real do intervalo, não
    truncamento — só marcar parcial quando exceder o teto exibido (500)."""
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(monkeypatch, _dashboard(coverage="complete"))
    db = _FakeDB([], [], [_alerta(i) for i in range(500)])
    resultado = await report_service.build_executive_report(db, _USER, "c1")
    assert resultado["cobertura"] == "completa"


async def test_cobertura_incompleta_com_501_alertas_no_periodo(monkeypatch):
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(monkeypatch, _dashboard(coverage="complete"))
    db = _FakeDB([], [], [_alerta(i) for i in range(501)])
    resultado = await report_service.build_executive_report(db, _USER, "c1")
    assert resultado["cobertura"] == "parcial"
    assert any("alertas do período" in nota for nota in resultado["notas_cobertura"])


async def test_cobertura_completa_com_499_alertas_no_periodo(monkeypatch):
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(monkeypatch, _dashboard(coverage="complete"))
    db = _FakeDB([], [], [_alerta(i) for i in range(499)])
    resultado = await report_service.build_executive_report(db, _USER, "c1")
    assert resultado["cobertura"] == "completa"


async def test_relatorio_ausente_para_empresa_fora_do_escopo(monkeypatch):
    _patch_profile(monkeypatch, None)
    resultado = await report_service.build_executive_report(_FakeDB(), _USER, "inexistente")
    assert resultado is None
