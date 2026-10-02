"""I1 (auditoria de Inteligência): /rag/ingerir-ai-log não pode levar saída de IA
à base como conhecimento aprovado/global sem curadoria humana."""
import datetime as _dt
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.ai_log import AIStatusHITL, AITipoUso
from app.routers import rag as rag_router
from app.routers.rag import IngerirAILogRequest, ingerir_ai_log_aprovado
from app.services import ingestion_service


class _Res:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _ExecDB:
    def __init__(self, obj):
        self._obj = obj

    async def execute(self, *a, **kw):
        return _Res(self._obj)

    async def commit(self):
        pass


def _log():
    return SimpleNamespace(
        id="log-1", user_id="user-1",
        status_hitl=AIStatusHITL.revisado,
        tipo_uso=AITipoUso.redacao_peca,
        created_at=_dt.datetime(2026, 7, 5),
        resposta="Texto gerado por IA com mais de cinquenta caracteres para ingestão.",
        critica_adversarial=None,
    )


async def test_ingere_como_pendente_nunca_aprovado(monkeypatch):
    capturado = {}

    async def fake_upsert(db, **kw):
        capturado.update(kw)
        return "novo"

    monkeypatch.setattr(ingestion_service, "upsert_documento", fake_upsert)
    monkeypatch.setattr(rag_router, "chunk_texto", lambda t: ["c1"])
    out = await ingerir_ai_log_aprovado(
        "log-1", IngerirAILogRequest(), db=_ExecDB(_log()),
        cu=SimpleNamespace(id="user-1"),
    )
    assert capturado["extra"]["rag_status"] == "pendente"
    assert capturado["extra"]["requires_human_review"] is True
    assert capturado["extra"]["gerado_por_ia"] is True
    assert "aprovado_por" not in capturado["extra"]
    assert capturado["confianca"] != "alta"
    assert out["rag_status"] == "pendente"


@pytest.mark.parametrize("cat", [
    "legislacao_federal", "sumula_stj", "jurisprudencia_stf",
    "peca_interna", "precedente_interno",
])
async def test_categoria_normativa_ou_restrita_422(cat, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("não deve ingerir")

    monkeypatch.setattr(ingestion_service, "upsert_documento", boom)
    with pytest.raises(HTTPException) as e:
        await ingerir_ai_log_aprovado(
            "log-1", IngerirAILogRequest(categoria=cat),
            db=_ExecDB(_log()), cu=SimpleNamespace(id="user-1"),
        )
    assert e.value.status_code == 422


def test_rota_exige_papel_juridico():
    rota = next(r for r in rag_router.router.routes
                if getattr(r, "path", "").endswith("/ingerir-ai-log/{log_id}"))
    nomes = [getattr(d.call, "__qualname__", "") for d in rota.dependant.dependencies]
    assert any("require_roles" in n for n in nomes)
