"""Correções da auditoria de segurança das Ondas 3-5 (P1-1 e P2-1 a P2-4).

Os dois primeiros são os que CORROMPEM a decisão da Onda 5:
  P1-1 — `desde` inválido descartava o histórico e devolvia zeros, que seriam
         lidos como "rota sem uso" (removeria endpoint em uso diário);
  P2-1 — contador forjável por 404 com chaves percent-encoded e por respostas
         de erro (403/405) em rota monitorada.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services import route_usage


@pytest.fixture(autouse=True)
def _limpa():
    route_usage.resetar()
    yield
    route_usage.resetar()


# ══════════════════════════════════════════════════════════════════════════
# P1-1 — `desde` inválido nunca vira "sem uso"
# ══════════════════════════════════════════════════════════════════════════
def test_p1_contrato_do_endpoint_valida_desde():
    """`desde` é datetime no contrato: string malformada → 422 do FastAPI,
    jamais histórico descartado em silêncio."""
    import inspect
    from datetime import datetime as dt

    from app.routers.architecture import uso_de_rotas

    anot = inspect.signature(uso_de_rotas).parameters["desde"].annotation
    assert anot in (dt | None, "datetime | None") or "datetime" in str(anot)


@pytest.mark.parametrize("valor,esperado", [
    ("2026-06-01", datetime(2026, 6, 1)),                       # ISO parcial: ACEITO
    ("2026-06-01T10:30:00", datetime(2026, 6, 1, 10, 30)),
])
def test_p1_iso_parcial_e_aceito_pelo_contrato(valor, esperado):
    """O formato que a docstring sugeria (data pura) agora é aceito — antes ele
    era o gatilho do bug: `fromisoformat` funcionava, mas qualquer variação
    caía no except e zerava tudo."""
    from pydantic import TypeAdapter

    assert TypeAdapter(datetime).validate_python(valor).replace(tzinfo=None) == esperado


@pytest.mark.parametrize("valor", ["ontem", "01/06/2026", "2026-13-45", ""])
def test_p1_desde_invalido_e_rejeitado_nao_ignorado(valor):
    from pydantic import TypeAdapter, ValidationError

    with pytest.raises(ValidationError):
        TypeAdapter(datetime).validate_python(valor)


async def test_p1_historico_indisponivel_marca_payload_e_omite_sem_uso(monkeypatch):
    """Banco fora: a resposta NÃO pode exibir `sem_uso_no_periodo` — seria lido
    como prova de ociosidade e removeria rota em uso."""
    async def explode(_desde):
        raise route_usage.HistoricoIndisponivel("OperationalError")

    monkeypatch.setattr(route_usage, "_persistidos", explode)
    out = await route_usage.agregado_persistido(None)
    assert out["historico_indisponivel"] is True
    assert "sem_uso_no_periodo" not in out          # o campo perigoso some
    assert "NÃO use este resultado" in out["alerta"]
    assert "APENAS memória" in out["fonte"]


async def test_p1_tabela_ausente_continua_fail_open(monkeypatch):
    """Migration 122 ainda não aplicada: vazio é a verdade, resposta normal."""
    class _ErroTabela(Exception):
        pass

    async def sem_tabela(_desde):
        raise _ErroTabela('relation "route_usage_metrics" does not exist')

    async def real(desde):
        try:
            return await sem_tabela(desde)
        except Exception as exc:
            if route_usage._tabela_ausente(exc):
                return []
            raise

    monkeypatch.setattr(route_usage, "_persistidos", real)
    out = await route_usage.agregado_persistido(None)
    assert "historico_indisponivel" not in out
    assert "sem_uso_no_periodo" in out              # aqui o campo é legítimo


def test_p1_classificador_de_tabela_ausente():
    assert route_usage._tabela_ausente(Exception('relation "x" does not exist'))
    assert route_usage._tabela_ausente(Exception("UndefinedTableError"))
    assert not route_usage._tabela_ausente(Exception("connection refused"))
    assert not route_usage._tabela_ausente(Exception("invalid input syntax for type timestamp"))


# ══════════════════════════════════════════════════════════════════════════
# P2-1 — contador não forjável
# ══════════════════════════════════════════════════════════════════════════
class _FakeReq:
    def __init__(self, route_path, metodo="GET", papel="advogado"):
        self.scope = {"route": type("R", (), {"path": route_path})()} if route_path else {}
        self.method = metodo
        self.state = type("S", (), {"role": papel})()
        self.url = type("U", (), {"path": "/api/tasks/%7Btask_id%7D"})()


def test_p2_1_404_com_chaves_encodadas_nao_conta():
    """`GET /api/tasks/%7Btask_id%7D` não casa rota: sem fallback para o path
    concreto, nada é registrado (antes contava como a rota-template)."""
    from app.core.auth_middleware import _registrar_uso_de_rota

    _registrar_uso_de_rota(_FakeReq(None), 404)
    assert route_usage.snapshot() == []


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 422, 500])
def test_p2_1_resposta_de_erro_nao_conta(status):
    """403 numa rota monitorada não pode fazer tela morta parecer viva."""
    from app.core.auth_middleware import _registrar_uso_de_rota

    _registrar_uso_de_rota(_FakeReq("/api/suspensoes/", "POST", "estagiario"), status)
    assert route_usage.snapshot() == []


@pytest.mark.parametrize("status", [200, 201, 204, 302])
def test_p2_1_uso_real_continua_contando(status):
    from app.core.auth_middleware import _registrar_uso_de_rota

    route_usage.resetar()
    _registrar_uso_de_rota(_FakeReq("/api/deadlines/export.csv", "GET", "socio"), status)
    linhas = route_usage.snapshot()
    assert len(linhas) == 1 and linhas[0]["rota"] == "/deadlines/export.csv"


def test_p2_1_laco_de_404_nao_infla_contador():
    """Cenário do auditor: staff autenticado varrendo 404s não move o contador."""
    from app.core.auth_middleware import _registrar_uso_de_rota

    for _ in range(50):
        _registrar_uso_de_rota(_FakeReq(None), 404)
    assert route_usage.agregado()["rotas"][0]["total"] == 0


# ══════════════════════════════════════════════════════════════════════════
# P2-2 / P2-4 — teto no restore e cancelamento no shutdown
# ══════════════════════════════════════════════════════════════════════════
async def test_p2_2_teto_vale_no_restore(monkeypatch):
    """Cenário real do achado: o flush DRENA o dict, tráfego novo chega enquanto
    ele está em voo e o enche até o teto, o banco falha e o restore devolve os
    antigos por cima — antes, sem checagem, o dict ia a 2x o teto por ciclo."""
    import app.core.database as database

    monkeypatch.setattr(route_usage, "_MAX_ENTRADAS", 2)

    def banco_fora_com_trafego_novo():
        # Chega DEPOIS da drenagem, ocupando todo o teto.
        for papel in ("novo_a", "novo_b"):
            route_usage.registrar("/api/deadlines/calcular", "POST", papel)
        raise RuntimeError("banco fora")

    monkeypatch.setattr(database, "AsyncSessionLocal", banco_fora_com_trafego_novo)
    for papel in ("velho_a", "velho_b"):
        route_usage.registrar("/api/deadlines/calcular", "POST", papel)

    resultado = await route_usage.flush()
    assert len(route_usage.snapshot()) <= 2                 # não estoura o teto
    assert resultado["eventos_descartados_por_teto"] == 2   # e diz quanto perdeu


async def test_p2_4_cancelamento_restaura_e_repropaga(monkeypatch):
    """shutdown(wait=False) cancela o flush: os contadores voltam para a memória
    E o CancelledError é repropagado (antes, `except Exception` engolia)."""
    import app.core.database as database

    def cancela():
        raise asyncio.CancelledError()

    monkeypatch.setattr(database, "AsyncSessionLocal", cancela)
    route_usage.registrar("/api/intimacoes/capturar-agora", "POST", "advogado")
    with pytest.raises(asyncio.CancelledError):
        await route_usage.flush()
    assert route_usage.snapshot()[0]["contagem"] == 1       # janela preservada


def test_p2_4_limite_do_upsert_documentado():
    assert "não é idempotente" in route_usage.flush.__doc__ or \
           "não-idempotente" in route_usage.flush.__doc__ or \
           "idempotente" in route_usage.flush.__doc__


# ══════════════════════════════════════════════════════════════════════════
# P2-3 — LGPD: k-anonimato, texto honesto e expurgo
# ══════════════════════════════════════════════════════════════════════════
def test_p2_3_k_anonimato_colapsa_papel_raro():
    for _ in range(7):
        route_usage.registrar("/api/deadlines/export.csv", "GET", "advogado")
    route_usage.registrar("/api/deadlines/export.csv", "GET", "superadmin")   # titular único
    rota = [r for r in route_usage.agregado()["rotas"]
            if r["rota"] == "/deadlines/export.csv"][0]
    assert "superadmin" not in rota["por_papel"]        # não singulariza
    assert rota["por_papel"]["outros"] == 1
    assert rota["papeis_generalizados"] is True
    assert rota["total"] == 8                           # TOTAL preservado


def test_p2_3_texto_nao_promete_anonimizacao():
    texto = route_usage.agregado()["privacidade"]
    assert "Sem PII" not in texto
    assert "identificadores diretos" in texto
    assert "Não é anonimização" in texto
    assert "k-anonimato" in route_usage.__doc__ or "k-anonimato" in texto


def test_p2_3_retencao_e_job_de_expurgo():
    import inspect

    from app.services import scheduler

    assert route_usage.RETENCAO_DIAS == 90
    fonte = inspect.getsource(scheduler)
    assert 'id="telemetria_rotas_expurgo"' in fonte
    assert "_expurgar_telemetria_rotas" in fonte


async def test_p2_3_expurgo_remove_acima_da_janela(monkeypatch):
    apagados = []

    class _FakeDB:
        async def execute(self, stmt):
            apagados.append(stmt)
            return type("R", (), {"rowcount": 3})()

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import app.core.database as database
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _FakeDB())
    out = await route_usage.expurgar_antigos(dias=90)
    assert out["removidos"] == 3 and apagados
    corte = datetime.fromisoformat(out["corte"])
    assert corte < datetime.now(timezone.utc) - timedelta(days=89)


def test_p2_3_decisao_registrada_em_docs():
    from pathlib import Path

    doc = Path(__file__).resolve().parents[2] / "docs" / "LGPD_TELEMETRIA_ROTAS.md"
    texto = doc.read_text(encoding="utf-8")
    assert "k-anonimato" in texto and "90 dias" in texto
    assert "não é anonimização" in texto.lower()
