"""Regressão — lacunas da barreira de PII achadas na auditoria do núcleo de IA
(03/10/2026), confirmadas por sonda empírica: cada formato abaixo seguia EM
CLARO para provider externo e a 2ª barreira (`validar_sem_pii`) respondia
"sem PII residual", porque reusa as mesmas entradas de `_PATTERNS`.

Cobre as três superfícies que consomem `_PATTERNS`: mascaramento
(`sanitizar_pii`), 2ª barreira (`validar_sem_pii`) e pseudonimização
reversível (caminho padrão do gateway para provider externo).
"""
from __future__ import annotations

import pytest

from app.services.ai.pseudonymizer import (
    pseudonimizar,
    reidratar,
    validar_sem_pii_pseudonimizado,
)
from app.services.sanitizer import (
    sanitizar_pii,
    sanitizar_pii_interno,
    validar_sem_pii,
)

# (rótulo, texto, valor que NÃO pode sobreviver)
VAZAMENTOS = [
    # IN RFB nº 2.229/2024 — exemplo oficial da Receita (DV 35 confere).
    ("cnpj_alfanumerico_mascarado", "CNPJ 12.ABC.345/01DE-35", "12.ABC.345/01DE-35"),
    ("cnpj_alfanumerico_compacto", "CNPJ 12ABC34501DE35", "12ABC34501DE35"),
    ("cpf_com_espacos", "CPF 123 456 789 09", "123 456 789 09"),
    ("cep_pontuado", "CEP 30.130-010", "30.130-010"),
    ("celular_sem_ddd", "ligar 99999-9999", "99999-9999"),
    ("rg_com_uf", "identidade MG-12.345.678", "12.345.678"),
    ("rg_rotulo_identidade", "carteira de identidade nº 12.345.678", "12.345.678"),
    ("titulo_eleitor", "título de eleitor 1234 5678 9012", "1234 5678 9012"),
    ("pis", "PIS 123.45678.90-1", "123.45678.90-1"),
    ("agencia", "agência 1234-5", "1234-5"),
    ("conta", "conta corrente 12345-6", "12345-6"),
    # NIA-08
    ("placa_mercosul", "veículo placa ABC1D23", "ABC1D23"),
    ("placa_antiga_rotulada", "placa: ABC-1234", "ABC-1234"),
    ("passaporte", "passaporte FZ123456", "FZ123456"),
    ("processo_pre_cnj", "processo 0024.12.345678-9", "0024.12.345678-9"),
]


@pytest.mark.parametrize("rotulo,texto,valor", VAZAMENTOS, ids=[v[0] for v in VAZAMENTOS])
def test_mascaramento_remove_formato(rotulo, texto, valor):
    limpo, houve = sanitizar_pii(texto)
    assert valor not in limpo, f"{rotulo}: {limpo!r}"
    assert houve


@pytest.mark.parametrize("rotulo,texto,valor", VAZAMENTOS, ids=[v[0] for v in VAZAMENTOS])
def test_segunda_barreira_detecta_formato_em_claro(rotulo, texto, valor):
    assert validar_sem_pii(texto), f"{rotulo}: 2ª barreira não viu {valor!r}"


@pytest.mark.parametrize("rotulo,texto,valor", VAZAMENTOS, ids=[v[0] for v in VAZAMENTOS])
def test_pseudonimizacao_remove_e_reidrata(rotulo, texto, valor):
    pseudo, mapa = pseudonimizar(texto)
    assert valor not in pseudo, f"{rotulo}: {pseudo!r}"
    assert validar_sem_pii_pseudonimizado(pseudo) == []
    assert reidratar(pseudo, mapa) == texto


def test_cnpj_alfanumerico_com_dv_invalido_e_sem_mascara_nao_e_mascarado():
    """Código alfanumérico qualquer de 14 posições não vira [CNPJ]: sem a
    máscara oficial, só mascara se o DV conferir (evita over-masking)."""
    texto = "lote 12ABC34501DE99"
    assert sanitizar_pii(texto)[0] == texto


def test_cnpj_numerico_legado_preservado():
    assert sanitizar_pii("CNPJ 11.222.333/0001-81")[0] == "CNPJ [CNPJ]"
    assert sanitizar_pii("CNPJ 11222333000181")[0] == "CNPJ [CNPJ]"


def test_variante_interna_mantem_cnpj_alfanumerico_visivel():
    """Uso interno (nunca sai do VPS) mantém CPF/CNPJ legíveis por decisão de
    2026-07-04 — vale também para o formato alfanumérico."""
    texto = "CNPJ 12.ABC.345/01DE-35"
    assert sanitizar_pii_interno(texto)[0] == texto


@pytest.mark.parametrize("texto", [
    "vigência 2024-2025 do contrato",          # intervalo de anos
    "Lei 9.605/1998, art. 54",                 # diploma legal
    "valor de R$ 12.345.678,90",               # montante
    "a conta foi paga em 2 parcelas",          # palavra "conta" sem número
    "Súmula 297 do STJ",
    "certificação ISO-9001 da empresa",        # placa antiga só com rótulo
])
def test_sem_falso_positivo_em_texto_juridico_comum(texto):
    assert sanitizar_pii(texto)[0] == texto
    assert validar_sem_pii(texto) == []


# ── NIA-02 — formas abreviadas das entidades do caso ─────────────────────────
_ENT = {"cliente": ["Ana Paula Souza"], "parte_contraria": ["Banco Exemplo S.A."]}


def test_razao_social_sem_sufixo_recebe_o_mesmo_marcador():
    texto = "O Banco Exemplo S.A. negativou a cliente; depois, o Banco Exemplo cobrou."
    pseudo, mapa = pseudonimizar(texto, _ENT)
    assert "Banco Exemplo" not in pseudo
    assert pseudo.count("[PARTE_CONTRARIA_1]") == 2
    assert mapa["[PARTE_CONTRARIA_1]"] == "Banco Exemplo S.A."


def test_prenome_e_ultimo_sobrenome_recebem_o_mesmo_marcador():
    texto = "Ana Paula Souza ajuizou a ação. Ana Souza juntou os extratos."
    pseudo, mapa = pseudonimizar(texto, _ENT)
    assert "Ana Souza" not in pseudo
    assert pseudo.count("[CLIENTE_1]") == 2
    assert mapa["[CLIENTE_1]"] == "Ana Paula Souza"


def test_variante_nao_morde_nome_completo_de_outra_entidade():
    ent = {"cliente": ["Ana Paula Souza"], "parte_contraria": ["Ana Souza Lima"]}
    pseudo, mapa = pseudonimizar("Ana Souza Lima contestou.", ent)
    assert pseudo == "[PARTE_CONTRARIA_1] contestou."


def test_prenome_isolado_nao_e_mascarado_por_variante():
    """Prenome/sobrenome isolado fica fora de propósito (calibragem pendente):
    "Vitória" também é palavra comum do texto jurídico."""
    ent = {"cliente": ["Vitória Maria Santos"]}
    pseudo, _ = pseudonimizar("a vitória da tese foi parcial", ent)
    assert "vitória" in pseudo
