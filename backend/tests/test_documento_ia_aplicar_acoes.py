"""POST /documentos-ia/aplicar-acoes — segurança (revisão 2026-07-14).

Cobre os dois achados HIGH da revisão: (1) responsavel_id só pode ser
atribuído a quem tem acesso legítimo ao MESMO caso; (2) intake_result
valida contra o schema Pydantic real (não aceita dict/tipo arbitrário).
"""
import pytest
from fastapi import HTTPException

from app.models.case import Case
from app.models.user import User, UserRole
from app.schemas.document_intake import DocumentoIntakeResult, PrazoExtraido


class _FakeDB:
    def __init__(self, user_lookup: dict):
        self._user_lookup = user_lookup
        self.added: list = []
        self.commits = 0

    async def get(self, model, id_):
        return self._user_lookup.get(id_)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _user(uid: str = "u1", role: UserRole = UserRole.advogado) -> User:
    return User(id=uid, role=role)


def _case(**kw) -> Case:
    base = dict(id="case1", titulo="Ação de Cobrança", client_id="cli1",
                area="civil", advogado_responsavel_id="u1", advogado_auxiliar_id=None)
    base.update(kw)
    return Case(**base)


async def _prep(monkeypatch, caso, user_lookup):
    from app.routers import documento_ia as mod

    async def _acesso_ok(db, cu, case_id):
        return caso

    async def _audit(*a, **k):
        return None

    monkeypatch.setattr(mod, "verificar_acesso_caso", _acesso_ok)
    monkeypatch.setattr(mod, "criar_audit_log", _audit)
    return mod, _FakeDB(user_lookup)


def _payload(mod, **kw):
    base = dict(
        case_id="case1",
        intake_result=DocumentoIntakeResult(prazos=[
            PrazoExtraido(tipo="contestação", termo_final="2026-08-01", fatal=True),
        ]),
        criar_prazos=True, criar_tarefas=False, criar_alerta=False,
    )
    base.update(kw)
    return mod.AplicarAcoesRequest(**base)


async def test_responsavel_id_estranho_ao_caso_e_rejeitado(monkeypatch):
    """Usuário sem vínculo com o caso (não é gestão, nem responsável/auxiliar)
    não pode ser alvo de prazo/tarefa criado por outro usuário."""
    caso = _case()
    intruso = _user(uid="u_estranho", role=UserRole.advogado)
    mod, db = await _prep(monkeypatch, caso, {"u_estranho": intruso})

    payload = _payload(mod, responsavel_id="u_estranho")
    with pytest.raises(HTTPException) as exc:
        await mod.aplicar_acoes(payload, db=db, current_user=_user())
    assert exc.value.status_code == 422
    assert db.added == []  # nada foi gravado antes da rejeição


async def test_responsavel_id_gestao_e_aceito(monkeypatch):
    """Sócio (gestão) pode ser alvo mesmo sem ser responsável/auxiliar do caso."""
    caso = _case()
    socio = _user(uid="u_socio", role=UserRole.socio)
    mod, db = await _prep(monkeypatch, caso, {"u_socio": socio})

    payload = _payload(mod, responsavel_id="u_socio")
    out = await mod.aplicar_acoes(payload, db=db, current_user=_user())
    assert out["ok"] is True
    assert len(out["prazos_criados"]) == 1
    assert db.added[0].responsavel_id == "u_socio"


async def test_responsavel_id_auxiliar_do_caso_e_aceito(monkeypatch):
    caso = _case(advogado_auxiliar_id="u_aux")
    aux = _user(uid="u_aux", role=UserRole.advogado)
    mod, db = await _prep(monkeypatch, caso, {"u_aux": aux})

    payload = _payload(mod, responsavel_id="u_aux")
    out = await mod.aplicar_acoes(payload, db=db, current_user=_user())
    assert out["ok"] is True


async def test_intake_result_rejeita_tipo_invalido():
    """DocumentoIntakeResult.prazos aceita só lista de PrazoExtraido — payload
    solto (dict arbitrário) não valida no schema em vez de virar texto cru
    em Deadline/Task."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DocumentoIntakeResult(prazos="não é uma lista")
