# Testes da matriz tese×prova (Fase C) — funções PURAS (sem rede/DB).
from app.services.matriz_provas import (
    MATRIZ,
    provas_recomendadas,
    provas_recomendadas_texto,
)


# ── provas_recomendadas ───────────────────────────────────────────────────────

def _todas_provas(recs):
    return [p for r in recs for p in r["provas"]]


def test_dano_material_geral_casa_nf_recibo():
    recs = provas_recomendadas("civil", "Pleiteia indenização por dano material")
    teses = {r["tese"] for r in recs}
    assert "Dano material" in teses
    provas = _todas_provas(recs)
    assert "Nota fiscal" in provas
    assert "Recibo" in provas
    assert "Comprovante de pagamento" in provas


def test_juros_abusivos_bancario_casa_planilha_pericia():
    recs = provas_recomendadas("bancario", "Revisional por juros abusivos e capitalização")
    provas = _todas_provas(recs)
    assert "Planilha evolutiva do débito" in provas
    assert "Perícia contábil" in provas
    assert "Contrato bancário" in provas


def test_falha_prestacao_servico_consumidor():
    recs = provas_recomendadas("consumidor", "houve falha na prestação do serviço contratado")
    teses = {r["tese"] for r in recs}
    assert "Falha na prestação do serviço" in teses
    provas = _todas_provas(recs)
    assert "Contrato de prestação de serviço" in provas
    assert "Protocolos de atendimento" in provas


def test_incapacidade_laboral_previdenciario():
    recs = provas_recomendadas("previdenciario", "auxílio-doença por incapacidade laboral")
    provas = _todas_provas(recs)
    assert "Laudos médicos" in provas
    assert "CAT (Comunicação de Acidente de Trabalho)" in provas


def test_horas_extras_trabalhista():
    recs = provas_recomendadas("trabalhista", "pagamento de horas extras não quitadas")
    provas = _todas_provas(recs)
    assert "Cartões de ponto" in provas
    assert "Controles de jornada" in provas


def test_nulidade_ato_administrativo():
    recs = provas_recomendadas("administrativo", "nulidade de ato administrativo por vício")
    provas = _todas_provas(recs)
    assert "Processo administrativo integral" in provas
    assert "Comprovante de ciência / intimação" in provas


def test_sem_match_retorna_vazio():
    assert provas_recomendadas("civil", "texto qualquer sem tese reconhecida aqui") == []
    assert provas_recomendadas("civil", "") == []
    assert provas_recomendadas("area_inexistente", "dano material") != []  # geral ainda casa


def test_tolerante_a_acento_e_caixa():
    sem = provas_recomendadas("bancario", "JUROS ABUSIVOS")
    com = provas_recomendadas("bancario", "juros abusívos")
    assert _todas_provas(sem) == _todas_provas(com)
    assert "Perícia contábil" in _todas_provas(sem)


def test_dedup_tese_e_prova():
    # "dano material" + "dano moral" no mesmo texto → duas teses distintas,
    # cada uma aparece UMA vez.
    recs = provas_recomendadas("civil", "dano material e também dano moral no caso")
    teses = [r["tese"] for r in recs]
    assert len(teses) == len(set(teses))  # sem tese duplicada
    for r in recs:
        assert len(r["provas"]) == len(set(r["provas"]))  # sem prova duplicada


def test_nunca_levanta_excecao_em_inputs_estranhos():
    assert provas_recomendadas(None, None) == []
    assert provas_recomendadas(123, ["lista"]) == []
    assert provas_recomendadas("civil", {"dict": 1}) == []


def test_geral_aplica_a_qualquer_area():
    # A tese "Dano moral" está em "geral" → casa mesmo numa área específica.
    recs = provas_recomendadas("tributario", "pedido de dano moral")
    assert "Dano moral" in {r["tese"] for r in recs}


# ── provas_recomendadas_texto ─────────────────────────────────────────────────

def test_texto_compacto_contem_tese_e_provas():
    txt = provas_recomendadas_texto("bancario", "juros abusivos")
    assert "Juros / tarifas abusivos" in txt
    assert "Perícia contábil" in txt
    assert "|" in txt or ":" in txt  # formato compacto


def test_texto_vazio_sem_excecao():
    assert provas_recomendadas_texto("civil", "") == ""
    assert provas_recomendadas_texto(None, None) == ""
    assert provas_recomendadas_texto("civil", "nada casa aqui") == ""


def test_matriz_bem_formada():
    # Invariante estrutural: toda entrada tem tese(str), termos(list) e provas(list).
    for area, entradas in MATRIZ.items():
        assert isinstance(area, str)
        for e in entradas:
            assert isinstance(e["tese"], str) and e["tese"]
            assert isinstance(e["termos"], list) and e["termos"]
            assert isinstance(e["provas"], list) and e["provas"]
