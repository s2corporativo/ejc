from pathlib import Path


ROOT = Path(__file__).parents[1]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_produtores_oficiais_declaram_aprovacao_explicitamente():
    produtores = (
        "app/services/ingestors/planalto.py",
        "app/services/ingestors/lexml.py",
        "app/services/ingestors/stj.py",
        "app/services/ingestors/tjmg.py",
        "app/services/ingestors/camara.py",
        "app/services/ingestors/senado.py",
        "app/services/seed_conhecimento.py",
    )
    for rel in produtores:
        src = _src(rel)
        assert '"rag_status": "aprovado"' in src, rel


def test_produtores_que_exigem_curadoria_declaram_pendente_explicitamente():
    datajud = _src("app/services/datajud_cognitive_feed.py")
    rag_router = _src("app/routers/rag.py")

    assert '"rag_status": "pendente"' in datajud
    assert '"rag_status": "pendente"' in rag_router
