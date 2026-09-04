"""Score Jurídico por IA — POST /cases/{case_id}/score-juridico/calcular.

Regressão do bug em que o handler importava `ai_service.gerar_resposta_ia`
(função inexistente): o `except Exception` amplo engolia o ImportError e o
endpoint gravava as 7 dimensões ZERADAS a cada requisição — falha invisível.

Padrão test_provas_sugerir_faltantes.py (sem Postgres): handler chamado direto
com fake de sessão; `ai_gateway.chat` monkeypatched. Cobre: caminho real pelo
gateway (task_type + dados do caso no prompt), parsing e persistência das notas,
gate de role (piso equipe jurídica) e degradação graciosa (nunca 500).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Mappings:
    def __init__(self, rows):
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _Mappings(self._rows)


class _FakeDB:
    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.commits = 0
        self.added: list = []   # I9: o AILog do score entra por db.add

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, *a, **k):
        return _Result(self._resultados.pop(0))

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


_CASE_ROW = {
    "titulo": "Ação de Cobrança — Maria Silva",
    "area": "civil",
    "status": "ativo",
    "valor_causa": 15000,
    "docs": 4,
    "prazos": 2,
}

_JSON_IA = (
    '{"pedido":15,"causa_de_pedir":14,"fundamentacao":18,"provas":16,'
    '"jurisprudencia":12,"documentos_obrigatorios":9,"conformidade_formal":5,'
    '"detalhes":{"obs":"ok"},"recomendacoes":["Anexar laudo"]}'
)


def _gw_resp(texto: str) -> SimpleNamespace:
    return SimpleNamespace(texto=texto, modelo="claude-x", provedor="anthropic",
                           input_tokens=100, output_tokens=50)


async def _noop_acesso(db, cu, case_id):
    return None


async def _noop_audit(*a, **k):
    return None


# ── Rota montada ──────────────────────────────────────────────────────────────

def test_rota_calcular_score_montada_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/cases/{case_id}/score-juridico/calcular") for p in paths)


# ── Gate de role (piso equipe jurídica) ───────────────────────────────────────

@pytest.mark.parametrize("role", [UserRole.secretaria, UserRole.financeiro,
                                  UserRole.cliente_externo])
def test_req_adv_bloqueia_nao_juridico(role):
    from app.routers.score_juridico import _req_adv
    with pytest.raises(HTTPException) as exc:
        _req_adv(cu=_user(role))
    assert exc.value.status_code == 403


def test_req_adv_libera_equipe_juridica():
    from app.routers.score_juridico import _req_adv
    u = _user(UserRole.advogado)
    assert _req_adv(cu=u) is u


# ── Fluxo feliz: usa o gateway e persiste as notas reais ──────────────────────

async def test_calcular_usa_gateway_e_persiste_scores(monkeypatch):
    from app.routers import score_juridico as mod
    from app.services import ai_gateway

    chamado = {}

    async def _fake_chat(messages, **kw):
        chamado["task_type"] = kw.get("task_type")
        chamado["user"] = messages[1]["content"]
        return _gw_resp(_JSON_IA)

    monkeypatch.setattr(ai_gateway, "chat", _fake_chat)
    monkeypatch.setattr(mod, "verificar_acesso_caso", _noop_acesso)
    monkeypatch.setattr(mod, "criar_audit_log", _noop_audit)

    db = _FakeDB([[_CASE_ROW], [{"id": "score1"}]])
    out = await mod.calcular_score(case_id="case1", db=db, cu=_user(UserRole.advogado))

    # O gateway REAL foi acionado com o tipo de tarefa e os dados do caso.
    assert chamado["task_type"] == "analise_juridica"
    assert "Ação de Cobrança" in chamado["user"]
    assert "civil" in chamado["user"]
    # As notas da IA (não-zeradas) foram parseadas e persistidas.
    assert out["pedido"] == 15
    assert out["fundamentacao"] == 18
    assert out["total"] == 15 + 14 + 18 + 16 + 12 + 9 + 5  # 89
    assert out["id"] == "score1"
    # I9 (análise E2E 03/09): o score gravava sem AILog. Agora o AILog é
    # commitado (ai_guard) ANTES do INSERT do score → 2 commits, e o registro
    # carrega o caso, o modelo e o tipo de uso.
    from app.models.ai_log import AILog, AITipoUso
    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    assert logs[0].case_id == "case1"
    assert logs[0].tipo_uso == AITipoUso.analise_caso
    assert "[SCORE_JURIDICO]" in logs[0].prompt_sanitizado
    assert db.commits == 2
    # S8: vocabulário HITL canônico somado ao "aviso" legado.
    assert out["is_rascunho"] is True and out["aviso_hitl"] and out["status_hitl"] == "gerado"
    assert "aviso" in out


# ── Degradação graciosa: IA indisponível não vira 500 ─────────────────────────

async def test_calcular_ia_indisponivel_fallback_zerado_sem_500(monkeypatch):
    from app.routers import score_juridico as mod
    from app.services import ai_gateway

    async def _boom(messages, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ai_gateway, "chat", _boom)
    monkeypatch.setattr(mod, "verificar_acesso_caso", _noop_acesso)
    monkeypatch.setattr(mod, "criar_audit_log", _noop_audit)

    db = _FakeDB([[_CASE_ROW], [{"id": "score2"}]])
    out = await mod.calcular_score(case_id="case1", db=db, cu=_user(UserRole.advogado))

    assert out["total"] == 0
    assert "Score calculado manualmente" in out["recomendacoes"]
    assert db.commits == 1  # grava o registro (fallback), sem 500
    assert db.added == []   # sem resposta de IA não há AILog a gravar
    assert out["is_rascunho"] is True
