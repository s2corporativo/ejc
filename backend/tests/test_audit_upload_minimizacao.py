"""Minimização LGPD dos metadados de auditoria de upload."""

from app.models.audit_log import _minimizar_payload_upload


def test_upload_preserva_ids_e_substitui_detalhes_por_contagens():
    entrada = {
        "documentos": ["doc-1", "doc-2"],
        "duplicados": ["CPF-12345678900.pdf"],
        "erros": [
            {"arquivo": "Joao-Silva-processo-0001.pdf", "erro": "Formato não suportado"},
            {"arquivo": "Maria.pdf", "erro": "Arquivo vazio"},
        ],
    }
    saida = _minimizar_payload_upload(entrada)

    assert saida == {
        "documentos": ["doc-1", "doc-2"],
        "duplicados_count": 1,
        "erros_count": 2,
    }
    assert "CPF-12345678900.pdf" not in repr(saida)
    assert "Joao-Silva" not in repr(saida)


def test_upload_formato_inesperado_falha_fechado_sem_persistir_valor():
    saida = _minimizar_payload_upload(
        {"duplicados": "nome-sensivel.pdf", "erros": {"arquivo": "cpf.pdf"}}
    )
    assert saida == {"duplicados_count": 1, "erros_count": 1}


def test_payload_nao_e_mutado():
    entrada = {"duplicados": ["nome.pdf"]}
    _minimizar_payload_upload(entrada)
    assert entrada == {"duplicados": ["nome.pdf"]}
