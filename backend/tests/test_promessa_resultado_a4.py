"""A-4 (auditoria IA 2026-07-17): deteccao de promessa de resultado (vedacao OAB)
cobre parafrases de garantia, alem da palavra 'garantia'. E ALERTA, nunca reescrita."""
from app.services.ai.core.response_validator import detectar_promessa_resultado


def test_detecta_garantia_explicita():
    assert detectar_promessa_resultado("O exito e garantido neste caso.")
    assert detectar_promessa_resultado("Temos 100% de chance de sucesso.")


def test_detecta_parafrases_de_garantia():
    # Novas parafrases cobertas pelo A-4 (fillers curtos + tolerancia a acento).
    for txt in [
        "O resultado esta assegurado.",
        "Trata-se de vitoria garantida.",
        "Nao ha como perder essa acao.",
        "As chances sao altissimas.",
        "Risco zero de derrota.",
        "Com certeza vamos ganhar.",
    ]:
        assert detectar_promessa_resultado(txt), f"nao detectou: {txt}"


def test_detecta_promessa_numerica_de_resultado():
    # Auditoria IA 2026-07-18: percentual de resultado prometido ao cliente
    # tambem e vedado (OAB art. 34 / Prov. 205), em qualquer ordem.
    for txt in [
        "90% de exito garantido ao cliente.",
        "Voce tem chance de 95% de ganhar essa acao.",
        "A probabilidade de vitoria e de 92%.",
        "Estimo 88% de procedencia do pedido.",
        "O caso esta praticamente ganho.",
        "E praticamente certo que venceremos.",
    ]:
        assert detectar_promessa_resultado(txt), f"nao detectou promessa numerica: {txt}"


def test_nao_dispara_em_analise_neutra():
    # Linguagem juridica prudente NAO deve disparar (evita ruido de HITL).
    for txt in [
        "Ha jurisprudencia favoravel, mas o resultado depende da prova.",
        "As chances de exito sao razoaveis, com riscos a considerar.",
        "Recomenda-se cautela na conducao do caso.",
    ]:
        assert not detectar_promessa_resultado(txt), f"falso positivo: {txt}"
