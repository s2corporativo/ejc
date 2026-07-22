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
   e executa quando ligado (o gate é LIGADO por default=True); add_job
   registrado no start_scheduler.
5) Federação EXPLÍCITA por jurisdição (ALMG/MG-estadual, Betim-municipal, TRT-3,
   TRF-6, juizados): presença no catálogo, URN/consulta bem-formadas e na
   allowlist oficial, categoria correta por esfera, e wiring no ingerir().
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


# ── 5. Federação EXPLÍCITA por jurisdição ─────────────────────────────────────

_SLUGS_ESPERADOS = {
    "mg_estadual_almg", "betim_municipal",
    "trt3_jurisprudencia", "trf6_jurisprudencia", "juizados_especiais",
}


def test_jurisdicoes_federadas_cobrem_alvos_e_tipos():
    por_slug = {j.slug: j for j in lexml.JURISDICOES_FEDERADAS}
    assert _SLUGS_ESPERADOS <= set(por_slug)
    # Legislação estadual/municipal são face 'legislacao'; tribunais/juizados
    # são face 'jurisprudencia'.
    assert por_slug["mg_estadual_almg"].tipo == "legislacao"
    assert por_slug["betim_municipal"].tipo == "legislacao"
    assert por_slug["trt3_jurisprudencia"].tipo == "jurisprudencia"
    assert por_slug["trf6_jurisprudencia"].tipo == "jurisprudencia"
    assert por_slug["juizados_especiais"].tipo == "jurisprudencia"
    # Betim é MUNICIPAL: a localidade carrega o município no esquema URN LexML.
    assert por_slug["betim_municipal"].localidade == "minas.gerais;betim"
    assert por_slug["mg_estadual_almg"].localidade == "minas.gerais"


def test_urn_prefixo_bem_formada_por_jurisdicao():
    for j in lexml.JURISDICOES_FEDERADAS:
        urn = lexml.urn_prefixo(j)
        assert lexml._urn_bem_formada(urn), urn
        assert urn.startswith("urn:lex:br;minas.gerais")
    por_slug = {j.slug: j for j in lexml.JURISDICOES_FEDERADAS}
    assert lexml.urn_prefixo(por_slug["betim_municipal"]) == \
        "urn:lex:br;minas.gerais;betim:camara.municipal"
    assert lexml.urn_prefixo(por_slug["mg_estadual_almg"]) == \
        "urn:lex:br;minas.gerais:assembleia.legislativa"
    assert lexml.urn_prefixo(por_slug["trt3_jurisprudencia"]) == \
        "urn:lex:br;minas.gerais:tribunal.regional.trabalho.regiao.3"
    # URN malformada é rejeitada (não é URL; validada por forma)
    assert not lexml._urn_bem_formada("urn:lex:br")
    assert not lexml._urn_bem_formada("http://lexml.gov.br/x")


def test_categoria_de_gravacao_por_esfera():
    for j in lexml.JURISDICOES_FEDERADAS:
        cat = lexml._CATEGORIA[j.tipo]
        if j.tipo == "legislacao":
            # INVARIANTE DE SEGURANÇA: legislação federada NUNCA em 'legislacao%'
            assert cat == "referencia_legislativa"
            assert not cat.startswith("legislacao")
        else:
            assert cat == "jurisprudencia"


def test_consulta_url_e_urn_passam_pela_allowlist_oficial():
    from app.routers.ia_governanca import _fonte_oficial
    for j in lexml.JURISDICOES_FEDERADAS:
        url = lexml.consulta_url(j.consulta, j.tipo)
        assert _fonte_oficial(url) is True, url        # lexml.gov.br é oficial
    # o helper interno do ingestor delega para a MESMA allowlist canônica
    assert lexml._url_oficial("https://www.lexml.gov.br/busca/pesquisa?palavras=x") is True
    assert lexml._url_oficial("https://jusbrasil.com.br/x") is False
    assert lexml._url_oficial("") is False


def test_plano_federacao_inclui_jurisdicoes_e_temas(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "LEXML_INGEST_TEMAS", "tema1", raising=False)
    plano = lexml._plano_federacao(s)
    # jurisdições explícitas entram com objeto JurisdicaoLexML e seu tipo único
    jurs = [(c, t, j) for (c, t, j) in plano if j is not None]
    slugs = {j.slug for (_, _, j) in jurs}
    assert _SLUGS_ESPERADOS <= slugs
    # tema genérico entra nos DOIS tipos, sem jurisdição
    temas = [(c, t) for (c, t, j) in plano if j is None]
    assert ("tema1", "legislacao") in temas and ("tema1", "jurisprudencia") in temas


