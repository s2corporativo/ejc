"""Regressão de roteamento por keyword dos ramos jurídicos (IA-04).

Trava os 2 misroutes BAIXOS achados na auditoria de segurança dos 8 novos
agentes (correção de roteamento por substring — ordem em _KEYWORDS_PARA_AGENTE
é first-match-wins):

1. "cláusula penal" (instituto contratual, CC arts. 408-416) NÃO pode cair no
   CriminalLawAgent por casar a keyword crua "penal".
2. Tokens curtos por substring: "transito" cru casava "disposições transitórias".

classify_intent é 100% determinístico (sem LLM), então estes casos são estáveis.
"""
from app.services.ai.core.intent_classifier import classify_intent


def _agente(mensagem: str) -> str:
    return classify_intent(task_type="", domain=None, mensagem=mensagem).agente


def test_clausula_penal_nao_vai_para_criminal():
    # ContractLawAgent foi retirado na consolidação 38→8 (2026-09-06); o
    # desempate contra "penal" cru segue necessário e cai no CaseAgent.
    assert _agente("preciso revisar a cláusula penal do contrato") == "CaseAgent"


def test_disposicoes_transitorias_nao_caem_em_transito():
    # "transito" cru (substring de "transitórias") foi removido das keywords.
    assert _agente("análise das disposições transitórias") != "TrafficLawAgent"


def test_mensagem_criminal_pura_continua_criminal():
    assert _agente("denúncia criminal, ação penal contra o réu") == "CriminalLawAgent"


def test_erro_medico_com_dano_moral_vai_para_civil():
    # MedicalLawAgent foi retirado na consolidação 38→8 (2026-09-06):
    # responsabilidade médica é espécie de responsabilidade civil (art. 951
    # CC) e as keywords foram dobradas sobre CivilLawAgent.
    assert _agente("erro médico com dano moral") == "CivilLawAgent"
