from app.services.module_registry import (
    MODULE_REGISTRY,
    gerar_mapa_modulos,
    listar_modulos,
    module_keys_registradas,
    resumir_mapa_modulos,
)


def test_module_registry_tem_chaves_unicas():
    keys = [m["module_key"] for m in MODULE_REGISTRY]
    assert len(keys) == len(set(keys))


def test_module_registry_cobre_modulos_criticos():
    keys = {m["module_key"] for m in MODULE_REGISTRY}
    assert {
        "dashboard",
        "clientes",
        "casos",
        "documentos",
        "prazos",
        "financeiro",
        "honorarios",
        "ia",
        "conhecimento",
        "jurimetria",
        "portal",
        "auditoria",
        "usuarios",
        "mapa-modulos",
    }.issubset(keys)


def test_module_registry_tem_campos_essenciais():
    campos = {
        "module_key",
        "nome",
        "grupo",
        "frontend_route",
        "backend_prefixes",
        "status",
        "perfis",
        "dependencias",
        "usa_ia",
        "dados_sensiveis",
        "responsavel_operacional",
        "responsavel_tecnico",
    }
    for modulo in MODULE_REGISTRY:
        assert campos.issubset(modulo.keys())
        assert modulo["module_key"]
        assert modulo["nome"]
        assert modulo["frontend_route"].startswith("/")
        assert isinstance(modulo["backend_prefixes"], list)
        assert modulo["status"] in {"ativo", "beta", "legado", "oculto", "descontinuado"}


def test_module_keys_registradas():
    assert "clientes" in module_keys_registradas()
    assert "mapa-modulos" in module_keys_registradas()


def test_listar_modulos_retorna_copia():
    modulos = listar_modulos()
    assert modulos is not MODULE_REGISTRY
    assert modulos[0] is not MODULE_REGISTRY[0]


def test_gerar_mapa_modulos_detecta_manual_e_endpoint():
    rotas = [{"path": "/api/clients/", "methods": ["GET"], "name": "listar"}]
    mapa = gerar_mapa_modulos(rotas, ["clientes"])
    clientes = next(m for m in mapa if m["module_key"] == "clientes")
    assert clientes["tem_manual"] is True
    assert clientes["qtd_endpoints_detectados"] == 1
    assert clientes["precisa_revisao"] is False


def test_resumir_mapa_modulos():
    mapa = gerar_mapa_modulos([], [])
    resumo = resumir_mapa_modulos(mapa)
    assert resumo["total"] == len(MODULE_REGISTRY)
    assert resumo["sem_manual"] == len(MODULE_REGISTRY)
    assert resumo["sem_endpoint_detectado"] == len(MODULE_REGISTRY)
    assert resumo["ativos"] > 0
    assert resumo["beta"] >= 1
    assert resumo["usam_ia"] > 0
    assert resumo["dados_sensiveis"] > 0
