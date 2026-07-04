"""Verificador RIGOROSO de jurisprudência — parser CNJ (DV mód. 97), súmulas em
faixa, recursos superiores, menções vagas, score e DataJud opt-in (mockado)."""
import pytest

from app.services.verificador_jurisprudencia import (
    MAX_CONSULTAS_DATAJUD,
    SUMULA_TETO,
    analisar_texto,
    decodificar_cnj,
    validar_dv_cnj,
    verificar_jurisprudencia,
)

# Números CNJ pré-calculados (DV pelo módulo 97 — Res. CNJ 65/2008):
CNJ_VALIDO_TJMG = "0001234-10.2020.8.13.0024"   # DV correto, TJMG
CNJ_VALIDO_STJ = "0004567-56.2019.3.00.0000"    # DV correto, STJ
CNJ_DV_ERRADO = "0001234-11.2020.8.13.0024"     # DV incorreto
CNJ_TRIB_INEXISTENTE = "0001234-16.2020.8.99.0024"  # DV ok, TJ '99' não existe


class _Row:
    def first(self):
        return None   # base RAG "vazia": nada confirmado


class _FakeDB:
    async def execute(self, *a, **k):
        return _Row()


class _RowSumula:
    def first(self):
        return ("Súmula 7 STJ — reexame de prova",)


class _FakeDBComSumula:
    async def execute(self, *a, **k):
        return _RowSumula()


def _por_tipo(r, tipo):
    return [c for c in r["citacoes"] if c["tipo"] == tipo]


# ── Dígito verificador CNJ ────────────────────────────────────────────────────

def test_dv_cnj_valido_e_invalido():
    assert validar_dv_cnj(CNJ_VALIDO_TJMG)
    assert validar_dv_cnj(CNJ_VALIDO_STJ)
    assert not validar_dv_cnj(CNJ_DV_ERRADO)
    assert not validar_dv_cnj("123")  # tamanho errado


def test_decodifica_segmento_tribunal():
    d = decodificar_cnj(CNJ_VALIDO_TJMG)
    assert d["tribunal"] == "TJMG" and d["ano"] == "2020" and d["tribunal_valido"]
    d2 = decodificar_cnj(CNJ_VALIDO_STJ)
    assert d2["tribunal"] == "STJ" and d2["tribunal_valido"]
    d3 = decodificar_cnj(CNJ_TRIB_INEXISTENTE)
    assert not d3["tribunal_valido"]


async def test_cnj_dv_valido_sem_datajud_fica_identificada():
    r = await verificar_jurisprudencia(_FakeDB(), f"Ação no processo {CNJ_VALIDO_TJMG}.")
    (c,) = _por_tipo(r, "processo_cnj")
    assert c["status"] == "identificada"
    assert c["tribunal"] == "TJMG"
    assert c["encontrada"] is False        # chave legada preservada
    assert c["aviso"]


async def test_cnj_dv_invalido_vira_suspeita():
    r = await verificar_jurisprudencia(_FakeDB(), f"Como decidido em {CNJ_DV_ERRADO}.")
    (c,) = _por_tipo(r, "processo_cnj")
    assert c["status"] == "suspeita"
    assert "verificador" in c["aviso"].lower() or "dígito" in c["aviso"].lower()


async def test_cnj_tribunal_inexistente_vira_suspeita():
    r = await verificar_jurisprudencia(_FakeDB(), f"Autos {CNJ_TRIB_INEXISTENTE}.")
    (c,) = _por_tipo(r, "processo_cnj")
    assert c["status"] == "suspeita"


# ── Súmulas: faixa plausível + confirmação no RAG ────────────────────────────

async def test_sumula_em_faixa_nao_confirmada_fica_identificada():
    r = await verificar_jurisprudencia(_FakeDB(), "Aplica-se a Súmula 297 do STJ.")
    (c,) = _por_tipo(r, "sumula")
    assert c["status"] == "identificada"
    assert c["tribunal"] == "STJ"


async def test_sumula_fora_de_faixa_vira_suspeita():
    acima = SUMULA_TETO["STJ"] + 100
    r = await verificar_jurisprudencia(_FakeDB(), f"Nos termos da Súmula {acima} do STJ.")
    (c,) = _por_tipo(r, "sumula")
    assert c["status"] == "suspeita"
    assert "faixa" in c["aviso"]


async def test_sumula_confirmada_no_rag_fica_verificada():
    r = await verificar_jurisprudencia(_FakeDBComSumula(), "Incide a Súmula 7 do STJ.")
    sums = _por_tipo(r, "sumula")
    assert sums and sums[0]["status"] == "verificada"
    assert sums[0]["encontrada"] is True and sums[0]["fonte"]
    assert r["confirmadas"] >= 1


# ── Recursos superiores ──────────────────────────────────────────────────────

async def test_resp_identificado_com_tribunal_stj():
    r = await verificar_jurisprudencia(
        _FakeDB(),
        "Conforme REsp 1.737.428/SP, Terceira Turma, Rel. Min. Nancy Andrighi, "
        "julgado em 12/02/2019.",
    )
    (c,) = _por_tipo(r, "recurso")
    assert c["status"] == "identificada"
    assert c["tribunal"] == "STJ"
    assert c["orgao"] and "Turma" in c["orgao"]
    assert c["relator"] and "Nancy" in c["relator"]
    assert c["data"] == "12/02/2019"


