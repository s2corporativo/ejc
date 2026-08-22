from app.models.legal_thesis_bank import (
    LegalPrecedent,
    LegalSource,
    LegalSourceSnapshot,
    LegalThesis,
)
from app.services.legal_thesis_bank_service import (
    contar_status,
    hash_conteudo,
    normalizar_chave,
    precedente_pode_ser_recomendado,
    tese_pode_ser_recomendada,
    validar_dominios_tese,
)


def test_hash_de_conteudo_e_idempotente_para_espacos():
    assert hash_conteudo("  fraude   bancária\n em PIX ") == hash_conteudo("fraude bancária em PIX")
    assert len(hash_conteudo("conteúdo")) == 64


def test_normalizacao_de_chave_remove_acentos_e_separadores():
    assert normalizar_chave("Consumidor / Negativação Indevida") == "consumidor-negativacao-indevida"


def test_tese_so_e_recomendavel_quando_vigente_e_validada():
    assert tese_pode_ser_recomendada("validada") is True
    assert tese_pode_ser_recomendada("revisada") is True
    assert tese_pode_ser_recomendada("coletada") is False
    assert tese_pode_ser_recomendada("validada", vigente=False) is False


def test_precedente_exige_url_publicidade_e_minimizacao():
    assert precedente_pode_ser_recomendado("validado", "https://tribunal.example/julgado") is True
    assert precedente_pode_ser_recomendado("identificado", "https://tribunal.example/julgado") is False
    assert precedente_pode_ser_recomendado("validado", None) is False
    assert precedente_pode_ser_recomendado("validado", "https://tribunal.example/julgado", "restrito") is False
    assert precedente_pode_ser_recomendado("validado", "https://tribunal.example/julgado", dados_minimizados=False) is False


def test_validacao_de_dominio_da_tese_e_explicita():
    assert validar_dominios_tese("validada", "ataque", "processual", 80) == []
    assert validar_dominios_tese("inexistente", "lado", "tipo", 101) == [
        "status inválido: inexistente",
        "lado inválido: lado",
        "tipo inválido: tipo",
        "score_forca deve estar entre 0 e 100",
    ]


def test_contagem_de_status_nao_e_probabilidade():
    assert contar_status(["validada", "revisada", "validada"]) == {
        "validada": 2,
        "revisada": 1,
    }


def test_metadata_registra_as_entidades_canonicas():
    assert {
        LegalSource.__tablename__,
        LegalSourceSnapshot.__tablename__,
        LegalPrecedent.__tablename__,
        LegalThesis.__tablename__,
    } <= set(LegalThesis.metadata.tables)


def test_rotas_do_banco_nacional_exigem_usuario_autenticado():
    from app.main import app

    rotas = [
        rota
        for rota in app.routes
        if rota.path.startswith("/api/banco-nacional-teses")
        and rota.methods.intersection({"GET", "POST", "PATCH", "DELETE"})
    ]
    assert len(rotas) == 12
    for rota in rotas:
        nomes = set()
        pendentes = list(getattr(rota, "dependant", None).dependencies or [])
        while pendentes:
            dependencia = pendentes.pop()
            chamada = getattr(dependencia, "call", None)
            if chamada is not None:
                nomes.add(getattr(chamada, "__name__", type(chamada).__name__))
            pendentes.extend(getattr(dependencia, "dependencies", None) or [])
        assert "get_current_user" in nomes, rota.path
