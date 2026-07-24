from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.ai_proveniencia import (
    ProvenienciaJuridica,
    RespostaJuridicaRastreavel,
    ResumoConfiabilidadeFontes,
    StatusConferenciaFonte,
    TipoFonteJuridica,
)


def test_metadados_removem_pii_e_segredos_em_qualquer_nivel() -> None:
    fonte = ProvenienciaJuridica(
        tipo_fonte=TipoFonteJuridica.OUTRA,
        nome_arquivo="referencia.pdf",
        metadados={
            "chunk_id": "chunk-1",
            "client_id": "cliente-secreto",
            "api_token": "token-secreto",
            "nested": {
                "cpf": "000.000.000-00",
                "authorization": "Bearer segredo",
                "pagina_interna": 7,
            },
            "itens": [
                {"email": "pessoa@example.com", "ordem": 1},
                {"ordem": 2},
            ],
        },
    )

    assert fonte.metadados == {
        "chunk_id": "chunk-1",
        "nested": {"pagina_interna": 7},
        "itens": [{"ordem": 1}, {"ordem": 2}],
    }


def test_aprovacao_humana_exige_evidencia_de_auditoria() -> None:
    with pytest.raises(ValidationError):
        RespostaJuridicaRastreavel(
            conteudo="Resposta jurídica revisada.",
            resumo_fontes=ResumoConfiabilidadeFontes(),
            aprovado_humano=True,
        )

    resposta = RespostaJuridicaRastreavel(
        conteudo="Resposta jurídica revisada.",
        resumo_fontes=ResumoConfiabilidadeFontes(),
        aprovado_humano=True,
        aprovado_por="user-advogado-1",
        aprovado_em=datetime.now(UTC),
        registro_aprovacao_id="audit-1",
    )

    assert resposta.aprovado_humano is True
    assert resposta.registro_aprovacao_id == "audit-1"


def test_resumo_falsificado_e_rejeitado() -> None:
    fonte = ProvenienciaJuridica(
        tipo_fonte=TipoFonteJuridica.OUTRA,
        nome_arquivo="fonte-nao-localizada.pdf",
        status_conferencia=StatusConferenciaFonte.NAO_LOCALIZADA,
    )

    with pytest.raises(ValidationError):
        RespostaJuridicaRastreavel(
            conteudo="Resposta com resumo manual divergente.",
            fontes=[fonte],
            resumo_fontes=ResumoConfiabilidadeFontes(
                total=1,
                confirmadas=1,
                bloqueantes=0,
            ),
        )


def test_fonte_bloqueante_impede_marcacao_como_aprovada() -> None:
    fonte = ProvenienciaJuridica(
        tipo_fonte=TipoFonteJuridica.OUTRA,
        nome_arquivo="fonte-nao-localizada.pdf",
        status_conferencia=StatusConferenciaFonte.NAO_LOCALIZADA,
    )

    with pytest.raises(ValidationError):
        RespostaJuridicaRastreavel(
            conteudo="Resposta que ainda depende de conferência.",
            fontes=[fonte],
            resumo_fontes=ResumoConfiabilidadeFontes(
                total=1,
                nao_localizadas=1,
                bloqueantes=1,
            ),
            aprovado_humano=True,
            aprovado_por="user-advogado-1",
            aprovado_em=datetime.now(UTC),
            registro_aprovacao_id="audit-2",
        )
