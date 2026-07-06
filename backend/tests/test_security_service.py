"""Segurança operacional (Fase 5): resolução de IP e anti-brute-force."""
from app.services.security_service import (
    obter_ip_real,
    registrar_falha,
    esta_bloqueado,
    limpar_falhas,
    MAX_FALHAS,
)


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeReq:
    def __init__(self, headers=None, client_host=None):
        self.headers = headers or {}
        self.client = _FakeClient(client_host) if client_host else None


def test_ip_do_x_forwarded_for():
    # #9 (SEC-02): usa o ÚLTIMO salto do XFF (o posto pelo nosso Nginx), NÃO o
    # primeiro — o primeiro é controlado pelo cliente e era spoofável. Aqui
    # "203.0.113.5" é o valor forjado pelo cliente e "10.0.0.1" o real (Nginx).
    req = _FakeReq(headers={"x-forwarded-for": "203.0.113.5, 10.0.0.1"})
    assert obter_ip_real(req) == "10.0.0.1"


def test_ip_do_x_real_ip():
    req = _FakeReq(headers={"x-real-ip": "198.51.100.7"})
    assert obter_ip_real(req) == "198.51.100.7"


def test_ip_do_client_host():
    assert obter_ip_real(_FakeReq(client_host="192.168.1.1")) == "192.168.1.1"


def test_ip_fallback_zero():
    assert obter_ip_real(_FakeReq()) == "0.0.0.0"


def test_brute_force_bloqueia_apos_max_falhas():
    k = "test-bf-key-unica"
    limpar_falhas(k)
    assert esta_bloqueado(k) == (False, 0)
    for _ in range(MAX_FALHAS):
        registrar_falha(k)
    bloqueado, restante = esta_bloqueado(k)
    assert bloqueado is True
    assert restante > 0
    limpar_falhas(k)
    assert esta_bloqueado(k) == (False, 0)
