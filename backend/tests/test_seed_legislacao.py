# ── tests/test_seed_legislacao.py ────────────────────────────────────────────
# Ingestor UNIFICADO de legislação (lei seca) — app/services/ingestors/planalto.py
# + wrapper CLI scripts/seed_legislacao.py.
#
# Cinco frentes (nenhuma depende de rede — download SEMPRE mockado):
#   1. parser em unidade com fixture HTML versionada (recorte adaptado do
#      Planalto/CDC): texto limpo verbatim, boilerplate/riscado removidos,
#      divisão por artigo e chunks no formato que _existe_artigo consome;
#   2. integridade do catálogo unificado (9 códigos legados + 5 leis do seed);
#   3. executar_seed_legislacao() com upsert monkeypatchado (governança:
#      categoria/confiança/chave LEGADA planalto:<slug>; isolamento de falha);
#   4. idempotência + versionamento + smoke do gate no Postgres real
#      (RUN_DB_TESTS=1; mesmo padrão dos *_dblevel.py);
#   5. UNIFICAÇÃO no Postgres real: seed + job do scheduler na MESMA chave não
#      duplicam; doc de produção com chunking antigo é re-chunkado UMA vez.
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text as sql

import app.services.ingestors.planalto as pl
import scripts.seed_legislacao as sl
from app.services.ingestors.planalto import (
    CATALOGO,
    dividir_artigos,
    extrair_texto_planalto,
    montar_chunks,
    preparar_diploma,
)

FIXTURE = Path(__file__).parent / "fixtures" / "planalto_cdc_recorte.html"
NOME = "Código de Defesa do Consumidor (Lei 8.078/1990)"


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    """Mesmo padrão dos *_dblevel.py: descarta o pool do engine global após
    as frentes 4-5 (Postgres real, RUN_DB_TESTS) — sem isso, o próximo
    teste de OUTRO módulo (event loop novo por teste, padrão pytest-asyncio)
    pode herdar conexões presas ao loop já encerrado ('Future attached to a
    different loop'). No-op/barato nas frentes 1-3 (upsert mockado, sem
    engine real)."""
    yield
    from app.core.database import engine
    await engine.dispose()


@pytest.fixture(scope="module")
def html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def texto(html) -> str:
    return extrair_texto_planalto(html)


@pytest.fixture(scope="module")
def blocos(texto):
    return dividir_artigos(texto)


def _casa_existe_artigo(chunk: str, num: str) -> bool:
    """Reproduz em Python o lookup SQL de citation_check._existe_artigo:
    conteudo ILIKE '%Art. N %' OR conteudo ILIKE '%Art. Nº%'."""
    c = chunk.lower()
    return f"art. {num} " in c or f"art. {num}º" in c


# ══════════════════════════════════════════════════════════════════════════
# 1. Parser (fixture HTML)
# ══════════════════════════════════════════════════════════════════════════

def test_extrai_texto_remove_boilerplate_e_scripts(texto):
    assert "ruído de navegação" not in texto            # <script>
    assert "text-indent" not in texto                    # <style>
    assert "Subchefia para Assuntos Jurídicos" not in texto
    assert "Texto compilado" not in texto
    assert "Mensagem de veto" not in texto
    assert "Este texto não substitui o publicado" not in texto
    assert "\xa0" not in texto                           # NBSP normalizado


def test_extrai_texto_verbatim(texto):
    # texto de lei NÃO é resumido/reescrito — frases oficiais intactas
    assert ("Art. 2º Consumidor é toda pessoa física ou jurídica que adquire "
            "ou utiliza produto ou serviço como destinatário final.") in texto
    assert "salvo as decorrentes das relações de caráter trabalhista" in texto
    # epígrafe/ementa preservadas (fazem parte do documento oficial)
    assert "LEI Nº 8.078, DE 11 DE SETEMBRO DE 1990." in texto
    assert "Dispõe sobre a proteção do consumidor" in texto


