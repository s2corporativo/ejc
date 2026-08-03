"""T-P0-3 — cobrança PIX: o BR Code precisa ser VÁLIDO, não só existir.

`routers/pix.py` monta o "copia e cola" no padrão EMV do Banco Central e não
tinha teste nenhum (`docs/auditoria-ejc/14-testes.md`, T-P0-3: "pix.py e
api_keys.py sem teste — dinheiro e credencial"). É o pior lugar para não haver
teste: um BR Code errado não estoura no servidor. Ele sai com 200, chega ao
cliente, e falha no aplicativo do banco — ou cobra o valor errado.

Estes testes conferem a ESTRUTURA, não a aparência: reparseiam o payload campo a
campo (`ID + tamanho + valor`) e recalculam o CRC. É o que o app do banco faz.

**Defeito encontrado ao escrever este arquivo** (corrigido no mesmo commit): uma
chave PIX com mais de ~82 caracteres fazia `_emv` emitir TRÊS dígitos no espaço
de dois (`01130aaa…`), deslocando a leitura de todo o resto do payload. O BR
Code saía estruturalmente corrompido, com HTTP 200. Agora a chave é validada
contra o limite do BCB (77, o do tipo e-mail) e a rota responde 422.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.pix import _crc16, cobranca, gerar_brcode


def _parse_emv(payload: str) -> list[tuple[str, str]]:
    """Refaz a leitura do app do banco: ID(2) + tamanho(2) + valor(tamanho).

    Levanta se a estrutura não fechar — que é exatamente o sintoma do defeito
    de comprimento. Um `assert` sobre substring não pegaria isso.
    """
    campos, i = [], 0
    while i < len(payload):
        idf = payload[i:i + 2]
        tamanho = payload[i + 2:i + 4]
        if not tamanho.isdigit():
            raise ValueError(
                f"tamanho não numérico em {idf!r} (posição {i}): {tamanho!r} — "
                "payload desalinhado"
            )
        n = int(tamanho)
        valor = payload[i + 4:i + 4 + n]
        if len(valor) != n:
            raise ValueError(f"campo {idf} declara {n} e entrega {len(valor)}")
        campos.append((idf, valor))
        i += 4 + n
    return campos


def _campo(payload: str, idf: str) -> str | None:
    return next((v for k, v in _parse_emv(payload) if k == idf), None)


# ── CRC ──────────────────────────────────────────────────────────────────────

def test_crc16_bate_com_o_vetor_canonico():
    """CRC-16/CCITT-FALSE — o que o BCB exige. O vetor de verificação do
    algoritmo é `check("123456789") == 0x29B1`; sem ele, "o CRC é consistente
    consigo mesmo" é tudo que um teste de ida e volta provaria."""
    assert _crc16("123456789") == "29B1"


def test_crc_do_payload_cobre_o_proprio_marcador_6304():
    """O CRC do BR Code é calculado SOBRE o payload já terminado em '6304' —
    inclusive esses quatro caracteres. Errar isso gera um código que o banco
    recusa, e o servidor nunca fica sabendo."""
    brcode = gerar_brcode("chave@teste.com", "Fulano", "Belo Horizonte", 10.5)
    assert brcode[-8:-4] == "6304"
    assert _crc16(brcode[:-4]) == brcode[-4:]


# ── Estrutura e valores ──────────────────────────────────────────────────────

def test_brcode_e_estruturalmente_valido_e_carrega_o_valor_certo():
    brcode = gerar_brcode("chave@teste.com", "Fulano de Tal", "Belo Horizonte",
                          valor=10.5, txid="COB123")
    campos = dict(_parse_emv(brcode))

    assert campos["00"] == "01"            # payload format indicator
    assert campos["52"] == "0000"          # merchant category code
    assert campos["53"] == "986"           # moeda: BRL
    assert campos["58"] == "BR"            # país
    assert campos["59"] == "Fulano de Tal"
    assert campos["60"] == "Belo Horizonte"

    # Valor com DUAS casas — "10.5" seria recusado; e é dinheiro.
    assert campos["54"] == "10.50"

    # Merchant Account Information: domínio do arranjo + a chave.
    assert campos["26"].startswith("0014br.gov.bcb.pix")
    assert "chave@teste.com" in campos["26"]


@pytest.mark.parametrize(
    "valor,esperado",
    [(1, "1.00"), (10.5, "10.50"), (0.99, "0.99"), (1234.567, "1234.57"),
     (1_000_000, "1000000.00")],
)
def test_valor_sempre_com_duas_casas(valor, esperado):
    assert _campo(gerar_brcode("k@t.com", "N", "C", valor), "54") == esperado


@pytest.mark.parametrize("valor", [None, 0, 0.0])
def test_sem_valor_o_campo_54_nao_existe(valor):
    """BR Code sem valor é o "PIX em que o pagador digita quanto" — previsto no
    padrão. O campo tem de estar AUSENTE, não zerado: `5405 0.00` obrigaria o
    cliente a pagar zero."""
    assert _campo(gerar_brcode("k@t.com", "N", "C", valor), "54") is None


