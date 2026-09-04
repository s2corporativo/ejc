from pathlib import Path

from app.services.knowledge_governance import inferir_autoridade


ROOT = Path(__file__).parents[1]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_ingestores_classificam_proposicao_como_oficial_informativa():
    for rel in (
        "app/services/ingestors/camara.py",
        "app/services/ingestors/senado.py",
    ):
        src = _src(rel)
        assert 'categoria="proposicao_legislativa"' in src
        assert '"authority_level": "oficial_informativa"' in src
        assert '"source_official": True' in src
        assert '"proposicao_nao_vigente": True' in src
        assert 'confianca="media"' in src
        assert "não é norma vigente" in src


def test_metadado_explicito_impede_proposicao_de_receber_autoridade_normativa():
    autoridade = inferir_autoridade(
        "proposicao_legislativa",
        "https://www.camara.leg.br/",
        {
            "source_official": True,
            "authority_level": "oficial_informativa",
        },
    )
    assert autoridade["code"] == "oficial_informativa"
    assert autoridade["weight"] < 100
