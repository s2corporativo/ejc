from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.ai_proveniencia import (
    NivelConfidencialidadeFonte,
    ProvenienciaJuridica,
    StatusConferenciaFonte,
    TipoFonteJuridica,
)
from app.services.ai.proveniencia import (
    ProvenienciaEscopoError,
    construir_resposta_rastreavel,
    normalizar_lote_proveniencia,
    normalizar_proveniencia,
)


def test_normaliza_metadados_legados_sem_perder_extras() -> None:
    fonte = normalizar_proveniencia(
        {
            "source_type": "documento_caso",
            "filename": "contestacao.pdf",
            "doc_id": "doc-1",
            "page": 4,
            "excerpt": "Trecho utilizado pela análise.",
            "case_id": "case-1",
            "confidentiality": "restrita",
            "extraction_confidence": 0.93,
            "chunk_id": "chunk-7",
        },
        case_id_esperado="case-1",
    )

    assert fonte.nome_arquivo == "contestacao.pdf"
    assert fonte.documento_id == "doc-1"
    assert fonte.pagina == 4
    assert fonte.nivel_confidencialidade is NivelConfidencialidadeFonte.RESTRITA
    assert fonte.confianca_extracao == 0.93
    assert fonte.metadados == {"chunk_id": "chunk-7"}


def test_confidencialidade_padrao_e_interna() -> None:
    fonte = ProvenienciaJuridica(
        tipo_fonte=TipoFonteJuridica.OUTRA,
        nome_arquivo="referencia.pdf",
    )

    assert fonte.nivel_confidencialidade is NivelConfidencialidadeFonte.INTERNA


def test_segredo_justica_exige_case_id_verificavel() -> None:
    with pytest.raises(ValidationError):
        ProvenienciaJuridica(
            tipo_fonte=TipoFonteJuridica.DOCUMENTO_CASO,
            nome_arquivo="autos.pdf",
            nivel_confidencialidade=NivelConfidencialidadeFonte.SEGREDO_JUSTICA,
        )

    fonte = ProvenienciaJuridica(
        tipo_fonte=TipoFonteJuridica.DOCUMENTO_CASO,
        nome_arquivo="autos.pdf",
        case_id="case-1",
        nivel_confidencialidade=NivelConfidencialidadeFonte.SEGREDO_JUSTICA,
    )

    assert fonte.case_id == "case-1"


def test_rejeita_fonte_de_outro_caso() -> None:
    with pytest.raises(ProvenienciaEscopoError):
        normalizar_proveniencia(
            {
                "tipo_fonte": "documento_caso",
                "nome_arquivo": "documento.pdf",
                "case_id": "case-2",
            },
            case_id_esperado="case-1",
        )


def test_rejeita_fonte_interna_sem_case_id_verificavel() -> None:
    with pytest.raises(ProvenienciaEscopoError):
        normalizar_proveniencia(
            {
                "tipo_fonte": "peca_interna",
                "nome_arquivo": "modelo.docx",
            },
            case_id_esperado="case-1",
        )


def test_fonte_oficial_confirmada_exige_vigencia_e_data() -> None:
    with pytest.raises(ValidationError):
        ProvenienciaJuridica(
            tipo_fonte=TipoFonteJuridica.FONTE_OFICIAL,
            status_conferencia=StatusConferenciaFonte.CONFIRMADA,
            nivel_confidencialidade=NivelConfidencialidadeFonte.PUBLICA,
            url_oficial="https://fonte.oficial/ato",
            autoridade="Órgão oficial",
        )

    fonte = ProvenienciaJuridica(
        tipo_fonte=TipoFonteJuridica.FONTE_OFICIAL,
        status_conferencia=StatusConferenciaFonte.CONFIRMADA,
        nivel_confidencialidade=NivelConfidencialidadeFonte.PUBLICA,
        url_oficial="https://fonte.oficial/ato",
        autoridade="Órgão oficial",
        vigente=True,
        data_verificacao=datetime.now(UTC),
    )

    assert fonte.vigente is True


def test_deduplica_fontes_sem_ocultar_status_bloqueante() -> None:
    fonte = {
        "tipo_fonte": "documento_caso",
        "documento_id": "doc-1",
        "nome_arquivo": "inicial.pdf",
        "pagina": 2,
        "trecho": "Pedido principal.",
        "case_id": "case-1",
        "status_conferencia": "nao_localizada",
    }

    fontes = normalizar_lote_proveniencia(
        [fonte, dict(fonte)],
        case_id_esperado="case-1",
    )

    assert len(fontes) == 1

    resposta = construir_resposta_rastreavel(
        conteudo="Rascunho jurídico sujeito a conferência.",
        fontes=fontes,
        case_id="case-1",
    )

    assert resposta.resumo_fontes.total == 1
    assert resposta.resumo_fontes.nao_localizadas == 1
    assert resposta.resumo_fontes.bloqueantes == 1
    assert resposta.aprovado_humano is False
    assert resposta.pontos_validacao_humana


def test_nao_deduplica_conflito_de_status_ou_confidencialidade() -> None:
    base = {
        "tipo_fonte": "documento_caso",
        "documento_id": "doc-1",
        "nome_arquivo": "inicial.pdf",
        "pagina": 2,
        "trecho": "Pedido principal.",
        "case_id": "case-1",
    }
    confirmada = {
        **base,
        "status_conferencia": "confirmada",
        "nivel_confidencialidade": "interna",
        "data_verificacao": datetime.now(UTC),
    }
    bloqueante = {
        **base,
        "status_conferencia": "nao_localizada",
        "nivel_confidencialidade": "restrita",
    }

    fontes = normalizar_lote_proveniencia(
        [confirmada, bloqueante],
        case_id_esperado="case-1",
    )

    assert len(fontes) == 2
    resposta = construir_resposta_rastreavel(
        conteudo="Rascunho sujeito a revisão.",
        fontes=fontes,
        case_id="case-1",
    )
    assert resposta.resumo_fontes.confirmadas == 1
    assert resposta.resumo_fontes.nao_localizadas == 1
    assert resposta.resumo_fontes.bloqueantes == 1


def test_resposta_preserva_inferencia_separada_da_fonte() -> None:
    resposta = construir_resposta_rastreavel(
        conteudo="Conclusão provisória.",
        case_id="case-1",
        fontes=[
            {
                "tipo_fonte": "documento_caso",
                "documento_id": "doc-2",
                "nome_arquivo": "prova.pdf",
                "case_id": "case-1",
                "inferencia_ia": True,
            }
        ],
        pontos_validacao_humana=["Confirmar a relação entre o documento e o fato."],
    )

    assert resposta.resumo_fontes.inferencias_ia == 1
    assert resposta.pontos_validacao_humana == [
        "Confirmar a relação entre o documento e o fato."
    ]