def test_acentos_e_nome_longo_nao_quebram_o_payload():
    """Nome do recebedor: ASCII e no máximo 25 caracteres (limite do padrão).
    'Sociedade de Advogados Ção' com acento vira bytes que o banco não lê."""
    brcode = gerar_brcode(
        "k@t.com", "Escritório de Advocacia Conceição e Associados",
        "São João del-Rei", 10.0,
    )
    campos = dict(_parse_emv(brcode))
    assert campos["59"].isascii() and len(campos["59"]) <= 25
    assert campos["60"].isascii() and len(campos["60"]) <= 15
    assert campos["60"] == "Sao Joao del-Re"


def test_txid_e_sanitizado_para_alfanumerico():
    """O padrão só admite [A-Za-z0-9] no txid. Um traço ou barra vindo de um
    número de processo derrubaria a leitura."""
    brcode = gerar_brcode("k@t.com", "N", "C", 10.0, txid="0001234-56.2026/8.13")
    # Campo 62 é composto: contém o subcampo 05 (Reference Label = txid).
    dentro = dict(_parse_emv(_campo(brcode, "62")))
    assert dentro["05"] == "00012345620268 13".replace(" ", "")[:25]
    assert dentro["05"].isalnum(), dentro["05"]


def test_nome_vazio_cai_em_placeholder_valido():
    """Campo 59 é obrigatório no padrão — vazio invalida o BR Code inteiro."""
    assert _campo(gerar_brcode("k@t.com", "", "", 10.0), "59") == "RECEBEDOR"
    assert _campo(gerar_brcode("k@t.com", "", "", 10.0), "60") == "CIDADE"


# ── O defeito que este arquivo encontrou ─────────────────────────────────────

def test_chave_longa_demais_e_recusada_em_vez_de_corromper_o_payload():
    """A regressão do defeito achado ao escrever estes testes.

    Com 130 caracteres, `_emv("01", chave)` emitia `01130…` — três dígitos no
    espaço de dois. O `_parse_emv` abaixo é o app do banco: com o payload
    desalinhado, ele não consegue nem ler o próximo ID.
    """
    chave_absurda = "a" * 120 + "@teste.com"
    with pytest.raises(ValueError) as exc:
        gerar_brcode(chave_absurda, "Fulano", "BH", 10.0)
    assert "77" in str(exc.value)  # o limite do BCB aparece na mensagem


def test_chave_no_limite_do_bcb_ainda_gera_payload_legivel():
    """77 caracteres é o limite do tipo e-mail — tem de PASSAR, e o payload
    resultante tem de continuar reparseável (o campo 26 fica com 97, perto do
    teto de 99 do EMV; é a borda que interessa)."""
    chave = "a" * 67 + "@teste.com"      # 77 caracteres exatos
    assert len(chave) == 77
    brcode = gerar_brcode(chave, "Fulano", "BH", 10.0)
    campos = dict(_parse_emv(brcode))     # não levanta = estrutura íntegra
    assert chave in campos["26"]
    assert _crc16(brcode[:-4]) == brcode[-4:]


async def test_endpoint_responde_422_para_chave_invalida_em_vez_de_200_corrompido():
    """O que o cliente do escritório via antes: HTTP 200 com um código que o
    banco recusa. A falha tem de aparecer em quem emite, não em quem paga."""
    with pytest.raises(HTTPException) as exc:
        await cobranca(
            {"chave": "a" * 200, "nome": "Escritório", "valor": 100.0}, cu=None
        )
    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"nome": "Fulano"},                            # sem chave
        {"chave": "k@t.com"},                          # sem nome
        {"chave": "k@t.com", "nome": "F", "valor": "dez reais"},   # valor inválido
    ],
)
async def test_endpoint_valida_a_entrada(body):
    with pytest.raises(HTTPException) as exc:
        await cobranca(body, cu=None)
    assert exc.value.status_code == 422


# ── RBAC ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "role,permitido",
    [("superadmin", True), ("admin", True), ("socio", True), ("financeiro", True),
     ("advogado", False), ("advogado_auxiliar", False), ("estagiario", False),
     ("secretaria", False), ("cliente_externo", False)],
)
def test_gerar_cobranca_e_ato_financeiro(role, permitido):
    """Emitir cobrança em nome do escritório é ato fiduciário — o piso é
    financeiro+gestão, não "qualquer interno". `advogado` fica de FORA de
    propósito: o espelho é `fees._req_financeiro_mutacao`, não o piso jurídico.
    """
    from types import SimpleNamespace

    from app.routers.pix import _req_financeiro

    cu = SimpleNamespace(role=SimpleNamespace(value=role))
    if permitido:
        assert _req_financeiro(cu) is cu
    else:
        with pytest.raises(HTTPException) as exc:
            _req_financeiro(cu)
        assert exc.value.status_code == 403
