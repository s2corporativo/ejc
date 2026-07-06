from app.services.module_help_seed import DEFAULT_HELP_TOPICS


def test_default_help_topics_tem_chaves_unicas():
    keys = [t["module_key"] for t in DEFAULT_HELP_TOPICS]
    assert len(keys) == len(set(keys))


def test_default_help_topics_cobrem_modulos_principais():
    keys = {t["module_key"] for t in DEFAULT_HELP_TOPICS}
    assert {"clientes", "casos", "documentos", "prazos", "financeiro", "ia", "autofix"}.issubset(keys)


def test_default_help_topics_tem_conteudo():
    for topic in DEFAULT_HELP_TOPICS:
        assert topic["titulo"]
        assert len(str(topic["conteudo_md"])) > 40
