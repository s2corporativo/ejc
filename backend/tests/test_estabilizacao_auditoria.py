"""Auditoria de estabilização — cobre os endurecimentos desta rodada.

Sem banco real (mesmo padrão de fake-DB de test_ownership.py):

1. Data Room — `_usuario_ve_documento` reaplica o gate do GED (cofre +
   ownership do caso) ao listar/vincular documentos, fechando o vazamento de
   metadados de docs de casos alheios.
2. Config — o validador de produção recusa CORS_ORIGINS="*" (perigoso com
   allow_credentials=True), sem afetar desenvolvimento.
"""
import pytest
from cryptography.fernet import Fernet

from app.models.user import User, UserRole
from app.models.case import Case
from app.routers.data_room import _usuario_ve_documento


# ── Fakes (espelham test_ownership.py) ────────────────────────────────────────
class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDB:
    """execute() sempre devolve o mesmo Case (o único SELECT do gate de caso)."""
    def __init__(self, case):
        self._case = case

    async def execute(self, *a, **k):
        return _Res(self._case)


class _Doc:
    def __init__(self, conf: str, case_id):
        self.confidencialidade = type("C", (), {"value": conf})()
        self.case_id = case_id


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


# ── 1. Data Room — gate de acesso a documento ─────────────────────────────────
async def test_dataroom_doc_confidencial_bloqueia_nao_socio():
    """Cofre: doc restrito/confidencial exige socio+ — advogado comum não vê."""
    doc = _Doc("confidencial", None)
    assert await _usuario_ve_documento(_FakeDB(None), _user(UserRole.advogado), doc) is False


async def test_dataroom_doc_confidencial_socio_ve():
    doc = _Doc("confidencial", None)
    assert await _usuario_ve_documento(_FakeDB(None), _user(UserRole.socio), doc) is True


async def test_dataroom_doc_normal_sem_caso_ve():
    """Doc normal sem case_id: só o gate de cofre se aplica (passa)."""
    doc = _Doc("normal", None)
    assert await _usuario_ve_documento(_FakeDB(None), _user(UserRole.advogado), doc) is True


async def test_dataroom_doc_de_caso_alheio_bloqueia():
    """Doc normal de um caso que o advogado NÃO é dono → não vê (anti-IDOR)."""
    caso = Case(id="c1", advogado_responsavel_id="x", advogado_auxiliar_id="y")
    doc = _Doc("normal", "c1")
    assert await _usuario_ve_documento(_FakeDB(caso), _user(UserRole.advogado, "u1"), doc) is False


async def test_dataroom_doc_de_caso_proprio_ve():
    caso = Case(id="c1", advogado_responsavel_id="u1", advogado_auxiliar_id=None)
    doc = _Doc("normal", "c1")
    assert await _usuario_ve_documento(_FakeDB(caso), _user(UserRole.advogado, "u1"), doc) is True


# ── 2. Config — CORS wildcard barrado em produção ─────────────────────────────
def _prod_kwargs(**over):
    base = dict(
        APP_ENV="production",
        SECRET_KEY="s" * 64,
        PII_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        PII_HASH_KEY="h" * 32,
        FRONTEND_URL="https://app.exemplo.adv.br",
        CORS_ORIGINS="https://app.exemplo.adv.br",
    )
    base.update(over)
    return base


def test_producao_recusa_cors_wildcard():
    from app.core.config import Settings
    with pytest.raises(ValueError, match="CORS"):
        Settings(**_prod_kwargs(CORS_ORIGINS="*"))


def test_producao_aceita_origem_explicita():
    from app.core.config import Settings
    s = Settings(**_prod_kwargs())
    assert "*" not in s.cors_origins_list


def test_desenvolvimento_permite_wildcard():
    """Fora de produção o guard não se aplica (não levanta)."""
    from app.core.config import Settings
    s = Settings(APP_ENV="development", CORS_ORIGINS="*")
    assert s.cors_origins_list == ["*"]
