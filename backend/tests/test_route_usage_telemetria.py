"""Onda 3 §4.5 — telemetria de uso das rotas candidatas à remoção (insumo da Onda 5).

Cobre: registro só das rotas monitoradas, ausência de PII, agregação por rota e
papel, filtro por período, teto de memória e o endpoint admin de leitura.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import route_usage


@pytest.fixture(autouse=True)
def _limpa_contadores():
    route_usage.resetar()
    yield
    route_usage.resetar()


def test_registra_apenas_rotas_monitoradas():
    route_usage.registrar("/api/penal/ferramentas/prescricao-punitiva", "GET", "advogado")
    route_usage.registrar("/api/cases/{case_id}", "GET", "advogado")   # fora da lista
    linhas = route_usage.snapshot()
    assert len(linhas) == 1
    assert linhas[0]["rota"] == "/penal/ferramentas/prescricao-punitiva"
    assert linhas[0]["motivo"] == "duplicata"


@pytest.mark.parametrize("path", [
    "/api/legado/prazos",
    "/legado/prazos",
    "/api/legado/prazos/",
    "/api/legado/prazos?case_id=123",
])
def test_normalizacao_de_path(path):
    route_usage.registrar(path, "GET", "socio")
    assert route_usage.snapshot()[0]["rota"] == "/legado/prazos"


def test_nao_grava_pii():
    """Só rota, método, papel e hora — nada de id, ip ou querystring."""
    route_usage.registrar("/api/legado/tarefas?case_id=SEGREDO&cpf=111", "GET", "advogado")
    linha = route_usage.snapshot()[0]
    assert set(linha) == {"rota", "metodo", "papel", "hora", "contagem", "motivo"}
    serializado = str(linha)
    assert "SEGREDO" not in serializado and "cpf" not in serializado
    assert linha["papel"] == "advogado"      # papel, não usuário


def test_agrega_por_rota_e_papel():
    for _ in range(3):
        route_usage.registrar("/api/legado/prazos", "GET", "advogado")
    route_usage.registrar("/api/legado/prazos", "GET", "admin")
    agregado = route_usage.agregado()
    prazos = [r for r in agregado["rotas"] if r["rota"] == "/legado/prazos"][0]
    assert prazos["total"] == 4
    assert prazos["por_papel"] == {"advogado": 3, "admin": 1}


def test_lista_rotas_sem_uso_para_decisao_da_onda5():
    """Rotas monitoradas sem chamada aparecem com total 0 — base da remoção."""
    route_usage.registrar("/api/legado/prazos", "GET", "advogado")
    agregado = route_usage.agregado()
    assert "/legado/prazos" not in agregado["sem_uso_no_periodo"]
    assert "/legado/tarefas" in agregado["sem_uso_no_periodo"]
    assert "/trabalhista/ferramentas/horas-extras" in agregado["sem_uso_no_periodo"]
    # Todas as 8 rotas candidatas + o alias estão sob monitoramento.
    assert len(agregado["rotas"]) == len(route_usage.ROTAS_MONITORADAS) == 8


def test_filtro_por_periodo():
    route_usage.registrar("/api/legado/prazos", "GET", "advogado")
    futuro = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert route_usage.agregado(futuro)["rotas"][0]["total"] == 0
    passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert any(r["total"] == 1 for r in route_usage.agregado(passado)["rotas"])


def test_papel_ausente_nao_quebra():
    route_usage.registrar("/api/legado/intimacoes", "GET", None)
    assert route_usage.snapshot()[0]["papel"] == "desconhecido"


def test_registro_nunca_levanta_excecao():
    route_usage.registrar(None, None, None)          # entrada degenerada
    route_usage.registrar("", "", "")
    assert route_usage.snapshot() == []


def test_teto_de_memoria(monkeypatch):
    monkeypatch.setattr(route_usage, "_MAX_ENTRADAS", 2)
    for papel in ("a", "b", "c", "d"):
        route_usage.registrar("/api/legado/prazos", "GET", papel)
    assert len(route_usage.snapshot()) <= 2           # não cresce sem limite


def test_endpoint_admin_registrado_e_protegido():
    from app.main import app

    rota = [r for r in app.routes if getattr(r, "path", "") == "/api/architecture/uso-rotas"]
    assert rota, "endpoint de leitura da telemetria não está montado"
    deps = {getattr(d.call, "__name__", "") for d in rota[0].dependant.dependencies}
    assert "require_admin" in deps or any("admin" in d for d in deps)


async def test_endpoint_retorna_agregado():
    from app.routers.architecture import uso_de_rotas

    route_usage.registrar("/api/legado/suspensoes", "GET", "socio")
    out = await uso_de_rotas(desde=None, _=None)
    assert out["rotas"] and "privacidade" in out and "observacao" in out
    susp = [r for r in out["rotas"] if r["rota"] == "/legado/suspensoes"][0]
    assert susp["total"] == 1