def test_texto_riscado_revogado_mantem_so_a_anotacao(texto):
    # riscado COM anotação → teor sai, "(Revogado ...)" fica
    assert "Dispositivo hipotético" not in texto
    assert "(Revogado pela Lei nº 99.999, de 2020)" in texto
    # riscado SEM anotação → some por inteiro; anotação não-riscada ao lado fica
    assert "Redação antiga hipotética" not in texto
    assert "(Redação dada pela Lei nº 99.998, de 2019)" in texto


def test_dividir_artigos_um_bloco_por_artigo(blocos):
    rotulos = [r for r, _ in blocos if r]
    assert rotulos == ["Art. 1", "Art. 2", "Art. 3", "Art. 4", "Art. 6", "Art. 10"]
    por_rotulo = {r: t for r, t in blocos if r}
    # caput + parágrafos/incisos/alíneas juntos no bloco do artigo
    assert "Parágrafo único. Equipara-se a consumidor" in por_rotulo["Art. 2"]
    assert "§ 2º Serviço é qualquer atividade" in por_rotulo["Art. 3"]
    assert "(Revogado pela Lei nº 99.999, de 2020)" in por_rotulo["Art. 3"]
    assert "d) pela garantia dos produtos e serviços" in por_rotulo["Art. 4"]
    assert "anúncios publicitários" in por_rotulo["Art. 10"]
    # sem vazamento entre artigos
    assert "Equipara-se a consumidor" not in por_rotulo["Art. 3"]
    # preâmbulo (antes do Art. 1º) vira bloco sem rótulo
    assert blocos[0][0] is None and "LEI Nº 8.078" in blocos[0][1]


def test_dividir_artigos_referencia_interna_nao_abre_artigo():
    txt = ("Art. 5º Caput do quinto.\n"
           "Art. 2º da Lei nº 1.234 aplica-se subsidiariamente.\n"  # referência
           "Art. 6º Caput do sexto.")
    rotulos = [r for r, _ in dividir_artigos(txt) if r]
    assert rotulos == ["Art. 5", "Art. 6"]
    assert "aplica-se subsidiariamente" in dict(dividir_artigos(txt))["Art. 5"]


def test_dividir_artigos_sufixo_reset_e_milhar():
    txt = ("Art. 19. Caput.\n"
           "Art. 19-A. Incluído depois.\n"
           "Art. 1.022. Numeração com milhar.\n"
           "Art. 1º Recomeço de numeração (ex.: ADCT).")
    rotulos = [r for r, _ in dividir_artigos(txt) if r]
    assert rotulos == ["Art. 19", "Art. 19-A", "Art. 1.022", "Art. 1"]


# ══════════════════════════════════════════════════════════════════════════
# 2. Chunks no formato que _existe_artigo consome
# ══════════════════════════════════════════════════════════════════════════

def test_chunks_abrem_com_header_e_casam_existe_artigo(blocos):
    chunks = montar_chunks(NOME, blocos)
    assert chunks
    for c in chunks:
        primeira = c.split("\n", 1)[0]
        assert primeira.endswith(f"— {NOME}") or primeira == NOME
    # TODO artigo do recorte é encontrável pelo lookup do gate — inclusive o
    # "Art. 10." (grafia oficial com ponto), coberto pelo header "Art. 10 — ..."
    for num in ("1", "2", "3", "4", "6", "10"):
        assert any(_casa_existe_artigo(c, num) for c in chunks), f"Art. {num}"
    # verbatim dentro do chunk
    assert any("destinatário final." in c for c in chunks)


def test_chunks_respeitam_limite_do_pipeline(blocos):
    from app.services.ingestion_service import CHUNK_TAMANHO
    chunks = montar_chunks(NOME, blocos)
    # corpo limitado a CHUNK_TAMANHO; header de localização é o único acréscimo
    assert all(len(c) <= CHUNK_TAMANHO + 250 for c in chunks)


def test_artigo_longo_dividido_reabre_com_header():
    frase = "Inciso repetido para inflar o artigo além do limite do chunk. "
    blocos = [("Art. 7", "Art. 7º Caput longo. " + frase * 80)]
    chunks = montar_chunks(NOME, blocos, tamanho=1200)
    assert len(chunks) >= 2
    assert chunks[0].startswith(f"Art. 7 — {NOME}\n")
    assert all(c.startswith(f"Art. 7 (continuação) — {NOME}\n") for c in chunks[1:])
    assert all(_casa_existe_artigo(c, "7") for c in chunks)


