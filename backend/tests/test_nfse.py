"""Módulo NFS-e (emissão fiscal GATED) — sem rede real (httpx MockTransport),
sem banco (fakes no padrão test_infosimples).

Cobre: gate NFSE_ENABLED (503) e provedor inválido; credencial faltando (422);
token OAuth cacheado (uma auth p/ várias chamadas); montagem do DPS em
homologação (tpAmb=2, referencia, CNPJ, valores); erro do provedor tipado SEM
vazar client_secret/token; idempotência (não emite 2 pro mesmo fee); status;
consulta que atualiza a nota; e montagem das rotas em main.
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.client import Client
from app.models.fee import Fee
from app.models.nfse import NFSeStatus, NotaFiscalServico
from app.models.user import User, UserRole
from app.services import nfse as nfse_service
from app.services.nfse import (
    NFSeConfigError,
    NFSeDesabilitadaError,
    NFSePedidoEmissao,
    NFSeProviderError,
    NFSeTomador,
)
from app.services.nfse import nuvem_fiscal

CLIENT_SECRET = "cs-super-secreto-nao-vazar"
TOKEN = "tok-nfse-nao-vazar"


# ── Fixtures de configuração ────────────────────────────────────────────────────

@pytest.fixture()
def nfse_ligado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "NFSE_ENABLED", True)
    monkeypatch.setattr(s, "NFSE_MODO", "homologacao")
    monkeypatch.setattr(s, "NFSE_PROVEDOR", "nuvemfiscal")
    monkeypatch.setattr(s, "NFSE_NUVEMFISCAL_CLIENT_ID", "cli-id")
    monkeypatch.setattr(s, "NFSE_NUVEMFISCAL_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setattr(s, "NFSE_EMITENTE_CNPJ", "12.345.678/0001-99")
    monkeypatch.setattr(s, "NFSE_EMITENTE_MUN_IBGE", "3106200")
    monkeypatch.setattr(s, "NFSE_ISS_ALIQUOTA", 5.0)
    monkeypatch.setattr(s, "NFSE_CTRIB_NAC", "010701")
    nuvem_fiscal._token_cache.clear()
    return s


def _provider_com_handler(monkeypatch, handler):
    """NuvemFiscalProvider cujo cliente HTTP usa um MockTransport."""
    def _cli(timeout):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout)
    monkeypatch.setattr(nuvem_fiscal, "_novo_client", _cli)
    return nuvem_fiscal.NuvemFiscalProvider()


def _pedido(**kw) -> NFSePedidoEmissao:
    base = dict(
        referencia="fee-1",
        tomador=NFSeTomador(documento="529.982.247-25", nome="Fulano", uf="MG", cep="32600-000"),
        descricao="Honorários advocatícios",
        valor="1500.00",
    )
    base.update(kw)
    return NFSePedidoEmissao(**base)


def _socio() -> User:
    return User(id="u1", role=UserRole.socio)


# ── Gate: get_provider ──────────────────────────────────────────────────────────

def test_get_provider_desligado(monkeypatch):
    monkeypatch.setattr(get_settings(), "NFSE_ENABLED", False)
    with pytest.raises(NFSeDesabilitadaError):
        nfse_service.get_provider()


def test_get_provider_provedor_invalido(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "NFSE_ENABLED", True)
    monkeypatch.setattr(s, "NFSE_PROVEDOR", "outro")
    with pytest.raises(NFSeConfigError):
        nfse_service.get_provider()


def test_get_provider_nuvemfiscal(nfse_ligado):
    prov = nfse_service.get_provider()
    assert isinstance(prov, nuvem_fiscal.NuvemFiscalProvider)


# ── Credencial faltando → NFSeConfigError (router traduz p/ 422) ────────────────

async def test_emitir_sem_credencial_config_error(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "NFSE_ENABLED", True)
    monkeypatch.setattr(s, "NFSE_NUVEMFISCAL_CLIENT_ID", "")
    monkeypatch.setattr(s, "NFSE_NUVEMFISCAL_CLIENT_SECRET", "")
    monkeypatch.setattr(s, "NFSE_EMITENTE_CNPJ", "")
    prov = nuvem_fiscal.NuvemFiscalProvider()
    with pytest.raises(NFSeConfigError) as exc:
        await prov.emitir(_pedido())
    # Mensagem cita as chaves faltantes, sem segredo.
    assert "NFSE_NUVEMFISCAL_CLIENT_ID" in str(exc.value)
    assert CLIENT_SECRET not in str(exc.value)


# ── Token OAuth cacheado: uma auth para várias chamadas ─────────────────────────

async def test_token_oauth_cacheado(nfse_ligado, monkeypatch):
    auth_calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            auth_calls.append(1)
            corpo = dict(httpx.QueryParams(request.content.decode()))
            assert corpo["grant_type"] == "client_credentials"
            assert corpo["client_secret"] == CLIENT_SECRET  # só no corpo do token
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 3600})
        if request.url.path == "/nfse/dps":
            assert request.headers["authorization"] == f"Bearer {TOKEN}"
            return httpx.Response(200, json={"id": "nf_1", "status": "processando"})
        if request.url.path == "/nfse/nf_1":
            return httpx.Response(200, json={"id": "nf_1", "status": "autorizada", "numero": "42"})
        return httpx.Response(404)

    prov = _provider_com_handler(monkeypatch, handler)
    await prov.emitir(_pedido())
    await prov.consultar("nf_1")
    assert len(auth_calls) == 1  # token reaproveitado do cache de módulo


# ── Montagem do DPS em homologação ──────────────────────────────────────────────

async def test_emitir_monta_dps_homologacao(nfse_ligado, monkeypatch):
    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 3600})
        if request.url.path == "/nfse/dps":
            capturado.update(json.loads(request.content))
            return httpx.Response(200, json={"id": "nf_9", "status": "processando", "ambiente": "homologacao"})
        return httpx.Response(404)

    prov = _provider_com_handler(monkeypatch, handler)
    res = await prov.emitir(_pedido(referencia="fee-9"))

    assert res.status == "processando" and res.provider_id == "nf_9"
    assert capturado["ambiente"] == "homologacao"
    assert capturado["referencia"] == "fee-9"
    inf = capturado["infDPS"]
    assert inf["tpAmb"] == 2                              # homologação
    assert inf["prest"]["CNPJ"] == "12345678000199"      # só dígitos
    assert inf["toma"]["CPF"] == "52998224725"
    assert inf["serv"]["cServ"]["cTribNac"] == "010701"
    assert inf["serv"]["cServ"]["cItemListaServico"] == "17.14"
    assert inf["valores"]["vServPrest"]["vServ"] == 1500.0
    assert inf["valores"]["trib"]["tribMun"]["pAliq"] == 5.0


async def test_emitir_producao_tpamb_1(nfse_ligado, monkeypatch):
    monkeypatch.setattr(get_settings(), "NFSE_MODO", "producao")
    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 3600})
        capturado.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "nf_p", "status": "processando"})

    prov = _provider_com_handler(monkeypatch, handler)
    await prov.emitir(_pedido())
    assert capturado["ambiente"] == "producao"
    assert capturado["infDPS"]["tpAmb"] == 1


# ── Erro do provedor: tipado, sem vazar segredo ─────────────────────────────────

async def test_emitir_erro_provedor_sem_vazar_token(nfse_ligado, monkeypatch, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 3600})
        return httpx.Response(422, json={"error": {"code": "cnpj_invalido", "message": "CNPJ do tomador inválido"}})

    prov = _provider_com_handler(monkeypatch, handler)
    with pytest.raises(NFSeProviderError) as exc:
        await prov.emitir(_pedido())
    assert exc.value.code == "cnpj_invalido"
    assert "CNPJ do tomador inválido" in str(exc.value)
    assert CLIENT_SECRET not in str(exc.value)
    assert TOKEN not in str(exc.value)
    assert CLIENT_SECRET not in caplog.text


async def test_auth_falha_nao_vaza_segredo(nfse_ligado, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        # Auth 401 — a resposta poderia ecoar dados; a mensagem não pode vazar.
        return httpx.Response(401, json={"error": "invalid_client", "secret_echo": CLIENT_SECRET})

    prov = _provider_com_handler(monkeypatch, handler)
    with pytest.raises(NFSeProviderError) as exc:
        await prov.emitir(_pedido())
    assert CLIENT_SECRET not in str(exc.value)


# ── Status ──────────────────────────────────────────────────────────────────────

def test_status_atual(nfse_ligado):
    st = nfse_service.status_atual()
    assert st == {"enabled": True, "configured": True,
                  "ambiente": "homologacao", "provedor": "nuvemfiscal"}
    assert CLIENT_SECRET not in str(st)


def test_status_desligado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "NFSE_ENABLED", False)
    monkeypatch.setattr(s, "NFSE_NUVEMFISCAL_CLIENT_ID", "")
    monkeypatch.setattr(s, "NFSE_NUVEMFISCAL_CLIENT_SECRET", "")
    monkeypatch.setattr(s, "NFSE_EMITENTE_CNPJ", "")
    st = nfse_service.status_atual()
    assert st["enabled"] is False and st["configured"] is False


# ── Consulta que mapeia status ──────────────────────────────────────────────────

async def test_consultar_mapeia_autorizada(nfse_ligado, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 3600})
        return httpx.Response(200, json={"id": "nf_1", "status": "registrada", "numero": "77",
                                         "chave_acesso": "CHV", "ambiente": "homologacao"})

    prov = _provider_com_handler(monkeypatch, handler)
    res = await prov.consultar("nf_1")
    assert res.status == "autorizada"      # "registrada" → autorizada
    assert res.numero == "77" and res.chave_acesso == "CHV"


# ══ Camada de rotas (fakes de DB, sem rede) ═════════════════════════════════════

class _FakeDB:
    def __init__(self, objs=None, scalar_result=None):
        self.objs = objs or {}          # (ModelName, id) -> obj
        self.scalar_result = scalar_result
        self.added: list = []
        self.commits = 0

    async def get(self, model, ident):
        return self.objs.get((model.__name__, ident))

    async def scalar(self, stmt):
        return self.scalar_result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


class _FakeProvider:
    def __init__(self, resultado):
        self._r = resultado
        self.emitido: list = []

    async def emitir(self, pedido):
        self.emitido.append(pedido)
        return self._r

    async def consultar(self, pid):
        return self._r

    async def baixar_pdf(self, pid):
        return b"%PDF-1.4 fake"

    async def cancelar(self, pid, motivo):
        return self._r


def _fee():
    return Fee(id="f1", descricao="Honorários", valor=1500, client_id="c1",
               deleted_at=None)


def _cliente():
    return Client(id="c1", nome="Fulano da Silva", cpf="52998224725",
                  estado="MG", cep="32600-000")


def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/nfse/status") for p in paths)
    assert any(p.endswith("/nfse/emitir") for p in paths)
    assert any(p.endswith("/nfse/{nota_id}") for p in paths)
    assert any(p.endswith("/nfse/{nota_id}/pdf") for p in paths)
    assert any(p.endswith("/nfse/{nota_id}/cancelar") for p in paths)


async def test_endpoint_emitir_503_desligado(monkeypatch):
    from app.routers.nfse import EmitirIn, emitir_nfse

    monkeypatch.setattr(get_settings(), "NFSE_ENABLED", False)
    body = EmitirIn(fee_id="f1")
    with pytest.raises(HTTPException) as exc:
        await emitir_nfse(body, db=_FakeDB(), cu=_socio())
    assert exc.value.status_code == 503


async def test_endpoint_emitir_idempotente_409(nfse_ligado, monkeypatch):
    from app.routers.nfse import EmitirIn, emitir_nfse

    existente = NotaFiscalServico(id="nf_old", referencia="fee-f1",
                                  status=NFSeStatus.autorizada.value)
    db = _FakeDB(objs={("Fee", "f1"): _fee()}, scalar_result=existente)
    body = EmitirIn(fee_id="f1")
    with pytest.raises(HTTPException) as exc:
        await emitir_nfse(body, db=db, cu=_socio())
    assert exc.value.status_code == 409
    # Não chegou a persistir nova nota.
    assert not any(isinstance(o, NotaFiscalServico) for o in db.added)


async def test_endpoint_emitir_sucesso_persiste_e_audita(nfse_ligado, monkeypatch):
    from app.routers import nfse as router_mod
    from app.services.nfse import NFSeResultado

    resultado = NFSeResultado(status="processando", provider_id="nf_new",
                              ambiente="homologacao", numero=None)
    fake = _FakeProvider(resultado)
    monkeypatch.setattr("app.services.nfse.get_provider", lambda: fake)

    db = _FakeDB(objs={("Fee", "f1"): _fee(), ("Client", "c1"): _cliente()},
                 scalar_result=None)
    body = router_mod.EmitirIn(fee_id="f1")
    resp = await router_mod.emitir_nfse(body, db=db, cu=_socio())

    assert resp["status"] == "processando" and resp["provider_id"] == "nf_new"
    assert resp["referencia"] == "fee-f1"
    # Nota persistida + audit ANTES (NFSE_EMITIR) e DEPOIS (NFSE_EMITIDA).
    notas = [o for o in db.added if isinstance(o, NotaFiscalServico)]
    assert len(notas) == 1 and notas[0].fee_id == "f1"
    acoes = sorted(o.acao for o in db.added if o.__class__.__name__ == "AuditLog")
    assert acoes == ["NFSE_EMITIDA", "NFSE_EMITIR"]
    assert db.commits >= 2
    # Pedido montado com a referência do honorário e valor do fee.
    assert fake.emitido[0].referencia == "fee-f1"
    assert str(fake.emitido[0].valor) == "1500"


async def test_endpoint_emitir_avulso_exige_tomador():
    from app.routers.nfse import EmitirIn

    with pytest.raises(ValidationError):
        EmitirIn()  # sem fee_id e sem dados avulsos
    ok = EmitirIn(tomador={"documento": "52998224725", "nome": "X"},
                  valor="100.00", descricao="Serviço")
    assert ok.fee_id is None


async def test_endpoint_status_advogado(nfse_ligado):
    from app.routers.nfse import status_nfse
    from app.models.user import User, UserRole

    resp = await status_nfse(cu=User(id="a1", role=UserRole.advogado))
    assert resp["enabled"] is True and resp["ambiente"] == "homologacao"
    assert CLIENT_SECRET not in str(resp)


# ── Reserva atômica (fix TOCTOU) ────────────────────────────────────────────────

class _FakeProviderErro:
    """Provedor que estoura na emissão (simula falha externa)."""
    def __init__(self, exc):
        self._exc = exc

    async def emitir(self, pedido):
        raise self._exc


class _FakeDBIntegrity(_FakeDB):
    """FakeDB cujo 1º commit estoura IntegrityError (corrida na reserva)."""
    async def commit(self):
        from sqlalchemy.exc import IntegrityError
        self.commits += 1
        if self.commits == 1:
            raise IntegrityError("INSERT", {}, Exception("uq viol"))

    async def rollback(self):
        self.rolledback = True


async def test_endpoint_emitir_reaproveita_nota_terminal(nfse_ligado, monkeypatch):
    """Nota anterior rejeitada/cancelada → reaproveita a linha, não cria outra."""
    from app.routers import nfse as router_mod
    from app.services.nfse import NFSeResultado

    resultado = NFSeResultado(status="processando", provider_id="nf_re",
                              ambiente="homologacao", numero=None)
    monkeypatch.setattr("app.services.nfse.get_provider",
                        lambda: _FakeProvider(resultado))
    terminal = NotaFiscalServico(id="nf_x", referencia="fee-f1",
                                 status=NFSeStatus.rejeitada.value)
    db = _FakeDB(objs={("Fee", "f1"): _fee(), ("Client", "c1"): _cliente()},
                 scalar_result=terminal)
    resp = await router_mod.emitir_nfse(router_mod.EmitirIn(fee_id="f1"),
                                        db=db, cu=_socio())
    assert resp["id"] == "nf_x" and resp["status"] == "processando"
    # Reaproveita a linha existente — nenhuma NotaFiscalServico nova adicionada.
    assert not any(isinstance(o, NotaFiscalServico) for o in db.added)


async def test_endpoint_emitir_falha_provedor_marca_rejeitada(nfse_ligado, monkeypatch):
    """Falha do provedor → nota fica `rejeitada` (não presa em processando)."""
    from app.routers import nfse as router_mod

    prov = _FakeProviderErro(NFSeProviderError(502, "provedor fora do ar"))
    monkeypatch.setattr("app.services.nfse.get_provider", lambda: prov)
    db = _FakeDB(objs={("Fee", "f1"): _fee(), ("Client", "c1"): _cliente()},
                 scalar_result=None)
    with pytest.raises(HTTPException) as exc:
        await router_mod.emitir_nfse(router_mod.EmitirIn(fee_id="f1"),
                                     db=db, cu=_socio())
    assert exc.value.status_code == 502
    nota = next(o for o in db.added if isinstance(o, NotaFiscalServico))
    assert nota.status == NFSeStatus.rejeitada.value
    # Reserva (commit 1) + persistência da falha (commit 2).
    assert db.commits >= 2
    acoes = {o.acao for o in db.added if o.__class__.__name__ == "AuditLog"}
    assert "NFSE_EMISSAO_FALHOU" in acoes


async def test_endpoint_emitir_corrida_integrityerror_409(nfse_ligado, monkeypatch):
    """Duplo-clique: 2ª reserva colide no UNIQUE → 409 sem emitir de novo."""
    from app.routers import nfse as router_mod
    from app.services.nfse import NFSeResultado

    chamou = {"emitir": False}

    class _Prov:
        async def emitir(self, pedido):
            chamou["emitir"] = True
            return NFSeResultado(status="processando", provider_id="x")

    monkeypatch.setattr("app.services.nfse.get_provider", lambda: _Prov())
    db = _FakeDBIntegrity(objs={("Fee", "f1"): _fee(), ("Client", "c1"): _cliente()},
                          scalar_result=None)
    with pytest.raises(HTTPException) as exc:
        await router_mod.emitir_nfse(router_mod.EmitirIn(fee_id="f1"),
                                     db=db, cu=_socio())
    assert exc.value.status_code == 409
    # A colisão barra ANTES de tocar o provedor — sem emissão dupla real.
    assert chamou["emitir"] is False
