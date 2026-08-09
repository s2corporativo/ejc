import pytest
from pydantic import ValidationError

from app.modules.dpt360.intake_schemas import DptInboundOpportunity


def test_acionejus_permanece_bloqueado_nesta_integracao():
    with pytest.raises(ValidationError):
        DptInboundOpportunity(
            origem="acionejus",
            assunto="Encaminhamento",
            mensagem="Demanda recebida pela plataforma para triagem.",
        )


def test_site_aceita_metadados_de_origem_sem_criar_cliente():
    payload = DptInboundOpportunity(
        origem="site_depaulateixeira",
        pagina="/empresarial",
        campanha="empresarial-360",
        assunto="Consultoria regulatória",
        mensagem="Empresa deseja avaliação inicial de riscos regulatórios.",
        email=" CONTATO@EXEMPLO.COM ",
        consentimento_privacidade=True,
        urgencia_declarada="alta",
    )
    assert payload.email == "contato@exemplo.com"
    assert payload.origem == "site_depaulateixeira"
    assert payload.urgencia_declarada == "alta"


def test_email_invalido_e_rejeitado_sem_dependencia_externa():
    with pytest.raises(ValidationError):
        DptInboundOpportunity(
            origem="manual",
            assunto="Lead empresarial",
            mensagem="Demanda suficiente para ser encaminhada à triagem.",
            email="email-invalido",
        )
