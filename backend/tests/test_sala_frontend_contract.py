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
    # P0-473: a classificação usa o validador com DV (utils/documento), que
    # rejeita comprimento inválido em vez de truncar — nunca voltar ao
    # fatiamento por comprimento (slice/length ternário).
    assert "classificarDocumento" in SOURCE
    assert "clientDocument" in SOURCE
    assert ".slice(0, 14)" not in SOURCE
    assert 'documento.tipo === "cpf" ? documento.cpf : null' in SOURCE
    assert 'documento.tipo === "cnpj" ? documento.cnpj : null' in SOURCE


def test_sala_exibe_achados_antes_da_confirmacao():
    assert "Possíveis casos duplicados" in SOURCE
    assert "Alertas de conflito" in SOURCE
    assert "Possíveis clientes correspondentes" in SOURCE
