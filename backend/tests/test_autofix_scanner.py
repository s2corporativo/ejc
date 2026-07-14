from types import SimpleNamespace


from app.services.autofix_scanner import EXPECTED_MODULES, _coletar_rotas_api, _normalizar_module_key


def test_normalizar_module_key():
    assert _normalizar_module_key(" /Clientes/ ") == "clientes"


def test_expected_modules_contem_autofix():
    keys = {m["module_key"] for m in EXPECTED_MODULES}
    assert "autofix" in keys
    assert "documentos" in keys
    assert "clientes" in keys


def test_coletar_rotas_api_ignora_rotas_nao_api():
    app = SimpleNamespace(routes=[
        SimpleNamespace(path="/", methods={"GET"}, name="home"),
        SimpleNamespace(path="/api/health", methods={"GET", "HEAD"}, name="health"),
    ])
    rotas = _coletar_rotas_api(app)
    assert rotas == [{"path": "/api/health", "methods": ["GET"], "name": "health"}]