def test_artigos_curtos_agrupados_enumeram_todos_no_header():
    blocos = [("Art. 10", "Art. 10. Caput curto."),
              ("Art. 11", "Art. 11. Outro caput curto."),
              ("Art. 12", "Art. 12. Terceiro caput curto.")]
    chunks = montar_chunks(NOME, blocos, tamanho=1200)
    assert len(chunks) == 1
    header = chunks[0].split("\n", 1)[0]
    assert header == f"Art. 10 · Art. 11 · Art. 12 — {NOME}"
    for num in ("10", "11", "12"):     # "Art. 11." não casaria sem o header
        assert _casa_existe_artigo(chunks[0], num)


# ══════════════════════════════════════════════════════════════════════════
# 3. Catálogo unificado (códigos legados do job semanal + leis do seed)
# ══════════════════════════════════════════════════════════════════════════

def test_catalogo_unificado_planalto_sem_duplicatas():
    slugs = [l["slug"] for l in CATALOGO]
    assert len(slugs) == len(set(slugs))
    # 9 códigos legados do ingestor (chaves de produção) + 5 leis novas do seed
    assert {"cf88", "cc", "cpc", "clt", "cdc", "cp", "cpp", "eca", "ctn",
            "l9099", "lgpd", "cflo", "lca", "pnma"} == set(slugs)
    for lei in CATALOGO:
        assert lei["url"].startswith("https://www.planalto.gov.br/ccivil_03/"), lei["slug"]
        assert lei["titulo"] and lei["area"], lei["slug"]
    # o wrapper CLI reexporta o MESMO catálogo (escritor único, sem cópia)
    assert sl.CATALOGO is pl.CATALOGO


def test_urls_legadas_de_producao_preservadas():
    # As URLs dos 9 códigos que já existiam no job semanal (produção) não
    # podem mudar — são a `fonte` dos docs vigentes com chave planalto:<slug>.
    urls = {l["slug"]: l["url"] for l in CATALOGO}
    assert urls["cf88"].endswith("/constituicao/constituicaocompilado.htm")
    assert urls["cc"].endswith("/leis/2002/l10406compilada.htm")
    assert urls["cpc"].endswith("/_ato2015-2018/2015/lei/l13105.htm")
    assert urls["clt"].endswith("/decreto-lei/del5452compilado.htm")
    assert urls["cdc"].endswith("/leis/l8078compilado.htm")
    assert urls["cp"].endswith("/decreto-lei/del2848compilado.htm")
    assert urls["cpp"].endswith("/decreto-lei/del3689compilado.htm")
    assert urls["eca"].endswith("/leis/l8069compilado.htm")
    assert urls["ctn"].endswith("/leis/l5172compilado.htm")


# ══════════════════════════════════════════════════════════════════════════
# 4. Seed com upsert monkeypatchado (sem Postgres, sem rede)
# ══════════════════════════════════════════════════════════════════════════

class _FakeDB:
    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.fixture()
def pipeline_mockado(monkeypatch, html):
    import app.services.ingestion_service as ing

    chamadas: list[dict] = []
    execucoes: list[dict] = []

    async def fake_upsert(db, **kw):
        chamadas.append(kw)
        return "novo"

    async def fake_fonte(db, slug, descricao, categoria_rag=None):
        assert slug == sl.FONTE_SLUG and categoria_rag == "legislacao"

    async def fake_exec(db, slug, **kw):
        execucoes.append({"slug": slug, **kw})

    async def fake_html(diploma, cache_dir=None):
        return html

    async def fake_rechunk(db, chave):
        return False               # _FakeDB não tem execute(); DB real na frente 5

    monkeypatch.setattr(ing, "upsert_documento", fake_upsert)
    monkeypatch.setattr(ing, "registrar_fonte", fake_fonte)
    monkeypatch.setattr(ing, "marcar_execucao", fake_exec)
    monkeypatch.setattr(pl, "obter_html", fake_html)
    monkeypatch.setattr(pl, "_rechunk_pendente", fake_rechunk)
    return chamadas, execucoes


