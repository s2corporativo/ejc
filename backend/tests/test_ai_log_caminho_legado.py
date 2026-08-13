# ── tests/test_ai_log_caminho_legado.py ──────────────────────────────────────
# Compliance #4a — "AILog obrigatório": endpoints VIVOS que chamam IA pelo
# caminho LEGADO (shim core.ai_brain → ai_gateway.chat via
# ai_gateway.processar_demanda) precisam gravar AILog. Antes NÃO gravavam.
#
# Cobre o endpoint instrumentado de forma ADITIVA:
#   - clients.py::ia_analise_cliente         (POST /clients/{id}/ia-analise)
# e a preservação da semântica de erro: em FALHA da IA o endpoint NÃO grava
# AILog (mesma semântica dos endpoints de IA já auditados) e NÃO levanta —
# o comportamento do shim (exceção → status="falha") é preservado.
#
# (cases.py::assistente_estrategico_caso, POST /cases/{id}/assistente-estrategico,
# foi removido em F1a — docs/PLANO_FUSAO_CASO_UNICO.md — por não ter nenhum
# consumidor no frontend e duplicar, sem rate limit nem piso de papel, o
# endpoint real de ai.py::assistente_estrategico.)
#
# Padrão dos testes de IA do projeto (sem Postgres/HTTP): handler chamado
# direto com fake de sessão; gateway central monkeypatched (exercita o shim
# legado real ponta a ponta, sem bater em provider).
from __future__ import annotations

from types import SimpleNamespace

from app.models.ai_log import AILog, AITipoUso
from app.models.user import User, UserRole
from app.routers import clients as clients_router
from app.services.ai_gateway import GatewayResponse


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Scalars:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalars(self):
        return _Scalars(self._val if isinstance(self._val, (list, tuple)) else [])


class _FakeDB:
    def __init__(self, resultados):
        self._resultados = list(resultados)
        self.added: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _fake_chat(texto="RASCUNHO: análise estratégica.", provedor="ollama", modelo="modelo-x"):
    async def chat(messages, task_type="", **kw):
        return GatewayResponse(
            texto=texto, modelo=modelo, provedor=provedor,
            task_type=task_type, input_tokens=12, output_tokens=34,
        )
    return chat


# ── clients.py :: ia_analise_cliente ──────────────────────────────────────────

async def test_ia_analise_cliente_grava_ailog(monkeypatch):
    from app.services import ai_gateway
    monkeypatch.setattr(ai_gateway, "chat", _fake_chat(texto="Perfil de risco moderado."))

    # responsavel_id == caller: satisfaz o gate de titularidade (sigilo interno)
    # sem tocar no _FakeDB — advogado só analisa o perfil da própria carteira.
    cliente = SimpleNamespace(
        id="cli-1", nome_exibicao="Empresa ACME", tipo="pj", deleted_at=None,
        responsavel_id="user-9",
    )
    casos = [SimpleNamespace(id="c1", client_id="cli-1")]
    fees = [SimpleNamespace(id="f1", client_id="cli-1")]
    db = _FakeDB([cliente, casos, fees])
    cu = User(id="user-9", role=UserRole.advogado)

    r = await clients_router.ia_analise_cliente("cli-1", db=db, cu=cu)

    assert r["status"] == "sucesso"

    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    log = logs[0]
    assert log.user_id == "user-9"
    assert log.case_id is None  # análise de cliente, não de caso
    # Perfil de CLIENTE → tipo_uso=outro (não "analise_caso"/sugestão de teses).
    assert log.tipo_uso == AITipoUso.outro
    assert log.resposta == "Perfil de risco moderado."
    assert log.modelo == "ollama/modelo-x"
    assert db.commits >= 1


# ── intelligence.py (canônico) :: analise_impacto ─────────────────────────────────────
# Único endpoint que mudou de execução (generate → processar_demanda) e o único
# que grava tipo_uso=outro sanitizando o prompt no próprio endpoint.

async def test_analise_impacto_grava_ailog(monkeypatch):
    from app.services import ai_gateway
    from app.routers import intelligence as intel_router
    monkeypatch.setattr(ai_gateway, "chat", _fake_chat(texto="Impacto: alta relevância tributária."))

    db = _FakeDB([])  # endpoint não faz db.execute; só grava o AILog
    cu = User(id="user-7", role=UserRole.socio)

    r = await intel_router.analise_impacto(
        {"texto": "Nova tese fixada pelo STF sobre PIS/COFINS."}, db=db, cu=cu,
    )

    # Resposta ao cliente preservada (mesmo shape do generate legado).
    assert r == {"resumo_executivo": "Impacto: alta relevância tributária."}

    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    log = logs[0]
    assert log.user_id == "user-7"
    assert log.case_id is None
    assert log.tipo_uso == AITipoUso.outro
    assert log.resposta == "Impacto: alta relevância tributária."
    assert log.modelo == "ollama/modelo-x"  # modelo REAL exposto por processar_demanda
    assert db.commits >= 1


async def test_analise_impacto_falha_nao_grava_ailog(monkeypatch):
    """IA falha → endpoint retorna {'resumo_executivo': _ERRO_SEGURO} sem levantar
    e SEM gravar AILog (semântica de erro preservada)."""
    from app.services import ai_gateway
    from app.routers import intelligence as intel_router
    from app.core.ai_brain import _ERRO_SEGURO

    async def chat_falha(messages, task_type="", **kw):
        raise RuntimeError("provider indisponível")

    monkeypatch.setattr(ai_gateway, "chat", chat_falha)

    db = _FakeDB([])
    cu = User(id="u7", role=UserRole.socio)

    r = await intel_router.analise_impacto({"texto": "qualquer fato"}, db=db, cu=cu)

    assert r == {"resumo_executivo": _ERRO_SEGURO}  # shim converte exceção
    assert [o for o in db.added if isinstance(o, AILog)] == []
