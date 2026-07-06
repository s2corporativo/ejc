"""Item 1.1 — auditoria: usuário/módulo/IP preenchidos em TODOS os eventos.

O bug do log de auditoria tinha duas causas:
  A) frontend lia chaves erradas (coberto por teste de frontend/typecheck);
  B) só o LOGIN gravava IP — os demais writers passavam ip=None e gravavam NULL.

Aqui cobrimos a causa (B): criar_audit_log agora usa, como fallback, o IP real
capturado por requisição pelo ClientIPMiddleware (ContextVar). Sem banco real:
um fake-DB captura o objeto AuditLog adicionado.
"""
from app.models.audit_log import criar_audit_log
from app.core.request_context import (
    set_client_ip,
    get_client_ip,
    _extrai_ip,
    _client_ip,
)


class _FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


# ── ContextVar / fallback de IP ───────────────────────────────────────────────
async def test_criar_audit_log_usa_ip_do_contexto_quando_omitido():
    """Writer que não passa ip= herda o IP da requisição (ContextVar)."""
    token = _client_ip.set("203.0.113.9")
    try:
        db = _FakeDB()
        await criar_audit_log(
            db, user_id="u1", user_role="advogado",
            acao="UPLOAD", entidade="documents", registro_id="d1",
        )
        assert db.added[0].ip == "203.0.113.9"
        assert db.added[0].user_id == "u1"
        assert db.added[0].entidade == "documents"
    finally:
        _client_ip.reset(token)


async def test_ip_explicito_tem_precedencia_sobre_contexto():
    """Se o chamador passa ip= (caso do LOGIN), esse valor prevalece."""
    token = _client_ip.set("10.0.0.1")
    try:
        db = _FakeDB()
        await criar_audit_log(
            db, user_id="u1", user_role="socio",
            acao="LOGIN", entidade="auth", ip="198.51.100.7",
        )
        assert db.added[0].ip == "198.51.100.7"
    finally:
        _client_ip.reset(token)


async def test_sem_contexto_ip_fica_none():
    """Fora de uma requisição HTTP (ex.: job do scheduler) não há IP — NULL."""
    set_client_ip(None)
    db = _FakeDB()
    await criar_audit_log(db, user_id=None, user_role=None, acao="CREATE", entidade="cases")
    assert db.added[0].ip is None


# ── Extração de IP do scope ASGI (respeita proxy reverso) ─────────────────────
def _scope(headers, client=("127.0.0.1", 5000)):
    return {"type": "http", "headers": headers, "client": client}


def test_extrai_ip_prioriza_x_forwarded_for():
    # #9 (SEC-02): usa o ÚLTIMO salto do XFF (posto pelo nosso Nginx), não o
    # primeiro — o primeiro é controlado pelo cliente e era spoofável.
    scope = _scope([(b"x-forwarded-for", b"172.16.0.5, 10.0.0.1")])
    assert _extrai_ip(scope) == "10.0.0.1"


def test_extrai_ip_usa_x_real_ip_quando_sem_xff():
    scope = _scope([(b"x-real-ip", b"192.0.2.44")])
    assert _extrai_ip(scope) == "192.0.2.44"


def test_extrai_ip_cai_no_client_do_socket():
    scope = _scope([], client=("192.0.2.88", 443))
    assert _extrai_ip(scope) == "192.0.2.88"


def test_get_client_ip_default_none():
    set_client_ip(None)
    assert get_client_ip() is None
