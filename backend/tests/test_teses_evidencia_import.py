"""Coleta de evidência jurídica para teses (PR 3 da série de consolidação do
Banco de Teses — reusa o pipeline de importação de jurisprudência já testado
em tests/test_juris_import.py; aqui cobrimos só a camada nova: gravação em
`legal_evidence` com dedup, e o envelope de rota/job, no mesmo padrão daquele
arquivo).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.security import ROLE_LEVEL
from app.models.user import User, UserRole
from app.models.tese import Tese, TeseTipo, TeseStatus
from app.models.tese_extensoes import LegalEvidence
from app.services import teses_evidencia_import as tei
from app.services.juris_import.base import JulgadoNormalizado
from app.routers import teses_evidencia_import as router_mod
from app.routers.teses_evidencia_import import ColetarEvidenciaRequest, coletar_evidencia

_TABELAS = [User.__table__, Tese.__table__, LegalEvidence.__table__]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _julgado(tribunal: str = "STJ", numero: str = "REsp 123",
             ementa: str = "Ementa exemplo") -> JulgadoNormalizado:
    return JulgadoNormalizado(
        tribunal=tribunal, numero=numero, ementa=ementa,
        url_fonte="https://stj.jus.br/x", data="2024-05-10",
        orgao_julgador="3ª Turma", relator="Min. Fulano",
    )


async def _nova_tese(db) -> Tese:
    t = Tese(
        id=str(uuid4()), titulo="Tese de teste",
        descricao="Descrição de teste com mais de dez caracteres",
        tipo=TeseTipo.escritorio, status=TeseStatus.ativa,
    )
    db.add(t)
    await db.commit()
    return t


# ── importar_evidencias — service ────────────────────────────────────────────

async def test_importar_evidencias_grava_com_status_coletada(db):
    t = await _nova_tese(db)
    resumo = await tei.importar_evidencias(
        db, [_julgado()], tese_id=t.id, fonte_slug="lexml", user_id="u1")
    assert resumo == {"importados": 1, "duplicados": 0, "erros": 0}

    rows = (await db.execute(
        select(LegalEvidence).where(LegalEvidence.tese_id == t.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "coletada"
    assert rows[0].coletado_por == "u1"
    assert rows[0].tipo_fonte == "lexml"
    assert rows[0].hash_fingerprint


async def test_importar_evidencias_deduplica_mesmo_julgado_no_mesmo_lote(db):
    t = await _nova_tese(db)
    j = _julgado()
    resumo = await tei.importar_evidencias(
        db, [j, j], tese_id=t.id, fonte_slug="lexml", user_id="u1")
    assert resumo == {"importados": 1, "duplicados": 1, "erros": 0}


async def test_importar_evidencias_deduplica_por_tribunal_numero_entre_fontes(db):
    """Mesmo julgado, ementa reformatada por outra fonte — dedup por
    (tribunal, numero) pega mesmo quando o hash de conteúdo diverge."""
    t = await _nova_tese(db)
    j1 = _julgado(ementa="Ementa versão 1")
    j2 = _julgado(ementa="Ementa versão 2 (mesma decisão, reformatada)")
    r1 = await tei.importar_evidencias(db, [j1], tese_id=t.id, fonte_slug="lexml", user_id="u1")
    r2 = await tei.importar_evidencias(db, [j2], tese_id=t.id, fonte_slug="stj", user_id="u1")
    assert r1 == {"importados": 1, "duplicados": 0, "erros": 0}
    assert r2 == {"importados": 0, "duplicados": 1, "erros": 0}


async def test_importar_evidencias_nao_deduplica_entre_teses_diferentes(db):
    t1 = await _nova_tese(db)
    t2 = await _nova_tese(db)
    j = _julgado()
    r1 = await tei.importar_evidencias(db, [j], tese_id=t1.id, fonte_slug="lexml", user_id="u1")
    r2 = await tei.importar_evidencias(db, [j], tese_id=t2.id, fonte_slug="lexml", user_id="u1")
    assert r1["importados"] == 1
    assert r2["importados"] == 1   # mesma decisão pode fundamentar teses diferentes


async def test_importar_evidencias_erro_em_um_nao_aborta_os_demais(db, monkeypatch):
    vez = {"n": 0}
    original = tei._hash_fingerprint

    def _hash_com_falha(j):
        vez["n"] += 1
        if vez["n"] == 1:
            raise RuntimeError("falha simulada")
        return original(j)

    monkeypatch.setattr(tei, "_hash_fingerprint", _hash_com_falha)
    t = await _nova_tese(db)
    resumo = await tei.importar_evidencias(
        db, [_julgado(numero="1"), _julgado(numero="2")],
        tese_id=t.id, fonte_slug="lexml", user_id="u1")
    assert resumo == {"importados": 1, "duplicados": 0, "erros": 1}


async def test_importar_evidencias_data_malformada_vira_none(db):
    t = await _nova_tese(db)
    j = JulgadoNormalizado(tribunal="STJ", numero="REsp 999", ementa="...",
                            url_fonte="https://x", data="não é uma data")
    await tei.importar_evidencias(db, [j], tese_id=t.id, fonte_slug="lexml", user_id="u1")
    row = (await db.execute(
        select(LegalEvidence).where(LegalEvidence.tese_id == t.id)
    )).scalar_one()
    assert row.data_julgamento is None


# ── Router: RBAC, validação de fonte, job assíncrono ─────────────────────────

class _BT(BackgroundTasks):
    def __init__(self):
        super().__init__()
        self.agendados = []

    def add_task(self, fn, *a, **kw):
        self.agendados.append((fn, a, kw))


async def test_coletar_evidencia_exige_permissao_de_edicao(db):
    t = await _nova_tese(db)
    req = ColetarEvidenciaRequest(fonte="lexml", consulta="dano moral bancário")
    estagiario = User(id="u1", role=UserRole.estagiario)
    with pytest.raises(HTTPException) as exc:
        await coletar_evidencia(t.id, req, _BT(), db=db, cu=estagiario)
    assert exc.value.status_code == 403


async def test_coletar_evidencia_tese_inexistente_404(db):
    req = ColetarEvidenciaRequest(fonte="lexml", consulta="dano moral bancário")
    advogado = User(id="u1", role=UserRole.advogado)
    with pytest.raises(HTTPException) as exc:
        await coletar_evidencia(str(uuid4()), req, _BT(), db=db, cu=advogado)
    assert exc.value.status_code == 404


async def test_coletar_evidencia_fonte_desconhecida_422(db):
    t = await _nova_tese(db)
    req = ColetarEvidenciaRequest(fonte="fonte-que-nao-existe", consulta="dano moral")
    advogado = User(id="u1", role=UserRole.advogado)
    with pytest.raises(HTTPException) as exc:
        await coletar_evidencia(t.id, req, _BT(), db=db, cu=advogado)
    assert exc.value.status_code == 422


async def test_coletar_evidencia_agenda_job_e_status_e_consultavel_pelo_dono(db):
    t = await _nova_tese(db)
    req = ColetarEvidenciaRequest(fonte="lexml", consulta="dano moral bancário", limite=10)
    advogado = User(id="u1", role=UserRole.advogado)
    bt = _BT()
    out = await coletar_evidencia(t.id, req, bt, db=db, cu=advogado)
    assert out["status"] == "executando"
    assert out["tese_id"] == t.id
    assert len(bt.agendados) == 1
    assert bt.agendados[0][0] is tei.executar_coleta_evidencia

    tei.registrar_job(out["job_id"], {
        "job_id": out["job_id"], "status": "concluido", "tese_id": t.id,
        "user_id": "u1", "resumo": {"importados": 2, "duplicados": 0, "erros": 0},
    })
    st = await router_mod.status_coleta_evidencia(t.id, out["job_id"], cu=advogado)
    assert st["status"] == "concluido"
    assert st["resumo"]["importados"] == 2


async def test_status_coleta_evidencia_de_outro_usuario_responde_404(db):
    t = await _nova_tese(db)
    job_id = str(uuid4())
    tei.registrar_job(job_id, {
        "job_id": job_id, "status": "concluido", "tese_id": t.id, "user_id": "dono",
    })
    outro = User(id="outro-usuario", role=UserRole.advogado)
    with pytest.raises(HTTPException) as exc:
        await router_mod.status_coleta_evidencia(t.id, job_id, cu=outro)
    assert exc.value.status_code == 404


def test_pode_editar_gate_hierarquico_correto():
    """Confirma que o gate reusado (_pode_editar de routers/teses.py) exige
    advogado+, coerente com o rate limit/RBAC de juris_import (_GATE_ADVOGADO)."""
    from app.routers.teses import _pode_editar
    assert not _pode_editar(User(id="u1", role=UserRole.estagiario))
    assert not _pode_editar(User(id="u1", role=UserRole.secretaria))
    assert _pode_editar(User(id="u1", role=UserRole.advogado))
    assert _pode_editar(User(id="u1", role=UserRole.socio))
    assert ROLE_LEVEL["advogado"] <= ROLE_LEVEL["socio"]
