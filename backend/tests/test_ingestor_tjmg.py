"""Ingestor TJMG (crawler de jurisprudência estadual MG → RAG).

Cobre (SEM rede — o portal do TJMG não é alcançável neste ambiente; a
validação contra o HTML real do site é separada, na VPS):
1) _parse_tjmg_html: extração tolerante de nº, relator, órgão, classe, data e
   ementa a partir de um HTML no formato do TJMG (fixture representativa);
   decodificação de entidades e captura de classe IRDR/IAC.
2) _limpar_html: unescape de entidades HTML.
3) _chave: dedup determinístico (com número do acórdão e sem — hash da ementa).
4) _monta_conteudo / _temas / _janela: montagem do conteúdo citável e config.
5) ingerir(): wiring de upsert por item, metadados/confiança, dedup
   intra-execução e tolerância a erro de upsert.
6) Gate do scheduler: job_ingestao_tjmg é no-op com TJMG_INGEST_ENABLED=False
   (default) e executa quando ligado; add_job registrado no start_scheduler.
"""
from __future__ import annotations

import app.services.ingestors.tjmg as tjmg
import app.services.jurisprudencia_externa as je
from app.core.config import get_settings


# ── Fixture: HTML no formato de resultados do TJMG (shape representativo) ──────
HTML_TJMG = """
<html><body>
<table id="resultados">
  <tr class="resultadoLinha">
    <td>
      Ac&oacute;rd&atilde;o: 1.0027.23.123456-7/001<br>
      Relator: Des. Jo&atilde;o da Silva Pereira<br>
      &Oacute;rg&atilde;o Julgador: 5&ordf; C&acirc;mara C&iacute;vel<br>
      Classe: Apela&ccedil;&atilde;o C&iacute;vel<br>
      Data do Julgamento: 15/03/2026<br>
      Ementa: APELA&Ccedil;&Atilde;O C&Iacute;VEL. A&Ccedil;&Atilde;O DE INDENIZA&Ccedil;&Atilde;O.
      DANO MORAL CONFIGURADO. Negativa indevida de cobertura por plano de sa&uacute;de.
      Dever de indenizar reconhecido. Recurso provido.
    </td>
  </tr>
  <tr class="resultadoLinha">
    <td>
      Ac&oacute;rd&atilde;o: 1.0027.23.777888-9/001<br>
      Relator: Desa. Maria Souza<br>
      &Oacute;rg&atilde;o Julgador: 12&ordf; C&acirc;mara C&iacute;vel<br>
      Classe: Incidente de Resolu&ccedil;&atilde;o de Demandas Repetitivas<br>
      Data do Julgamento: 02/02/2026<br>
      Ementa: IRDR. Fixa&ccedil;&atilde;o de tese sobre juros remunerat&oacute;rios em
      contratos banc&aacute;rios no &acirc;mbito do TJMG. Tese vinculante firmada.
    </td>
  </tr>
</table>
</body></html>
"""


# ── 1. _parse_tjmg_html ───────────────────────────────────────────────────────

def test_parse_tjmg_html_extrai_campos():
    itens = je._parse_tjmg_html(HTML_TJMG)
    assert len(itens) == 2

    a = itens[0]
    assert a["numero_acordao"] == "1.0027.23.123456-7/001"
    assert a["relator"].startswith("Des. Jo")           # entidades decodificadas
    assert "João" in a["relator"]                    # João
    assert "Câmara Cível" in a["orgao_julgador"]  # Câmara Cível
    assert a["classe"] == "Apelação Cível"   # Apelação Cível
    assert a["data_julgamento"] == "2026-03-15"
    assert "DANO MORAL" in a["ementa"]
    assert "plano de saúde" in a["ementa"]          # saúde (unescaped)
    assert a["tribunal"] == "TJMG"
    assert a["area_juridica"]                             # inferida, não vazia
    assert a["numero_acordao"] in a["link_original"]     # link do espelho

    # Segundo bloco: classe IRDR (precedente qualificado da base de acórdãos)
    b = itens[1]
    assert b["classe"].startswith("Incidente de Resolu")
    assert b["data_julgamento"] == "2026-02-02"


def test_parse_tjmg_html_vazio_ou_lixo_nao_quebra():
    assert je._parse_tjmg_html("") == []
    assert je._parse_tjmg_html("<html><body>sem resultados</body></html>") == []


def test_parse_ementa_com_sumula_inline_nao_trunca():
    """Ementa que cita "Súmula N" inline NÃO pode ser truncada (regressão do
    token de parada acidental)."""
    html = """
    <tr class="resultadoLinha"><td>
      Acórdão: 1.0000.00.111111-1/001<br>
      Relator: Des. Fulano de Tal<br>
      Ementa: AGRAVO INTERNO. Aplica-se a Súmula 568 do STJ ao caso concreto.
      Recurso improvido por unanimidade.
    </td></tr>"""
    itens = je._parse_tjmg_html(html)
    assert len(itens) == 1
    ementa = itens[0]["ementa"]
    assert "Súmula 568" in ementa and "Recurso improvido" in ementa


