"""Contrato de ingestão segura para `origem_conteudo=modelo_simulado`."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "backend" / "scripts" / "ingestao_biblioteca_juridica.py"
_SPEC = importlib.util.spec_from_file_location("ingestao_biblioteca_modelo_simulado", _SCRIPT)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)


def _modelo(**overrides):
    doc = {
        "tipo_camada": "modelo_peca",
        "canonical_id": "MOD-SIM-000001",
        "origem_conteudo": "modelo_simulado",
        "autoridade_juridica": "modelo_sem_autoridade",
        "authority_level": "modelo_sem_autoridade",
        "score_autoridade": 0,
        "area_juridica": "tributario",
        "nivel_confiaca": "BAIXA",
        "data_pesquisa": "2026-08-19",
        "gerado_por_IA": True,
        "__file": "fixture-modelo.md",
        "__body": "MODELO SIMULADO. Não citar como jurisprudência.",
        "__raw": "---\ntipo_camada: modelo_peca\n---\ncorpo",
    }
    doc.update(overrides)
    return doc


def test_modelo_simulado_valido_e_aceito_pelo_validador() -> None:
    assert "modelo_simulado" in MOD.ORIGEM_VOCAB
    assert MOD.validar([_modelo()]) == []


def test_modelo_simulado_nao_pode_ter_autoridade_ou_score() -> None:
    erros = MOD.validar([
        _modelo(
            autoridade_juridica="jurisprudencial",
            authority_level="jurisprudencia_oficial",
            score_autoridade=90,
        )
    ])
    texto = "\n".join(erros).lower()
    assert "autoridade" in texto
    assert "score_autoridade=0" in texto
    assert "authority_level" in texto


def test_modelo_simulado_exige_marcacao_de_ia() -> None:
    erros = MOD.validar([_modelo(gerado_por_IA=False)])
    assert any("gerado_por_IA=true" in erro for erro in erros)


def test_modelo_simulado_exige_tipo_modelo_peca() -> None:
    erros = MOD.validar([_modelo(tipo_camada="tese_juridica")])
    assert any("tipo_camada=modelo_peca" in erro for erro in erros)


def test_extra_preserva_autoridade_zero_e_revisao_humana() -> None:
    extra = MOD.build_extra(_modelo())
    assert extra["origem_conteudo"] == "modelo_simulado"
    assert extra["autoridade_juridica"] == "modelo_sem_autoridade"
    assert extra["authority_level"] == "modelo_sem_autoridade"
    assert extra["score_autoridade"] == 0
    assert extra["nivel_confiaca"] == "BAIXA"
    assert extra["rag_status"] == "pendente"
    assert extra["requires_human_review"] is True
    assert extra["human_reviewed"] is False


def test_upsert_mapeia_confianca_baixa_sem_elevacao() -> None:
    fonte = inspect.getsource(MOD.main)
    assert '"ALTA": "alta"' in fonte
    assert '"MEDIA": "media"' in fonte
    assert '"BAIXA": "baixa"' in fonte
    assert '"alta" if d.get("nivel_confiaca") == "ALTA" else "media"' not in fonte


def test_23_modelos_reais_do_lote_passam_validacao_governada() -> None:
    base = ROOT / "docs" / "biblioteca_juridica"
    modelos = []
    for path in sorted(base.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = MOD.strip_frontmatter(raw)
        if meta.get("origem_conteudo") != "modelo_simulado":
            continue
        meta["__file"] = str(path)
        meta["__body"] = body
        meta["__raw"] = raw
        modelos.append(meta)

    assert len(modelos) == 23
    assert MOD.validar(modelos) == []
