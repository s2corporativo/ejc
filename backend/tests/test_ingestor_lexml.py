"""Ingestor LexML (federação legislação + jurisprudência → RAG).

Cobre (SEM rede — o LexML não é alcançável neste ambiente; buscar_lexml é
mockado, mesma estratégia do test_ingestor_tjmg):
1) _chave: dedup determinístico, namespaced por tipo (leg/jur) — com URN e sem
   (hash de título+ementa).
2) _monta_conteudo / _temas: montagem do conteúdo citável e config de temas.
3) ingerir(): wiring de upsert por item (2 tipos por tema), categorias corretas,
   INVARIANTE DE SEGURANÇA (legislação NÃO entra em 'legislacao%' — não afrouxa o
   citation gate), metadados/confiança, dedup intra-execução e tolerância a erro.
4) Gate do scheduler: job_ingestao_lexml é no-op com LEXML_INGEST_ENABLED=False
   (default) e executa quando ligado; add_job registrado no start_scheduler.
"""
from __future__ import annotations

import app.services.ingestors.lexml as lexml
from app.core.config import get_settings


# ── Fixtures: itens no shape que jurisprudencia_externa.buscar_lexml devolve ──
LEG_ITEM = {
    "titulo": "Lei Estadual MG 12.345/2020 — servidor público",
    "ementa": "Dispõe sobre o regime jurídico dos servidores públicos do Estado "
              "de Minas Gerais e dá outras providências relativas à carreira.",
    "tribunal": "TJMG", "relator": "Assembleia Legislativa de Minas Gerais",
    "numero_acordao": "minas.gerais:lei;12.345;2020", "data_julgamento": "2020-06-01",
    "fonte": "LexML", "link_original": "https://www.lexml.gov.br/urn/x",
    "area_juridica": "Administrativo", "orgao_julgador": "", "classe": "",
}
JUR_ITEM = {
    "titulo": "TRT-3 — horas extras",
    "ementa": "HORAS EXTRAS. Ônus da prova. Cartões de ponto britânicos. "
              "Invalidade. Devidas as horas extras habituais e reflexos.",
    "tribunal": "TRT-3", "relator": "Des. Fulano",
    "numero_acordao": "tribunal.regional.trabalho.3;ac;0001", "data_julgamento": "2025-05-10",
    "fonte": "LexML", "link_original": "https://www.lexml.gov.br/urn/y",
    "area_juridica": "Trabalhista", "orgao_julgador": "", "classe": "Acórdão",
}
JUR_SEM_URN = {
    "titulo": "STJ — recurso repetitivo consumidor",
    "ementa": "RECURSO REPETITIVO. Direito do consumidor. Fixação de tese sobre "
              "cobrança indevida e repetição do indébito em dobro.",
    "tribunal": "STJ", "relator": "Min. Beltrano",
    "numero_acordao": "", "data_julgamento": "2024-03-03",
    "fonte": "LexML", "link_original": "", "area_juridica": "Consumidor",
    "orgao_julgador": "", "classe": "Acórdão",
}


# ── 1. _chave (dedup determinístico namespaced por tipo) ──────────────────────

def test_chave_com_urn_namespaced_por_tipo():
    kl = lexml._chave(LEG_ITEM, "legislacao")
    kj = lexml._chave(LEG_ITEM, "jurisprudencia")
    assert kl == "lexml:leg:minas.gerais:lei;12.345;2020"
    assert kj == "lexml:jur:minas.gerais:lei;12.345;2020"
    assert kl != kj          # mesmo URN não colide entre as faces leg/jur


def test_chave_sem_urn_usa_hash_estavel():
    k1 = lexml._chave(JUR_SEM_URN, "jurisprudencia")
    k2 = lexml._chave(dict(JUR_SEM_URN), "jurisprudencia")
    assert k1 == k2
    assert k1.startswith("lexml:jur:") and len(k1) == len("lexml:jur:") + 16
    outro = {"titulo": "x", "ementa": "ementa completamente diferente aqui"}
    assert lexml._chave(outro, "jurisprudencia") != k1


# ── 2. _monta_conteudo / _temas ───────────────────────────────────────────────

