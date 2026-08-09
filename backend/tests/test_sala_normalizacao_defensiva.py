"""Regressões das normalizações defensivas da Sala Jurídica (#890)."""
from app.models.legal_chat import LegalChatMessage, LegalChatSession
from app.models.legal_chat_normalization import (
    normalizar_area_sugerida,
    normalizar_citacoes,
)


def test_area_sugerida_aceita_slug_canonico_e_rejeita_valor_livre():
    assert normalizar_area_sugerida("civil") == "civil"
    assert normalizar_area_sugerida("trabalhista") == "trabalhista"
    assert normalizar_area_sugerida("direito-das-estrelas") is None
    assert normalizar_area_sugerida(123) is None
    assert normalizar_area_sugerida(None) is None


def test_listener_normaliza_area_nova_antes_de_chegar_ao_wizard():
    sessao = LegalChatSession(
        id="sessao-1",
        titulo="Teste",
        area_sugerida="area-inexistente",
        created_by="user-1",
    )
    assert sessao.area_sugerida is None

    sessao.area_sugerida = "ambiental"
    assert sessao.area_sugerida == "ambiental"


def test_citacoes_legadas_so_preservam_objetos():
    entrada = [
        "total",
        "confirmadas",
        None,
        3,
        {"trecho": "art. 5º", "status": "verificada"},
        {"tipo": "sumula", "status": "identificada"},
    ]
    assert normalizar_citacoes(entrada) == [
        {"trecho": "art. 5º", "status": "verificada"},
        {"tipo": "sumula", "status": "identificada"},
    ]
    assert normalizar_citacoes("total") == []
    assert normalizar_citacoes({"citacoes": []}) == []


def test_listener_impede_nova_persistencia_de_citacao_malformada():
    msg = LegalChatMessage(
        id="msg-1",
        session_id="sessao-1",
        autor="ia",
        modo="conversa_livre",
        conteudo="Resposta",
        citacoes=["total", {"trecho": "Lei X", "status": "verificada"}],
    )
    assert msg.citacoes == [{"trecho": "Lei X", "status": "verificada"}]