async def test_seed_governanca_categoria_confianca_chave(pipeline_mockado):
    chamadas, execucoes = pipeline_mockado
    rel = await sl.executar_seed_legislacao(_FakeDB(), apenas="cdc,lgpd")
    assert not rel["falhas"] and set(rel["sucessos"]) == {"cdc", "lgpd"}
    assert len(chamadas) == 2
    for c in chamadas:
        assert c["categoria"] == "legislacao"       # o que _existe_artigo filtra
        assert c["confianca"] == "alta"             # fonte oficial (lei seca)
        assert c["fonte"].startswith("https://www.planalto.gov.br/")
        assert c["chave_origem"].startswith("planalto:")   # chave LEGADA de produção
        assert c["embutir_vetores"] is False        # default: auto-reembed depois
        assert c["forcar_nova_versao"] is False     # sem doc antigo → sem força
        assert c["extra"]["fonte_url"].startswith("https://www.planalto.gov.br/")
        assert c["extra"]["divisao"] == "por_artigo"
        assert c["extra"]["slug"] and c["extra"]["area"]
        assert c["chunks"] and all(isinstance(x, str) for x in c["chunks"])
    assert {c["chave_origem"] for c in chamadas} == \
           {"planalto:cdc", "planalto:lgpd"}
    assert execucoes and execucoes[0]["status"] == "sucesso" \
           and execucoes[0]["novos"] == 2 and execucoes[0]["total"] == 2


async def test_falha_de_uma_lei_nao_aborta_as_demais(pipeline_mockado, monkeypatch, html):
    chamadas, execucoes = pipeline_mockado

    async def html_com_falha(diploma, cache_dir=None):
        if diploma["slug"] == "cdc":
            raise RuntimeError("simulação: Planalto fora do ar")
        return html

    monkeypatch.setattr(pl, "obter_html", html_com_falha)
    rel = await sl.executar_seed_legislacao(_FakeDB(), apenas="cdc,l9099")
    assert set(rel["sucessos"]) == {"l9099"}
    assert "cdc" in rel["falhas"] and "Planalto fora do ar" in rel["falhas"]["cdc"]
    assert execucoes[0]["status"] == "parcial" and "cdc" in (execucoes[0]["erro"] or "")


async def test_ingestor_scheduler_usa_mesmo_pipeline(pipeline_mockado, monkeypatch):
    # planalto.ingerir (job semanal) passa pelos MESMOS ingerir_diploma/upsert
    chamadas, _ = pipeline_mockado
    monkeypatch.setattr(pl, "CATALOGO", [l for l in CATALOGO if l["slug"] == "cdc"])
    novos, total = await pl.ingerir(_FakeDB())
    assert (novos, total) == (1, 1)
    assert chamadas[-1]["chave_origem"] == "planalto:cdc"
    assert chamadas[-1]["extra"]["divisao"] == "por_artigo"
    assert chamadas[-1]["embutir_vetores"] is True   # job embeda inline (legado)


async def test_apenas_com_slug_desconhecido_falha_cedo(pipeline_mockado):
    with pytest.raises(SystemExit):
        await sl.executar_seed_legislacao(_FakeDB(), apenas="nao-existe")


def test_preparar_diploma_rejeita_pagina_errada():
    with pytest.raises(ValueError):
        preparar_diploma(CATALOGO[0], "<html><body><p>404</p></body></html>")


# ══════════════════════════════════════════════════════════════════════════
# 5. Idempotência + versionamento + gate + unificação (Postgres, RUN_DB_TESTS=1)
# ══════════════════════════════════════════════════════════════════════════

pytestmark_db = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture()
async def _engine_isolado():
    """Isola o engine async do loop-por-função do pytest-asyncio (mesmo padrão
    dos *_dblevel.py) — sem isso o pool asyncpg fica preso ao loop do teste
    anterior ('attached to a different loop')."""
    from app.core.database import engine
    await engine.dispose()
    yield
    await engine.dispose()


