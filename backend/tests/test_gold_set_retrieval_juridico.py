# ── tests/test_gold_set_retrieval_juridico.py ────────────────────────────────
# Integridade OFFLINE (sem banco, sem LLM) do gold set jurídico de retrieval
# (app/eval/gold_set_retrieval_juridico.jsonl). Roda no CI normal — NÃO exige
# RUN_DB_TESTS. É a garantia anti-invenção: cada item do gold set aponta para
# uma fonte REAL e ATIVA já semeável na base (súmula do SUMULAS_SEED ou diploma
# do planalto.CATALOGO), com título/chave/categoria EXATAMENTE iguais aos que os
# seeders gravam. Se alguém marcar uma súmula como superada/cancelada, remover um
# diploma do catálogo ou renomear um título, este teste falha — o gold set nunca
# fica apontando para algo que o RAG não pode recuperar.
from __future__ import annotations

import pytest

from app.eval.retrieval_juridico_eval import carregar
from app.services.sumulas_ingestion import SUMULAS_SEED, _titulo


def _seed_por_chave() -> dict[str, dict]:
    idx = {}
    for s in SUMULAS_SEED:
        trib = s.get("tribunal", "").lower()
        num = str(s.get("numero") or s.get("numero_vinculante", ""))
        idx[f"sumula:{trib}:{num}"] = s
    return idx


GOLD = carregar()
SEED_IDX = _seed_por_chave()


def test_gold_set_tem_tamanho_de_baseline():
    """Baseline curado: 10–20 itens (recomendação do GUIA de curadoria)."""
    assert 10 <= len(GOLD) <= 20, f"gold set tem {len(GOLD)} itens (esperado 10–20)"


def test_ids_unicos_e_campos_obrigatorios():
    ids = [it.get("id") for it in GOLD]
    assert len(ids) == len(set(ids)), "há id duplicado no gold set"
    for it in GOLD:
        assert str(it.get("id") or "").strip(), "item sem id"
        assert str(it.get("query") or "").strip(), f"{it.get('id')}: query vazia"
        assert it.get("expected_titulos"), f"{it.get('id')}: expected_titulos vazio"
        assert str(it.get("chave_origem_esperada") or "").strip(), \
            f"{it.get('id')}: sem chave_origem_esperada (necessária p/ gate de presença)"
        assert it.get("fonte_seed") in ("sumulas_seed", "planalto_catalogo"), \
            f"{it.get('id')}: fonte_seed inválida"


def test_itens_de_sumula_referenciam_verbete_real_e_ATIVO():
    """Cada item de súmula casa com um verbete do SUMULAS_SEED que está ATIVO
    (situacao='ativa' → indexado no RAG) e cujo título/chave/categoria batem
    EXATAMENTE com o que ingerir_sumulas_seed grava."""
    itens = [it for it in GOLD if it.get("fonte_seed") == "sumulas_seed"]
    assert itens, "gold set sem itens de súmula"
    for it in itens:
        chave = it["chave_origem_esperada"]
        s = SEED_IDX.get(chave)
        assert s is not None, f"{it['id']}: chave {chave} não existe no SUMULAS_SEED"
        assert s.get("situacao", "ativa") == "ativa", (
            f"{it['id']}: súmula {chave} está '{s.get('situacao')}' — NÃO é indexada no "
            f"RAG; remova/troque este item do gold set")
        assert it["expected_titulos"][0] == _titulo(s), (
            f"{it['id']}: título {it['expected_titulos'][0]!r} != título semeado "
            f"{_titulo(s)!r}")
        trib = s["tribunal"].lower()
        assert it.get("expected_categorias") == [f"sumula_{trib}"], (
            f"{it['id']}: categoria esperada != sumula_{trib}")


def test_itens_de_lei_referenciam_diploma_real_do_catalogo():
    """Cada item de lei casa com um diploma do planalto.CATALOGO (slug, título e
    categoria 'legislacao' exatos). Import guardado: bs4 é dependência do
    ingestor; sem ela o bloco de leis é pulado (o de súmulas continua valendo)."""
    pytest.importorskip("bs4")
    from app.services.ingestors.planalto import CATALOGO, CATEGORIA, PREFIXO_CHAVE

    por_slug = {d["slug"]: d for d in CATALOGO}
    itens = [it for it in GOLD if it.get("fonte_seed") == "planalto_catalogo"]
    for it in itens:
        chave = it["chave_origem_esperada"]
        assert chave.startswith(PREFIXO_CHAVE), f"{it['id']}: chave {chave} sem prefixo do planalto"
        slug = chave[len(PREFIXO_CHAVE):]
        d = por_slug.get(slug)
        assert d is not None, f"{it['id']}: slug {slug!r} não existe no CATALOGO"
        assert it["expected_titulos"][0] == d["titulo"], (
            f"{it['id']}: título {it['expected_titulos'][0]!r} != título do catálogo {d['titulo']!r}")
        assert it.get("expected_categorias") == [CATEGORIA], (
            f"{it['id']}: categoria esperada != {CATEGORIA}")
