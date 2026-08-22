"""Seed da Base de Conhecimento (services/seed_conhecimento.py).

Garante: corpus determinístico e válido (chaves únicas ejc_seed:*, conteúdo
mínimo, nenhuma categoria restrita), idempotência do executar_seed (dedup por
chave_origem via upsert), agendamento gracioso da jurisprudência inicial
(fontes desabilitadas → lista vazia, sem exceção) e degradação de flags
(DataJud desligado → erro tipado, não 500 genérico).
"""
from __future__ import annotations

import pytest
from fastapi import BackgroundTasks

from app.services import seed_conhecimento as sc
from app.services.ai_service import _RESTRICTED_CATS


# ── Corpus ───────────────────────────────────────────────────────────────────

def test_corpus_chaves_unicas_e_prefixo():
    docs = sc.montar_documentos_seed()
    chaves = [d["chave_origem"] for d in docs]
    assert len(chaves) == len(set(chaves)), "chave_origem duplicada no seed"
    assert all(c.startswith("ejc_seed:") for c in chaves)
    # corpus mínimo esperado: readme + checklist + padrão-ouro + áreas + modelos
    assert len(docs) >= 20
    assert "ejc_seed:banco_nacional_teses_v1" in chaves


def test_corpus_conteudo_minimo_e_titulos():
    for d in sc.montar_documentos_seed():
        assert len(d["conteudo"].strip()) >= 50, f"{d['chave_origem']} curto demais"
        assert d["titulo"].strip(), f"{d['chave_origem']} sem título"


def test_corpus_nao_usa_categorias_restritas():
    # Categorias restritas são filtradas fail-closed pela busca sem escopo de
    # cliente — o seed institucional precisa ser recuperável por todos.
    for d in sc.montar_documentos_seed():
        assert d["categoria"] not in _RESTRICTED_CATS


def test_corpus_e_deterministico():
    a = sc.montar_documentos_seed()
    b = sc.montar_documentos_seed()
    assert a == b


# ── Idempotência do executar_seed ────────────────────────────────────────────

async def test_executar_seed_idempotente(monkeypatch):
    vistos: dict[str, str] = {}

    async def upsert_fake(db, *, chave_origem, conteudo, **kw):
        # Comportamento do upsert real: 1ª vez "novo"; mesmo conteúdo depois
        # → "inalterado" (dedup por chave_origem + hash).
        if vistos.get(chave_origem) == conteudo:
            return "inalterado"
        resultado = "novo" if chave_origem not in vistos else "atualizado"
        vistos[chave_origem] = conteudo
        return resultado

    monkeypatch.setattr(sc, "upsert_documento", upsert_fake)

    r1 = await sc.executar_seed_conhecimento(db=None)
    assert r1["novos"] == r1["total"] > 0
    assert r1["atualizados"] == r1["inalterados"] == 0

    r2 = await sc.executar_seed_conhecimento(db=None)
    assert r2["inalterados"] == r2["total"] == r1["total"]
    assert r2["novos"] == r2["atualizados"] == 0


async def test_executar_seed_confianca_alta_e_fonte(monkeypatch):
    chamadas: list[dict] = []

    async def upsert_fake(db, **kw):
        chamadas.append(kw)
        return "novo"

    monkeypatch.setattr(sc, "upsert_documento", upsert_fake)
    await sc.executar_seed_conhecimento(db=None, embutir_vetores=False)
    assert chamadas
    for kw in chamadas:
        assert kw["confianca"] == "alta"
        assert kw["fonte"] == sc.FONTE_SEED
        assert kw["embutir_vetores"] is False


# ── Jurisprudência inicial (opt-in, graciosa) ────────────────────────────────

def test_jurisprudencia_inicial_fontes_desabilitadas(monkeypatch):
    from app.services.juris_import import FONTES

    for f in FONTES.values():
        monkeypatch.setitem(f, "enabled", False)
    bt = BackgroundTasks()
    jobs = sc.agendar_jurisprudencia_inicial(bt, "user-1", "socio")
    assert jobs == []
    assert bt.tasks == []


def test_jurisprudencia_inicial_agenda_por_fonte_e_tema(monkeypatch):
    from app.services.juris_import import FONTES

    ativas = [slug for slug, f in FONTES.items() if f.get("enabled")]
    if not ativas:  # ambiente com JURIS_IMPORT_FONTES vazio
        pytest.skip("nenhuma fonte habilitada neste ambiente")
    bt = BackgroundTasks()
    jobs = sc.agendar_jurisprudencia_inicial(bt, "user-1", "socio")
    assert len(jobs) == len(ativas) * len(sc.TEMAS_JURISPRUDENCIA_INICIAL)
    assert len(bt.tasks) == len(jobs)
    assert all(j["fonte"] in ativas for j in jobs)


def test_jurisprudencia_inicial_nunca_levanta(monkeypatch):
    # Import interno quebrado → função retorna [] (best-effort), sem exceção.
    import app.services.juris_import as ji

    monkeypatch.delattr(ji, "FONTES")
    bt = BackgroundTasks()
    jobs = sc.agendar_jurisprudencia_inicial(bt, None, None)
    assert jobs == []


# ── Degradação de flag (integração desligada ≠ 500) ─────────────────────────

async def test_datajud_desligado_erro_tipado(monkeypatch):
    from app.services import datajud_service

    monkeypatch.setattr(datajud_service.settings, "DATAJUD_ENABLED", False)
    with pytest.raises(datajud_service.DataJudDesabilitadoError):
        await datajud_service.consultar_movimentos("0000000-00.2024.8.13.0024")


def test_rota_seed_montada_com_gate_de_role():
    from app.main import app as fastapi_app

    rota = next(
        (r for r in fastapi_app.routes
         if getattr(r, "path", "") == "/api/rag/seed" and "POST" in getattr(r, "methods", set())),
        None,
    )
    assert rota is not None, "POST /api/rag/seed não montada"
    # o gate socio+ entra como dependência require_roles no endpoint
    import inspect
    dep_names = [
        getattr(p.default, "dependency", None).__qualname__
        for p in inspect.signature(rota.endpoint).parameters.values()
        if getattr(getattr(p.default, "dependency", None), "__qualname__", None)
    ]
    assert any("require_roles" in n for n in dep_names)
