# -*- coding: utf-8 -*-
"""Cartão de crédito não pode escapar da barreira que antecede provider externo.

Achado da auditoria funcional de 22/08/2026 (Issue #1237), na verificação das
proteções não negociáveis do CLAUDE.md (regra 4: "jamais enviar PII não
sanitizada para provedor externo").

`_sanitizar_messages_externo` é a última barreira antes de Anthropic/Groq e a
sua docstring promete mascarar "CPF/CNPJ/processo/RG/e-mail/telefone/CEP/
cartão/PIX". O cartão não estava coberto na prática:

    entrada   "cartao 4111 1111 1111 1111"
    saída     "cartao 41[TELEFONE] 1111"      <- 6 dígitos em claro
    residual  []                              <- e a 2ª barreira dizia "limpo"

Duas causas somadas:

1. Os padrões são aplicados **em ordem** e TELEFONE (índice 5) vem antes de
   CARTAO (índice 7). O padrão de telefone não tinha guarda à esquerda, então
   casava "11 1111 1111" no MEIO do cartão, quebrava a sequência e impedia o
   padrão de cartão de casar. Sobravam "41" e "1111" em claro — rotulados como
   telefone.
2. `validar_sem_pii`, a segunda barreira, checava os índices 0-6, 9 e 10 —
   **sem** CARTAO (7) nem CHAVE_PIX (8). Um cartão ou chave PIX residual era
   reportado como "nenhuma PII residual".

Reordenar a lista não era opção: o arquivo marca os índices 0-6 como
referenciados por `validar_sem_pii`, e `sanitizar_pii_interno` fatia `[2:]`.
A correção foi uma guarda `(?<!\\d)` no padrão de telefone (mesma posição) e a
inclusão dos dois tipos faltantes na segunda barreira.

Cartão em processo não é hipótese remota: ação de consumo sobre fraude,
contestação de compra e revisão de contrato bancário trazem o número no
documento.
"""
from __future__ import annotations

import pytest

from app.services.sanitizer import sanitizar_pii, validar_sem_pii

CARTAO = "4111 1111 1111 1111"


@pytest.mark.parametrize(
    "numero",
    ["4111 1111 1111 1111", "4111111111111111", "4111-1111-1111-1111",
     "4111.1111.1111.1111"],
)
def test_cartao_e_mascarado_por_inteiro(numero: str):
    """Nenhum trecho de 4 dígitos do cartão pode sobreviver."""
    limpo, _ = sanitizar_pii(f"pagamento no cartao {numero}")
    assert "[CARTAO]" in limpo
    for bloco in numero.replace("-", " ").replace(".", " ").split():
        assert bloco not in limpo, f"trecho {bloco!r} do cartão vazou: {limpo!r}"


def test_cartao_nao_e_rotulado_como_telefone():
    """O sintoma exato do defeito: "41[TELEFONE] 1111"."""
    limpo, _ = sanitizar_pii(f"cartao {CARTAO}")
    assert "[TELEFONE]" not in limpo
    assert limpo.strip() == "cartao [CARTAO]"


def test_segunda_barreira_enxerga_cartao_residual():
    """`validar_sem_pii` precisa acusar cartão — antes retornava lista vazia."""
    assert "CARTAO" in validar_sem_pii(f"numero {CARTAO}")


def test_segunda_barreira_enxerga_chave_pix_residual():
    """CHAVE_PIX (índice 8) também faltava na segunda barreira."""
    uuid = "123e4567-e89b-12d3-a456-426614174000"
    assert "CHAVE_PIX" in validar_sem_pii(f"chave pix {uuid}")


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("tel (31) 98888-7777", "[TELEFONE]"),
        ("contato +55 31 98888-7777", "[TELEFONE]"),
        ("fixo (31) 3222-1111", "[TELEFONE]"),
    ],
)
def test_telefone_continua_sendo_mascarado(texto: str, esperado: str):
    """A guarda `(?<!\\d)` não pode custar a detecção de telefone real."""
    limpo, _ = sanitizar_pii(texto)
    assert esperado in limpo
    assert "8888" not in limpo and "3222" not in limpo


