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


# ── Teto de tempo por tentativa (achado P1-2, revisão de 04/09/2026) ─────────
# O overlay do boot falhou porque uma operação de BANCO TRAVOU — e travamento
# não levanta exceção. Sem teto, a tentativa agendada espera as MESMAS
# consultas para sempre e, com max_instances=1 (default do APScheduler), IMPEDE
# todas as rodadas seguintes: a janela de exposição de credencial revogada
# deixa de ser "≤10 min" e vira indefinida.

async def test_tentativa_travada_do_retry_e_abortada_pelo_teto(monkeypatch):
    import asyncio
    import time

    from app.services import credential_vault_service as cofre
    from app.services import scheduler as sch

    monkeypatch.setattr(sch.settings, "STARTUP_STEP_TIMEOUT_SECONDS", 0.05)

    class _Sessao:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    estado = {"cancelada": False}

    async def _overlay_travado(_db):
        try:
            await asyncio.sleep(30)      # consulta que não responde nem falha
        except asyncio.CancelledError:
            estado["cancelada"] = True   # a tentativa TERMINA de fato
            raise
        return []                        # pragma: no cover

    marcados: list[str] = []
    monkeypatch.setattr(sch, "AsyncSessionLocal", lambda: _Sessao())
    monkeypatch.setattr(cofre, "aplicar_overlay", _overlay_travado)
    monkeypatch.setattr(
        cofre, "estado_overlay", lambda: {"aplicado": False, "status": "falho"}
    )
    monkeypatch.setattr(cofre, "marcar_overlay_falho", marcados.append)

    inicio = time.monotonic()
    # wait_for é rede de segurança do TESTE: sem o teto no job a corrotina
    # ficaria pendurada e o teste morreria em vez de acusar a regressão.
    await asyncio.wait_for(sch._reaplicar_overlay_cofre(), timeout=5)

    assert time.monotonic() - inicio < 5
    assert estado["cancelada"] is True, "tentativa travada tem de ser cancelada"
    assert marcados == ["TimeoutError"], "o motivo fica consultável no estado"


async def test_rodada_seguinte_roda_depois_de_uma_tentativa_travada(monkeypatch):
    """Tentativa travada não pode confiscar as rodadas seguintes."""
    import asyncio

    from app.services import credential_vault_service as cofre
    from app.services import scheduler as sch

    monkeypatch.setattr(sch.settings, "STARTUP_STEP_TIMEOUT_SECONDS", 0.05)

    class _Sessao:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    tentativas: list[str] = []

    async def _travado(_db):
        tentativas.append("travada")
        await asyncio.sleep(30)
        return []                        # pragma: no cover

    async def _ok(_db):
        tentativas.append("ok")
        return ["DATAJUD_API_KEY"]

    monkeypatch.setattr(sch, "AsyncSessionLocal", lambda: _Sessao())
    monkeypatch.setattr(
        cofre, "estado_overlay", lambda: {"aplicado": False, "status": "falho"}
    )
    monkeypatch.setattr(cofre, "marcar_overlay_falho", lambda _t: None)

    monkeypatch.setattr(cofre, "aplicar_overlay", _travado)
    await asyncio.wait_for(sch._reaplicar_overlay_cofre(), timeout=5)
    monkeypatch.setattr(cofre, "aplicar_overlay", _ok)
    await asyncio.wait_for(sch._reaplicar_overlay_cofre(), timeout=5)

    assert tentativas == ["travada", "ok"]


# ── Corrida retry × revogação (achado P1-3) ─────────────────────────────────
# aplicar_overlay LÊ as linhas ativas, aguarda uma SEGUNDA consulta e só então
# muta o Settings compartilhado. Se o retry lê a credencial ativa ANTES de a
# revogação commitar mas escreve DEPOIS do overlay da própria requisição, ele
# RESTAURA o valor revogado e marca `aplicado=True` — os retries seguintes
# viram no-op e a credencial revogada segue valendo até o restart.

class _ResultadoFake:
    def __init__(self, linhas):
        self._linhas = linhas

    def all(self):
        return self._linhas


class _SessaoFake:
    """Sessão dupla: `atraso` = pontos de suspensão da consulta (banco lento é
    justamente o que põe o processo na janela degradada)."""

    def __init__(self, banco: dict, atraso: int = 0):
        self.banco = banco
        self.atraso = atraso

    async def execute(self, _stmt):
        import asyncio

        for _ in range(self.atraso):
            await asyncio.sleep(0)
        return _ResultadoFake([(k,) for k in sorted(self.banco["historico"])])


async def test_retry_lento_nao_restaura_credencial_revogada(monkeypatch):
    import asyncio

    from app.core.config import get_settings
    from app.services import credential_vault_service as svc

    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "valor-do-env")
    estado_anterior = dict(svc._OVERLAY_RUNTIME)

    banco = {
        "ativos": {"DATAJUD_API_KEY": "chave-antiga-revogada"},
        "historico": {"DATAJUD_API_KEY"},
    }

    async def _resolver(db):
        # A LEITURA acontece agora; a resposta é que demora a chegar. É esse
        # descompasso (ler antes do commit, escrever depois) que produz a
        # corrida — um duplo que relesse `banco` no fim não a reproduziria.
        lido = dict(banco["ativos"])
        for _ in range(db.atraso):
            await asyncio.sleep(0)
        return lido

    monkeypatch.setattr(svc, "resolver_overlay", _resolver)

    async def _retry_lento():
        # Job agendado: sessão própria, banco lento (a razão de o overlay do
        # boot ter falhado), leitura ANTES do commit da revogação.
        await svc.aplicar_overlay(_SessaoFake(banco, atraso=3))

    async def _requisicao_de_revogacao():
        await asyncio.sleep(0)          # a requisição chega com o retry em voo
        banco["ativos"].clear()         # COMMIT da revogação
        # routers/credential_vault.py aplica o overlay na MESMA requisição,
        # logo após o commit.
        await svc.aplicar_overlay(_SessaoFake(banco, atraso=0))

    try:
        await asyncio.gather(_retry_lento(), _requisicao_de_revogacao())
        assert settings.DATAJUD_API_KEY == "", (
            "credencial revogada não pode ser restaurada pelo retry em voo"
        )
    finally:
        svc._OVERLAY_RUNTIME.clear()
        svc._OVERLAY_RUNTIME.update(estado_anterior)
