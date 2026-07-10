from app.models.rag import KnowledgeDoc
from app.services.rag_drive_reclassifier import (
    _build_resultado,
    classificar_doc_rag_drive,
    is_google_drive_doc,
)


def _doc(**kwargs):
    base = {
        "id": "doc-1",
        "titulo": "Indulto 2024 PRD - Extinção de puniblidade.docx",
        "categoria": "doutrina",
        "chave_origem": "gdrive:file-1",
        "vigente": True,
        "extra": {
            "source": "google_drive",
            "drive": {
                "name": "Indulto 2024 PRD - Extinção de puniblidade.docx",
                "path": "geral/PEÇAS PRÁTICAS EM PENAL",
                "full_path": "geral/PEÇAS PRÁTICAS EM PENAL/Indulto 2024 PRD - Extinção de puniblidade.docx",
                "mime_type_original": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
        },
    }
    base.update(kwargs)
    return KnowledgeDoc(**base)


def test_reconhece_doc_google_drive_por_extra_ou_chave():
    assert is_google_drive_doc(_doc()) is True
    assert is_google_drive_doc(_doc(extra={}, chave_origem="gdrive:abc")) is True
    assert is_google_drive_doc(_doc(extra={}, chave_origem="manual:abc")) is False


def test_classifica_doc_drive_legado_como_modelo_juridico():
    doc = _doc()
    decisao = classificar_doc_rag_drive(doc)
    assert decisao.categoria == "modelo_documento_juridico"
    assert decisao.area_juridica == "penal_execucao"
    resultado = _build_resultado(doc, decisao, apply=False)
    assert resultado.categoria_atual == "doutrina"
    assert resultado.categoria_final == "modelo_documento_juridico"
    assert resultado.alteraria is True
    assert resultado.aplicado is False


def test_arquivo_teste_seria_retirado_da_vigencia_sem_excluir():
    doc = _doc(
        titulo="teste_ejc_drive.txt",
        categoria="doutrina",
        extra={
            "source": "google_drive",
            "drive": {
                "name": "teste_ejc_drive.txt",
                "path": "geral",
                "full_path": "geral/teste_ejc_drive.txt",
                "mime_type_original": "text/plain",
            },
        },
    )
    decisao = classificar_doc_rag_drive(doc)
    resultado = _build_resultado(doc, decisao, apply=True)
    assert decisao.excluir is True
    assert resultado.categoria_final == "nao_indexar"
    assert resultado.vigente_atual is True
    assert resultado.vigente_final is False
    assert resultado.aplicado is True
