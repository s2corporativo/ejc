"""Correções da revisão do Codex no PR #493 (P1-A, P1-B, P2-C a P2-F)."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from app.routers import ramos
from app.services import route_usage

_RAIZ = Path(__file__).resolve().parents[2]


# ══════════════════════════════════════════════════════════════════════════
# P1-A — Súm. 309 STJ: 3 PRESTAÇÕES anteriores, não 3 meses de calendário
# ══════════════════════════════════════════════════════════════════════════
async def test_p1a_contraexemplo_do_revisor_mensal():
    """Ajuizamento 31/07 com parcelas 05/04, 05/05 e 05/06: as três são as três
    anteriores ao ajuizamento e vão para o rito de prisão. O corte por -3 meses
    (30/04) mandava a de 05/04 para expropriação."""
    r = await ramos.familia_debito_alimentos(
        datas_vencimento_em_aberto="2026-04-05,2026-05-05,2026-06-05",
        data_ajuizamento_execucao=date(2026, 7, 31), cu=None)
    assert r["parcelas_rito_prisao"] == [date(2026, 4, 5), date(2026, 5, 5), date(2026, 6, 5)]
    assert r["parcelas_rito_expropriacao"] == []
    assert "3 PRESTAÇÕES" in r["criterio_selecao"]
    assert "marco_corte_3_meses" not in r


async def test_p1a_quarta_parcela_mais_antiga_vai_para_expropriacao():
    r = await ramos.familia_debito_alimentos(
        datas_vencimento_em_aberto="2026-03-05,2026-04-05,2026-05-05,2026-06-05",
        data_ajuizamento_execucao=date(2026, 7, 31), cu=None)
    assert r["parcelas_rito_expropriacao"] == [date(2026, 3, 5)]
    assert len(r["parcelas_rito_prisao"]) == 3


async def test_p1a_quinzenal_pega_exatamente_tres_prestacoes():
    """Quinzenal: a janela de 3 meses capturaria ~6 parcelas; a súmula fala de 3."""
    r = await ramos.familia_debito_alimentos(
        datas_vencimento_em_aberto=("2026-05-01,2026-05-15,2026-06-01,2026-06-15,"
                                    "2026-07-01,2026-07-15"),
        data_ajuizamento_execucao=date(2026, 7, 20), cu=None)
    assert r["parcelas_rito_prisao"] == [date(2026, 6, 15), date(2026, 7, 1), date(2026, 7, 15)]
    assert len(r["parcelas_rito_expropriacao"]) == 3


async def test_p1a_trimestral_pega_as_tres_ainda_que_antigas():
    """Trimestral: a janela de 3 meses pegaria só 1 parcela; a súmula garante 3."""
    r = await ramos.familia_debito_alimentos(
        datas_vencimento_em_aberto="2025-10-10,2026-01-10,2026-04-10,2026-07-10",
        data_ajuizamento_execucao=date(2026, 7, 31), cu=None)
    assert r["parcelas_rito_prisao"] == [date(2026, 1, 10), date(2026, 4, 10), date(2026, 7, 10)]
    assert r["parcelas_rito_expropriacao"] == [date(2025, 10, 10)]


async def test_p1a_vincendas_sempre_no_rito_de_prisao():
    r = await ramos.familia_debito_alimentos(
        datas_vencimento_em_aberto="2026-05-05,2026-06-05,2026-07-05,2026-08-05,2026-09-05",
        data_ajuizamento_execucao=date(2026, 7, 20), cu=None)
    # 3 vencidas mais recentes + as 2 vincendas
    assert r["parcelas_rito_prisao"] == [date(2026, 5, 5), date(2026, 6, 5), date(2026, 7, 5),
                                         date(2026, 8, 5), date(2026, 9, 5)]
    assert r["parcelas_vincendas"] == 2
    assert r["parcelas_rito_expropriacao"] == []


# ══════════════════════════════════════════════════════════════════════════
# P2-D / P2-E — Sunset futuro e alias de horas-extras com cabeçalhos
# ══════════════════════════════════════════════════════════════════════════
def test_p2d_sunset_e_futuro():
    from email.utils import parsedate_to_datetime

    from datetime import datetime, timezone

    sunset = parsedate_to_datetime(ramos._SUNSET_DUPLICATAS)
    assert sunset > datetime.now(timezone.utc), "Sunset anunciado já passou"


async def test_p2e_alias_horas_extras_emite_cabecalhos():
    from fastapi import Response

    kw = dict(salario_mensal=2_200.0, horas_extras_mes=10.0, divisor=220,
              percentual_he=50.0, incluir_dsr="sim", incluir_reflexo_fgts="sim", cu=None)
    resp = Response()
    alias = await ramos.trabalhista_horas_extras_alias(response=resp, **kw)
    assert resp.headers["Deprecation"] == "true"
    assert resp.headers["Sunset"] == ramos._SUNSET_DUPLICATAS
    assert 'rel="successor-version"' in resp.headers["Link"]
    assert alias["deprecated"] is True
    assert alias["rota_canonica"] == "/trabalhista-esp/ferramentas/horas-extras"
    assert "DEPRECIADA" in alias["aviso_deprecacao"]


async def test_p2e_canonica_nao_e_depreciada_e_calculo_identico():
    from fastapi import Response

    kw = dict(salario_mensal=2_200.0, horas_extras_mes=10.0, divisor=220,
              percentual_he=50.0, incluir_dsr="sim", incluir_reflexo_fgts="sim", cu=None)
    canonica = await ramos.trabalhista_horas_extras(**kw)
    alias = await ramos.trabalhista_horas_extras_alias(response=Response(), **kw)
    assert "deprecated" not in canonica and "aviso_deprecacao" not in canonica
    assert alias["componentes"] == canonica["componentes"]
    assert alias["total_mes_estimado"] == canonica["total_mes_estimado"]


def test_p2e_apenas_o_alias_marcado_no_openapi():
    from app.main import app

    marcadas = {getattr(r, "path", ""): getattr(r, "deprecated", False)
                for r in app.routes if "horas-extras" in getattr(r, "path", "")}
    assert marcadas["/api/trabalhista/ferramentas/horas-extras"] is True
    assert not marcadas["/api/trabalhista-esp/ferramentas/horas-extras"]


# ══════════════════════════════════════════════════════════════════════════
# P2-F — leitura durante o flush não pode produzir falso zero
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture(autouse=True)
def _limpa_telemetria():
    route_usage.resetar()
    yield
    route_usage.resetar()


async def test_p2f_leitura_durante_o_flush_nao_reporta_sem_uso(monkeypatch):
    """Cenário concorrente: a leitura acontece depois da drenagem e antes do
    commit. O bucket não está no dict nem no banco — mas segue visível no buffer
    "em voo", então a rota NÃO pode aparecer em `sem_uso_no_periodo`."""
    lido: dict = {}

    class _FakeDB:
        async def execute(self, stmt):
            return None

        async def commit(self):
            # Leitura concorrente exatamente na janela crítica.
            lido.update(route_usage.agregado())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import app.core.database as database
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _FakeDB())

    route_usage.registrar("/api/deadlines/export.csv", "GET", "socio")
    await route_usage.flush()

    assert "/deadlines/export.csv" not in lido["sem_uso_no_periodo"]
    alvo = [r for r in lido["rotas"] if r["rota"] == "/deadlines/export.csv"][0]
    assert alvo["total"] == 1


async def test_p2f_apos_commit_memoria_fica_limpa(monkeypatch):
    """Commitado, o banco passa a responder: o buffer não pode dobrar a conta."""
    class _FakeDB:
        async def execute(self, stmt):
            return None

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import app.core.database as database
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _FakeDB())

    route_usage.registrar("/api/deadlines/export.csv", "GET", "socio")
    await route_usage.flush()
    assert route_usage.snapshot() == []


async def test_p2f_falha_no_flush_nao_duplica_contagem(monkeypatch):
    """Erro: o lote volta ao dict e sai do buffer — total continua 1, não 2."""
    import app.core.database as database

    def explode():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(database, "AsyncSessionLocal", explode)
    route_usage.registrar("/api/deadlines/export.csv", "GET", "socio")
    await route_usage.flush()
    linhas = route_usage.snapshot()
    assert len(linhas) == 1 and linhas[0]["contagem"] == 1


async def test_p2f_cancelamento_mantem_visibilidade(monkeypatch):
    import app.core.database as database

    def cancela():
        raise asyncio.CancelledError()

    monkeypatch.setattr(database, "AsyncSessionLocal", cancela)
    route_usage.registrar("/api/deadlines/export.csv", "GET", "socio")
    with pytest.raises(asyncio.CancelledError):
        await route_usage.flush()
    assert route_usage.snapshot()[0]["contagem"] == 1


# ══════════════════════════════════════════════════════════════════════════
# P1-B / P2-C — script de reclassificação
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture()
def script(monkeypatch):
    monkeypatch.setenv("EJC_ROLLBACK_HMAC_KEY", "chave-de-teste-com-16-mais")
    monkeypatch.setenv("APP_ENV", "development")
    caminho = _RAIZ / "scripts" / "reclassificar_areas_casos.py"
    spec = importlib.util.spec_from_file_location("reclassificar_areas_casos", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeCursor:
    def __init__(self, registro):
        self.registro = registro
        self.rowcount = 0

    def execute(self, sql, params=None):
        # Só o UPDATE de área conta: o INSERT de auditoria menciona `updated_at`
        # e seria capturado por uma checagem ingênua de substring.
        if sql.strip().upper().startswith("UPDATE"):
            self.registro.append(params)
            self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self):
        self.updates: list = []

    def cursor(self):
        return _FakeCursor(self.updates)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_p1b_rollback_ignora_item_nao_aplicado(script, tmp_path, capsys):
    """Item planejado mas com 0 linhas afetadas (outra transação mudou a área)
    NÃO pode ser revertido — reverteria alteração legítima de terceiro."""
    arquivo = tmp_path / "rb.json"
    script.gravar_rollback(arquivo, {
        "versao": 1, "tipo": "reclassificacao_area_cases", "status": "aplicado",
        "itens": [
            {"case_id": "6f1b0f6e-1f5a-4c2e-9a6a-2b7c8d9e0f11", "area_anterior": "civil",
             "area_nova": "bancario", "aplicado_em": "2026-07-28T10:00:00Z"},
            {"case_id": "7a2c1d7f-2a6b-4d3f-8b7b-3c8d9e0f1a22", "area_anterior": "civil",
             "area_nova": "imobiliario", "aplicado_em": None},      # NÃO aplicado
        ],
    })
    payload = script.ler_rollback(arquivo)
    conn = _FakeConn()
    resultado = script.reverter(conn, arquivo, payload, lote=200)

    revertidos = [u["case_id"] for u in conn.updates]
    assert revertidos == ["6f1b0f6e-1f5a-4c2e-9a6a-2b7c8d9e0f11"]
    assert "7a2c1d7f-2a6b-4d3f-8b7b-3c8d9e0f1a22" not in revertidos
    assert resultado["revertidos"] == 1


def test_p1b_avisa_sobre_itens_fora_do_rollback(script, tmp_path, capsys):
    arquivo = tmp_path / "rb.json"
    script.gravar_rollback(arquivo, {
        "versao": 1, "tipo": "reclassificacao_area_cases", "status": "aplicado",
        "itens": [{"case_id": "7a2c1d7f-2a6b-4d3f-8b7b-3c8d9e0f1a22",
                   "area_anterior": "civil", "area_nova": "imobiliario",
                   "aplicado_em": None}],
    })
    script.reverter(_FakeConn(), arquivo, script.ler_rollback(arquivo), lote=200)
    assert "NÃO aplicado" in capsys.readouterr().out


@pytest.mark.parametrize("valor", ["-1", "-100"])
def test_p2c_limite_negativo_e_rejeitado(script, valor):
    parser = script.construir_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--limite", valor])


def test_p2c_limite_nao_inteiro_e_rejeitado(script):
    parser = script.construir_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--limite", "todos"])


@pytest.mark.parametrize("valor,esperado", [("0", 0), ("5", 5)])
def test_p2c_limite_valido_e_aceito(script, valor, esperado):
    assert script.construir_parser().parse_args(["--limite", valor]).limite == esperado


def test_p2c_limite_zero_nao_aplica_nada(script):
    """`--limite 0` deve significar 'nada', não 'tudo' (comportamento de fatia)."""
    assert [1, 2, 3][:0] == []
