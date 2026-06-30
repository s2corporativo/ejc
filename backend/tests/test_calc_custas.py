"""Custas/Taxa Judiciária TJMG — conversões UFEMG e guarda da tabela (Fase 5)."""
import pytest
from fastapi import HTTPException

from app.services.calc import custas_tjmg as c


def test_ufemg_para_reais():
    # UFEMG 2026 = R$ 5,7899
    assert c.ufemg_para_reais(1) == 5.79
    assert c.ufemg_para_reais(100) == 578.99


def test_reais_para_ufemg_roundtrip():
    assert c.reais_para_ufemg(5.7899) == pytest.approx(1.0, abs=1e-4)
    assert c.reais_para_ufemg(144747.50) == pytest.approx(25000.0, abs=0.01)


def test_isencao_taxa_reais():
    # 25.000 UFEMG × 5,7899 = R$ 144.747,50
    assert float(c.ISENCAO_TAXA_REAIS) == pytest.approx(144747.50, abs=0.01)


def test_analisar_sem_tabela_oficial_retorna_503():
    # Enquanto FAIXAS_CUSTAS não é carregada, analisar() deve falhar fechado (503),
    # nunca inventar um valor de custas.
    assert c.FAIXAS_CUSTAS == []
    with pytest.raises(HTTPException) as exc:
        c.analisar(50000)
    assert exc.value.status_code == 503
