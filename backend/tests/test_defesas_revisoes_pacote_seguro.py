from app.core.fastapi_compat import flatten_routes
from app.routers.defesas_revisoes_avancado import planejar_pacote, router as pacote_router


def test_pacote_bloqueia_kit_e_motor_quando_documentacao_nao_apta():
    resultado = {
        "checklist_obrigatorio": [
            {"item": "Decisão recorrida", "status": "pendente", "impeditivo": True},
        ],
        "documentos_faltantes": ["Decisão recorrida"],
    }
    plano = planejar_pacote("multa_administrativa", resultado)

    assert plano["completude"]["nivel"] == "nao_apto_para_redacao"
    assert plano["gerar_kit_inicial"] is False
    assert plano["liberar_motor_peca"] is False
    assert plano["motivo_bloqueio"]
    assert {item["codigo"] for item in plano["documentos_diagnosticos"]} >= {
        "relatorio", "cronologia", "matriz", "checklist", "indice", "provas",
    }


def test_pacote_apto_libera_kit_e_motor_sob_revisao_humana():
    resultado = {
        "checklist_obrigatorio": [
            {"item": "Contrato", "status": "atendido", "impeditivo": True},
            {"item": "Extratos", "status": "atendido", "impeditivo": True},
        ],
        "documentos_faltantes": [],
    }
    plano = planejar_pacote("revisao_bancaria", resultado)

    assert plano["completude"]["nivel"] == "apto_para_redacao"
    assert plano["gerar_kit_inicial"] is True
    assert plano["liberar_motor_peca"] is True
    assert plano["motivo_bloqueio"] is None
    assert "calculo" in {item["codigo"] for item in plano["documentos_diagnosticos"]}


def test_pacote_com_ressalvas_ainda_libera_fluxo_com_alerta_humano():
    resultado = {
        "checklist_obrigatorio": [
            {"item": "Fotografias adicionais", "status": "confirmar", "impeditivo": False},
        ],
        "documentos_faltantes": [],
    }
    plano = planejar_pacote("multa_transito", resultado)

    assert plano["completude"]["nivel"] == "apto_com_ressalvas"
    assert plano["liberar_motor_peca"] is True


def test_rota_pacote_existe_so_na_implementacao_segura():
    """A implementação segura continua registrando exatamente uma rota POST."""
    rotas = [
        route
        for route in flatten_routes(pacote_router.routes)
        if getattr(route, "path", None) == "/defesas-revisoes/avancado/pacote"
        and "POST" in getattr(route, "methods", set())
    ]
    assert len(rotas) == 1
    assert rotas[0].endpoint.__module__.endswith("defesas_revisoes_avancado")
