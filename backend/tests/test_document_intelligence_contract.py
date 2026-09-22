from __future__ import annotations

from app.services.document_intelligence import build_case_intelligence, comparar_inteligencia


def test_build_case_intelligence_preserva_incerteza_e_nao_inventa_endereco():
    result = build_case_intelligence({
        "fatos": "O cliente relata inadimplemento contratual.",
        "cliente": {"nome": "Pessoa Teste", "confianca": "baixa", "origem": "relato"},
        "parte_contraria": "Empresa Teste",
        "area": {"valor": "civil", "confianca": 0.7},
        "documentos_faltantes": ["contrato integral"],
        "provas_necessarias": ["comprovantes de pagamento"],
        "honorarios_sugeridos": {
            "disponivel": True,
            "seccional": "OAB/MG",
            "candidatos": [{"item_codigo": "X", "fonte": "OAB/MG"}],
        },
    })

    assert result.classificacao["ramo_principal"] == "civil"
    assert result.fatos[0].estado == "alegado_cliente"
    assert result.partes[0].confianca.valor is None  # texto desconhecido não vira certeza
    assert result.honorarios.disponivel is True
    assert result.honorarios.candidatos[0]["item_codigo"] == "X"
    assert not any("endereco" in str(item).lower() for item in result.model_dump().values())
    assert result.revisao_obrigatoria is True


def test_comparar_inteligencia_sinaliza_impacto_sem_promover_conclusao():
    diff = comparar_inteligencia(
        {"fatos": [{"conteudo": "versão antiga"}], "riscos": []},
        {"fatos": [{"conteudo": "versão nova"}], "riscos": [{"descricao": "risco"}]},
    )

    assert diff["houve_alteracao"] is True
    assert set(diff["campos_alterados"]) == {"fatos", "riscos"}
    assert all(item["requer_revisao_humana"] for item in diff["alteracoes"])
