# ── tests/test_extracao_estruturada.py ───────────────────────────────────────
# Extração determinística (Fase 3A): CNJ, CPF/CNPJ com DV, datas, valores,
# e-mails, telefones. Sem IA, sem banco — puro.
from app.services.extracao_estruturada import (
    extrair_estruturas,
    validar_cnpj,
    validar_cpf,
)


# ── CPF ──────────────────────────────────────────────────────────────────────

def test_cpf_valido():
    assert validar_cpf("529.982.247-25")
    assert validar_cpf("52998224725")


def test_cpf_invalido_dv():
    assert not validar_cpf("529.982.247-26")   # DV errado
    assert not validar_cpf("12345678900")


def test_cpf_invalido_repetido_ou_tamanho():
    assert not validar_cpf("111.111.111-11")   # dígitos repetidos
    assert not validar_cpf("1234567890")       # 10 dígitos
    assert not validar_cpf("")


# ── CNPJ ─────────────────────────────────────────────────────────────────────

def test_cnpj_valido():
    assert validar_cnpj("11.222.333/0001-81")
    assert validar_cnpj("11222333000181")
    # CNPJ real do escritório (config ESCRITORIO_CNPJ)
    assert validar_cnpj("32.491.468/0001-12")


def test_cnpj_invalido():
    assert not validar_cnpj("11.222.333/0001-82")  # DV errado
    assert not validar_cnpj("00.000.000/0000-00")  # repetido
    assert not validar_cnpj("1122233300018")       # 13 dígitos


# ── Extração integrada ───────────────────────────────────────────────────────

TEXTO = (
    "Processo nº 0001234-56.2024.8.13.0027, autor João (CPF 529.982.247-25), "
    "ré Empresa X (CNPJ 11.222.333/0001-81). Audiência em 15/03/2024, "
    "citação em 2 de janeiro de 2024. Condenação de R$ 15.000,00 mais "
    "honorários de R$ 1.500,50. Contato: joao@example.com, (31) 99999-8888."
)


def test_extrai_processo_cnj():
    res = extrair_estruturas(TEXTO)
    assert [o["valor"] for o in res["processos_cnj"]] == ["0001234-56.2024.8.13.0027"]


def test_extrai_cpf_e_cnpj_validados():
    res = extrair_estruturas(TEXTO)
    assert [o["valor"] for o in res["cpfs"]] == ["529.982.247-25"]
    assert [o["valor"] for o in res["cnpjs"]] == ["11.222.333/0001-81"]


def test_cpf_com_dv_invalido_nao_e_extraido():
    res = extrair_estruturas("CPF do réu: 111.444.777-00 (inválido)")
    assert res["cpfs"] == []


def test_extrai_datas_numericas_e_por_extenso():
    res = extrair_estruturas(TEXTO)
    valores = [o["valor"] for o in res["datas"]]
    assert "15/03/2024" in valores
    assert "2 de janeiro de 2024" in valores


def test_extrai_valores_monetarios():
    res = extrair_estruturas(TEXTO)
    valores = [o["valor"] for o in res["valores"]]
    assert "R$ 15.000,00" in valores
    assert "R$ 1.500,50" in valores


def test_extrai_email_e_telefone():
    res = extrair_estruturas(TEXTO)
    assert [o["valor"] for o in res["emails"]] == ["joao@example.com"]
    assert any("99999-8888" in o["valor"] for o in res["telefones"])


def test_posicoes_apontam_para_o_trecho():
    res = extrair_estruturas(TEXTO)
    for tipo in ("processos_cnj", "cpfs", "cnpjs", "datas", "valores",
                 "emails", "telefones"):
        for o in res[tipo]:
            assert TEXTO[o["inicio"]:o["fim"]] == o["valor"]


def test_cpf_dentro_de_cnj_nao_vaza():
    # Os 11 primeiros dígitos de um nº CNJ não devem virar "CPF"
    res = extrair_estruturas("Autos 5001234-11.2023.8.13.0024 sem partes.")
    assert res["cpfs"] == []
    assert len(res["processos_cnj"]) == 1


def test_texto_vazio_e_total():
    res = extrair_estruturas("")
    assert res["total"] == 0
    res2 = extrair_estruturas(TEXTO)
    assert res2["total"] == sum(
        len(res2[k]) for k in res2 if k != "total"
    )


def test_resultado_json_serializavel():
    import json
    json.dumps(extrair_estruturas(TEXTO))
