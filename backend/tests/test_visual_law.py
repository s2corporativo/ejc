"""Visual Law — fases/timeline, matriz de risco (CPC 25), badges de alerta e
calculadora de breakeven/VPL. Testes unitários das funções puras (sem banco)."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.visual_law import BreakevenIn
from app.services import visual_law_core as vl
from app.services import bcb_service
from app.services.diplomacia_digital import DiplomaciaDigital


# ── Linha do tempo: fases e status ────────────────────────────────────────────
def test_fases_judicial_conhecimento():
    fases = vl.montar_fases("conhecimento")
    assert [f["fase"] for f in fases] == [
        "pre_processual", "conhecimento", "recursal", "execucao"]
    assert [f["status"] for f in fases] == ["concluida", "atual", "futura", "futura"]
    assert fases[1]["label"] == "Conhecimento"


def test_fases_judicial_execucao_todas_anteriores_concluidas():
    fases = vl.montar_fases("execucao")
    assert [f["status"] for f in fases] == ["concluida", "concluida", "concluida", "atual"]


def test_fases_administrativo_trilha_propria():
    fases = vl.montar_fases("administrativo")
    assert fases == [{"fase": "administrativo", "label": "Administrativo",
                      "status": "atual"}]


def test_fases_nula_assume_inicio():
    fases = vl.montar_fases(None)
    assert fases[0]["status"] == "atual"
    assert all(f["status"] == "futura" for f in fases[1:])


def test_proximos_passos_prazos_reais_antes_das_estimativas():
    prazos = [{"titulo": "Contestação", "data": "2026-08-01"}]
    passos = vl.montar_proximos_passos("conhecimento", prazos)
    assert passos[0] == {"titulo": "Contestação", "origem": "prazo",
                         "data_estimada": "2026-08-01",
                         "detalhe": "Prazo pendente cadastrado no caso"}
    estimativas = [p for p in passos if p["origem"] == "estimativa"]
    assert [p["titulo"] for p in estimativas] == ["Sentença", "Prazo recursal (15 dias úteis)"]
    assert all(p["data_estimada"] is None for p in estimativas)


# ── Estagnação (dias parado) ──────────────────────────────────────────────────
@pytest.mark.parametrize("dias,nivel", [
    (0, "ok"), (30, "ok"), (31, "atencao"), (60, "atencao"), (61, "critico"),
])
def test_classificar_estagnacao_limiares(dias, nivel):
    assert vl.classificar_estagnacao(dias) == nivel
    assert vl.montar_estagnacao(dias) == {"dias_parado": dias, "nivel": nivel}


def test_estagnacao_caso_fechado_sempre_ok():
    # Caso encerrado/arquivado não estagna: parado é o estado esperado
    assert vl.montar_estagnacao(180, fechado=True) == {"dias_parado": 180,
                                                       "nivel": "ok"}
    # sem a flag, 180 dias seguiria crítico
    assert vl.montar_estagnacao(180)["nivel"] == "critico"


def test_dias_parado_desde_datas_injetadas():
    agora = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
    assert vl.dias_parado_desde(agora - timedelta(days=45), agora) == 45
    # naive → assume UTC (mesmo critério do case_health)
    assert vl.dias_parado_desde(datetime(2026, 7, 3, 12, 0), agora) == 1
    assert vl.dias_parado_desde(None, agora) == 0
    # referência futura nunca produz dias negativos
    assert vl.dias_parado_desde(agora + timedelta(days=3), agora) == 0


# ── Matriz de risco: probabilidade × impacto ──────────────────────────────────
@pytest.mark.parametrize("risco,score,esperado,fonte", [
    ("baixo", None, "remoto", "risco_cadastrado"),
    ("medio", None, "possivel", "risco_cadastrado"),
    ("alto", None, "provavel", "risco_cadastrado"),
    ("ALTO", 90, "provavel", "risco_cadastrado"),   # risco vence o score
    (None, 85, "remoto", "score_saude"),
    (None, 80, "remoto", "score_saude"),
    (None, 79, "possivel", "score_saude"),
    (None, 50, "possivel", "score_saude"),
    (None, 49, "provavel", "score_saude"),
    (None, None, "provavel", "score_saude"),        # sem nada → pior caso
    ("invalido", 85, "remoto", "score_saude"),
])
def test_derivar_probabilidade(risco, score, esperado, fonte):
    assert vl.derivar_probabilidade(risco, score) == (esperado, fonte)


@pytest.mark.parametrize("valor,esperado", [
    (1000.0, "baixo"), (50_000.0, "baixo"), (50_000.01, "medio"),
    (500_000.0, "medio"), (500_000.01, "alto"), (None, "indefinido"),
])
def test_classificar_impacto_faixas(valor, esperado):
    assert vl.classificar_impacto(valor) == esperado


@pytest.mark.parametrize("prob,imp,x,y,nivel,trat", [
    ("remoto", "baixo", 0, 0, "baixo", "nao_divulgar"),
    ("remoto", "alto", 0, 2, "moderado", "nao_divulgar"),
    ("possivel", "medio", 1, 1, "moderado", "divulgar_em_nota"),
    ("provavel", "baixo", 2, 0, "moderado", "provisionar"),
    ("provavel", "medio", 2, 1, "elevado", "provisionar"),
    ("provavel", "alto", 2, 2, "critico", "provisionar"),
    # impacto indefinido: eixo y neutro (médio), tratamento pela probabilidade
    ("possivel", "indefinido", 1, 1, "moderado", "divulgar_em_nota"),
    ("provavel", "indefinido", 2, 1, "elevado", "provisionar"),
])
def test_montar_quadrante(prob, imp, x, y, nivel, trat):
    assert vl.montar_quadrante(prob, imp) == {
        "x": x, "y": y, "nivel": nivel, "tratamento_contabil": trat}


def test_montar_matriz_9_quadrantes():
    matriz = vl.montar_matriz()
    assert len(matriz) == 3 and all(len(linha) == 3 for linha in matriz)
    assert matriz[0][0] == {"nivel": "baixo", "label": "Baixo"}
    assert matriz[2][2] == {"nivel": "critico", "label": "Crítico"}
    assert matriz[1][1]["nivel"] == "moderado"
    # monotônico: nenhum quadrante fica mais leve ao aumentar prob. ou impacto
    ordem = ["baixo", "moderado", "elevado", "critico"]
    for y in range(3):
        for x in range(3):
            if x > 0:
                assert ordem.index(matriz[y][x]["nivel"]) >= ordem.index(matriz[y][x - 1]["nivel"])
            if y > 0:
                assert ordem.index(matriz[y][x]["nivel"]) >= ordem.index(matriz[y - 1][x]["nivel"])


# ── Badges de alerta ──────────────────────────────────────────────────────────
def test_badge_estagnacao_regra_60_dias():
    assert vl.badge_estagnacao(30) is None
    b45 = vl.badge_estagnacao(45)
    assert b45["codigo"] == "parado_30d" and b45["severidade"] == "atencao"
    assert b45["pulsante"] is False
    assert vl.badge_estagnacao(60)["codigo"] == "parado_30d"  # 60 ainda não é crítico
    b61 = vl.badge_estagnacao(61)
    assert b61 == {"codigo": "parado_60d", "severidade": "critica",
                   "label": "Atenção Crítica",
                   "detalhe": "Processo sem movimentação há 61 dias",
                   "pulsante": True}


def test_montar_badges_converte_fatores_sem_duplicar_estagnacao():
    fatores = [
        {"fator": "prazo_vencido", "impacto": -20, "detalhe": "2 prazo(s) vencido(s)"},
        {"fator": "sem_movimentacao", "impacto": -15, "detalhe": "70 dias sem movimentação"},
        {"fator": "sem_posmortem", "impacto": -5, "detalhe": "Sem lições aprendidas"},
    ]
    badges = vl.montar_badges(fatores, dias_parado=70)
    codigos = [b["codigo"] for b in badges]
    assert codigos == ["parado_60d", "prazo_vencido", "sem_posmortem"]
    assert badges[0]["pulsante"] is True
    prazo = badges[1]
    assert prazo["severidade"] == "critica" and prazo["pulsante"] is True
    assert prazo["detalhe"] == "2 prazo(s) vencido(s)"
    assert badges[2]["severidade"] == "info" and badges[2]["pulsante"] is False


def test_montar_badges_sem_fatores_e_sem_estagnacao():
    assert vl.montar_badges([], dias_parado=10) == []


def test_montar_badges_caso_fechado_sem_badge_de_estagnacao():
    # Fechado com 180 dias parado: NENHUM badge parado_60d/parado_30d;
    # os demais fatores do case_health continuam virando badges.
    fatores = [{"fator": "sem_posmortem", "impacto": -5,
                "detalhe": "Sem lições aprendidas"}]
    badges = vl.montar_badges(fatores, dias_parado=180, fechado=True)
    assert [b["codigo"] for b in badges] == ["sem_posmortem"]
    # sem a flag, o mesmo cenário emitiria o badge crítico pulsante
    assert vl.montar_badges(fatores, dias_parado=180)[0]["codigo"] == "parado_60d"


# ── Breakeven / VPL ───────────────────────────────────────────────────────────
def test_tempo_tramitacao_por_tribunal():
    assert vl.tempo_tramitacao_estimado("TJMG") == (4.5, "tribunal_cnj")
    assert vl.tempo_tramitacao_estimado("tjsp") == (4.2, "tribunal_cnj")
    assert vl.tempo_tramitacao_estimado("TRF6") == (5.0, "tribunal_cnj")
    assert vl.tempo_tramitacao_estimado("TRT3") == (2.5, "tribunal_cnj")
    # STJ: adicional de 2 anos sobre a estimativa base (4.0)
    assert vl.tempo_tramitacao_estimado("STJ") == (6.0, "tribunal_cnj")
    assert vl.tempo_tramitacao_estimado(None) == (4.0, "default")
    assert vl.tempo_tramitacao_estimado("outro") == (4.0, "default")


def test_normalizar_pct_escala_percentual_0_100():
    # Contrato da API: SEMPRE escala 0–100 (sem heurística de fração)
    assert vl.normalizar_pct(10) == pytest.approx(0.10)
    assert vl.normalizar_pct(1) == pytest.approx(0.01)      # 1 é 1%, não 100%
    assert vl.normalizar_pct(0.5) == pytest.approx(0.005)   # meio por cento
    assert vl.normalizar_pct(100) == pytest.approx(1.0)
    assert vl.normalizar_pct(0.0) == 0.0


def test_breakeven_in_defaults_em_escala_percentual():
    p = BreakevenIn(prob_exito=0.7)
    assert p.custas_pct == 10.0
    assert p.honorarios_sucumbencia_pct == 10.0


def test_breakeven_in_rejeita_infinity_e_valores_absurdos():
    # "Infinity" no JSON viraria float('inf') — allow_inf_nan=False barra (422)
    with pytest.raises(ValidationError):
        BreakevenIn.model_validate({"valor_causa": "Infinity", "prob_exito": 0.5})
    with pytest.raises(ValidationError):
        BreakevenIn(valor_causa=float("nan"), prob_exito=0.5)
    with pytest.raises(ValidationError):
        BreakevenIn(valor_causa=1e13, prob_exito=0.5)   # acima do teto 1e12


def test_calcular_breakeven_valores_conhecidos():
    # valor 100k · prob 0.7 · 2 anos · selic 10% · custas 10 + sucumbência 10
    # (escala 0–100 da API, normalizada para fração como faz o router)
    r = vl.calcular_breakeven(
        valor_causa=100_000.0, prob_exito=0.7, tempo_anos=2.0, selic_anual=0.10,
        custas_pct=vl.normalizar_pct(10.0),
        honorarios_sucumbencia_pct=vl.normalizar_pct(10.0),
        tribunal="TJMG", tempo_fonte="tribunal_cnj", selic_fonte="fallback",
    )
    assert r["valor_esperado"] == 70_000.0
    # custas 10k + sucumbência esperada 100k×10%×0.3 = 3k
    assert r["custos_estimados"] == 13_000.0
    assert r["custos_detalhe"] == {"custas": 10_000.0,
                                   "honorarios_sucumbencia_esperados": 3_000.0}
    # VPL = (70000 − 13000) / 1.1² = 57000 / 1.21
    assert r["vpl_litigio"] == pytest.approx(47_107.44, abs=0.01)
    assert r["breakeven"] == r["vpl_litigio"]
    assert r["sugestao_acordo"] == r["vpl_litigio"]
    assert r["comparativo"]["litigio_vpl"] == r["vpl_litigio"]
    assert r["comparativo"]["acordo_imediato_equivalente"] == r["vpl_litigio"]
    assert r["comparativo"]["custo_do_tempo"] == pytest.approx(9_892.56, abs=0.01)
    assert r["parametros"]["tribunal"] == "TJMG"
    assert r["parametros"]["selic_fonte"] == "fallback"
    assert r["parametros"]["tempo_anos"] == 2.0
    assert len(r["memoria_calculo"]) >= 5


def test_calcular_breakeven_sem_custos_igual_vpl_simples():
    r = vl.calcular_breakeven(100_000.0, 0.5, 4.0, 0.1075,
                              custas_pct=0.0, honorarios_sucumbencia_pct=0.0)
    esperado = 50_000.0 / (1.1075 ** 4)
    assert r["vpl_litigio"] == pytest.approx(esperado, abs=0.01)
    assert r["custos_estimados"] == 0.0


def test_diplomacia_digital_retrocompativel():
    # Contrato antigo de /diplomacia-v3/calcular-acordo intacto com os defaults
    r = DiplomaciaDigital().calcular_ponto_equilibrio(100_000.0, 0.7, 2.0)
    vpl = 70_000.0 / (1.1075 ** 2)
    assert r["valor_causa"] == 100_000.0
    assert r["probabilidade_exito"] == 0.7
    assert r["tempo_estimado_anos"] == 2.0
    assert r["valor_presente_liquido"] == pytest.approx(vpl, abs=0.01)
    assert r["sugestao_acordo_ideal"] == pytest.approx(vpl * 1.05, abs=0.01)
    assert r["custo_oportunidade_perda"] == pytest.approx(70_000.0 - vpl, abs=0.01)
    assert r["custos_estimados"] == 0.0  # chave aditiva, neutra nos defaults


# ── Selic anualizada (BCB) — fallback determinístico ──────────────────────────
@pytest.fixture(autouse=True)
def _limpa_cache_negativo_bcb(monkeypatch):
    """Isola o cache negativo do BCB entre testes (estado de módulo)."""
    monkeypatch.setattr(bcb_service, "_fallback_ate", 0.0)


async def test_selic_anualizada_via_bcb(monkeypatch):
    async def fake_serie(codigo, ini, fim):
        assert codigo == 4390  # série Selic mensal
        return [{"data": f"01/{m:02d}/2026", "valor": "0,80"} for m in range(1, 13)]

    monkeypatch.setattr(bcb_service, "_buscar_serie", fake_serie)
    r = await bcb_service.selic_anualizada()
    assert r["fonte"] == "bcb"
    assert r["meses_compostos"] == 12
    assert r["selic_anual"] == pytest.approx(1.008 ** 12 - 1, abs=1e-6)


async def test_selic_anualizada_menos_de_12_meses_composicao_equivalente(monkeypatch):
    async def fake_serie(codigo, ini, fim):
        return [{"data": f"01/{m:02d}/2026", "valor": "1,00"} for m in range(1, 7)]

    monkeypatch.setattr(bcb_service, "_buscar_serie", fake_serie)
    r = await bcb_service.selic_anualizada()
    assert r["fonte"] == "bcb"
    assert r["meses_compostos"] == 6
    assert r["selic_anual"] == pytest.approx(1.01 ** 12 - 1, abs=1e-6)


async def test_selic_anualizada_fallback_deterministico(monkeypatch):
    async def fake_serie(codigo, ini, fim):
        raise RuntimeError("BCB fora do ar")

    monkeypatch.setattr(bcb_service, "_buscar_serie", fake_serie)
    r = await bcb_service.selic_anualizada()
    assert r == {"selic_anual": 0.1075, "fonte": "fallback", "meses_compostos": 0}


async def test_selic_anualizada_cache_negativo_nao_tenta_de_novo(monkeypatch):
    """Após uma falha, o fallback fica memorizado por FALLBACK_TTL_SEGUNDOS:
    dentro da janela não abre nova conexão com o BCB; expirada, tenta de novo.
    Relógio injetado (sem depender de tempo real)."""
    chamadas = {"n": 0}

    async def serie_fora_do_ar(codigo, ini, fim):
        chamadas["n"] += 1
        raise RuntimeError("BCB fora do ar")

    relogio = {"t": 1_000.0}
    monkeypatch.setattr(bcb_service, "_buscar_serie", serie_fora_do_ar)
    monkeypatch.setattr(bcb_service, "_agora", lambda: relogio["t"])

    r1 = await bcb_service.selic_anualizada()
    assert r1["fonte"] == "fallback" and chamadas["n"] == 1

    # Dentro da janela: serve o fallback direto, SEM nova tentativa no BCB
    relogio["t"] += 60.0
    r2 = await bcb_service.selic_anualizada()
    assert r2 == {"selic_anual": 0.1075, "fonte": "fallback", "meses_compostos": 0}
    assert chamadas["n"] == 1

    # Janela expirada: volta a tentar o BCB
    relogio["t"] += bcb_service.FALLBACK_TTL_SEGUNDOS
    await bcb_service.selic_anualizada()
    assert chamadas["n"] == 2


async def test_selic_anualizada_sucesso_limpa_cache_negativo(monkeypatch):
    relogio = {"t": 1_000.0}
    monkeypatch.setattr(bcb_service, "_agora", lambda: relogio["t"])

    async def serie_fora_do_ar(codigo, ini, fim):
        raise RuntimeError("BCB fora do ar")

    monkeypatch.setattr(bcb_service, "_buscar_serie", serie_fora_do_ar)
    assert (await bcb_service.selic_anualizada())["fonte"] == "fallback"

    # BCB volta após a janela: sucesso responde "bcb" e zera o cache negativo
    relogio["t"] += bcb_service.FALLBACK_TTL_SEGUNDOS + 1.0

    async def serie_ok(codigo, ini, fim):
        return [{"data": f"01/{m:02d}/2026", "valor": "0,80"} for m in range(1, 13)]

    monkeypatch.setattr(bcb_service, "_buscar_serie", serie_ok)
    assert (await bcb_service.selic_anualizada())["fonte"] == "bcb"
    assert bcb_service._fallback_ate == 0.0
