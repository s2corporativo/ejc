import io
import zipfile

import pytest

from app.services.entrada_universal_service import (
    EXTENSOES_SUPORTADAS,
    avaliar_prontidao,
    classificar_documento,
    comparar_documentos,
    expandir_zip,
    manifesto_pacote,
)


def _zip(entries: dict[str, bytes]) -> bytes:
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, raw in entries.items():
            zf.writestr(name, raw)
    return buff.getvalue()


def _item(tipo: str, nome: str = "doc.pdf", confianca: float = 0.95, texto: str = "") -> dict:
    return {
        "filename": nome,
        "extraction_status": "concluido",
        "classification": {"tipo": tipo},
        "extraction_meta": {
            "confianca_media": confianca,
            "paginas": [{"pagina": 1, "texto": texto, "confianca": confianca}],
        },
    }


def test_catalogo_de_formatos_universal_inclui_legados_fotos_planilhas_e_zip():
    obrigatorios = {".pdf", ".docx", ".doc", ".jpg", ".heic", ".heif", ".xlsx", ".xls", ".csv", ".zip"}
    assert obrigatorios.issubset(EXTENSOES_SUPORTADAS)


def test_expandir_zip_preserva_documentos_suportados():
    raw = _zip({"contrato.docx": b"doc", "fotos/local.jpg": b"jpg"})
    itens = expandir_zip("dossie.zip", raw)
    assert [item["nome"] for item in itens] == ["contrato.docx", "local.jpg"]
    assert all(item["origem_zip"] == "dossie.zip" for item in itens)


def test_expandir_zip_rejeita_path_traversal_e_zip_aninhado():
    with pytest.raises(ValueError, match="caminho inseguro"):
        expandir_zip("dossie.zip", _zip({"../segredo.pdf": b"x"}))
    with pytest.raises(ValueError, match="ZIP aninhado"):
        expandir_zip("dossie.zip", _zip({"outro.zip": b"x"}))


def test_classificacao_especializada_por_modalidade():
    transito = classificar_documento(
        "notificacao.pdf",
        "NOTIFICAÇÃO DE PENALIDADE. Recurso à JARI. Código da infração e RENAVAM.",
        "multa_transito",
    )
    bancario = classificar_documento(
        "cedula.pdf",
        "Cédula de crédito bancário. Custo efetivo total CET, taxa de juros e IOF.",
        "revisao_bancaria",
    )
    assert transito["tipo"] in {"notificacao_transito", "auto_infracao_transito", "documento_veiculo_condutor"}
    assert bancario["tipo"] in {"contrato_bancario", "cet_tarifas_seguros"}
    assert transito["metodo"] == "regras_locais"


def test_prontidao_bloqueia_sem_documentos_obrigatorios():
    resultado = avaliar_prontidao("revisao_bancaria", [_item("contrato_bancario")])
    assert resultado["nivel"] == "nao_apto_para_redacao"
    assert "Planilha de evolução da dívida e extratos" in resultado["documentos_faltantes"]


def test_prontidao_fica_apta_com_todos_documentos_e_ocr_confiavel():
    itens = [
        _item("contrato_bancario"),
        _item("evolucao_divida"),
        _item("parcelas_pagas"),
        _item("cet_tarifas_seguros"),
    ]
    resultado = avaliar_prontidao("revisao_bancaria", (item for item in itens))
    assert resultado["nivel"] == "apto_para_redacao"
    assert resultado["documentos_faltantes"] == []


def test_prontidao_com_baixa_confianca_exige_ressalva():
    itens = [
        _item("contrato_original", confianca=0.4),
        _item("execucao_pagamentos"),
    ]
    resultado = avaliar_prontidao("revisao_contratual", itens)
    assert resultado["nivel"] == "apto_com_ressalvas"
    assert "doc.pdf" in resultado["arquivos_baixa_qualidade"]


def test_comparacao_detecta_placas_e_percentuais_divergentes():
    itens = [
        _item("contrato_original", "original.pdf", texto="Placa ABC1D23. Multa de 10%."),
        _item("aditivo_contratual", "aditivo.pdf", texto="Placa XYZ9Z99. Multa de 30%."),
    ]
    tipos = {item["tipo"] for item in comparar_documentos(itens)}
    assert "divergencia_placas" in tipos
    assert "percentuais_divergentes" in tipos


def test_manifesto_tem_dez_itens_e_bloqueia_peca_quando_nao_apto():
    manifesto = manifesto_pacote("multa_transito", {"nivel": "nao_apto_para_redacao"})
    assert len(manifesto) == 10
    peca = next(item for item in manifesto if item["codigo"] == "peca_principal")
    assert peca["status"] == "bloqueado"
