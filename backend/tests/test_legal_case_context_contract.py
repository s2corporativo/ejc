from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.legal_case_context import (
    SpecializedCaseContext,
    format_context_value,
    legal_area_context_label,
)


def test_specialized_case_context_e_contrato_neutro() -> None:
    ctx = SpecializedCaseContext(
        label="Cível/Consumidor",
        fields=(("Tipo", "consumidor"), ("Valor", "R$ 1.000,00")),
    )
    assert ctx.label == "Cível/Consumidor"
    assert ctx.source == "legacy_vertical"
    assert ctx.fields[0] == ("Tipo", "consumidor")


def test_formatacao_do_contexto_preserva_contrato_legado() -> None:
    assert format_context_value(None) == "—"
    assert format_context_value(True) == "Sim"
    assert format_context_value(False) == "Não"
    assert format_context_value(date(2026, 9, 25)) == "25/09/2026"
    assert format_context_value(SimpleNamespace(value="busca_apreensao")) == "busca apreensao"
    assert "1" in format_context_value(Decimal("1.00"))


def test_label_de_area_conhecida_independe_de_satelite() -> None:
    assert legal_area_context_label("consumidor") == "Cível/Consumidor"


def test_label_de_area_desconhecida_preserva_valor_original() -> None:
    assert legal_area_context_label("area_experimental") == "area_experimental"


def test_label_de_area_enum_like_preserva_contrato() -> None:
    assert legal_area_context_label(SimpleNamespace(value="consumidor")) == "Cível/Consumidor"
