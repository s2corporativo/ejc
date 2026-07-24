from app.services.rag_provenance import (
    StatusFonte,
    avaliar_status_fonte,
    normalizar_proveniencia,
)


def test_fonte_aprovada_e_revisada_e_confirmada():
    doc = {
        "id": "doc-1",
        "titulo": "Código de Processo Civil",
        "fonte": "https://www.planalto.gov.br/cpc",
        "vigente": True,
        "revisado": True,
        "extra": {"rag_status": "aprovado"},
    }

    status, motivos = avaliar_status_fonte(doc)

    assert status is StatusFonte.CONFIRMADA
    assert motivos == ["documento aprovado, revisado ou conferido"]


def test_fonte_nao_vigente_nao_pode_ser_promovida_a_confirmada():
    doc = {
        "id": "doc-2",
        "titulo": "Norma histórica",
        "fonte": "https://example.test/norma",
        "vigente": False,
        "revisado": True,
        "extra": {
            "rag_status": "aprovado",
            "proveniencia": {"status_fonte": "confirmada"},
        },
    }

    status, _ = avaliar_status_fonte(doc)

    assert status is StatusFonte.POSSIVELMENTE_DESATUALIZADA


def test_fonte_explicitamente_nao_localizada_permanece_bloqueada():
    doc = {
        "id": "doc-3",
        "titulo": "Precedente indicado pelo usuário",
        "vigente": True,
        "extra": {"proveniencia": {"fonte_localizada": False}},
    }

    status, _ = avaliar_status_fonte(doc)

    assert status is StatusFonte.NAO_LOCALIZADA


def test_fonte_sem_identificacao_e_marcada_como_insuficiente():
    status, motivos = avaliar_status_fonte({"id": "doc-4", "extra": {}})

    assert status is StatusFonte.IDENTIFICACAO_INSUFICIENTE
    assert "faltam título" in motivos[0]


def test_fonte_identificada_sem_revisao_fica_pendente():
    doc = {
        "id": "doc-5",
        "titulo": "Parecer interno",
        "fonte": "parecer.docx",
        "vigente": True,
        "revisado": False,
        "extra": {},
    }

    status, _ = avaliar_status_fonte(doc)

    assert status is StatusFonte.PENDENTE_CONFERENCIA


def test_normalizacao_expoe_proveniencia_sem_client_id():
    doc = {
        "id": "doc-6",
        "titulo": "Contestação modelo",
        "categoria": "precedente_interno",
        "fonte": "/arquivos/modelos/contestacao.docx",
        "chave_origem": "modelo:contestacao:1",
        "case_id": "case-1",
        "client_id": "client-secreto",
        "versao": 2,
        "vigente": True,
        "revisado": True,
        "hash_conteudo": "abc123",
        "extra": {
            "rag_status": "aprovado",
            "proveniencia": {
                "data_documento": "2026-07-01",
                "processo_origem": "0000000-00.2026.8.13.0000",
            },
        },
    }
    chunk = {
        "id": "chunk-1",
        "chunk_index": 3,
        "conteudo": "Trecho jurídico relevante com fundamentação e pedidos.",
        "metadata": {"pagina": 12},
    }

    resultado = normalizar_proveniencia(doc=doc, chunk=chunk, limite_trecho=20)

    assert resultado["documento_id"] == "doc-6"
    assert resultado["chunk_id"] == "chunk-1"
    assert resultado["nome_arquivo"] == "contestacao.docx"
    assert resultado["pagina"] == 12
    assert resultado["case_id"] == "case-1"
    assert resultado["processo_origem"] == "0000000-00.2026.8.13.0000"
    assert resultado["status_fonte"] == "confirmada"
    assert resultado["trecho"].endswith("…")
    assert "client_id" not in resultado