def test_parse_orgao_nao_captura_camara_da_ementa():
    """Sem rótulo "Órgão Julgador" e sem câmara NUMERADA, não se inventa órgão
    a partir da palavra "Câmara" solta na ementa."""
    html = """
    <tr class="resultadoLinha"><td>
      Acórdão: 1.0000.00.222222-2/001<br>
      Relator: Desa. Beltrana<br>
      Ementa: APELAÇÃO CÍVEL. Decisão mantida pela Câmara julgadora.
      Dano moral configurado. Recurso não provido.
    </td></tr>"""
    itens = je._parse_tjmg_html(html)
    assert len(itens) == 1
    assert itens[0]["orgao_julgador"] == ""


def test_limpar_html_unescape():
    out = je._limpar_html("A&ccedil;&atilde;o <b>de</b> sa&uacute;de &amp; cia")
    assert out == "Ação de saúde & cia"


# ── 2. _chave (dedup determinístico) ──────────────────────────────────────────

def test_chave_com_numero_acordao():
    it = {"numero_acordao": "1.0027.23.123456-7/001", "ementa": "x" * 60}
    assert tjmg._chave(it, "dano moral") == "tjmg:1.0027.23.123456-7/001"


def test_chave_sem_numero_e_hash_estavel():
    it = {"numero_acordao": "", "ementa": "EMENTA sobre plano de saúde e cobertura"}
    k1 = tjmg._chave(it, "tema1")
    k2 = tjmg._chave(dict(it), "tema2")   # tema diferente, mesma ementa → mesma chave
    assert k1 == k2
    assert k1.startswith("tjmg:ementa:") and len(k1) == len("tjmg:ementa:") + 16
    outro = {"numero_acordao": "", "ementa": "ementa completamente diferente"}
    assert tjmg._chave(outro, "tema1") != k1


# ── 3. _monta_conteudo / _temas / _janela ─────────────────────────────────────

def test_monta_conteudo_inclui_ementa_e_metadados():
    txt = tjmg._monta_conteudo({
        "classe": "Apelação Cível", "orgao_julgador": "5ª Câmara Cível",
        "relator": "Des. João", "data_julgamento": "2026-03-15",
        "area_juridica": "Saúde", "ementa": "APELAÇÃO. DANO MORAL.",
    })
    assert "EMENTA:" in txt and "DANO MORAL" in txt
    assert "Apelação Cível" in txt and "5ª Câmara Cível" in txt
    assert "Relator(a): Des. João" in txt


def test_temas_default_e_override(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "TJMG_INGEST_TEMAS", "", raising=False)
    assert tjmg._temas(s) == tjmg.TEMAS_PADRAO
    monkeypatch.setattr(s, "TJMG_INGEST_TEMAS", " dano moral , usucapião ,", raising=False)
    assert tjmg._temas(s) == ["dano moral", "usucapião"]


def test_janela_datas(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "TJMG_INGEST_JANELA_DIAS", 0, raising=False)
    assert tjmg._janela(s) == ("", "")
    monkeypatch.setattr(s, "TJMG_INGEST_JANELA_DIAS", 30, raising=False)
    di, df = tjmg._janela(s)
    # formato dd/mm/aaaa e início <= fim
    assert len(di) == 10 and di[2] == "/" and di[5] == "/"
    assert di <= df or di.split("/")[::-1] <= df.split("/")[::-1]


# ── Infra de mock (sem rede, sem banco) — mesmo padrão do test_ingestor_djen ──

class _FakeDB:
    async def commit(self):
        pass

    async def rollback(self):
        pass


ITEM_A = {
    "titulo": "Acórdão TJMG 1.0027.23.123456-7/001",
    "ementa": "APELAÇÃO CÍVEL. DANO MORAL. Negativa de cobertura por plano de "
              "saúde. Dever de indenizar. Recurso provido pela Câmara.",
    "tribunal": "TJMG", "relator": "Des. João Pereira",
    "numero_acordao": "1.0027.23.123456-7/001",
    "data_julgamento": "2026-03-15", "fonte": "TJMG",
    "link_original": "https://www5.tjmg.jus.br/jurisprudencia/formEspelhoAcordao.do",
    "area_juridica": "Saúde",
    "orgao_julgador": "5ª Câmara Cível", "classe": "Apelação Cível",
}
ITEM_B = {
    "titulo": "Acórdão TJMG",
    "ementa": "IRDR. Tese sobre juros remuneratórios em contratos bancários "
              "firmada em incidente repetitivo no âmbito do TJMG.",
    "tribunal": "TJMG", "relator": "Desa. Maria Souza",
    "numero_acordao": "", "data_julgamento": "2026-02-02", "fonte": "TJMG",
    "link_original": "", "area_juridica": "Bancário",
    "orgao_julgador": "12ª Câmara Cível",
    "classe": "Incidente de Resolução de Demandas Repetitivas",
}