def test_monta_conteudo_jurisprudencia_inclui_tribunal_e_ementa():
    txt = lexml._monta_conteudo(JUR_ITEM, "jurisprudencia")
    assert "TRT-3 — horas extras" in txt
    assert "Tribunal: TRT-3" in txt
    assert "HORAS EXTRAS" in txt


def test_monta_conteudo_legislacao_nao_rotula_tribunal():
    txt = lexml._monta_conteudo(LEG_ITEM, "legislacao")
    assert "Lei Estadual MG" in txt
    assert "Tribunal:" not in txt          # tribunal é metadado só de julgado


def test_temas_default_e_override(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "LEXML_INGEST_TEMAS", "", raising=False)
    assert lexml._temas(s) == lexml.TEMAS_PADRAO
    monkeypatch.setattr(s, "LEXML_INGEST_TEMAS", " TRT-3 horas extras , Betim lei municipal ,",
                        raising=False)
    assert lexml._temas(s) == ["TRT-3 horas extras", "Betim lei municipal"]


def test_temas_padrao_cobre_autoridades_alvo():
    blob = " ".join(lexml.TEMAS_PADRAO).lower()
    for alvo in ("tjmg", "trt-3", "trf-6", "trf-1", "tst", "stj", "stf",
                 "juizado especial", "almg", "betim"):
        assert alvo in blob, alvo


# ── Infra de mock (sem rede, sem banco) — mesmo padrão do test_ingestor_tjmg ──

class _FakeDB:
    async def commit(self):
        pass

    async def rollback(self):
        pass


def _prepara(monkeypatch, *, temas="tema1", por_tipo=None, upserts=None,
             upsert_erro=False):
    s = get_settings()
    monkeypatch.setattr(s, "LEXML_INGEST_TEMAS", temas, raising=False)
    monkeypatch.setattr(s, "LEXML_INGEST_MAX_POR_TEMA", 20, raising=False)

    chamadas: list[tuple[str, str]] = []
    por_tipo = por_tipo or {
        ("tema1", "legislacao"): [LEG_ITEM],
        ("tema1", "jurisprudencia"): [JUR_ITEM, JUR_SEM_URN],
    }

    async def fake_buscar(palavras, tipo="jurisprudencia", por_pagina=10, **kw):
        chamadas.append((palavras, tipo))
        return list(por_tipo.get((palavras, tipo), []))

    monkeypatch.setattr(lexml, "buscar_lexml", fake_buscar)

    async def fake_upsert(db, **kwargs):
        if upsert_erro:
            raise RuntimeError("boom")
        if upserts is not None:
            upserts.append(kwargs)
        return "novo"

    monkeypatch.setattr(lexml, "upsert_documento", fake_upsert)
    return chamadas


# ── 3. ingerir() ──────────────────────────────────────────────────────────────

async def test_ingerir_varre_dois_tipos_e_categoriza(monkeypatch):
    ups: list[dict] = []
    chamadas = _prepara(monkeypatch, upserts=ups)

    novos, total = await lexml.ingerir(_FakeDB())

    # cada tema é buscado nos DOIS tipos
    assert ("tema1", "legislacao") in chamadas
    assert ("tema1", "jurisprudencia") in chamadas
    assert (novos, total) == (3, 3)      # LEG + 2 JUR

    por_chave = {u["chave_origem"]: u for u in ups}
    assert "lexml:leg:minas.gerais:lei;12.345;2020" in por_chave
    assert "lexml:jur:tribunal.regional.trabalho.3;ac;0001" in por_chave
    assert any(c.startswith("lexml:jur:") and len(c) == len("lexml:jur:") + 16
               for c in por_chave)       # JUR_SEM_URN via hash

    leg = por_chave["lexml:leg:minas.gerais:lei;12.345;2020"]
    jur = por_chave["lexml:jur:tribunal.regional.trabalho.3;ac;0001"]

    # INVARIANTE DE SEGURANÇA: legislação federada NÃO entra em 'legislacao%'
    # (não afrouxa citation_check._existe_artigo, que casa categoria LIKE
    # 'legislacao%'); jurisprudência é 'jurisprudencia' (gate de súmula é 'sumula%').
    assert leg["categoria"] == "referencia_legislativa"
    assert not leg["categoria"].startswith("legislacao")
    assert jur["categoria"] == "jurisprudencia"

    # tribunal só na face jurisprudência
    assert jur["tribunal"] == "TRT-3"
    assert leg["tribunal"] is None

    # governança da fonte oficial
    assert all(u["confianca"] == "alta" for u in ups)
    assert all(u["extra"]["rag_status"] == "aprovado" for u in ups)
    assert all(u["extra"]["origem"] == "lexml" for u in ups)
    assert leg["extra"]["tipo_fonte"] == "legislacao_referencia"
    assert jur["extra"]["tipo_fonte"] == "jurisprudencia_oficial"


