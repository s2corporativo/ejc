from __future__ import annotations

import pytest

from app.services import diagnostico_juridico_service as svc


def test_calendario_validado(monkeypatch):
    monkeypatch.setattr(
        svc,
        "calendario_runtime_status",
        lambda: {
            "status": "validado",
            "feriados_ok": True,
            "suspensoes_ok": True,
        },
    )
    item = svc._probe_calendario_prazos()
    assert item["status"] == "ok"
    assert item["feriados_ok"] is True
    assert item["suspensoes_ok"] is True


def test_calendario_degradado_bloqueia_confianca(monkeypatch):
    monkeypatch.setattr(
        svc,
        "calendario_runtime_status",
        lambda: {
            "status": "degradado",
            "feriados_ok": False,
            "suspensoes_ok": True,
            "feriados_erro_tipo": "DatabaseError",
            "suspensoes_erro_tipo": None,
        },
    )
    item = svc._probe_calendario_prazos()
    assert item["status"] == "erro"
    assert "preliminares" in item["detalhe"]
    assert "DatabaseError" in item["detalhe"]


def test_dou_tres_falhas_consecutivas_vira_erro(monkeypatch):
    monkeypatch.setattr(
        svc,
        "status_dou",
        lambda: {
            "status": "degradado",
            "ultima_execucao": "2026-08-19T12:00:00+00:00",
            "falhas_consecutivas": 3,
            "ultimo_erro_tipo": "HTTPStatusError",
        },
    )
    item = svc._probe_dou_runtime()
    assert item["status"] == "erro"
    assert item["falhas_consecutivas"] == 3
    assert "HTTPStatusError" in item["detalhe"]
    assert "keyword" not in item


@pytest.mark.asyncio
async def test_wrapper_recalcula_status_geral(monkeypatch):
    async def base(_db=None):
        return {
            "gerado_em": "2026-08-19T12:00:00+00:00",
            "status_geral": "ok",
            "resumo": {"ok": 1, "alerta": 0, "erro": 0, "desligado": 0},
            "subsistemas": [
                {
                    "nome": "Banco de dados",
                    "status": "ok",
                    "detalhe": "ok",
                    "acao_sugerida": "",
                    "latencia_ms": 1,
                }
            ],
            "aviso": "somente leitura",
        }

    monkeypatch.setattr(svc.diagnostico_service, "diagnostico_completo", base)
    monkeypatch.setattr(
        svc,
        "calendario_runtime_status",
        lambda: {"status": "nao_inicializado", "feriados_ok": None, "suspensoes_ok": None},
    )
    monkeypatch.setattr(
        svc,
        "status_dou",
        lambda: {"status": "nunca_executado", "falhas_consecutivas": 0},
    )

    payload = await svc.diagnostico_completo_com_juridico(None)
    assert payload["status_geral"] == "alerta"
    assert payload["resumo"]["alerta"] == 1
    assert len(payload["subsistemas"]) == 3


# ── Captura vazia por muitos dias seguidos ───────────────────────────────────
# O heartbeat do DOU já media RESULTADO por execução (`ultima_quantidade`), e
# distinguia "0 publicações" de "fonte fora do ar". O que faltava era a
# TENDÊNCIA: uma consulta saudável que não traz nada, repetida todo dia,
# mantinha o painel verde. É a forma exata do defeito que o CLAUDE.md registra
# ("a captura DJEN reporta ok há meses sem nunca ter capturado nada") — só que
# aqui o dado para detectá-lo já existia e ninguém o somava.

def _estado_ok(vazias: int, quantidade: int = 0) -> dict:
    return {
        "status": "ok",
        "ultima_execucao": "2026-08-22T06:00:00+00:00",
        "ultima_quantidade": quantidade,
        "falhas_consecutivas": 0,
        "execucoes_sem_resultado": vazias,
        "ultimo_erro_tipo": None,
    }


def test_uma_execucao_vazia_continua_ok(monkeypatch):
    """Dia sem publicação é normal — não pode virar alarme."""
    monkeypatch.setattr(svc, "status_dou", lambda: _estado_ok(1))
    item = svc._probe_dou_runtime()
    assert item["status"] == "ok"


def test_semana_inteira_sem_capturar_vira_alerta(monkeypatch):
    monkeypatch.setattr(
        svc, "status_dou",
        lambda: _estado_ok(svc.DOU_EXECUCOES_SEM_RESULTADO_ALERTA),
    )
    item = svc._probe_dou_runtime()
    assert item["status"] == "alerta"
    assert item["execucoes_sem_resultado"] == svc.DOU_EXECUCOES_SEM_RESULTADO_ALERTA
    assert "keyword" in item["detalhe"]
    # A ação precisa dizer o que conferir; "verifique o sistema" não serve.
    assert "keywords ativas" in item["acao_sugerida"]


def test_captura_com_resultado_zera_a_sequencia(monkeypatch):
    """Uma captura que traz publicação limpa o contador — senão o alerta
    ficaria grudado depois de resolvido."""
    from app.services import diario_oficial_service as dos

    monkeypatch.setitem(dos._DOU_STATUS, "execucoes_sem_resultado", 9)
    dos._registrar_status_dou(ok=True, quantidade=3)
    assert dos._DOU_STATUS["execucoes_sem_resultado"] == 0

    dos._registrar_status_dou(ok=True, quantidade=0)
    assert dos._DOU_STATUS["execucoes_sem_resultado"] == 1


def test_falha_de_fonte_nao_conta_como_execucao_vazia(monkeypatch):
    """São defeitos diferentes: fonte fora do ar já tem `falhas_consecutivas`.
    Somar os dois esconderia o que cada um diz."""
    from app.services import diario_oficial_service as dos

    monkeypatch.setitem(dos._DOU_STATUS, "execucoes_sem_resultado", 4)
    dos._registrar_status_dou(ok=False, erro=RuntimeError("fonte caiu"))
    assert dos._DOU_STATUS["execucoes_sem_resultado"] == 4
    assert dos._DOU_STATUS["falhas_consecutivas"] >= 1
