from app.services.dossie_documental_canonico import (
    VERSAO_DOSSIE_DOCUMENTAL,
    construir_dossie_documental_canonico,
)


def _item(
    *,
    document_id: str,
    sha256: str,
    filename: str,
    source_order: int,
    texto: str,
    batch_id: str = "lote-1",
    pagina: int = 1,
    versao: int = 1,
    versao_grupo_id: str | None = None,
    versao_vigente: bool = True,
) -> dict:
    return {
        "batch_id": batch_id,
        "batch_created_at": "2026-07-31T10:00:00+00:00",
        "document_created_at": "2026-07-31T10:00:00+00:00",
        "document_id": document_id,
        "filename": filename,
        "source_order": source_order,
        "sha256": sha256,
        "extraction_status": "concluido",
        "classification": {"tipo": "prova_documental"},
        "versao": versao,
        "versao_grupo_id": versao_grupo_id,
        "versao_vigente": versao_vigente,
        "extraction_meta": {
            "paginas": [
                {
                    "pagina": pagina,
                    "texto": texto,
                    "confianca": 0.98,
                    "metodo": "texto_nativo",
                    "requer_revisao": False,
                }
            ]
        },
    }


def test_dossie_preserva_texto_literal_e_rastreabilidade_da_fonte():
    resultado = construir_dossie_documental_canonico(
        [
            _item(
                document_id="doc-1",
                sha256="a" * 64,
                filename="contrato.pdf",
                source_order=1,
                texto="Cláusula literal preservada sem reescrita.",
            )
        ]
    )

    assert resultado["versao"] == VERSAO_DOSSIE_DOCUMENTAL
    assert resultado["qtd_documentos"] == 1
    assert resultado["qtd_paginas_com_texto"] == 1
    assert "Cláusula literal preservada sem reescrita." in resultado["texto_contexto"]
    assert "documento_id=doc-1" in resultado["texto_contexto"]
    assert f"sha256_original={'a' * 64}" in resultado["texto_contexto"]
    assert resultado["fontes"][0]["pagina"] == 1
    assert len(resultado["fontes"][0]["sha256_texto_extraido"]) == 64


def test_selo_canonico_independe_da_ordem_de_entrada():
    primeiro = _item(
        document_id="doc-1",
        sha256="1" * 64,
        filename="primeiro.pdf",
        source_order=1,
        texto="Primeiro fato documental.",
    )
    segundo = _item(
        document_id="doc-2",
        sha256="2" * 64,
        filename="segundo.pdf",
        source_order=2,
        texto="Segundo fato documental.",
    )

    resultado_a = construir_dossie_documental_canonico([segundo, primeiro])
    resultado_b = construir_dossie_documental_canonico([primeiro, segundo])

    assert resultado_a["sha256_manifesto"] == resultado_b["sha256_manifesto"]
    assert resultado_a["manifesto"] == resultado_b["manifesto"]
    assert resultado_a["texto_contexto"] == resultado_b["texto_contexto"]


def test_documento_repetido_por_hash_preserva_copia_sem_duplicar_o_fato():
    original = _item(
        document_id="doc-original",
        sha256="f" * 64,
        filename="prova.pdf",
        source_order=1,
        texto="Fato existente em um único original.",
    )
    duplicado = _item(
        document_id="doc-duplicado",
        sha256="f" * 64,
        filename="copia-prova.pdf",
        source_order=2,
        texto="Fato existente em um único original.",
    )

    resultado = construir_dossie_documental_canonico([original, duplicado])

    assert resultado["qtd_documentos"] == 2
    assert resultado["duplicados_omitidos"] == 1
    assert resultado["manifesto"][1]["duplicado_de_documento_id"] == "doc-original"
    assert resultado["texto_contexto"].count("Fato existente em um único original.") == 1
    assert "CÓPIA DOCUMENTAL" in resultado["texto_contexto"]


def test_historico_de_versoes_permanece_no_manifesto():
    versao_1 = _item(
        document_id="doc-v1",
        sha256="d" * 64,
        filename="contrato-v1.pdf",
        source_order=1,
        texto="Redação contratual original.",
        versao=1,
        versao_grupo_id="grupo-contrato",
        versao_vigente=False,
    )
    versao_2 = _item(
        document_id="doc-v2",
        sha256="e" * 64,
        filename="contrato-v2.pdf",
        source_order=2,
        texto="Redação contratual substitutiva.",
        versao=2,
        versao_grupo_id="grupo-contrato",
        versao_vigente=True,
    )

    resultado = construir_dossie_documental_canonico([versao_2, versao_1])

    assert [doc["versao"] for doc in resultado["manifesto"]] == [1, 2]
    assert resultado["manifesto"][0]["versao_vigente"] is False
    assert resultado["manifesto"][1]["versao_vigente"] is True
    assert "Redação contratual original." in resultado["texto_contexto"]
    assert "Redação contratual substitutiva." in resultado["texto_contexto"]


def test_interpretacao_de_ia_nao_entra_no_manifesto_canonico():
    item = _item(
        document_id="doc-1",
        sha256="b" * 64,
        filename="auto.pdf",
        source_order=1,
        texto="Em 10/01/2026 foi lavrado o auto número 123.",
    )
    item["analise_ia"] = {
        "resumo_executivo": {"fatos": "Conclusão não confirmada da IA."},
        "estrategia": {"objetivo": "Anular o ato."},
    }

    resultado = construir_dossie_documental_canonico([item])

    assert "Conclusão não confirmada da IA." not in resultado["texto_contexto"]
    assert "Anular o ato." not in resultado["texto_contexto"]
    assert "Em 10/01/2026 foi lavrado o auto número 123." in resultado["texto_contexto"]


def test_truncamento_do_contexto_nao_altera_o_selo_do_manifesto():
    item = _item(
        document_id="doc-1",
        sha256="c" * 64,
        filename="processo.pdf",
        source_order=1,
        texto="conteúdo documental " * 100,
    )

    curto = construir_dossie_documental_canonico([item], limite_texto=300)
    amplo = construir_dossie_documental_canonico([item], limite_texto=10_000)

    assert curto["truncado"] is True
    assert amplo["truncado"] is False
    assert curto["sha256_manifesto"] == amplo["sha256_manifesto"]
    assert "CONTEÚDO DOCUMENTAL TRUNCADO" in curto["texto_contexto"]
