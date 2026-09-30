"""Regressão de ownership + trilha WORM nos exports (export.py).

Achados de origem:
  1. `GET /export/clientes.csv` rodava `select(Client)` da base inteira e
     devolvia nome + CPF/CNPJ em claro + email + telefone, sem qualquer filtro
     de ownership — assimetria com `export_casos`, que filtra.
  2. Só `clientes.csv` gravava trilha; `casos.csv` e `casos/{id}.pdf` não.
     `audit_logs` é WORM por trigger (migration 131): trilha ausente é trilha
     inexistente para sempre.
  3. O gate era tupla literal inline na linha do handler — não nomeado, não
     reusável, não testável.

Padrão do repo (tests/test_hardening_ownership_2026_07.py): sem banco real,
`_SeqDB`/`_Res` fake + chamada direta ao handler.

Mapa teste→comportamento travado:
  T1 gestão vê a base inteira (escopo integral)
  T2 não-gestão vê só próprio OU com caso visível
  T3 allowlist EXATA: barra estagiario/secretaria/cliente_externo e preserva
     financeiro (comportamento M04 — trave-se para ninguém "corrigir" depois)
  T4 gate não é piso hierárquico: estagiario(3) < financeiro(4) e mesmo assim
     estagiario é barrado
  T5 trilha presente nos 3 exports
  T6 falha na trilha não vaza dado: 503 e nenhum Response construído
  T7 `detalhes` sem PII
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from app.models.user import User, UserRole
from app.models.client import ClientTipo, ClientStatus
from app.models.case import CaseArea, CaseStatus
from app.routers import export as export_mod
from app.routers.export import (
    EXPORT_CLIENTES_ROLES,
    export_casos,
    export_caso_pdf,
    export_clientes,
    requer_export_clientes,
)


# ── Fakes (espelham _Res/_SeqDB do arquivo vizinho) ───────────────────────────

_UNSET = object()


class _Res:
    def __init__(self, *, scalar_one=None, all=_UNSET):
        self._scalar_one = scalar_one
        self._all = [] if all is _UNSET else all

    def scalar_one_or_none(self):
        return self._scalar_one

    def scalars(self):
        return self

    def all(self):
        return self._all


class _SeqDB:
    def __init__(self, results=()):
        self._results = list(results)
        self.executed = []
        self.added = []
        self.commits = 0
        self.commit_error: Exception | None = None

    async def execute(self, stmt, *a, **k):
        self.executed.append(stmt)
        if self._results:
            return self._results.pop(0)
        return _Res()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        if self.commit_error is not None:
            raise self.commit_error
        self.commits += 1

    async def rollback(self):
        pass


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


class _Row:
    """Linha de resultado com os atributos que o handler lê.

    Não é o ORM: `Client.documento_plain` é property de leitura (decifra sob
    demanda) e não tem setter, e o resto dos enums não interessa ao gate.
    """
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _cliente(cid: str, nome: str = "Maria Souza", doc: str = "123.456.789-00",
             mail: str = "maria@ex.com", tel: str = "31999998888",
             resp: str | None = None) -> _Row:
    return _Row(id=cid, nome=nome, tipo=ClientTipo.PF,
                status=ClientStatus.ativo, documento_plain=doc,
                email=mail, telefone=tel, responsavel_id=resp)


def _caso(cid: str = "c1", titulo: str = "Contrato",
          parte: str = "Contraparte X") -> _Row:
    return _Row(id=cid, numero_interno="2026-0001", titulo=titulo,
                area=CaseArea.civil, status=CaseStatus.aberto,
                numero_processo="0000000-00.0000.0.00.0000",
                parte_contraria=parte)


@pytest.fixture
def trilha(monkeypatch):
    """Intercepta `criar_audit_log` e devolve a lista de registros gravados."""
    registros: list[dict] = []

    async def fake(db, user_id, user_role, acao, entidade, registro_id=None,
                   detalhes=None, **kw):
        registros.append({
            "user_id": user_id, "user_role": user_role, "acao": acao,
            "entidade": entidade, "registro_id": registro_id,
            "detalhes": detalhes,
        })
        db.add(object())

    monkeypatch.setattr(export_mod, "criar_audit_log", fake)
    return registros


# ══ T1 — gestão vê a base inteira ════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.superadmin, UserRole.admin,
                                  UserRole.socio])
async def test_T1_gestao_ve_base_inteira(trilha, role):
    """`_ve_todos` (nível >= socio) não recebe predicado de escopo."""
    rows = [_cliente("c1"), _cliente("c2")]
    db = _SeqDB([_Res(all=rows)])
    resp = await export_clientes(db=db, cu=_user(role))
    assert isinstance(resp, StreamingResponse)
    assert len(rows) == 2
    where = str(db.executed[0]).split("WHERE", 1)[1]
    assert "responsavel_id" not in where and "client_id" not in where
    assert "deleted_at IS NULL" in where
    assert trilha[0]["detalhes"].startswith("escopo=integral")


# ══ T2 — não-gestão: próprio OU com caso visível ═══════════════════════════

@pytest.mark.asyncio
async def test_T2_nao_gestao_aplica_escopo_proprio_ou_caso_visivel(trilha):
    """Fora da gestão, o SQL carrega os DOIS predicados em OR."""
    db = _SeqDB([_Res(all=[_cliente("c1", resp="u1")])])
    await export_clientes(db=db, cu=_user(UserRole.financeiro))
    sql = str(db.executed[0])
    assert "clients.responsavel_id" in sql          # cliente próprio
    assert "cases.client_id" in sql                 # cliente com caso visível
    assert "OR" in sql
    # mesmo par responsável/auxiliar de export_casos
    assert "advogado_responsavel_id" in sql
    assert "advogado_auxiliar_id" in sql
    assert "cases.deleted_at IS NULL" in sql
    assert trilha[0]["detalhes"].startswith("escopo=proprio")


# ══ T3/T4 — allowlist EXATA, não hierárquica ═══════════════════════════════

@pytest.mark.parametrize("role", [UserRole.estagiario, UserRole.secretaria,
                                  UserRole.cliente_externo])
def test_T3_allowlist_barra_fora_do_conjunto(role):
    with pytest.raises(HTTPException) as e:
        requer_export_clientes(_user(role))
    assert e.value.status_code == 403


@pytest.mark.parametrize("role", [UserRole.superadmin, UserRole.admin,
                                  UserRole.socio, UserRole.financeiro])
def test_T3_allowlist_preserva_m04(role):
    """M04: `financeiro` continua com acesso — decisão do titular, não do dev."""
    requer_export_clientes(_user(role))  # não levanta
    assert role.value in EXPORT_CLIENTES_ROLES


def test_T4_gate_nao_e_piso_hierarquico():
    """`estagiario` (3) é MENOR que `financeiro` (4) e mesmo assim barrado.

    Um piso numérico escolheria min(allowlist) = 4 e abriria o estagiário.
    """
    from app.core.security import ROLE_LEVEL
    assert ROLE_LEVEL["estagiario"] < ROLE_LEVEL["financeiro"]
    with pytest.raises(HTTPException):
        requer_export_clientes(_user(UserRole.estagiario))


@pytest.mark.asyncio
async def test_T3_export_clientes_403_para_estagiario(trilha):
    db = _SeqDB([_Res(all=[_cliente("c1")])])
    with pytest.raises(HTTPException) as e:
        await export_clientes(db=db, cu=_user(UserRole.estagiario))
    assert e.value.status_code == 403
    assert db.executed == [] and trilha == []   # nada sai, nada é registrado


# ══ T5 — trilha nos três exports ════════════════════════════════════════════

@pytest.mark.asyncio
async def test_T5_trilha_export_clientes(trilha):
    db = _SeqDB([_Res(all=[_cliente("c1")])])
    await export_clientes(db=db, cu=_user(UserRole.socio))
    assert [r["acao"] for r in trilha] == ["EXPORT_CLIENTES_CSV"]
    assert trilha[0]["entidade"] == "clients"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_T5_trilha_export_casos(trilha):
    db = _SeqDB([_Res(all=[])])
    await export_casos(db=db, cu=_user(UserRole.advogado))
    assert [r["acao"] for r in trilha] == ["EXPORT_CASOS_CSV"]
    assert trilha[0]["entidade"] == "cases"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_T5_trilha_export_caso_pdf_com_registro_id(trilha, monkeypatch):
    """O PDF é o único export que liga a trilha a um caso concreto."""
    async def fake_pdf(db, case_id, user_id):
        return b"%PDF-1.4 fake"

    monkeypatch.setattr("app.services.pdf_service.gerar_caso_pdf", fake_pdf)
    db = _SeqDB([_Res(scalar_one=_caso("case-42"))])
    resp = await export_caso_pdf(case_id="case-42", db=db,
                                 cu=_user(UserRole.advogado))
    assert isinstance(resp, Response)
    assert [r["acao"] for r in trilha] == ["EXPORT_CASO_PDF"]
    assert trilha[0]["registro_id"] == "case-42"
    assert db.commits == 1


# ══ T6 — fail-closed: trilha quebrada não vaza dado ══════════════════════════

@pytest.mark.asyncio
async def test_T6_falha_no_log_nao_vaza_clientes(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("audit_logs indisponível")

    monkeypatch.setattr(export_mod, "criar_audit_log", boom)
    rows = [_cliente("c1", doc="123.456.789-00", mail="maria@ex.com")]
    db = _SeqDB([_Res(all=rows)])
    with pytest.raises(HTTPException) as e:
        await export_clientes(db=db, cu=_user(UserRole.socio))
    assert e.value.status_code == 503
    # nenhum corpo produzido — nada de PII em StreamingResponse
    assert db.commits == 0


@pytest.mark.asyncio
async def test_T6_falha_no_commit_nao_vaza_casos(monkeypatch, trilha):
    db = _SeqDB([_Res(all=[_caso()])])
    db.commit_error = RuntimeError("deadlock")
    with pytest.raises(HTTPException) as e:
        await export_casos(db=db, cu=_user(UserRole.advogado))
    assert e.value.status_code == 503
    assert trilha[0]["acao"] == "EXPORT_CASOS_CSV"   # tentou registrar


@pytest.mark.asyncio
async def test_T6_falha_no_commit_nao_vaza_pdf(monkeypatch):
    async def fake_pdf(db, case_id, user_id):
        return b"%PDF-1.4 fake"

    monkeypatch.setattr("app.services.pdf_service.gerar_caso_pdf", fake_pdf)
    db = _SeqDB([_Res(scalar_one=_caso("case-42"))])
    db.commit_error = RuntimeError("deadlock")
    with pytest.raises(HTTPException) as e:
        await export_caso_pdf(case_id="case-42", db=db,
                              cu=_user(UserRole.advogado))
    assert e.value.status_code == 503


# ══ T7 — `detalhes` sem PII ═════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_T7_detalhes_sem_pii(trilha):
    alvos = ("maria", "maria@ex.com", "31999998888", "123.456.789-00",
             "souza", "12345678900")
    db = _SeqDB([_Res(all=[_cliente("c1"),
                           _cliente("c2", nome="João Da Silva")])])
    await export_clientes(db=db, cu=_user(UserRole.socio))
    d = trilha[0]["detalhes"].lower()
    for alvo in alvos:
        assert alvo.lower() not in d
    assert "registros=2" in d


@pytest.mark.asyncio
async def test_T7_detalhes_caso_pdf_sem_pii(trilha, monkeypatch):
    async def fake_pdf(db, case_id, user_id):
        return b"%PDF-1.4 fake"

    monkeypatch.setattr("app.services.pdf_service.gerar_caso_pdf", fake_pdf)
    db = _SeqDB([_Res(scalar_one=_caso("case-42"))])
    await export_caso_pdf(case_id="case-42", db=db, cu=_user(UserRole.advogado))
    d = trilha[0]["detalhes"].lower()
    assert "2026-0001" not in d and "parte" not in d
    assert "registros=1" in d
