"""Regressões de semântica profissional do PDF fiscal — Issue #1553."""
from app.routers.tributario_fiscal import ConsolidacaoOut, _html_relatorio


def _payload() -> ConsolidacaoOut:
    return ConsolidacaoOut.model_validate({
        "regime": "lucro_real",
        "total_estimado": 44.40,
        "notas_analisadas": 1,
        "notas_com_erro": 0,
        "notas_prescritas": 0,
        "periodo": {"inicio": "2019-05-01", "fim": "2019-05-01"},
        "teses": [{
            "tese_id": "tema_69_stf",
            "titulo": "Tema 69 STF",
            "base_legal": "RE 574.706/PR",
            "fundamento": "Radar documental para revisão humana.",
            "aplicavel": True,
            "motivo_inaplicavel": None,
            "valor_estimado": 44.40,
            "memoria_calculo": ["Estimativa matemática de teste."],
            "alertas": ["Elegibilidade não avaliada."],
            "nivel_confianca": "estimativa_preliminar",
        }],
        "alertas_globais": [
            "PRESCRIÇÃO NÃO AVALIADA: a emissão da NF-e não é termo inicial universal."
        ],
        "aviso_hitl": "Pré-auditoria; revisão humana obrigatória.",
        "notas": [],
    })


def test_pdf_rotula_resultado_como_pre_auditoria_e_nao_credito_reconhecido() -> None:
    html = _html_relatorio(_payload())
    upper = html.upper()

    assert "PRÉ-AUDITORIA TRIBUTÁRIA POR XML" in upper
    assert "PRESCRIÇÃO: NÃO AVALIADA" in upper
    assert "SINAL TÉCNICO COMPATÍVEL COM O RADAR" in upper
    assert "ESTIMATIVA MATEMÁTICA" in upper
    assert "DIAGNÓSTICO DE RECUPERAÇÃO DE CRÉDITOS" not in upper
    assert "NOTA(S) PRESCRITA(S)" not in upper
    assert ">APLICÁVEL<" not in upper
    assert ">INAPLICÁVEL<" not in upper
