from __future__ import annotations

from pathlib import Path

from app.schemas.entrada import CriarCasoEntradaRequest, ProcessoConfirmadoEntrada

ROOT = Path(__file__).resolve().parents[1]


def test_schema_aceita_metadados_processuais_confirmados():
    processo = ProcessoConfirmadoEntrada(
        numero_cnj="50000008320268130027",
        tribunal="TJMG",
        comarca="Betim",
        vara="1ª Vara",
    )
    assert processo.tribunal == "TJMG"


def test_criacao_expoe_bloco_processo_confirmado_opcional():
    campo = CriarCasoEntradaRequest.model_fields["processo_confirmado"]
    assert campo.default is None


def test_service_exige_mesmo_cnj_do_rascunho_e_preserva_metadados():
    src = (ROOT / "app" / "services" / "entrada_service.py").read_text(
        encoding="utf-8"
    )
    assert "numero_confirmado != numero_rascunho" in src
    assert '"tribunal": payload.processo_confirmado.tribunal' in src
    assert '"comarca": payload.processo_confirmado.comarca' in src
    assert '"vara": payload.processo_confirmado.vara' in src
    assert '"fonte": "Entrada Única — metadados confirmados pelo advogado"' in src
