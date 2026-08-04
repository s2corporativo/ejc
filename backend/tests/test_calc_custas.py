"""Custas/Taxa Judiciária TJMG — conversões UFEMG e tabela oficial 2026.

Os valores esperados foram transcritos da tabela oficial do TJMG
("Tabela de Custas e Taxa Judiciária — 1ª Instância — Ano 2026", fonte no
módulo). Se o TJMG publicar nova tabela (novo exercício), estes testes DEVEM
ser atualizados junto com a carga — nunca ajustados para "passar".
"""
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


def test_tabela_oficial_carregada():
    assert c.TABELA_OFICIAL_CARREGADA is True
    assert c.VIGENCIA == "2026"
    assert "tjmg.jus.br" in c.FONTE_URL


def test_grupo1_faixa_inicial_e_intermediaria():
    # Tabela oficial, Grupo 1 (Vara Cível): 0,00–46.356,26 → 463,19 + 167,91.
    r = c.analisar(30_000)
    assert r["grupo"] == 1
    assert r["custas_iniciais"] == 463.19
    assert r["taxa_judiciaria"] == 167.91
    assert r["total_a_recolher"] == 631.10
    # 46.356,27–60.724,47 → 602,15 + 167,91 (e limite exato da faixa).
    r2 = c.analisar(60_724.47)
    assert r2["custas_iniciais"] == 602.15
    assert r2["total_a_recolher"] == 770.06


def test_grupo1_topo_aberto():
    # Acima de 4.045.976,33 → 3.010,75 + 17.630,25 = 20.640,99.
    r = c.analisar(10_000_000)
    assert r["faixa"]["ate"] is None
    assert r["custas_iniciais"] == 3010.75
    assert r["taxa_judiciaria"] == 17630.25
    assert r["total_a_recolher"] == 20640.99


def test_grupo2_familia_jec():
    # Grupo 2: 0,00–46.356,26 → 231,60 + 92,64 (total impresso 324,23 — a
    # tabela oficial arredonda a partir da UFEMG; guardamos o impresso).
    r = c.analisar(10_000, grupo=2)
    assert r["custas_iniciais"] == 231.60
    assert r["taxa_judiciaria"] == 92.64
    assert r["total_a_recolher"] == 324.23


def test_grupo3_sucessoes_faixa_sem_custas():
    # Grupo 3: até 60.724,47 as custas impressas são 0,00 (só taxa 92,64).
    r = c.analisar(50_000, grupo=3)
    assert r["custas_iniciais"] == 0.00
    assert r["taxa_judiciaria"] == 92.64


def test_grupo7_ms_com_observacao():
    r = c.analisar(50_000, grupo=7)
    assert r["custas_iniciais"] == 324.23
    assert "impetrante" in r.get("observacao_grupo", "")


def test_isencao_taxa_flag():
    assert c.analisar(100_000)["isencao_taxa_judiciaria"]["isento"] is True
    assert c.analisar(150_000)["isencao_taxa_judiciaria"]["isento"] is False


def test_grupos_nao_carregados_seguem_fail_closed():
    # Grupos 4/5 usam rubricas fixas por histórico — 503 até carga conferida,
    # nunca valor inventado (mesma doutrina fail-closed de antes da carga).
    for grupo in (4, 5):
        with pytest.raises(HTTPException) as exc:
            c.analisar(50_000, grupo=grupo)
        assert exc.value.status_code == 503


def test_grupo_invalido_422():
    with pytest.raises(HTTPException) as exc:
        c.analisar(50_000, grupo=9)
    assert exc.value.status_code == 422


def test_avisos_hitl_e_vigencia_presentes():
    r = c.analisar(30_000)
    avisos = " ".join(r["avisos"])
    assert "MINUTA" in avisos
    assert "vigente na data do efetivo pagamento" in avisos.lower()
    assert r["vigencia"] == "2026"
