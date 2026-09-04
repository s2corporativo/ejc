# ── tests/test_cofre_overlay_retry.py ────────────────────────────────────────
# Achado P1 (revisão de 04/09/2026): overlay do Cofre que estoura o teto do
# boot deixava a API rodando com as credenciais do arquivo de ambiente
# INDEFINIDAMENTE. Como o ambiente não conhece REVOGAÇÃO (aplicar_overlay zera
# para "" o campo com histórico e sem linha ativa), uma chave revogada no cofre
# voltava a funcionar sempre que o banco estivesse lento no boot.
#
# Contrato travado aqui: enquanto `estado_overlay()["aplicado"]` for False, o
# job `cofre_overlay_retry` reaplica o overlay; depois do sucesso é no-op sem
# I/O. Sem Postgres e sem rede (sessão e overlay são duplos).
from __future__ import annotations


# ── Reaplicação do overlay do cofre (achado P1) ──────────────────────────────

async def test_job_reaplica_overlay_do_cofre_enquanto_nao_aplicado(monkeypatch):
    """Enquanto o overlay não vinga, o processo usa credencial do ambiente —
    que não conhece revogação. O job reaplica até dar certo."""
    from app.services import credential_vault_service as cofre
    from app.services import scheduler as sch

    chamadas: list[str] = []

    class _Sessao:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    async def _fake_overlay(_db):
        chamadas.append("overlay")
        return ["DATAJUD_API_KEY"]

    monkeypatch.setattr(sch, "AsyncSessionLocal", lambda: _Sessao())
    monkeypatch.setattr(cofre, "aplicar_overlay", _fake_overlay)
    monkeypatch.setattr(
        cofre, "estado_overlay", lambda: {"aplicado": False, "status": "falho"}
    )

    await sch._reaplicar_overlay_cofre()
    assert chamadas == ["overlay"]


async def test_job_do_cofre_e_no_op_depois_do_sucesso(monkeypatch):
    from app.services import credential_vault_service as cofre
    from app.services import scheduler as sch

    def _explode():
        raise AssertionError("overlay já aplicado não pode abrir sessão")

    monkeypatch.setattr(sch, "AsyncSessionLocal", _explode)
    monkeypatch.setattr(
        cofre, "estado_overlay", lambda: {"aplicado": True, "status": "aplicado"}
    )

    await sch._reaplicar_overlay_cofre()   # não levanta


async def test_falha_na_reaplicacao_mantem_estado_falho(monkeypatch):
    from app.services import credential_vault_service as cofre
    from app.services import scheduler as sch

    marcados: list[str] = []

    class _Sessao:
        async def __aenter__(self):
            raise RuntimeError("banco fora")

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(sch, "AsyncSessionLocal", lambda: _Sessao())
    monkeypatch.setattr(
        cofre, "estado_overlay", lambda: {"aplicado": False, "status": "falho"}
    )
    monkeypatch.setattr(cofre, "marcar_overlay_falho", marcados.append)

    await sch._reaplicar_overlay_cofre()   # nunca propaga (é job agendado)
    assert marcados == ["RuntimeError"]


def test_job_do_cofre_esta_registrado_no_start_scheduler():
    from pathlib import Path

    fonte = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "scheduler.py"
    ).read_text(encoding="utf-8")
    assert "s.add_job(_reaplicar_overlay_cofre" in fonte
    assert 'id="cofre_overlay_retry"' in fonte
