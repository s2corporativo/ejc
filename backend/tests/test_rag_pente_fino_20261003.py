"""Regressões do pente fino do RAG (03/10/2026) sobre a auditoria de 04/09.

Cada teste nomeia o achado de `docs/auditoria/relatorios/2026-09-04-auditoria-profunda-rag.md`
que fecha:

* A-3  — piso de sigilo do caso propagado nos serviços que juntam caso + RAG;
* A-6  — gate sem cast `::boolean` (valor não conversível zerava o RAG);
* A-9  — recusa do curador sobrevive à nova versão do documento;
* A-13/M-11 — blocklist normalizada e chave legada `confianca='bloqueado'`.

Os testes db-level ao final rodam só com RUN_DB_TESTS=1 (Postgres + pgvector).
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.rag import KnowledgeDoc
from app.services import ai_service, ingestion_service
from app.services.ai.sanitization_policy import ModoSanitizacao

APP = Path(__file__).resolve().parents[1] / "app"


# ── A-6 / A-13 / M-11 ────────────────────────────────────────────────────────

def test_a6_gate_sem_cast_booleano():
    for incluir_ficticio in (False, True):
        assert "::boolean" not in ai_service.filtros_gate_rag(incluir_ficticio)


def test_a6_ficticio_e_conferido_sao_fail_closed():
    # Fictício: só é tratado como NÃO fictício com marcador ausente/falso.
    assert "COALESCE(kd.extra->>'ficticio','false')" in ai_service._FILTRO_FICTICIO_RAG
    assert "IN ('false','f','0','no','n','off','')" in ai_service._FILTRO_FICTICIO_RAG
    # Súmula: só sai da quarentena com verdadeiro inequívoco.
    assert "IN ('true','t','1','yes','y','on')" in ai_service._FILTRO_SUMULAS_QUARENTENA


def test_a13_m11_blocklist_normalizada_e_chave_legada():
    gate = ai_service._FILTRO_GATE_RAG
    assert "lower(btrim(COALESCE(kd.extra->>'rag_status','')))" in gate
    assert "lower(btrim(COALESCE(kd.extra->>'confianca','')))" in gate
    assert "lower(btrim(COALESCE(kd.extra->>'confidence_level','')))" in gate


# ── A-9 ──────────────────────────────────────────────────────────────────────

class _Resultado:
    def __init__(self, doc):
        self._doc = doc

    def scalar_one_or_none(self):
        return self._doc


class _BancoFalso:
    def __init__(self, existente):
        self.existente = existente
        self.adicionados = []

    async def execute(self, _stmt, _params=None):
        return _Resultado(self.existente)

    async def flush(self):
        return None

    def add(self, obj):
        self.adicionados.append(obj)


async def _nova_versao(extra_anterior: dict, extra_ingestor: dict) -> KnowledgeDoc:
    existente = KnowledgeDoc(
        id="doc-v1", titulo="Lei", categoria="legislacao",
        chave_origem="planalto:lei-a9", hash_conteudo="hash-antigo",
        versao=1, vigente=True, extra=extra_anterior,
    )
    db = _BancoFalso(existente)
    resultado = await ingestion_service.upsert_documento(
        db, titulo="Lei", categoria="legislacao",
        conteudo=("Texto compilado alterado na fonte oficial, longo o bastante "
                  "para gerar nova versão do documento."),
        chave_origem="planalto:lei-a9", extra=extra_ingestor,
        embutir_vetores=False,
        chunks=["Art. 1 Texto alterado suficientemente longo para compor um chunk."],
    )
    assert resultado == "atualizado"
    return next(o for o in db.adicionados if isinstance(o, KnowledgeDoc))


async def test_a9_recusa_sobrevive_a_nova_versao():
    novo = await _nova_versao({"rag_status": "recusado"}, {"rag_status": "aprovado"})
    assert novo.extra["rag_status"] == "recusado"


async def test_a9_recusa_com_caixa_e_espaco_tambem_sobrevive():
    novo = await _nova_versao({"rag_status": " Recusado "}, {"rag_status": "aprovado"})
    assert novo.extra["rag_status"] == "recusado"


async def test_a9_sem_recusa_previa_vale_o_status_do_ingestor():
    novo = await _nova_versao({"rag_status": "pendente"}, {"rag_status": "aprovado"})
    assert novo.extra["rag_status"] == "aprovado"


# ── A-3 ──────────────────────────────────────────────────────────────────────

_SERVICOS_CASO_MAIS_RAG = (
    "services/peca_service.py", "services/anexos_service.py",
    "services/checklist_ia.py", "services/dossie_service.py",
    "services/matriz_teses_service.py",
)


@pytest.mark.parametrize("rel", _SERVICOS_CASO_MAIS_RAG)
def test_a3_toda_chamada_ao_gateway_informa_o_sigilo(rel):
    arvore = ast.parse((APP / rel).read_text(encoding="utf-8"))
    chamadas = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        f = no.func
        nome = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        dono = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else ""
        if (nome == "gw_chat" or (nome == "chat" and dono == "ai_gateway")
                or (nome == "criticar_peca" and dono == "adversarial")):
            chamadas.append(no)
    assert chamadas, f"nenhuma chamada ao gateway localizada em {rel}"
    sem = [c.lineno for c in chamadas
           if not any(k.arg == "modo_sanitizacao" for k in c.keywords)]
    assert not sem, f"{rel}: chamadas ao gateway sem modo_sanitizacao nas linhas {sem}"


class _Parar(Exception):
    pass


async def test_a3_matriz_propaga_local_completo_do_caso(monkeypatch):
    from app.services import matriz_teses_service as mts

    capt = {}

    async def fake_chat(**kw):
        capt.update(kw)
        raise _Parar

    async def fake_modo(_db, case_id):
        return ModoSanitizacao.LOCAL_COMPLETO if case_id == "sigiloso" else None

    monkeypatch.setattr(mts, "gw_chat", fake_chat)
    monkeypatch.setattr(mts, "modo_sigilo_por_case_id", fake_modo)
    monkeypatch.setattr(mts, "get_settings", lambda: SimpleNamespace(AI_ENABLED=True))
    with pytest.raises(_Parar):
        await mts.decompor_questoes(object(), "u", "sigiloso", "penal",
                                    "fatos sanitizados suficientes para a decomposição")
    assert capt["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO


@pytest.mark.parametrize("case_id,area,esperado", [
    ("sigiloso", "civel", ModoSanitizacao.LOCAL_COMPLETO),   # sigilo marcado no caso
    (None, "infancia_juventude", ModoSanitizacao.LOCAL_COMPLETO),  # área sensível
    ("comum", "civel", None),                               # sem piso: modo da tarefa
])
async def test_a3_esteira_de_peca_propaga_piso_de_sigilo(monkeypatch, case_id, area, esperado):
    from app.services import peca_service
    from app.services.ai import entidades_caso, sanitization_policy

    capt = {}

    async def fake_chat(**kw):
        capt.update(kw)
        raise _Parar

    async def fake_modo(_db, cid):
        return ModoSanitizacao.LOCAL_COMPLETO if cid == "sigiloso" else None

    async def sem_entidades(_db, _cid):
        return None

    monkeypatch.setattr(peca_service, "gw_chat", fake_chat)
    monkeypatch.setattr(sanitization_policy, "modo_sigilo_por_case_id", fake_modo)
    monkeypatch.setattr(entidades_caso, "entidades_do_caso", sem_entidades)
    gen = peca_service.gerar_peca_pipeline(
        object(), "u", "peticao_inicial", area, "Fatos do caso.", "Pedidos.",
        [], case_id, None,
    )
    with pytest.raises(_Parar):
        async for _ in gen:
            pass
    assert capt["modo_sanitizacao"] == esperado


# ── db-level (Postgres real) ─────────────────────────────────────────────────

_db = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres+pgvector com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture
async def _engine_limpo(monkeypatch):
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)
    yield
    from app.core.database import engine
    await engine.dispose()


async def _ins(db, *, titulo, categoria, conteudo, extra):
    from sqlalchemy import text
    doc_id = str(uuid4())
    await db.execute(text(
        "INSERT INTO knowledge_docs (id, titulo, categoria, chave_origem, vigente, "
        "status_indexacao, extra) VALUES (:id,:t,:c,:k,true,'indexado',CAST(:e AS jsonb))"
    ), {"id": doc_id, "t": titulo, "c": categoria, "k": f"pf:{uuid4()}",
        "e": json.dumps(extra)})
    await db.execute(text(
        "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
        "VALUES (:id,:d,0,:c)"
    ), {"id": str(uuid4()), "d": doc_id, "c": conteudo})


@_db
@pytest.mark.parametrize("exigir_aprovado", [True, False])
async def test_db_valor_nao_booleano_nao_zera_o_rag_e_falha_fechado(
    _engine_limpo, monkeypatch, exigir_aprovado,
):
    """Com RAG_EXIGIR_APROVADO=false, a blocklist normalizada é a única
    barreira para ' Recusado ' e para a chave legada `confianca`."""
    from sqlalchemy import text

    from app.core.config import get_settings
    from app.core.database import AsyncSessionLocal

    monkeypatch.setattr(get_settings(), "RAG_EXIGIR_APROVADO", exigir_aprovado)

    termo = f"zzpf{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="PF_OK", categoria="doutrina",
                   conteudo=f"doutrina valida {termo}", extra={"rag_status": "aprovado"})
        # Antes: 'sim' quebrava o cast ::boolean (22P02) e zerava a busca inteira.
        await _ins(db, titulo="PF_FICTICIO_AMBIGUO", categoria="doutrina",
                   conteudo=f"modelo ambiguo {termo}",
                   extra={"rag_status": "aprovado", "ficticio": "sim"})
        await _ins(db, titulo="PF_SUMULA_AMBIGUA", categoria="sumula_stj",
                   conteudo=f"sumula ambigua {termo}",
                   extra={"rag_status": "aprovado", "conferido": "sim"})
        await db.execute(text(
            "UPDATE knowledge_docs SET fonte='sumula' WHERE titulo='PF_SUMULA_AMBIGUA'"))
        await _ins(db, titulo="PF_RECUSADO_CAIXA", categoria="doutrina",
                   conteudo=f"recusado caixa {termo}", extra={"rag_status": " Recusado "})
        await _ins(db, titulo="PF_CONFIANCA_LEGADA", categoria="doutrina",
                   conteudo=f"confianca legada {termo}",
                   extra={"rag_status": "aprovado", "confianca": "bloqueado"})
        await db.commit()
        res = await ai_service.buscar_contexto_rag(db, termo, limite=20, modo_or=True)
        titulos = {r["titulo"] for r in res}
        assert titulos == {"PF_OK"}, titulos
