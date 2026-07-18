"""Central de Atividades enriquecida (pendência backend do PR #274).

Cobre:
  1. GET /atividades expõe responsavel_id, prioridade e subtipo no shape
     (aditivo — contrato antigo preservado) e NULL onde a fonte não tem.
  2. PATCH /agenda-eventos/{id} aceita responsavel_id (opcional, exclude_unset),
     valida tipo e mantém 404 para evento inexistente.
  3. Sanidade da migration 097 (upgrade acrescenta colunas SÓ NO FINAL do
     SELECT; downgrade restaura a definição da 053).
  4. Validação da view REAL (colunas novas) — exige Postgres migrado, gated
     por RUN_DB_TESTS=1 (padrão dos *_dblevel.py).

Sem Postgres nos testes 1-3 (padrão _FakeDB de test_sociedades_cliente.py):
handlers chamados diretamente com sessão fake.
"""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Rows:
    """Resultado fake: serve .mappings().all() (dicts) e .first() (tuplas)."""

    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    """Fila de resultados para execute(); registra SQL/params executados."""

    def __init__(self, resultados):
        self._res = list(resultados)
        self.executed: list[tuple[str, dict | None]] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return _Rows(self._res.pop(0) if self._res else [])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _gestor() -> User:
    return User(id="g1", role=UserRole.admin)


# ── 1. GET /atividades — shape enriquecido ────────────────────────────────────

def _linha_view(**kw):
    base = dict(
        id="a1", tipo="prazo", titulo="Contestar", descricao=None,
        data=date(2026, 7, 20), status="pendente", case_id="c1",
        responsavel_id="u9", prioridade="alta", subtipo=None,
        caso_titulo="Caso X", dias_restantes=3,
    )
    base.update(kw)
    return base


async def test_atividades_expoe_responsavel_prioridade_subtipo():
    from app.routers.atividades import listar_atividades

    db = _FakeDB([[
        _linha_view(),
        _linha_view(id="e1", tipo="agenda", titulo="Reunião cliente",
                    prioridade=None, subtipo="reuniao", responsavel_id="u2"),
    ]])
    out = await listar_atividades(apenas_pendentes=True, db=db, cu=_gestor())

    prazo, agenda = out["data"]
    # Campos novos presentes (aditivo)
    assert prazo["responsavel_id"] == "u9"
    assert prazo["prioridade"] == "alta"
    assert prazo["subtipo"] is None          # prazo não tem subtipo
    assert agenda["prioridade"] is None      # agenda não tem prioridade
    assert agenda["subtipo"] == "reuniao"    # tipo real do evento de agenda
    assert agenda["responsavel_id"] == "u2"
    # Contrato antigo intacto
    for k in ("id", "tipo", "titulo", "descricao", "date", "status",
              "case_id", "caso_titulo", "dias_restantes", "urgencia"):
        assert k in prazo
    assert prazo["urgencia"] == "critico"    # dias_restantes=3


async def test_atividades_sql_seleciona_colunas_novas_da_view():
    from app.routers.atividades import listar_atividades

    db = _FakeDB([[]])
    await listar_atividades(apenas_pendentes=False, db=db, cu=_gestor())
    sql = db.executed[0][0]
    assert "v.responsavel_id" in sql
    assert "v.prioridade" in sql
    assert "v.subtipo" in sql
    assert "vw_atividades" in sql


# ── 2. PATCH /agenda-eventos/{id} — responsavel_id ────────────────────────────

async def test_patch_agenda_aceita_responsavel_id():
    from app.routers.agenda_eventos import EventoPatch, atualizar

    # 1º execute: SELECT case_id (sem caso → sem gate de ownership);
    # 2º execute: UPDATE.
    db = _FakeDB([[(None,)], []])
    out = await atualizar("e1", EventoPatch(responsavel_id="u7"), db=db, cu=_gestor())

    assert out == {"ok": True}
    upd_sql, upd_params = db.executed[1]
    assert "responsavel_id = :responsavel_id" in upd_sql
    assert upd_params["responsavel_id"] == "u7"
    assert db.commits == 1


