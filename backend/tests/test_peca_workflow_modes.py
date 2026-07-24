from app.schemas.peca_workflow import (
    ConfiguracaoMolde,
    ModoProducao,
    ProducaoModoRequest,
    ReferenciaDocumento,
)
from app.services.peca_workflow_service import (
    campos_guiados_obrigatorios,
    preparar_modo_producao,
)


def test_modo_livre_e_compatível_com_pipeline_existente():
    resultado = preparar_modo_producao(
        ProducaoModoRequest(
            modo=ModoProducao.LIVRE,
            tipo_peca="contestacao",
            area_direito="civil",
            instrucao_livre="Impugnar especificamente os fatos e revisar os pedidos.",
        )
    )

    assert resultado.pronto_para_redacao is True
    assert resultado.exige_aprovacao is False
    assert resultado.bloqueios == []
    assert "[INSTRUÇÃO DO ADVOGADO]" in resultado.instrucoes_pipeline


def test_modo_guiado_bloqueia_contestacao_incompleta():
    resultado = preparar_modo_producao(
        ProducaoModoRequest(
            modo=ModoProducao.GUIADO,
            tipo_peca="contestacao",
            area_direito="civil",
            respostas_guiadas={
                "autor": "Parte autora",
                "reu": "Parte ré",
                "pretensao_autor": "Indenização",
            },
        )
    )

    assert resultado.pronto_para_redacao is False
    assert "fatos_impugnados" in resultado.bloqueios[0]
    assert "pedidos" in resultado.bloqueios[0]


def test_campos_guiados_usam_fallback_seguro_para_tipo_desconhecido():
    assert campos_guiados_obrigatorios("tipo_novo") == (
        "partes",
        "fatos",
        "provas",
        "pedidos",
    )


def test_modo_molde_exige_versao_e_hash_estaveis():
    resultado = preparar_modo_producao(
        ProducaoModoRequest(
            modo=ModoProducao.MOLDE,
            tipo_peca="contestacao",
            area_direito="civil",
            molde=ConfiguracaoMolde(
                referencia=ReferenciaDocumento(documento_id="modelo-1")
            ),
        )
    )

    assert resultado.pronto_para_redacao is False
    assert any("versão do molde" in item for item in resultado.bloqueios)
    assert any("hash do molde" in item for item in resultado.bloqueios)
    assert any("detector de resíduos" in item for item in resultado.alertas)


def test_modo_molde_pronto_registra_identidade_e_checklist_antivazamento():
    resultado = preparar_modo_producao(
        ProducaoModoRequest(
            modo=ModoProducao.MOLDE,
            tipo_peca="contestacao",
            area_direito="civil",
            case_id="case-2",
            molde=ConfiguracaoMolde(
                referencia=ReferenciaDocumento(
                    documento_id="modelo-2",
                    versao=4,
                    hash_conteudo="abcdef123456",
                    nome="Contestação padrão",
                )
            ),
        )
    )

    assert resultado.pronto_para_redacao is True
    assert resultado.molde is not None
    assert resultado.molde.referencia.versao == 4
    assert "modelo-2" in resultado.instrucoes_pipeline
    assert any("caso anterior" in item for item in resultado.checklist_revisao)


def test_modo_agente_nao_redige_sem_caso_documentos_e_aprovacao():
    resultado = preparar_modo_producao(
        ProducaoModoRequest(
            modo=ModoProducao.AGENTE,
            tipo_peca="contestacao",
            area_direito="civil",
        )
    )

    assert resultado.pronto_para_redacao is False
    assert resultado.exige_aprovacao is True
    assert len(resultado.etapas) == 10
    assert resultado.etapas[8].codigo == "aprovacao"
    assert any("exige vínculo" in item for item in resultado.bloqueios)
    assert any("documentos autorizados" in item for item in resultado.bloqueios)
    assert any("aprovadas" in item or "aprovada" in item for item in resultado.bloqueios)
    assert "Não redija a peça final" in resultado.instrucoes_pipeline


def test_modo_agente_aprovado_fica_pronto_sem_chamada_de_ia():
    resultado = preparar_modo_producao(
        ProducaoModoRequest(
            modo=ModoProducao.AGENTE,
            tipo_peca="replica",
            area_direito="consumidor",
            case_id="case-3",
            documentos_considerados=[
                ReferenciaDocumento(
                    documento_id="doc-1",
                    versao=2,
                    hash_conteudo="123456abcdef",
                )
            ],
            aprovado_para_redacao=True,
        )
    )

    assert resultado.pronto_para_redacao is True
    assert resultado.bloqueios == []
    assert resultado.documentos_considerados[0].documento_id == "doc-1"
    assert resultado.etapas[-1].codigo == "redacao_revisao"


def test_campos_guiados_sao_normalizados_sem_duplicacao():
    resultado = preparar_modo_producao(
        ProducaoModoRequest(
            modo=ModoProducao.GUIADO,
            tipo_peca="tipo_novo",
            area_direito="civil",
            respostas_guiadas={
                " Partes ": "A e B",
                "Fatos": "Fatos confirmados",
                "Provas": ["Documento 1"],
                "Pedidos": "Procedência",
            },
        )
    )

    assert resultado.pronto_para_redacao is True
    assert set(resultado.campos_estruturados) == {
        "partes",
        "fatos",
        "provas",
        "pedidos",
    }