async def test_ingerir_deduplica_intra_execucao(monkeypatch):
    ups: list[dict] = []
    # mesmo LEG_ITEM aparece em tema1 e tema2 (só entra uma vez)
    por_tipo = {
        ("tema1", "legislacao"): [LEG_ITEM],
        ("tema1", "jurisprudencia"): [],
        ("tema2", "legislacao"): [LEG_ITEM],
        ("tema2", "jurisprudencia"): [],
    }
    _prepara(monkeypatch, temas="tema1,tema2", por_tipo=por_tipo, upserts=ups)
    novos, total = await lexml.ingerir(_FakeDB())
    assert (novos, total) == (1, 1)
    assert len(ups) == 1


async def test_ingerir_ignora_ementa_curta(monkeypatch):
    ups: list[dict] = []
    curto = {**LEG_ITEM, "numero_acordao": "urn-curto", "ementa": "curta"}
    _prepara(monkeypatch, temas="tema1",
             por_tipo={("tema1", "legislacao"): [curto],
                       ("tema1", "jurisprudencia"): []}, upserts=ups)
    assert await lexml.ingerir(_FakeDB()) == (0, 0)
    assert ups == []


async def test_ingerir_tolerante_a_erro_de_upsert(monkeypatch):
    _prepara(monkeypatch, temas="tema1",
             por_tipo={("tema1", "legislacao"): [LEG_ITEM],
                       ("tema1", "jurisprudencia"): []}, upsert_erro=True)
    # erro no upsert é capturado (rollback + continua) → não levanta; com commit
    # por item, o item falho NÃO persiste nem conta.
    assert await lexml.ingerir(_FakeDB()) == (0, 0)


async def test_ingerir_tolerante_a_erro_de_busca(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "LEXML_INGEST_TEMAS", "tema1", raising=False)

    async def fake_buscar(palavras, tipo="jurisprudencia", por_pagina=10, **kw):
        raise RuntimeError("LexML fora do ar")

    monkeypatch.setattr(lexml, "buscar_lexml", fake_buscar)
    # rede/fonte indisponível num tipo/tema NÃO derruba a execução
    assert await lexml.ingerir(_FakeDB()) == (0, 0)


# ── 4. Gate no scheduler ──────────────────────────────────────────────────────

async def test_job_lexml_gate_off_e_on(monkeypatch):
    from app.services import scheduler as sch
    import app.services.ingestion_service as ing

    execucoes: list[str] = []

    async def fake_exec(slug, *a, **k):
        execucoes.append(slug)
        return (0, 0)

    monkeypatch.setattr(ing, "executar_ingestao", fake_exec)

    # Gate OFF (explícito — independe do default): job é no-op.
    monkeypatch.setattr(get_settings(), "LEXML_INGEST_ENABLED", False)
    await sch.job_ingestao_lexml()
    assert execucoes == []                                # no-op com gate off

    # Gate ON (default do titular): job executa a ingestão.
    monkeypatch.setattr(get_settings(), "LEXML_INGEST_ENABLED", True)
    await sch.job_ingestao_lexml()
    assert execucoes == ["lexml"]


def test_job_lexml_registrado_no_scheduler():
    import inspect
    from app.services import scheduler as sch
    src = inspect.getsource(sch.start_scheduler)
    assert "job_ingestao_lexml" in src and "ing_lexml" in src
