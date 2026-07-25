"""Guardas estáticas do fluxo crítico Sala → caso.

O teste é deliberadamente simples e bloqueante: evita regressão para UUID técnico,
uso do endpoint legado e envio indistinto de CNPJ como CPF.
"""
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "pages"
    / "SalaAnaliseJuridica.tsx"
).read_text(encoding="utf-8")


def test_sala_usa_nucleo_unico_de_ia():
    assert 'api.post("/ai/core/analyze"' in SOURCE
    assert 'api.post("/ai/analisar-caso"' not in SOURCE
    assert 'surface: "sala_analise"' in SOURCE


def test_sala_nao_pede_uuid_tecnico_do_cliente():
    assert "ID do cliente" not in SOURCE
    assert "Pesquisar cliente autorizado" in SOURCE
    assert 'api.get("/clients"' in SOURCE


def test_sala_classifica_documento_pf_pj():
    assert "digits.length <= 11 ? digits : null" in SOURCE
    assert "digits.length > 11 ? digits : null" in SOURCE
    assert "clientDocument" in SOURCE


def test_sala_exibe_achados_antes_da_confirmacao():
    assert "Possíveis casos duplicados" in SOURCE
    assert "Alertas de conflito" in SOURCE
    assert "Possíveis clientes correspondentes" in SOURCE