# Item que buscar_lexml devolveria para a consulta explícita do TRT-3.
_TRT3 = next(j for j in lexml.JURISDICOES_FEDERADAS if j.slug == "trt3_jurisprudencia")
_ALMG = next(j for j in lexml.JURISDICOES_FEDERADAS if j.slug == "mg_estadual_almg")
JUR_TRT3_ITEM = {
    "titulo": "TRT-3 — adicional de insalubridade",
    "ementa": "ADICIONAL DE INSALUBRIDADE. Perícia. Base de cálculo. Devido o "
              "adicional em grau médio com reflexos nas verbas rescisórias.",
    "tribunal": "TRT-3", "relator": "Des. Ciclano",
    "numero_acordao": "tribunal.regional.trabalho.regiao.3;ac;9999",
    "data_julgamento": "2025-04-01", "fonte": "LexML",
    "link_original": "https://www.lexml.gov.br/urn/z", "area_juridica": "Trabalhista",
}
LEG_ALMG_ITEM = {
    "titulo": "Lei Estadual MG 99.999/2021 — carreira do servidor",
    "ementa": "Institui plano de carreira dos servidores do Estado de Minas "
              "Gerais e estabelece regras de progressão e vencimentos.",
    "tribunal": "", "relator": "Assembleia Legislativa de Minas Gerais",
    "numero_acordao": "minas.gerais:lei;99.999;2021", "data_julgamento": "2021-02-02",
    "fonte": "LexML",
    # link NÃO-oficial de propósito: deve ser rejeitado e cair p/ a URL de consulta
    "link_original": "https://jusbrasil.com.br/lei-mg", "area_juridica": "Administrativo",
}


async def test_ingerir_federa_jurisdicoes_explicitas(monkeypatch):
    ups: list[dict] = []
    # Só as consultas das jurisdições ALMG e TRT-3 retornam itens; nenhum tema.
    por_tipo = {
        (_TRT3.consulta, "jurisprudencia"): [JUR_TRT3_ITEM],
        (_ALMG.consulta, "legislacao"): [LEG_ALMG_ITEM],
    }
    _prepara(monkeypatch, temas="", por_tipo=por_tipo, upserts=ups)
    novos, total = await lexml.ingerir(_FakeDB())
    assert (novos, total) == (2, 2)

    por_chave = {u["chave_origem"]: u for u in ups}
    trt3 = por_chave["lexml:jur:tribunal.regional.trabalho.regiao.3;ac;9999"]
    almg = por_chave["lexml:leg:minas.gerais:lei;99.999;2021"]

    # Categorias corretas por esfera (invariante de segurança preservado)
    assert almg["categoria"] == "referencia_legislativa"
    assert not almg["categoria"].startswith("legislacao")
    assert trt3["categoria"] == "jurisprudencia"

    # Metadados da federação explícita
    assert trt3["extra"]["jurisdicao"] == "trt3_jurisprudencia"
    assert trt3["extra"]["esfera"] == "trabalhista"
    assert trt3["extra"]["urn_lex_prefixo"] == \
        "urn:lex:br;minas.gerais:tribunal.regional.trabalho.regiao.3"
    assert almg["extra"]["jurisdicao"] == "mg_estadual_almg"
    assert almg["extra"]["urn_lex_prefixo"] == \
        "urn:lex:br;minas.gerais:assembleia.legislativa"

    # 'fonte' GRAVADA sempre passa a allowlist oficial:
    from app.routers.ia_governanca import _fonte_oficial
    assert _fonte_oficial(trt3["fonte"]) is True         # link_original oficial (lexml.gov.br)
    assert trt3["fonte"] == "https://www.lexml.gov.br/urn/z"
    # link não-oficial do ALMG é descartado → cai p/ a URL de consulta do federador
    assert _fonte_oficial(almg["fonte"]) is True
    assert almg["fonte"].startswith("https://www.lexml.gov.br/busca/pesquisa")


async def test_ingerir_temas_ainda_rodam_com_jurisdicoes_ativas(monkeypatch):
    # As jurisdições explícitas NÃO desligam a varredura por tema: com um tema
    # override e itens só nele, o resultado é o mesmo do comportamento anterior.
    ups: list[dict] = []
    chamadas = _prepara(monkeypatch, upserts=ups)   # temas='tema1', itens padrão
    novos, total = await lexml.ingerir(_FakeDB())
    assert (novos, total) == (3, 3)                  # LEG + 2 JUR do tema1
    # o plano também consultou as jurisdições explícitas (mesmo sem itens)
    assert (_TRT3.consulta, "jurisprudencia") in chamadas
    assert (_ALMG.consulta, "legislacao") in chamadas
