from datetime import datetime, timezone
from types import SimpleNamespace

from app.modules.dpt360 import report_service
from app.modules.dpt360.schemas import DptCompanyProfile

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


def _caso_critico(i: int, client_id="c1") -> SimpleNamespace:
    return SimpleNamespace(
        id=f"case-{i}", client_id=client_id, titulo=f"Caso {i}", area="tributario",
        status="aberto", prioridade="critica", risco=None,
        proxima_acao=None, proxima_acao_prazo=None, created_at=None,
    )


def _patch_profile(monkeypatch, profile):
    async def fake(*_a, **_kw):
        return profile
    monkeypatch.setattr(report_service, "get_company_profile", fake)


def _patch_dashboard(monkeypatch, *, coverage="complete", notes=None):
    dashboard = SimpleNamespace(coverage=coverage, notes=notes or [])

    async def fake(*_a, **_kw):
        return dashboard
    monkeypatch.setattr(report_service, "build_dashboard", fake)


async def test_relatorio_ausente_para_empresa_fora_do_escopo(monkeypatch):
    _patch_profile(monkeypatch, None)
    resultado = await report_service.build_executive_report(_FakeDB(), _USER, "inexistente")
    assert resultado is None


async def test_cobertura_completa_sem_truncamento_em_nenhuma_secao(monkeypatch):
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(monkeypatch, coverage="complete")
    db = _FakeDB([_caso_critico(1)], [], [])
    resultado = await report_service.build_executive_report(db, _USER, "c1")
    assert resultado["cobertura"] == "completa"
    assert resultado["notas_cobertura"] == []


async def test_cobertura_parcial_quando_mais_de_10_riscos_criticos(monkeypatch):
    """Achado do review: "principais_riscos" tem teto próprio (10) e precisa
    entrar na verificação de cobertura como casos/prazos/alertas — do contrário
    uma empresa com mais de 10 riscos críticos teria a lista cortada sem aviso."""
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(monkeypatch, coverage="complete")
    muitos_criticos = [_caso_critico(i) for i in range(15)]
    db = _FakeDB(muitos_criticos, [], [])
    resultado = await report_service.build_executive_report(db, _USER, "c1")
    assert resultado["cobertura"] == "parcial"
    assert len(resultado["principais_riscos"]) == 10       # teto respeitado
    assert any("riscos atuais" in nota for nota in resultado["notas_cobertura"])


async def test_cobertura_parcial_quando_dashboard_agregado_e_parcial(monkeypatch):
    _patch_profile(monkeypatch, _profile())
    _patch_dashboard(monkeypatch, coverage="partial", notes=["carteira truncada"])
    db = _FakeDB([], [], [])
    resultado = await report_service.build_executive_report(db, _USER, "c1")
    assert resultado["cobertura"] == "parcial"
    assert any("carteira truncada" in nota for nota in resultado["notas_cobertura"])