def test_barreira_final_do_gateway_nao_deixa_residuo():
    """Percurso real: é isto que segue para Anthropic/Groq."""
    from app.services.ai_gateway import _sanitizar_messages_externo

    msgs = [{"role": "user", "content":
             f"Cliente com CPF 529.982.247-25 contesta compra no cartao {CARTAO}, "
             "telefone (31) 98888-7777, e-mail cliente@exemplo.com.br."}]
    limpos, residual = _sanitizar_messages_externo(msgs)
    enviado = limpos[0]["content"]
    assert residual == [], f"PII residual rumo ao provider externo: {residual}"
    for vazamento in ("4111", "1111", "529.982.247-25", "98888",
                      "cliente@exemplo.com.br"):
        assert vazamento not in enviado, f"{vazamento!r} vazou: {enviado!r}"


# ── Comprimentos de cartão além de 16 dígitos ───────────────────────────────
# Achado P1 da revisão do Codex em 2026-08-22 (PR #1238), e é REGRESSÃO da
# correção acima. O padrão de cartão exigia exatamente 16 dígitos; um PAN de
# outro comprimento (AmEx 15, Visa antigo 13, Maestro 19) só era mascarado por
# ACIDENTE — pelo padrão de TELEFONE mordendo o final dele. Ao pôr a guarda
# `(?<!\d)` no telefone, o acidente sumiu e o PAN passou a atravessar INTEIRO:
#
#     antes da 1ª correção   "cartao 37828[TELEFONE]"      <- 5 dígitos em claro
#     depois dela            "cartao 378282246310005"      <- 15 em claro
#     residual               []                            <- 2ª barreira cega
#
# Corrigir 16 dígitos e piorar os outros comprimentos é pior do que não ter
# mexido: a barreira passou a mentir com mais confiança.

@pytest.mark.parametrize(
    "bandeira,numero",
    [
        ("AmEx 15 sem separador", "378282246310005"),
        ("AmEx 15 agrupado 4-6-5", "3782 822463 10005"),
        ("AmEx 15 com hifens", "3782-822463-10005"),
        ("Visa antigo 13", "4222222222222"),
        ("Visa 16", "4111111111111111"),
        ("Maestro 19", "6011111111111111117"),
        ("Visa 19 agrupado", "4111 1111 1111 1111 123"),
    ],
)
def test_cartao_de_qualquer_comprimento_e_mascarado(bandeira: str, numero: str):
    """13 a 19 dígitos: nenhum trecho pode sobreviver rumo ao provider externo."""
    limpo, _ = sanitizar_pii(f"cartao {numero}")
    assert "[CARTAO]" in limpo, f"{bandeira} não foi mascarado: {limpo!r}"
    for bloco in numero.replace("-", " ").replace(".", " ").split():
        assert bloco not in limpo, f"{bandeira}: {bloco!r} vazou em {limpo!r}"


@pytest.mark.parametrize(
    "numero", ["378282246310005", "4222222222222", "6011111111111111117"],
)
def test_segunda_barreira_enxerga_cartao_de_outros_comprimentos(numero: str):
    """A 2ª barreira reusa `_PATTERNS[7]`; ampliar o padrão tem de alcançá-la."""
    assert "CARTAO" in validar_sem_pii(f"numero {numero}")


@pytest.mark.parametrize(
    "texto",
    [
        "audiencia designada para 31-12-2026 01-01-2027",
        "protocolado em 2026-08-22 05:27:28",
        "valor atualizado de R$ 1.234.567,89",
        "prazo de 15 dias uteis, arts. 219 e 220 do CPC",
    ],
)
def test_nao_mascara_data_nem_valor_como_cartao(texto: str):
    """Sobra-mascarar também custa: data de audiência é o dado mais sensível
    de uma peça, e duas datas vizinhas somam 16 dígitos. Por isso o separador é
    OBRIGATÓRIO nas alternativas agrupadas do padrão."""
    limpo, _ = sanitizar_pii(texto)
    assert "[CARTAO]" not in limpo, f"mascarou indevidamente: {limpo!r}"


def test_barreira_final_do_gateway_com_amex():
    """Mesmo percurso real do teste acima, agora com AmEx de 15 dígitos."""
    from app.services.ai_gateway import _sanitizar_messages_externo

    msgs = [{"role": "user", "content":
             "Consumidor contesta compra no cartao 378282246310005 "
             "feita em 31-12-2026, telefone (31) 98888-7777."}]
    limpos, residual = _sanitizar_messages_externo(msgs)
    enviado = limpos[0]["content"]
    assert residual == [], f"PII residual rumo ao provider externo: {residual}"
    assert "378282246310005" not in enviado, f"PAN AmEx vazou: {enviado!r}"
    assert "3782" not in enviado and "10005" not in enviado
    # a data da compra não pode ter sido engolida junto
    assert "31-12-2026" in enviado, f"data virou cartão: {enviado!r}"
