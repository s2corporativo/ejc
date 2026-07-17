# ── tests/test_ai_log_caminho_legado.py ──────────────────────────────────────
# Compliance #4a — "AILog obrigatório": endpoints VIVOS que chamam IA pelo
# caminho LEGADO (shim core.ai_brain → ai_gateway.chat via
# ai_gateway.processar_demanda) precisam gravar AILog. Antes NÃO gravavam.
#
# Cobre os endpoints instrumentados de forma ADITIVA:
#   - cases.py::assistente_estrategico_caso  (POST /cases/{id}/assistente-estrategico)
#   - clients.py::ia_analise_cliente         (POST /clients/{id}/ia-analise)
# e a preservação da semântica de erro: em FALHA da IA o endpoint NÃO grava
# AILog (mesma semântica dos endpoints de IA já auditados) e NÃO levanta —
# o comportamento do shim (exceção → status="falha") é preservado.
#
# Padrão dos testes de IA do projeto (sem Postgres/HTTP): handler chamado
# direto com fake de sessão; gateway central monkeypatched (exercita o shim
# legado real ponta a ponta, sem bater em provider).
from __future__ import annotations

from types import SimpleNamespace

from app.models.ai_log import AILog, AITipoUso
from app.models.user import User, UserRole
from app.routers import cases as cases_router
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


# ── cases.py :: assistente_estrategico_caso ───────────────────────────────────

async def test_assistente_estrategico_caso_grava_ailog(monkeypatch):
    from app.services import ai_gateway
    monkeypatch.setattr(ai_gateway, "chat", _fake_chat())

    caso = SimpleNamespace(
        id="case-1", titulo="Ação de Cobrança", numero_processo=None,
        area="civel", tese_principal="Inadimplemento", deleted_at=None,
        advogado_responsavel_id=None, advogado_auxiliar_id=None,
    )
    partes = [SimpleNamespace(nome="Fulano de Tal", case_id="case-1")]
    movs = [SimpleNamespace(descricao="Juntada de documento", case_id="case-1")]
    db = _FakeDB([caso, partes, movs])
    cu = User(id="user-1", role=UserRole.socio)

    r = await cases_router.assistente_estrategico_caso(
        "case-1", demanda="Qual a melhor estratégia?", db=db, cu=cu,
    )

    # Resposta ao cliente inalterada (shape do shim legado preservado).
    assert r["status"] == "sucesso"
    assert r["resposta"] == "RASCUNHO: análise estratégica."

    # AILog obrigatório gravado.
    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    log = logs[0]
    assert log.user_id == "user-1"
    assert log.case_id == "case-1"
    assert log.tipo_uso == AITipoUso.analise_caso
    assert log.resposta == "RASCUNHO: análise estratégica."
    assert log.modelo == "ollama/modelo-x"  # modelo REAL devolvido pelo shim
    assert db.commits >= 1


async def test_assistente_estrategico_caso_falha_nao_grava_ailog(monkeypatch):
    """Semântica de erro preservada: IA falha → status='falha', SEM raise e SEM
    poluir a auditoria com modelo falso/erro (igual aos já auditados)."""
    from app.services import ai_gateway

    async def chat_falha(messages, task_type="", **kw):
        raise RuntimeError("provider indisponível")

    monkeypatch.setattr(ai_gateway, "chat", chat_falha)

    caso = SimpleNamespace(
        id="case-2", titulo="T", numero_processo=None, area="civel",
        tese_principal=None, deleted_at=None,
        advogado_responsavel_id=None, advogado_auxiliar_id=None,
    )
    db = _FakeDB([caso, [], []])
    cu = User(id="u2", role=UserRole.socio)

    r = await cases_router.assistente_estrategico_caso(
        "case-2", demanda="d", db=db, cu=cu,
    )

    assert r["status"] == "falha"  # shim converte exceção — endpoint não levanta
    assert [o for o in db.added if isinstance(o, AILog)] == []


# ── clients.py :: ia_analise_cliente ──────────────────────────────────────────

async def test_ia_analise_cliente_grava_ailog(monkeypatch):
    from app.services import ai_gateway
    monkeypatch.setattr(ai_gateway, "chat", _fake_chat(texto="Perfil de risco moderado."))

    cliente = SimpleNamespace(
        id="cli-1", nome_exibicao="Empresa ACME", tipo="pj", deleted_at=None,
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
    assert log.tipo_uso == AITipoUso.analise_caso
    assert log.resposta == "Perfil de risco moderado."
    assert log.modelo == "ollama/modelo-x"
    assert db.commits >= 1
