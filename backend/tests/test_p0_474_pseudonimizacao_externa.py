"""P0-474 — prova negativa: nomes próprios não atravessam o gateway.

Texto com pessoa física, empresa (razão social), advogado com OAB e
logradouro deve sair 100% pseudonimizado; o mapa reverso reidrata local.
A rede de segurança (nome de alta confiança em claro → bloqueio do
provider externo) é verificada no cenário de escape.
"""
from __future__ import annotations

from app.services.ai.ner_local import detectar_empresas, detectar_nomes
from app.services.ai.pseudonymizer import (
    pseudonimizar,
    reidratar,
    validar_sem_pii_pseudonimizado,
)

_TEXTO = (
    "A vítima Ana Paula Ferreira relatou que a Transportadora Veloz Ltda "
    "não efetuou o pagamento. O advogado Dr. Marcos Lima, OAB/MG 123.456, "
    "informou que a autora reside na Rua das Acácias, nº 123, e apresentou "
    "o CPF 529.982.247-25 como comprovante de identidade."
)


def test_nenhum_nome_atravessa_o_gateway():
    resultado, mapa = pseudonimizar(_TEXTO)

    # Prova negativa: nada identificável sobrevive em claro.
    assert "Ana Paula Ferreira" not in resultado
    assert "Transportadora Veloz" not in resultado
    assert "Marcos Lima" not in resultado
    assert "123.456" not in resultado          # inscrição OAB
    assert "Acácias" not in resultado          # logradouro
    assert "529.982.247-25" not in resultado   # CPF

    # Marcadores estáveis presentes (relação preservada para o modelo).
    assert "[PESSOA_" in resultado
    assert "[EMPRESA_" in resultado
    assert "[OAB_" in resultado
    assert "[ENDERECO_" in resultado
    assert "[CPF_" in resultado

    # Segunda barreira: nada residual — o texto PODE ir ao provider externo.
    assert validar_sem_pii_pseudonimizado(resultado) == []

    # Mapa reverso reidrata localmente (round-trip completo).
    reidratado = reidratar(resultado, mapa)
    assert "Ana Paula Ferreira" in reidratado
    assert "Transportadora Veloz Ltda" in reidratado
    assert "Rua das Acácias" in reidratado


def test_mapa_reverso_nunca_vai_no_texto():
    resultado, mapa = pseudonimizar(_TEXTO)
    for valor_real in mapa.values():
        assert valor_real not in resultado


def test_nome_que_escapa_dispara_fail_closed():
    # Simula falha da pseudonimização: nome de ALTA confiança em claro.
    texto_cru = "A testemunha Carla Mendes confirmou o ocorrido."
    residual = validar_sem_pii_pseudonimizado(texto_cru)
    assert "PESSOA" in residual  # gateway PULA o provider externo


def test_detectar_empresas_exige_sufixo_societario():
    assert detectar_empresas("A Transportadora Veloz Ltda entregou.") == [
        "Transportadora Veloz Ltda"
    ]
    # Sem sufixo não detecta (nome-fantasia vem via cadastro de entidades).
    assert detectar_empresas("A empresa entregou a carga combinada.") == []


def test_marcadores_nao_sao_redetectados():
    # Idempotência: rodar duas vezes não gera dupla marcação.
    uma_vez, _ = pseudonimizar(_TEXTO)
    duas_vezes, mapa2 = pseudonimizar(uma_vez)
    assert duas_vezes == uma_vez
    assert mapa2 == {}


def test_pessoas_detectadas_no_texto_de_referencia():
    nomes = detectar_nomes(_TEXTO)
    assert "Ana Paula Ferreira" in nomes
    assert "Marcos Lima" in nomes


def test_regressao_cliente_com_nome_do_escritorio_e_pseudonimizado():
    # Bug pré-existente: "paula"/"teixeira" na stoplist por token solto faziam
    # clientes como "Ana Paula Ferreira" escapar da pseudonimização.
    assert "Ana Paula Ferreira" in detectar_nomes(
        "A autora Ana Paula Ferreira ajuizou a ação."
    )
    assert "José Teixeira Filho" in detectar_nomes(
        "O réu José Teixeira Filho foi citado."
    )
    # A identidade do escritório (controlador) segue fora da pseudonimização.
    assert detectar_nomes(
        "Escritório De Paula Teixeira Advogados, por Clovis José Soares."
    ) == []
