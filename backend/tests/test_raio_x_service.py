from types import SimpleNamespace

from app.services.raio_x_service import consolidar_relatorio


def _documento(doc_id: str, resultado: dict):
    return SimpleNamespace(
        id=doc_id,
        nome_original=f"{doc_id}.pdf",
        tipo_documento="processo",
        sha256=f"hash-{doc_id}",
        resultado_analise=resultado,
    )


def test_consolidacao_mantem_prazos_como_potenciais_e_nao_confirmados():
    relatorio = consolidar_relatorio([
        _documento(
            "doc-1",
            {
                "intake_result": {
                    "cliente": "Cliente teste",
                    "numero_processo": "0000000-00.2026.8.00.0000",
                    "resumo_fatos": "Relato extraído do documento.",
                    "prazos": [
                        {
                            "titulo": "Prazo informado na peça",
                            "data": "21/07/2026",
                        }
                    ],
                }
            },
        )
    ])

    assert relatorio["confianca_global"] == "insuficiente_para_automatizacao"
    assert relatorio["prazos_potenciais"][0]["titulo"] == "Prazo informado na peça"
    assert relatorio["cronologia"][0]["data"] == "2026-07-21"
    assert relatorio["cronologia"][0]["confirmado"] is False
    assert "confirmação humana" in relatorio["aviso"]


def test_consolidacao_remove_repeticoes_e_preserva_fontes():
    resultado = {
        "intake_result": {
            "partes": ["Maria", "maria", "Empresa X"],
            "pedidos": ["Tutela", "Tutela"],
            "provas": ["Contrato"],
        }
    }
    relatorio = consolidar_relatorio([
        _documento("doc-1", resultado),
        _documento("doc-2", resultado),
    ])

    assert relatorio["partes"] == ["Maria", "Empresa X"]
    assert relatorio["pedidos"] == ["Tutela"]
    assert relatorio["provas"] == ["Contrato"]
    assert [fonte["documento_id"] for fonte in relatorio["fontes"]] == [
        "doc-1",
        "doc-2",
    ]
