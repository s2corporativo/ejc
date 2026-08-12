from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.modules.dpt360 import report_service
from app.modules.dpt360.schemas import (
    DptCaseSummary,
    DptCompanyProfile,
    DptDashboardMetrics,
    DptDashboardResponse,
    DptDeadlineSummary,
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
    def __init__(self, rows=None):
        self._rows = rows or []

    async def execute(self, *_a, **_kw):
        return _FakeResult(self._rows)


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


def _case(i: int, client_id="c1") -> DptCaseSummary:
    return DptCaseSummary(
        id=f"case-{i}",
        client_id=client_id,
        titulo=f"Caso {i}",
        area="tributario",
        status="aberto",
        prioridade="critica",  # conta como crítico em _is_critical_case
    )


def _deadline(i: int, case_id: str) -> DptDeadlineSummary:
    return DptDeadlineSummary(
        id=f"deadline-{i}",
        case_id=case_id,
        titulo=f"Prazo {i}",
        data_prazo=date(2027, 1, 1),
        status="pendente",
        prioridade="alta",
    )


def _dashboard(*, coverage="complete", notes=None, cases=None) -> DptDashboardResponse:
    cases = cases if cases is not None else [_case(1)]
    return DptDashboardResponse(
        generated_at=datetime.now(timezone.utc),
        metrics=DptDashboardMetrics(),
        companies=[],
        cases=cases,
        deadlines=[_deadline(1, cases[0].id)] if cases else [],
        priorities=[],
        coverage=coverage,
        notes=notes or [],
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
    resultado = await report_service.build_executive_report(_FakeDB(), _USER, "c1")
    assert resultado["cobertura_completa"] is True
    assert resultado["cobertura_notas"] == []


async def test_cobertura_incompleta_quando_dashboard_agregado_e_parcial(monkeypatch):
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(
        monkeypatch,
        _dashboard(coverage="partial", notes=["carteira truncada"]),
    )
    resultado = await report_service.build_executive_report(_FakeDB(), _USER, "c1")
    assert resultado["cobertura_completa"] is False
    assert "carteira truncada" in resultado["cobertura_notas"]


async def test_cobertura_incompleta_por_truncamento_local_mesmo_com_dashboard_completo(monkeypatch):
    """Achado do review: mesmo com o dashboard inteiro marcado 'complete', uma
    empresa com mais de 30 casos tem a lista cortada pelo teto do PRÓPRIO
    relatório — isso também precisa zerar cobertura_completa, não só o teto
    global do dashboard."""
    muitos_casos = [_case(i) for i in range(35)]
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(monkeypatch, _dashboard(coverage="complete", cases=muitos_casos))
    resultado = await report_service.build_executive_report(_FakeDB(), _USER, "c1")
    assert resultado["cobertura_completa"] is False
    assert len(resultado["casos"]) == 30           # teto do relatório respeitado
    assert any("cortadas" in nota for nota in resultado["cobertura_notas"])


async def test_relatorio_ausente_para_empresa_fora_do_escopo(monkeypatch):
    _patch_profile(monkeypatch, None)
    resultado = await report_service.build_executive_report(_FakeDB(), _USER, "inexistente")
    assert resultado is None