async def test_patch_agenda_responsavel_id_e_opcional_exclude_unset():
    from app.routers.agenda_eventos import EventoPatch, atualizar

    db = _FakeDB([[(None,)]])
    out = await atualizar("e1", EventoPatch(titulo="Novo título"), db=db, cu=_gestor())

    assert out == {"ok": True}
    upd_sql, upd_params = db.executed[1]
    assert "titulo = :titulo" in upd_sql
    # Campo não enviado NÃO entra no UPDATE (exclude_unset)
    assert "responsavel_id" not in upd_sql


async def test_patch_agenda_sem_campos_nao_atualiza():
    from app.routers.agenda_eventos import EventoPatch, atualizar

    db = _FakeDB([[(None,)]])
    out = await atualizar("e1", EventoPatch(), db=db, cu=_gestor())
    assert out == {"ok": True}
    assert len(db.executed) == 1  # só o SELECT — nenhum UPDATE
    assert db.commits == 0


async def test_patch_agenda_evento_inexistente_404():
    from app.routers.agenda_eventos import EventoPatch, atualizar

    db = _FakeDB([[]])
    with pytest.raises(HTTPException) as exc:
        await atualizar("nao-existe", EventoPatch(responsavel_id="u7"),
                        db=db, cu=_gestor())
    assert exc.value.status_code == 404


async def test_patch_agenda_tipo_invalido_422():
    from app.routers.agenda_eventos import EventoPatch, atualizar

    db = _FakeDB([[(None,)]])
    with pytest.raises(HTTPException) as exc:
        await atualizar("e1", EventoPatch(tipo="festa"), db=db, cu=_gestor())
    assert exc.value.status_code == 422


def test_evento_patch_tem_responsavel_id_opcional():
    from app.routers.agenda_eventos import EventoPatch

    campo = EventoPatch.model_fields.get("responsavel_id")
    assert campo is not None
    assert not campo.is_required()


# ── 3. Sanidade da migration 097 (sem banco) ──────────────────────────────────

_MIG = Path(__file__).resolve().parents[1] / "alembic" / "versions" / \
    "097_vw_atividades_enriquecida.py"


def test_migration_097_upgrade_acrescenta_colunas_no_final():
    src = _MIG.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE VIEW vw_atividades" in src
    # Cada perna do UNION termina com os 2 campos novos (prioridade, subtipo)
    assert "d.prioridade::text AS prioridade, NULL::text AS subtipo" in src
    assert "t.prioridade::text, NULL::text" in src
    assert "NULL::text, a.tipo::text" in src  # subtipo = tipo real da agenda
    # As 2 fontes sem prioridade nem subtipo (suspensões, intimações) devolvem
    # NULL em ambos
    assert src.count("NULL::text, NULL::text") == 2


def test_migration_097_downgrade_restaura_versao_053():
    src = _MIG.read_text(encoding="utf-8")
    mig_053 = (_MIG.parent / "053_reconcile_schema.py").read_text(encoding="utf-8")
    assert 'down_revision = "096_rag_embedding_1024"' in src
    assert "DROP VIEW IF EXISTS vw_atividades" in src
    # Downgrade NÃO contém os campos novos na definição restaurada
    m = re.search(r"_VIEW_053 = \"\"\"(.*?)\"\"\"", src, re.S)
    assert m and "prioridade" not in m.group(1) and "subtipo" not in m.group(1)
    # E a definição restaurada é a mesma da 053 (colunas por perna idênticas)
    assert "d.case_id, d.responsavel_id" in m.group(1)
    assert "d.case_id, d.responsavel_id" in mig_053


# ── 4. View real (Postgres migrado) — RUN_DB_TESTS=1 ──────────────────────────

@pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)
async def test_vw_atividades_tem_colunas_novas_no_banco():
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cols = {
            r[0] for r in (await db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'vw_atividades'"
            ))).all()
        }
    assert {"responsavel_id", "prioridade", "subtipo"} <= cols
