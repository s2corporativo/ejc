"""Gestão societária de CLIENTES (vertical Empresarial) — /empresarial/sociedades.

Sem Postgres real (padrão test_ownership.py): handlers chamados diretamente com
fake de sessão + lógica pura de services/sociedades_service. Cobre: criação,
percentual calculado, alerta de quotas divergentes, visibilidade (advogado sem
acesso ao cliente → 404), evento automático na saída de sócio e mascaramento
LGPD do documento do sócio (NUNCA texto puro em resposta/persistência).
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.client import Client
from app.models.sociedade_cliente import (
    EventoSocietario, SociedadeCliente, SocioSociedade,
)
from app.models.user import User, UserRole
from app.schemas.sociedade_cliente import SociedadeCreate, SocioCreate
from app.services.sociedades_service import (
    calcular_percentual, mascarar_documento, montar_cap_table,
    preparar_documento_socio,
)


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalar(self):
        return self._val

    def first(self):
        # client_ownership.pode_ver_cliente usa .first() (#1348)
        return self._val


class _FakeDB:
    """Sessão fake: fila de resultados para execute(); registra add/delete."""

    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.added: list = []
        self.deleted: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


def _sociedade(**kw) -> SociedadeCliente:
    base = dict(id="soc1", client_id="cli1", razao_social="ACME Ltda",
                tipo_societario="LTDA", capital_social=Decimal("100000"),
                deleted_at=None)
    base.update(kw)
    return SociedadeCliente(**base)


def _cliente(responsavel_id="dono") -> Client:
    return Client(id="cli1", nome="Cliente PJ", responsavel_id=responsavel_id)


# ── Rotas montadas ────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/empresarial/sociedades") for p in paths)
    assert any(p.endswith("/empresarial/sociedades/{sociedade_id}") for p in paths)
    assert any(p.endswith("/empresarial/sociedades/{sociedade_id}/socios") for p in paths)
    assert any(p.endswith("/empresarial/sociedades/{sociedade_id}/eventos") for p in paths)


# ── Criação ───────────────────────────────────────────────────────────────────

async def test_criacao_sociedade():
    from app.models.audit_log import AuditLog
    from app.routers.sociedades_cliente import criar

    db = _FakeDB([_cliente()])  # gestão: só a query do cliente
    out = await criar(
        payload=SociedadeCreate(client_id="cli1", razao_social="ACME Ltda",
                                tipo_societario="LTDA",
                                capital_social=Decimal("100000")),
        db=db, cu=_user(UserRole.socio),
    )
    assert out["razao_social"] == "ACME Ltda"
    assert out["tipo_societario"] == "LTDA"
    assert out["capital_social"] == 100000.0
    socs = [o for o in db.added if isinstance(o, SociedadeCliente)]
    assert len(socs) == 1 and socs[0].client_id == "cli1"
    # Audit log obrigatório na escrita.
    assert any(isinstance(o, AuditLog) and o.entidade == "sociedades_cliente"
               for o in db.added)
    assert db.commits == 1


async def test_criacao_para_cliente_fora_do_escopo_404():
    from app.routers.sociedades_cliente import criar

    # advogado u1 não é responsável pelo cliente e não atua em caso dele (None).
    db = _FakeDB([_cliente(responsavel_id="outro"), None])
    with pytest.raises(HTTPException) as exc:
        await criar(
            payload=SociedadeCreate(client_id="cli1", razao_social="ACME Ltda",
                                    tipo_societario="LTDA"),
            db=db, cu=_user(UserRole.advogado),
        )
    assert exc.value.status_code == 404
    assert db.added == []


# ── Cap table: percentual e alerta ────────────────────────────────────────────

def test_percentual_calculado():
    assert calcular_percentual(Decimal("250"), Decimal("1000")) == 25.0
    assert calcular_percentual(Decimal("1"), Decimal("3")) == 33.33
    assert calcular_percentual(Decimal("10"), 0) == 0.0  # sem quotas declaradas


def test_cap_table_sem_divergencia():
    ct = montar_cap_table(Decimal("100000"), [Decimal("60000"), Decimal("40000")])
    assert ct["total_quotas"] == 100000.0
    assert ct["capital_social"] == 100000.0
    assert ct["alerta_percentual"] is None


def test_cap_table_alerta_quotas_divergentes():
    # Quotas declaradas (60k) ≠ capital social (100k) → quadro incompleto ou
    # valores divergentes do contrato: o alerta explica que os percentuais
    # são calculados sobre as quotas declaradas.
    ct = montar_cap_table(Decimal("100000"), [Decimal("30000"), Decimal("30000")])
    assert ct["total_quotas"] == 60000.0
    assert ct["alerta_percentual"] is not None
    assert "capital social" in ct["alerta_percentual"]


def test_cap_table_sem_capital_nao_alerta():
    ct = montar_cap_table(None, [Decimal("10"), Decimal("90")])
    assert ct["capital_social"] is None
    assert ct["alerta_percentual"] is None


# ── Visibilidade (padrão do cliente) ──────────────────────────────────────────

async def test_advogado_sem_acesso_ao_cliente_404():
    from app.routers.sociedades_cliente import _carregar_sociedade

    # sociedade existe, cliente de outro responsável, nenhum caso do advogado.
    db = _FakeDB([_sociedade(), _cliente(responsavel_id="outro"), None])
    with pytest.raises(HTTPException) as exc:
        await _carregar_sociedade(db, _user(UserRole.advogado), "soc1")
    assert exc.value.status_code == 404


async def test_advogado_responsavel_pelo_cliente_passa():
    from app.routers.sociedades_cliente import _carregar_sociedade

    db = _FakeDB([_sociedade(), _cliente(responsavel_id="u1")])
    soc = await _carregar_sociedade(db, _user(UserRole.advogado, "u1"), "soc1")
    assert soc.id == "soc1"


async def test_advogado_com_caso_do_cliente_passa():
    from app.routers.sociedades_cliente import _carregar_sociedade

    # não é responsável pelo cliente, mas atua em caso dele (query devolve id).
    db = _FakeDB([_sociedade(), _cliente(responsavel_id="outro"), "case1"])
    soc = await _carregar_sociedade(db, _user(UserRole.advogado, "u1"), "soc1")
    assert soc.id == "soc1"


async def test_gestao_ve_tudo():
    from app.routers.sociedades_cliente import _carregar_sociedade

    db = _FakeDB([_sociedade(), _cliente(responsavel_id="outro")])
    soc = await _carregar_sociedade(db, _user(UserRole.socio), "soc1")
    assert soc.id == "soc1"


async def test_sociedade_inexistente_404():
    from app.routers.sociedades_cliente import _carregar_sociedade

    db = _FakeDB([None])
    with pytest.raises(HTTPException) as exc:
        await _carregar_sociedade(db, _user(UserRole.socio), "nao-existe")
    assert exc.value.status_code == 404


# ── Evento automático na saída de sócio ───────────────────────────────────────

async def test_saida_de_socio_registra_evento_automatico():
    from app.routers.sociedades_cliente import remover_socio

    socio = SocioSociedade(id="s1", sociedade_id="soc1", nome="Fulano",
                           quotas=Decimal("100"))
    # rota flat /socios/{socio_id}: [sócio, sociedade, cliente] (gestão)
    db = _FakeDB([socio, _sociedade(), _cliente()])
    out = await remover_socio(socio_id="s1", db=db, cu=_user(UserRole.socio))
    assert "saida_socio" in out.detail

    assert db.deleted == [socio]
    eventos = [o for o in db.added if isinstance(o, EventoSocietario)]
    assert len(eventos) == 1
    assert eventos[0].tipo == "saida_socio"
    assert eventos[0].sociedade_id == "soc1"
    assert "Fulano" in eventos[0].descricao


# ── LGPD: mascaramento do documento do sócio ──────────────────────────────────

def test_mascara_cpf_e_cnpj():
    assert mascarar_documento("123.456.789-01") == "***.456.789-**"
    assert mascarar_documento("12345678901") == "***.456.789-**"
    assert mascarar_documento("12.345.678/0001-90") == "12.345.678/****-**"
    assert mascarar_documento(None) is None
    assert mascarar_documento("") is None


def test_preparo_pii_nunca_texto_puro():
    cpf = "12345678901"
    pii = preparar_documento_socio(cpf)
    assert pii["documento_mascarado"] == "***.456.789-**"
    # Ciphertext e hash não podem conter o documento em claro.
    assert cpf not in (pii["documento_enc"] or "")
    assert cpf not in (pii["documento_hash"] or "")
    assert pii["documento_hash"] != cpf and len(pii["documento_hash"]) == 64
    # Roundtrip só via serviço de crypto (chave do ambiente).
    from app.services.pii_crypto import decrypt
    assert decrypt(pii["documento_enc"]) == cpf


async def test_resposta_do_socio_nao_vaza_documento():
    from app.routers.sociedades_cliente import adicionar_socio

    cpf = "12345678901"
    db = _FakeDB([_sociedade(), _cliente()])  # gestão
    out = await adicionar_socio(
        sociedade_id="soc1",
        payload=SocioCreate(nome="Fulano", documento=cpf,
                            quotas=Decimal("100"), administrador=True),
        db=db, cu=_user(UserRole.socio),
    )
    # Resposta: só a máscara; nenhum campo com o documento em claro.
    assert out["documento_mascarado"] == "***.456.789-**"
    assert "documento" not in out
    assert cpf not in str(out)

    # Persistência: objeto gravado não tem o texto puro em nenhum atributo.
    socio = next(o for o in db.added if isinstance(o, SocioSociedade))
    assert socio.documento_mascarado == "***.456.789-**"
    assert cpf not in (socio.documento_enc or "")
    assert cpf not in (socio.documento_hash or "")
    assert not hasattr(socio, "documento") or getattr(socio, "documento", None) is None
