from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from app.services.seed_conhecimento import TEMAS_JURISPRUDENCIA_INICIAL


CATALOGO = Path(__file__).resolve().parents[1] / "app" / "eval" / "fontes_publicas_iniciais.json"


def test_catalogo_publico_tem_fontes_priorizadas_e_sem_casos():
    data = json.loads(CATALOGO.read_text(encoding="utf-8"))
    assert data["status"] == "semente_publica_sem_casos_proprios"
    assert len(data["fontes"]) >= 30
    assert "caso_real" in data["nao_e"]
    assert "gold_set_humano_atestado" in data["nao_e"]


def test_catalogo_publico_restringe_urls_a_dominios_oficiais():
    data = json.loads(CATALOGO.read_text(encoding="utf-8"))
    permitidos = ("planalto.gov.br", "stf.jus.br", "stj.jus.br", "tst.jus.br", "gov.br")
    for fonte in data["fontes"]:
        parsed = urlparse(fonte["url"])
        assert parsed.scheme == "https"
        assert any(parsed.hostname == dominio or parsed.hostname.endswith("." + dominio) for dominio in permitidos)
        assert fonte["tipo"] in {
            "norma_vigente",
            "norma_vigente_com_transicao",
            "precedente_vinculante",
            "jurisprudencia_persuasiva",
            "informativo_normativo",
            "informativo_operacional",
        }


def test_seed_de_jurisprudencia_cobre_as_areas_iniciais():
    assert len(TEMAS_JURISPRUDENCIA_INICIAL) == 15
    texto = " ".join(TEMAS_JURISPRUDENCIA_INICIAL).lower()
    for termo in ("consumidor", "trabalh", "civil", "criminal", "tribut", "reforma"):
        assert termo in texto
