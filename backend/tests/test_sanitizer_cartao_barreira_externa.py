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
    """A 2ª barreira reusa a MESMA entrada de `_PATTERNS`; ampliar tem de alcançá-la."""
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


# ── PAN AGRUPADO de 13 a 18 dígitos ─────────────────────────────────────────
# Segundo achado P1 do Codex sobre o MESMO ponto, um SHA depois. A ampliação
# anterior enumerou FORMATOS (contíguo, 4-4-4-4, 4-6-5) e por isso continuou
# deixando de fora todo agrupamento que não estivesse na lista:
#
#     'cartao 4222 2222 2222 2'    -> intacto,  residual=[]
#     'cartao 3782 822463 1000 5'  -> 'cartao 3782 [TELEFONE] 5'
#
# O segundo é o sintoma que o Achado 8 veio matar, reaparecendo: o padrão de
# TELEFONE (índice 5) roda antes do de cartão e morde o miolo do PAN.
#
# A correção troca "enumerar formato" por CONTAR DÍGITO (`_MatcherCartao`) e
# move o cartão para ANTES do telefone na lista — depois de CPF/CNPJ. Como a
# ordem passou a estar na própria `_PATTERNS`, todo consumidor herda a correção,
# inclusive o `ai/pseudonymizer.py`, que percorre a lista por conta própria.

@pytest.mark.parametrize(
    "descricao,numero",
    [
        ("13 agrupado 4-4-4-1", "4222 2222 2222 2"),
        ("13 com hifens", "4222-2222-2222-2"),
        ("15 agrupado 4-6-4-1", "3782 822463 1000 5"),
        ("16 agrupado", "4111 1111 1111 1111"),
        ("17 agrupado", "4111 1111 1111 1111 1"),
        ("18 agrupado", "4111 1111 1111 1111 12"),
        ("19 agrupado 4-4-4-4-3", "6011 1111 1111 1111 117"),
        ("19 com pontos", "6011.1111.1111.1111.117"),
    ],
)
def test_pan_agrupado_de_qualquer_comprimento(descricao: str, numero: str):
    limpo, _ = sanitizar_pii(f"cartao {numero}")
    assert "[CARTAO]" in limpo, f"{descricao} não mascarado: {limpo!r}"
    assert "[TELEFONE]" not in limpo, f"{descricao} virou telefone: {limpo!r}"
    for bloco in numero.replace("-", " ").replace(".", " ").split():
        assert bloco not in limpo, f"{descricao}: {bloco!r} vazou em {limpo!r}"


@pytest.mark.parametrize(
    "numero", ["4222 2222 2222 2", "3782 822463 1000 5", "4111 1111 1111 1111 12"],
)
def test_segunda_barreira_enxerga_pan_agrupado(numero: str):
    assert "CARTAO" in validar_sem_pii(f"numero {numero}")


@pytest.mark.parametrize(
    "texto",
    [
        "audiencias em 2026-08-22 2027-09-30",          # 16 dígitos em duas datas ISO
        "prazos 31-12-2026 01-01-2027 02-02-2028",
        "protocolado em 2026-08-22 05:27:28",
        "valor de R$ 1.234.567,89 corrigido",
        "CEP 30130-010 e CEP 31270-901",
    ],
)
def test_contagem_de_digitos_nao_engole_datas_nem_valores(texto: str):
    """A contagem só vale com o piso de 3 dígitos nos grupos intermediários:
    sem ele, duas datas vizinhas somam 13-19 dígitos e viram '[CARTAO]'."""
    limpo, _ = sanitizar_pii(texto)
    assert "[CARTAO]" not in limpo, f"mascarou indevidamente: {limpo!r}"


def test_cnpj_sem_pontuacao_continua_sendo_cnpj():
    """14 dígitos é o empate CNPJ × Diners. Na variante EXTERNA o CNPJ é
    mascarado no índice 1, antes da passada de cartão — o rótulo não pode
    trocar para [CARTAO], senão a pseudonimização reidrata errado."""
    limpo, _ = sanitizar_pii("CNPJ 12345678000190")
    assert "[CNPJ]" in limpo and "[CARTAO]" not in limpo


def test_variante_interna_mantem_cnpj_legivel():
    """`sanitizar_pii_interno` deixa CPF/CNPJ visíveis de propósito e nunca sai
    do VPS. A passada de cartão não pode capturar o CNPJ de 14 dígitos."""
    from app.services.sanitizer import sanitizar_pii_interno, validar_sem_pii_interno

    limpo, _ = sanitizar_pii_interno("CNPJ 12345678000190 e cartao 378282246310005")
    assert "12345678000190" in limpo, f"CNPJ deixou de ser legível: {limpo!r}"
    assert "[CARTAO]" in limpo and "378282246310005" not in limpo
    assert validar_sem_pii_interno(limpo) == []


def test_pseudonimizacao_tambem_cobre_pan_agrupado():
    """O pseudonymizer itera `_PATTERNS` por conta própria e está no caminho
    externo (`ai_gateway`). Sem a mesma passada, ficaria com a cobertura antiga."""
    from app.services.ai.pseudonymizer import pseudonimizar, reidratar

    original = "cartao 4222 2222 2222 2 do cliente"
    saida, mapa = pseudonimizar(original)
    assert "4222" not in saida, f"PAN vazou na pseudonimização: {saida!r}"
    # Reversível: o marcador tem de reidratar no PAN original, senão a resposta
    # do provider volta com o número trocado.
    assert reidratar(saida, mapa) == original


# ── Separador REPETIDO ──────────────────────────────────────────────────────
# 3ª revisão do Codex, e o terceiro furo neste mesmo ponto — sempre no
# DELIMITADOR, nunca na contagem. PAN copiado de PDF/OCR chega com espaço
# duplo, e `[\s.-]` (um só) não reconhecia o candidato:
#
#     'cartao 4111  1111  1111  1111'  -> intacto,  residual=[]
#
# `\s` inclui quebra de linha de propósito: PAN partido em duas linhas por OCR
# é caso real num sistema que recebe documento digitalizado.

@pytest.mark.parametrize(
    "descricao,numero",
    [
        ("espaço duplo", "4111  1111  1111  1111"),
        ("espaço triplo", "4111   1111   1111   1111"),
        ("separadores misturados", "4111 . 1111 - 1111  1111"),
        ("quebra de linha (OCR)", "4111\n1111 1111 1111"),
        ("hífen + espaço", "4111 - 1111 - 1111 - 1111"),
    ],
)
def test_pan_com_separador_repetido(descricao: str, numero: str):
    limpo, _ = sanitizar_pii(f"cartao {numero}")
    assert "[CARTAO]" in limpo, f"{descricao} não mascarado: {limpo!r}"
    assert "1111" not in limpo, f"{descricao}: dígitos vazaram em {limpo!r}"
    assert "CARTAO" in validar_sem_pii(f"numero {numero}")


@pytest.mark.parametrize(
    "texto",
    [
        "audiencias em 2026-08-22  2027-09-30",   # espaço duplo entre datas
        "prazos 31-12-2026 - 01-01-2027",
        "R$ 1.234.567,89  e  R$ 9.876.543,21",
    ],
)
def test_separador_repetido_nao_engole_datas(texto: str):
    """Tolerar separador repetido não pode custar a guarda contra datas: o piso
    de 3 dígitos nos grupos intermediários é o que continua segurando."""
    limpo, _ = sanitizar_pii(texto)
    assert "[CARTAO]" not in limpo, f"mascarou indevidamente: {limpo!r}"