def _lei_teste(slug: str) -> dict:
    return {"slug": slug, "area": "consumidor",
            "titulo": "CDC RECORTE DE TESTE (seed_legislacao)",
            "url": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"}


async def _docs(db, chave: str):
    return (await db.execute(sql(
        "SELECT id, versao, vigente FROM knowledge_docs "
        "WHERE chave_origem = :k ORDER BY versao"), {"k": chave})).all()


async def _limpar(chave: str):
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await db.execute(sql(
            "DELETE FROM knowledge_chunks WHERE doc_id IN "
            "(SELECT id FROM knowledge_docs WHERE chave_origem = :k)"), {"k": chave})
        await db.execute(sql(
            "UPDATE knowledge_docs SET versao_anterior_id = NULL "
            "WHERE chave_origem = :k"), {"k": chave})
        await db.execute(sql(
            "DELETE FROM knowledge_docs WHERE chave_origem = :k"), {"k": chave})
        await db.commit()


@pytestmark_db
async def test_idempotencia_versionamento_e_gate_no_banco(monkeypatch, html, _engine_isolado):
    from app.core.database import AsyncSessionLocal
    from app.services.citation_check import _existe_artigo

    slug, chave = "cdcteste", "planalto:cdcteste"
    monkeypatch.setattr(pl, "CATALOGO", [_lei_teste(slug)])

    paginas = {"v": html}

    async def fake_html(diploma, cache_dir=None):
        return paginas["v"]

    monkeypatch.setattr(pl, "obter_html", fake_html)

    try:
        # 1ª execução → novo
        async with AsyncSessionLocal() as db:
            rel = await sl.executar_seed_legislacao(db, apenas=slug)
            assert not rel["falhas"]
            assert rel["sucessos"][slug]["resultado"] == "novo"
            n_chunks_1 = rel["sucessos"][slug]["chunks"]

        async with AsyncSessionLocal() as db:
            docs = await _docs(db, chave)
            assert len(docs) == 1 and docs[0].versao == 1 and docs[0].vigente
            n_db = (await db.execute(sql(
                "SELECT count(*) FROM knowledge_chunks WHERE doc_id = :d"),
                {"d": docs[0].id})).scalar()
            assert n_db == n_chunks_1 > 0
            # smoke do gate anti-alucinação: "Art. 6" e "Art. 10." do recorte
            assert await _existe_artigo(db, "6") is not None
            assert await _existe_artigo(db, "10") is not None

        # 2ª execução, mesmo HTML → inalterado (idempotente, nada duplicado)
        async with AsyncSessionLocal() as db:
            rel2 = await sl.executar_seed_legislacao(db, apenas=slug)
            assert rel2["sucessos"][slug]["resultado"] == "inalterado"
        async with AsyncSessionLocal() as db:
            assert len(await _docs(db, chave)) == 1

        # HTML mudou (alteração legislativa) → NOVA VERSÃO, antiga preservada
        paginas["v"] = html.replace(
            "Brasília, 11 de setembro de 1990",
            "Art. 11. Parágrafo novo incluído por lei posterior.\n"
            "Brasília, 11 de setembro de 1990")
        async with AsyncSessionLocal() as db:
            rel3 = await sl.executar_seed_legislacao(db, apenas=slug)
            assert rel3["sucessos"][slug]["resultado"] == "atualizado"
        async with AsyncSessionLocal() as db:
            docs = await _docs(db, chave)
            assert [d.versao for d in docs] == [1, 2]
            assert [d.vigente for d in docs] == [False, True]
            assert await _existe_artigo(db, "11") is not None
    finally:
        await _limpar(chave)


@pytestmark_db
async def test_seed_e_job_semanal_mesma_chave_nao_duplicam(monkeypatch, html, _engine_isolado):
    """UNIFICAÇÃO: rodar o seed CLI e depois o ingestor do scheduler (ou
    vice-versa) escreve na MESMA chave planalto:<slug> → upsert, zero docs
    duplicados."""
    from app.core.database import AsyncSessionLocal

    slug, chave = "cdcseed", "planalto:cdcseed"
    monkeypatch.setattr(pl, "CATALOGO", [_lei_teste(slug)])

    async def fake_html(diploma, cache_dir=None):
        return html

    monkeypatch.setattr(pl, "obter_html", fake_html)

    try:
        # seed CLI primeiro → novo
        async with AsyncSessionLocal() as db:
            rel = await sl.executar_seed_legislacao(db, apenas=slug)
            assert rel["sucessos"][slug]["resultado"] == "novo"

        # job semanal em seguida, mesmo conteúdo → inalterado (não duplica)
        async with AsyncSessionLocal() as db:
            novos, total = await pl.ingerir(db)
            assert (novos, total) == (0, 1)

        async with AsyncSessionLocal() as db:
            docs = await _docs(db, chave)
            assert len(docs) == 1 and docs[0].vigente     # UM doc, uma versão
            # e o seed de novo também segue inalterado
            rel2 = await sl.executar_seed_legislacao(db, apenas=slug)
            assert rel2["sucessos"][slug]["resultado"] == "inalterado"
    finally:
        await _limpar(chave)


@pytestmark_db
async def test_rechunk_unico_de_doc_producao_com_divisao_antiga(monkeypatch, html, _engine_isolado):
    """Doc vigente de produção (chunking genérico antigo, extra sem
    divisao='por_artigo') com o MESMO conteúdo → 1ª execução força NOVA VERSÃO
    re-chunkada por artigo; 2ª execução volta a 'inalterado' (migração única)."""
    from app.core.database import AsyncSessionLocal
    from app.services.ingestion_service import upsert_documento

    slug, chave = "cdcvelho", "planalto:cdcvelho"
    lei = _lei_teste(slug)
    monkeypatch.setattr(pl, "CATALOGO", [lei])

    async def fake_html(diploma, cache_dir=None):
        return html

    monkeypatch.setattr(pl, "obter_html", fake_html)

    texto = extrair_texto_planalto(html)     # mesmo conteúdo (mesmo hash!)

    try:
        # Simula o doc de produção do ingestor ANTIGO: chunking genérico por
        # tamanho (chunks=None) e extra legado {"diploma", "origem"}.
        async with AsyncSessionLocal() as db:
            r = await upsert_documento(
                db, titulo=lei["titulo"], categoria="legislacao",
                conteudo=texto, chave_origem=chave, fonte=lei["url"],
                extra={"diploma": slug, "origem": "planalto"},
                confianca="alta", embutir_vetores=False,
            )
            assert r == "novo"
            await db.commit()

        # 1ª execução unificada → 'atualizado' apesar do hash idêntico
        async with AsyncSessionLocal() as db:
            rel = await sl.executar_seed_legislacao(db, apenas=slug)
            assert rel["sucessos"][slug]["resultado"] == "atualizado"

        async with AsyncSessionLocal() as db:
            docs = await _docs(db, chave)
            assert [d.versao for d in docs] == [1, 2]
            assert [d.vigente for d in docs] == [False, True]
            # nova versão marcada e chunkada por artigo (headers do gate)
            extra_div = (await db.execute(sql(
                "SELECT extra->>'divisao' FROM knowledge_docs "
                "WHERE id = :d"), {"d": docs[1].id})).scalar()
            assert extra_div == "por_artigo"
            primeiro = (await db.execute(sql(
                "SELECT conteudo FROM knowledge_chunks WHERE doc_id = :d "
                "ORDER BY chunk_index LIMIT 1"), {"d": docs[1].id})).scalar()
            assert lei["titulo"] in primeiro.split("\n", 1)[0]
            # histórico: chunks genéricos da v1 permanecem intactos
            n_v1 = (await db.execute(sql(
                "SELECT count(*) FROM knowledge_chunks WHERE doc_id = :d"),
                {"d": docs[0].id})).scalar()
            assert n_v1 > 0

        # 2ª execução → 'inalterado' (não re-chunkar de novo; idempotente)
        async with AsyncSessionLocal() as db:
            rel2 = await sl.executar_seed_legislacao(db, apenas=slug)
            assert rel2["sucessos"][slug]["resultado"] == "inalterado"
        async with AsyncSessionLocal() as db:
            assert len(await _docs(db, chave)) == 2
    finally:
        await _limpar(chave)