# ── Menções vagas → generica ─────────────────────────────────────────────────

async def test_mencao_vaga_sem_referencia_vira_generica():
    r = await verificar_jurisprudencia(
        _FakeDB(), "A jurisprudência pacífica dos tribunais ampara o pedido.")
    gen = _por_tipo(r, "generica")
    assert gen and gen[0]["status"] == "generica"
    assert "sem referência" in gen[0]["aviso"]


async def test_mencao_vaga_com_referencia_proxima_nao_vira_generica():
    r = await verificar_jurisprudencia(
        _FakeDB(),
        "É o entendimento consolidado do STJ (REsp 1.737.428/SP) sobre o tema.")
    assert not _por_tipo(r, "generica")
    assert _por_tipo(r, "recurso")


# ── Score de confiabilidade ──────────────────────────────────────────────────

async def test_score_pondera_status():
    # 1 verificada (súmula no RAG mockado)... usar duas verificações separadas:
    r = await verificar_jurisprudencia(
        _FakeDB(),
        f"Processo {CNJ_VALIDO_TJMG} e também {CNJ_DV_ERRADO}.")
    # 1 identificada (0.6) + 1 suspeita (0) sobre 2 → 30
    assert r["score"] == 30
    assert r["contagem_status"]["identificada"] == 1
    assert r["contagem_status"]["suspeita"] == 1


async def test_texto_sem_citacoes_score_null():
    r = await verificar_jurisprudencia(_FakeDB(), "Bom dia, segue relatório da reunião.")
    assert r["total"] == 0
    assert r["score"] is None
    assert any("Nenhuma citação" in a for a in r["avisos"])


# ── DataJud opt-in (mockado, fail-safe) ──────────────────────────────────────

async def test_datajud_confirma_vira_verificada(monkeypatch):
    from app.services import datajud_service

    async def fake_consulta(numero):
        return {"classe": "Procedimento Comum Cível", "orgao": "2ª Vara Cível",
                "movimentos": []}

    monkeypatch.setattr(datajud_service, "consultar_processo", fake_consulta)
    r = await verificar_jurisprudencia(
        _FakeDB(), f"Processo {CNJ_VALIDO_TJMG}.", consultar_datajud=True)
    (c,) = _por_tipo(r, "processo_cnj")
    assert c["status"] == "verificada"
    assert "DataJud" in c["fonte_verificacao"]
    assert c["orgao"] == "2ª Vara Cível"
    assert r["score"] == 100


async def test_datajud_falha_cai_para_identificada(monkeypatch):
    from app.services import datajud_service

    async def fake_erro(numero):
        raise RuntimeError("API fora do ar")

    monkeypatch.setattr(datajud_service, "consultar_processo", fake_erro)
    r = await verificar_jurisprudencia(
        _FakeDB(), f"Processo {CNJ_VALIDO_TJMG}.", consultar_datajud=True)
    (c,) = _por_tipo(r, "processo_cnj")
    assert c["status"] == "identificada"    # nunca erro
    assert "indisponível" in c["aviso"]


async def test_datajud_suspeita_nao_consome_consulta(monkeypatch):
    """DV inválido nem chega ao DataJud (economiza o teto de consultas)."""
    from app.services import datajud_service
    chamadas = []

    async def fake_consulta(numero):
        chamadas.append(numero)
        return None

    monkeypatch.setattr(datajud_service, "consultar_processo", fake_consulta)
    await verificar_jurisprudencia(
        _FakeDB(), f"Processos {CNJ_DV_ERRADO} e {CNJ_VALIDO_TJMG}.",
        consultar_datajud=True)
    assert chamadas == [CNJ_VALIDO_TJMG]
    assert MAX_CONSULTAS_DATAJUD == 5   # teto documentado


# ── Retrocompatibilidade do shape (call sites legados) ───────────────────────

async def test_shape_legado_preservado():
    r = await verificar_jurisprudencia(
        _FakeDB(), "Aplica-se a Súmula 7 do STJ e o art. 927 do CC ao caso.")
    # chaves de topo legadas
    for k in ("total", "confirmadas", "nao_encontradas", "citacoes", "aviso"):
        assert k in r
    assert r["total"] == 2 and r["confirmadas"] == 0 and r["nao_encontradas"] == 2
    # itens legados
    for c in r["citacoes"]:
        for k in ("citacao", "tipo", "encontrada", "fonte", "status", "aviso"):
            assert k in c
    rotulos = [c["citacao"] for c in r["citacoes"]]
    assert any("Súmula 7" in x for x in rotulos)
    assert any("927" in x for x in rotulos)


def test_parser_extrai_orgao_relator_data():
    achados = analisar_texto(
        f"Processo {CNJ_VALIDO_STJ}, Corte Especial, Rel. Min. Herman Benjamin, "
        "DJe de 03/05/2021."
    )
    (c,) = [a for a in achados if a["tipo"] == "processo_cnj"]
    assert c["orgao"] and "Corte Especial" in c["orgao"]
    assert c["relator"] and "Herman" in c["relator"]
    assert c["data"] == "03/05/2021"
