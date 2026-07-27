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


def test_monitora_endpoints_reais_e_nao_rotas_de_frontend():
    """/legado/* são rotas de FRONTEND — o backend nunca as recebe. O que é
    monitorado são os ENDPOINTS exclusivos das telas legadas."""
    assert not [r for r in route_usage.ROTAS_MONITORADAS if r.startswith("/legado/")]
    from app.main import app
    montadas = {(getattr(r, "path", "") or "").replace("/api", "", 1) for r in app.routes}
    for rota in route_usage.ROTAS_MONITORADAS:
        assert rota in montadas, f"{rota} não existe como endpoint montado"


def test_cobre_as_acoes_das_quatro_telas_legadas():
    motivos = set(route_usage.ROTAS_MONITORADAS.values())
    for tela in ("prazos", "intimacoes", "tarefas", "suspensoes"):
        assert any(m.startswith(f"legado:{tela}") for m in motivos), tela


@pytest.mark.parametrize("path", [
    "/api/deadlines/export.csv",
    "/deadlines/export.csv",
    "/api/deadlines/export.csv/",
    "/api/deadlines/export.csv?status=pendente",
])
def test_normalizacao_de_path(path):
    route_usage.registrar(path, "GET", "socio")
    assert route_usage.snapshot()[0]["rota"] == "/deadlines/export.csv"


def test_nao_grava_pii():
    """Só rota, método, papel e hora — nada de id, ip ou querystring."""
    route_usage.registrar("/api/tasks/{task_id}?case_id=SEGREDO&cpf=111", "GET", "advogado")
    linha = route_usage.snapshot()[0]
    assert set(linha) == {"rota", "metodo", "papel", "hora", "contagem", "motivo"}
    serializado = str(linha)
    assert "SEGREDO" not in serializado and "cpf" not in serializado
    assert linha["papel"] == "advogado"      # papel, não usuário


def test_agrega_por_rota_e_papel():
    for _ in range(3):
        route_usage.registrar("/api/deadlines/calcular", "POST", "advogado")
    route_usage.registrar("/api/deadlines/calcular", "POST", "admin")
    agregado = route_usage.agregado()
    prazos = [r for r in agregado["rotas"] if r["rota"] == "/deadlines/calcular"][0]
    assert prazos["total"] == 4
    assert prazos["por_papel"] == {"advogado": 3, "admin": 1}


def test_lista_rotas_sem_uso_para_decisao_da_onda5():
    """Rotas monitoradas sem chamada aparecem com total 0 — base da remoção."""
    route_usage.registrar("/api/deadlines/calcular", "POST", "advogado")
    agregado = route_usage.agregado()
    assert "/deadlines/calcular" not in agregado["sem_uso_no_periodo"]
    assert "/tasks/{task_id}" in agregado["sem_uso_no_periodo"]
    assert "/trabalhista/ferramentas/horas-extras" in agregado["sem_uso_no_periodo"]
    # Todas as 8 rotas candidatas + o alias estão sob monitoramento.
    assert len(agregado["rotas"]) == len(route_usage.ROTAS_MONITORADAS) == 16


def test_filtro_por_periodo():
    route_usage.registrar("/api/deadlines/calcular", "POST", "advogado")
    futuro = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert route_usage.agregado(futuro)["rotas"][0]["total"] == 0
    passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert any(r["total"] == 1 for r in route_usage.agregado(passado)["rotas"])


def test_papel_ausente_nao_quebra():
    route_usage.registrar("/api/intimacoes/capturar-agora", "POST", None)
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


async def test_endpoint_retorna_agregado(monkeypatch):
    """Endpoint soma histórico persistido + memória; sem banco, degrada para a
    memória (o helper de leitura é fail-open)."""
    from app.routers import architecture

    async def sem_banco(_desde):
        return []

    monkeypatch.setattr(route_usage, "_persistidos", sem_banco)
    route_usage.registrar("/api/suspensoes/simular", "POST", "socio")
    out = await architecture.uso_de_rotas(desde=None, _=None)
    assert out["rotas"] and "privacidade" in out and "observacao" in out
    assert "fonte" in out
    susp = [r for r in out["rotas"] if r["rota"] == "/suspensoes/simular"][0]
    assert susp["total"] == 1


async def test_flush_persiste_e_esvazia_memoria(monkeypatch):
    """O flush drena a memória; falha no banco DEVOLVE os contadores (fail-open)."""
    gravados = []

    class _FakeDB:
        async def execute(self, stmt):
            gravados.append(stmt)

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import app.core.database as database
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _FakeDB())

    route_usage.registrar("/api/deadlines/calcular", "POST", "advogado")
    route_usage.registrar("/api/deadlines/calcular", "POST", "advogado")
    resultado = await route_usage.flush()
    assert resultado["buckets"] == 1 and resultado["eventos"] == 2
    assert len(gravados) == 1
    assert route_usage.snapshot() == []          # memória drenada


async def test_flush_fail_open_devolve_contadores(monkeypatch):
    import app.core.database as database

    def explode():
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(database, "AsyncSessionLocal", explode)
    route_usage.registrar("/api/tasks/{task_id}", "DELETE", "admin")
    resultado = await route_usage.flush()
    assert resultado["eventos"] == 0 and "erro" in resultado
    # Nada se perde: o contador volta para a memória.
    assert route_usage.snapshot()[0]["contagem"] == 1


def test_modelo_persistido_sem_pii():
    """A tabela guarda só rota/método/papel/hora/contagem — nada de PII."""
    from app.models.route_usage_metric import RouteUsageMetric

    colunas = {c.key for c in RouteUsageMetric.__table__.columns}
    assert colunas == {"id", "rota", "metodo", "papel", "hora", "contagem",
                       "created_at", "updated_at"}
    proibidos = {"user_id", "ip", "usuario", "case_id", "query", "body", "cpf"}
    assert not (colunas & proibidos)


def test_job_de_flush_registrado():
    import inspect

    from app.services import scheduler

    fonte = inspect.getsource(scheduler)
    assert 'id="telemetria_rotas"' in fonte
    assert "_flush_telemetria_rotas" in fonte