def _prepara(monkeypatch, *, temas="tema1,tema2", por_tema=None, upserts=None,
             upsert_erro=False):
    s = get_settings()
    monkeypatch.setattr(s, "TJMG_INGEST_TEMAS", temas, raising=False)
    monkeypatch.setattr(s, "TJMG_INGEST_JANELA_DIAS", 0, raising=False)
    monkeypatch.setattr(s, "TJMG_INGEST_MAX_POR_TEMA", 50, raising=False)

    chamadas: list[str] = []
    por_tema = por_tema or {"tema1": [ITEM_A, ITEM_B], "tema2": [ITEM_A]}

    async def fake_buscar(palavras, por_pagina=10, *, data_inicial="",
                          data_final="", **kw):
        chamadas.append(palavras)
        return list(por_tema.get(palavras, []))

    monkeypatch.setattr(tjmg, "buscar_tjmg", fake_buscar)

    async def fake_upsert(db, **kwargs):
        if upsert_erro:
            raise RuntimeError("boom")
        if upserts is not None:
            upserts.append(kwargs)
        return "novo"

    monkeypatch.setattr(tjmg, "upsert_documento", fake_upsert)
    return chamadas


# ── 4. ingerir() ──────────────────────────────────────────────────────────────

async def test_ingerir_upserta_e_deduplica_intra_execucao(monkeypatch):
    ups: list[dict] = []
    chamadas = _prepara(monkeypatch, upserts=ups)

    novos, total = await tjmg.ingerir(_FakeDB())

    # tema1 → A,B (2 novos); tema2 → A (duplicata, ignorada intra-execução)
    assert chamadas == ["tema1", "tema2"]
    assert (novos, total) == (2, 2)
    chaves = [u["chave_origem"] for u in ups]
    assert "tjmg:1.0027.23.123456-7/001" in chaves
    assert any(c.startswith("tjmg:ementa:") for c in chaves)   # ITEM_B sem número
    # metadados e governança da fonte
    assert all(u["categoria"] == "jurisprudencia" for u in ups)
    assert all(u["tribunal"] == "TJMG" for u in ups)
    assert all(u["fonte"].startswith("TJMG") for u in ups)
    assert all(u["confianca"] == "alta" for u in ups)
    assert all(u["client_id"] is None for u in ups) if any("client_id" in u for u in ups) else True
    # conteúdo citável carrega a ementa
    assert any("EMENTA:" in u["conteudo"] for u in ups)
    a = next(u for u in ups if u["chave_origem"].endswith("123456-7/001"))
    assert a["extra"]["classe"] == "Apelação Cível"
    assert a["extra"]["tema_busca"] == "tema1"


async def test_ingerir_ignora_ementa_curta(monkeypatch):
    ups: list[dict] = []
    curto = {**ITEM_A, "numero_acordao": "1.0027.99.000001-1/001", "ementa": "curta"}
    _prepara(monkeypatch, temas="tema1",
             por_tema={"tema1": [curto]}, upserts=ups)
    assert await tjmg.ingerir(_FakeDB()) == (0, 0)
    assert ups == []


async def test_ingerir_tolerante_a_erro_de_upsert(monkeypatch):
    _prepara(monkeypatch, temas="tema1", por_tema={"tema1": [ITEM_A]},
             upsert_erro=True)
    # erro no upsert é capturado (rollback + continua) → não levanta; com commit
    # por item, o item falho NÃO persiste nem conta (métrica exata, sem inflar).
    novos, total = await tjmg.ingerir(_FakeDB())
    assert (novos, total) == (0, 0)


# ── 5. Gate no scheduler ──────────────────────────────────────────────────────

async def test_job_tjmg_gate_off_e_on(monkeypatch):
    from app.services import scheduler as sch
    import app.services.ingestion_service as ing

    execucoes: list[str] = []

    async def fake_exec(slug, *a, **k):
        execucoes.append(slug)
        return (0, 0)

    monkeypatch.setattr(ing, "executar_ingestao", fake_exec)

    # Gate OFF (explícito — independe do default): job é no-op.
    monkeypatch.setattr(get_settings(), "TJMG_INGEST_ENABLED", False)
    await sch.job_ingestao_tjmg()
    assert execucoes == []                                # no-op com gate off

    # Gate ON (default do titular): job executa a ingestão.
    monkeypatch.setattr(get_settings(), "TJMG_INGEST_ENABLED", True)
    await sch.job_ingestao_tjmg()
    assert execucoes == ["tjmg"]


def test_job_tjmg_registrado_no_scheduler():
    import inspect
    from app.services import scheduler as sch
    src = inspect.getsource(sch.start_scheduler)
    assert "job_ingestao_tjmg" in src and "ing_tjmg" in src
