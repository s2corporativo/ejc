from app.services.raio_x_export_service import gerar_docx, gerar_pdf


REPORT = {
    "aviso": "Análise preliminar sujeita à revisão humana.",
    "identificacao": {"numero_processo": "0000000-00.2026.8.00.0000", "area": "civil"},
    "sintese_executiva": "Síntese do processo.",
    "partes": ["Maria", "Empresa X"],
    "cronologia": [{"data": "2026-07-10", "evento": "Distribuição"}],
    "fatos_provas": [{"fato": "Fato", "estado": "correlacao_pendente"}],
    "pedidos": ["Pedido principal"],
    "decisoes": [],
    "contradicoes": [],
    "prazos_potenciais": [],
    "riscos": ["Risco probatório"],
    "pontos_fortes": [],
    "pontos_fracos": ["Documento pendente"],
    "proximos_passos": ["Revisar documentos"],
    "rito_jornada": {"nome": "Procedimento Comum Cível"},
    "fontes": [{"arquivo": "processo.pdf"}],
}


def test_gera_docx_valido():
    content = gerar_docx("Caso de teste", REPORT)
    assert content[:2] == b"PK"
    assert len(content) > 1000


def test_gera_pdf_valido():
    content = gerar_pdf("Caso de teste", REPORT)
    assert content.startswith(b"%PDF")
    assert len(content) > 500
