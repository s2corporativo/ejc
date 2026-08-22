import json
from pathlib import Path

from scripts.seed_jurisprudencia_ejc import carregar_julgados


ROOT = Path(__file__).resolve().parents[1]


def test_seed_piloto_contem_apenas_v4_em_quarentena():
    docs = carregar_julgados(
        ROOT / "seeds" / "jurisprudencia_ejc" / "rodada_piloto_2026_08" / "processos_v4.jsonl"
    )
    assert len(docs) == 13
    for doc in docs:
        assert doc["categoria"] == "jurisprudencia"
        extra = doc["extra"]
        assert extra["ficticio"] is False
        assert extra["fonte_validada"] is True
        assert extra["validation_tier"] == "V4_DIRETO"
        assert extra["rag_status"] == "quarentena"
        assert extra["cidade_origem"] in {"Betim", "Contagem"}
        assert extra["url_fonte"].startswith("https://")
        assert doc["chave_origem"].startswith("julgado:TJMG:")


def test_seed_nao_contamina_com_staging_ou_metadados():
    path = ROOT / "seeds" / "jurisprudencia_ejc" / "rodada_piloto_2026_08" / "processos_v4.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        extra = json.loads(line)["extra"]
        assert extra["validation_tier"] not in {"V1_STAGING", "V2_METADATA"}
        assert "quarentena" in json.loads(line)["conteudo"]
