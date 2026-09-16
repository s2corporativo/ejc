# ── tests/test_ai_log_caminho_legado.py ──────────────────────────────────────
# Compliance #4a — "AILog obrigatório".
#
# O endpoint clients.py::ia_analise_cliente migrou do caminho legado
# (ai_gateway.processar_demanda + registrar_ai_log manual) para o
# SingleAICoreOrchestrator, que é o responsável canônico por sanitização,
# provider policy, validação, HITL e persistência de AILog.
#
# Este arquivo preserva duas garantias distintas:
#   - Cliente IA usa o orquestrador institucional e propaga seu log_id/HITL;
#   - intelligence.py::analise_impacto continua cobrindo o caminho legado vivo.
#
# Padrão: handlers chamados diretamente com fake de sessão; nenhuma rede real.
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

async def test_ia_analise_cliente_usa_orquestrador_e_preserva_ailog_hitl(monkeypatch):
    from app.services.ai.core.orchestrator import orchestrator

    chamada = {}

    async def run_fake(**kwargs):
        chamada.update(kwargs)
        return {
            "conteudo": "Perfil de risco moderado.",
            "modelo": "ollama/modelo-x",
            "requer_revisao": True,
            "is_rascunho": True,
            "status_hitl": "gerado",
            "aviso_hitl": "Rascunho sujeito à revisão humana.",
            "sem_base_verificavel": False,
            "alertas": [],
            "citacoes": [],
            "log_id": "ailog-123",
        }

    monkeypatch.setattr(orchestrator, "run", run_fake)

    # responsavel_id == caller: satisfaz o gate de titularidade (sigilo interno)
    # sem consulta extra. Os agregados têm os campos efetivamente lidos pela rota.
    cliente = SimpleNamespace(
        id="cli-1", nome_exibicao="Empresa ACME", tipo="PJ", deleted_at=None,
        responsavel_id="user-9",
    )
    casos = [SimpleNamespace(
        id="c1", client_id="cli-1", area="civil", status="aberto",
    )]
    fees = [SimpleNamespace(
        id="f1", client_id="cli-1", valor=100.0, status="pago",
    )]
    db = _FakeDB([cliente, casos, fees])
    cu = User(id="user-9", role=UserRole.advogado)

    r = await clients_router.ia_analise_cliente("cli-1", db=db, cu=cu)

    assert r["status"] == "sucesso"
    assert r["resposta"] == "Perfil de risco moderado."
    assert r["modelo_utilizado"] == "ollama/modelo-x"
    assert r["revisao_obrigatoria"] is True
    assert r["is_rascunho"] is True
    assert r["status_hitl"] == "gerado"
    assert r["log_id"] == "ailog-123"

    # O endpoint não mantém mais um segundo logger paralelo: a trilha é do core.
    assert [o for o in db.added if isinstance(o, AILog)] == []
    assert chamada["db"] is db
    assert chamada["user"] is cu
    assert chamada["task_type"] == "resumo"
    assert chamada["domain"] == "clientes"
    assert chamada["usar_rag"] is False
    assert chamada["params"]["module_key"] == "clientes"
    assert chamada["params"]["surface"] == "cliente_ia"
    assert "Empresa ACME" not in chamada["mensagem"]
    assert "Total de casos não excluídos: 1" in chamada["mensagem"]
    assert "[INDICADORES AGREGADOS DO CLIENTE]" in chamada["mensagem"]


def test_categoria_ailog_cliente_nao_contamina_resumo_documental():
    """O perfil sem RAG continua sendo RESUMO, mas a telemetria da superfície
    Cliente IA preserva a categoria histórica `outro`. Resumo documental comum
    continua em `resumo_documento`."""
    from app.services.ai.core.audit_logger import _tipo_uso
    from app.services.system_prompts import TarefaIA

    prompt_cliente = (
        "Analise exclusivamente os indicadores agregados fornecidos.\n"
        "[INDICADORES AGREGADOS DO CLIENTE]\nTotal de casos não excluídos: 2"
    )
    assert _tipo_uso(TarefaIA.RESUMO, prompt_cliente) == AITipoUso.outro
    assert _tipo_uso(TarefaIA.RESUMO, "Resuma o documento anexado.") == AITipoUso.resumo_documento


# ── intelligence.py (legado vivo) :: analise_impacto ──────────────────────────
# Endpoint que chama o gateway canônico diretamente (shim core.ai_brain
# aposentado — auditoria Fase 7) e grava tipo_uso=outro sanitizando o prompt
# no próprio endpoint.

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
    assert log.modelo == "ollama/modelo-x"  # modelo REAL do GatewayResponse
    assert db.commits >= 1


async def test_analise_impacto_falha_nao_grava_ailog(monkeypatch):
    """IA falha → endpoint retorna {'resumo_executivo': _ERRO_SEGURO} sem levantar
    e SEM gravar AILog (semântica de erro preservada)."""
    from app.services import ai_gateway
    from app.routers import intelligence as intel_router
    from app.routers.intelligence import _ERRO_SEGURO_IA

    async def chat_falha(messages, task_type="", **kw):
        raise RuntimeError("provider indisponível")

    monkeypatch.setattr(ai_gateway, "chat", chat_falha)

    db = _FakeDB([])
    cu = User(id="u7", role=UserRole.socio)

    r = await intel_router.analise_impacto({"texto": "qualquer fato"}, db=db, cu=cu)

    assert r == {"resumo_executivo": _ERRO_SEGURO_IA}  # erro seguro, não propaga
    assert [o for o in db.added if isinstance(o, AILog)] == []