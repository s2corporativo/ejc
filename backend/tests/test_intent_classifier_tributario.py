from app.services.ai.core.intent_classifier import classify_intent

# task_type propositalmente fora de _TASK_PARA_AGENTE/_TAREFA_PARA_AGENTE e
# domain=None: força a resolução a cair no fallback por keyword da mensagem.
_TASK = "mensagem_livre_sem_mapeamento"


def _agente(mensagem: str) -> str:
    return classify_intent(_TASK, None, mensagem).agente


def test_ibs_cbs_e_lc_214_roteiam_para_tax_law_agent():
    assert _agente("Qual o impacto do IBS na minha empresa?") == "TaxLawAgent"
    assert _agente("Preciso entender a CBS na reforma") == "TaxLawAgent"
    assert _agente("Dúvida sobre a LC 214") == "TaxLawAgent"
    assert _agente("Isso é regulado pela Lei Complementar 214") == "TaxLawAgent"
    assert _agente("O que muda com o imposto seletivo?") == "TaxLawAgent"
    assert _agente("Como funciona o split payment?") == "TaxLawAgent"


def test_ibs_cbs_nao_casam_como_substring_de_outra_palavra():
    """Sem fronteira de palavra, "ibs"/"cbs" casariam com qualquer termo que os
    contivesse — falso positivo que tiraria a mensagem do agente correto
    (aqui, cai no CaseAgent default por não ter nenhuma keyword real)."""
    assert _agente("Preciso de ajuda com o cbsistema de cobrança") == "CaseAgent"
    assert _agente("O código ICBS não é um tributo real") == "CaseAgent"


def test_icms_bare_continua_roteando_tax_law_agent_como_palavra_inteira():
    assert _agente("Discussão sobre ICMS na operação") == "TaxLawAgent"
