"""CGU Portal da Transparência (sanções CEIS/CNEP/CEPIM) — sem rede, sem banco.

Cobre: gate flag/chave (503), sucesso normaliza as 3 bases, chave NUNCA
vaza no retorno/erro/audit, cache do dia SEM segunda chamada HTTP, parsing
tolerante a campos ausentes e tem_sancao. Fakes no padrão test_infosimples.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.user import User, UserRole
from app.services import transparencia_service
from app.services.transparencia_service import (
    IntegracaoDesligadaError,
    consultar_sancoes,
    normalizar_sancao,
    validar_cnpj,
)

CHAVE_TESTE = "chave-cgu-super-secreta-nao-vazar"
CNPJ = "11.222.333/0001-81"
CNPJ_DIG = "11222333000181"


@pytest.fixture()
def transparencia_ligada(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "TRANSPARENCIA_ENABLED", True)
    monkeypatch.setattr(s, "TRANSPARENCIA_API_KEY", CHAVE_TESTE)
    return s


# ── Fake DB (dispatch pelo SQL/params) ─────────────────────────────────────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar(self):
        return self._val


class _FakeDB:
    def __init__(self, cache: dict | None = None):
        # cache: {base: [normalizados]} — devolvido por base via params.
        self.cache = cache or {}
        self.inserts: list[dict] = []
        self.added: list = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        p = params or {}
        if "SELECT resultado FROM transparencia_cache" in sql:
            val = self.cache.get(p.get("base"))
            return _Res(json.dumps(val) if val is not None else None)
        if "INSERT INTO transparencia_cache" in sql:
            self.inserts.append(dict(p))
            return _Res(None)
        return _Res(None)  # DDL / DELETE

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _advogado() -> User:
    return User(id="u1", role=UserRole.advogado)


def _fake_get(por_base: dict, chamadas: list | None = None):
    """Fake de _get_json que devolve a lista da base embutida na URL."""
    async def _get(url, params, headers, timeout_s):
        if chamadas is not None:
            chamadas.append({"url": url, "params": params, "headers": headers})
        for base, lista in por_base.items():
            if url.rstrip("/").endswith("/" + base):
                # devolve tudo na página 1; página 2 vazia encerra o loop
                return lista if params.get("pagina") == 1 else []
        return []

    return _get


CEIS_ITEM = {
    "sancionado": {"nome": "EMPRESA X LTDA", "codigoFormatado": "11.222.333/0001-81"},
    "tipoSancao": {"descricaoResumida": "Inidônea"},
    "dataInicioSancao": "01/01/2023",
    "dataFimSancao": "01/01/2025",
    "orgaoSancionador": {"nome": "CGU", "siglaUf": "DF"},
    "fundamentacao": [{"descricao": "Art. 87 Lei 8.666/93"}],
}


# ── Rotas montadas ─────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/transparencia/sancoes") for p in paths)
    assert any(p.endswith("/transparencia/status") for p in paths)


# ── Gate ────────────────────────────────────────────────────────────────────────

async def test_gate_desligada(monkeypatch):
    monkeypatch.setattr(get_settings(), "TRANSPARENCIA_ENABLED", False)
    with pytest.raises(IntegracaoDesligadaError):
        await consultar_sancoes(_FakeDB(), CNPJ)


async def test_gate_sem_chave(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "TRANSPARENCIA_ENABLED", True)
    monkeypatch.setattr(s, "TRANSPARENCIA_API_KEY", "")
    with pytest.raises(IntegracaoDesligadaError):
        await consultar_sancoes(_FakeDB(), CNPJ)


async def test_endpoint_503_flag_desligada(monkeypatch):
    from app.routers.transparencia import SancoesIn, consultar_sancoes as endpoint

    monkeypatch.setattr(get_settings(), "TRANSPARENCIA_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        await endpoint(SancoesIn(cnpj=CNPJ), db=_FakeDB(), cu=_advogado())
    assert exc.value.status_code == 503


# ── Sucesso: normaliza as 3 bases, chave não vaza ──────────────────────────────

async def test_sucesso_normaliza_e_nao_vaza_chave(transparencia_ligada, monkeypatch):
    chamadas: list = []
    monkeypatch.setattr(
        transparencia_service, "_get_json",
        _fake_get({"ceis": [CEIS_ITEM], "cnep": [], "cepim": []}, chamadas))
    db = _FakeDB()

    r = await consultar_sancoes(db, CNPJ, user_id="u1", user_role="advogado")

    assert r["cnpj"] == CNPJ_DIG
    assert r["tem_sancao"] is True
    assert r["cache"] is False
    assert len(r["ceis"]) == 1 and r["cnep"] == [] and r["cepim"] == []
    s = r["ceis"][0]
    assert s["razao_social"] == "EMPRESA X LTDA"
    assert s["tipo_sancao"] == "Inidônea"
    assert s["orgao_sancionador"] == "CGU"
    assert s["fundamentacao"] == "Art. 87 Lei 8.666/93"
    # Chave só no header; nunca no retorno.
    assert CHAVE_TESTE not in json.dumps(r)
    assert all(c["headers"]["chave-api-dados"] == CHAVE_TESTE for c in chamadas)
    # 3 bases cacheadas (INSERT) + audit sem a chave.
    assert len(db.inserts) == 3
    audit = [a for a in db.added if a.__class__.__name__ == "AuditLog"][0]
    assert audit.acao == "CONSULTA_SANCOES"
    assert CHAVE_TESTE not in json.dumps(audit.dados_depois)
    assert CHAVE_TESTE not in (audit.detalhes or "")
    assert db.commits == 1


async def test_sem_sancao_tem_sancao_false(transparencia_ligada, monkeypatch):
    monkeypatch.setattr(
        transparencia_service, "_get_json",
        _fake_get({"ceis": [], "cnep": [], "cepim": []}))
    r = await consultar_sancoes(_FakeDB(), CNPJ)
    assert r["tem_sancao"] is False
    assert r["ceis"] == [] and r["cnep"] == [] and r["cepim"] == []


# ── Cache do dia: SEM segunda chamada HTTP ─────────────────────────────────────

async def test_cache_hit_sem_chamada(transparencia_ligada, monkeypatch):
    async def _nao_chamar(*a, **k):
        raise AssertionError("cache do dia não pode gerar nova chamada HTTP")

    monkeypatch.setattr(transparencia_service, "_get_json", _nao_chamar)
    salvo = [normalizar_sancao(CEIS_ITEM)]
    db = _FakeDB(cache={"ceis": salvo, "cnep": [], "cepim": []})

    r = await consultar_sancoes(db, CNPJ, user_id="u1", user_role="advogado")

    assert r["cache"] is True
    assert r["tem_sancao"] is True
    assert db.inserts == []  # nada regravado


# ── Parsing tolerante a campos ausentes ────────────────────────────────────────

def test_normalizar_tolerante_campos_ausentes():
    vazio = normalizar_sancao({})
    assert vazio["razao_social"] is None
    assert vazio["tipo_sancao"] == ""
    # CEPIM tem shape diferente (pessoaJuridica/motivo) — ainda normaliza.
    cepim = normalizar_sancao({
        "pessoaJuridica": {"nome": "ONG Y", "cnpjFormatado": "11.222.333/0001-81"},
        "motivo": "Prestação de contas rejeitada",
    })
    assert cepim["razao_social"] == "ONG Y"
    assert cepim["cnpj"] == CNPJ_DIG
    assert cepim["fundamentacao"] == "Prestação de contas rejeitada"


def test_validar_cnpj():
    assert validar_cnpj("11.222.333/0001-81") == CNPJ_DIG
    with pytest.raises(ValueError):
        validar_cnpj("123")


def test_schema_valida_cnpj():
    from app.routers.transparencia import SancoesIn

    assert SancoesIn(cnpj=CNPJ).cnpj == CNPJ_DIG
    with pytest.raises(ValidationError):
        SancoesIn(cnpj="123")


# ── Status: sem segredo ─────────────────────────────────────────────────────────

async def test_status_sem_segredo(transparencia_ligada):
    st = await transparencia_service.status(_FakeDB())
    assert st["enabled"] is True and st["configured"] is True
    assert CHAVE_TESTE not in json.dumps(st)
