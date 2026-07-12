"""Bloco 3 — Ingestão contínua de conhecimento (ANPD + Normas RFB → RAG).

Cobre (SEM rede — gov.br/RFB não são alcançáveis neste ambiente; a validação
contra o HTML real é feita na VPS, mesmo protocolo do ingestor TJMG):
1) Parser ANPD: extração tolerante de links de documento das páginas-índice
   gov.br (fixture representativa Plone), filtrando navegação/externos.
2) Parser RFB: extração de idAto+título da lista do sijut2consulta.
3) Chaves de dedup: anpd:<slug> e rfb:<tipo>:<numero>:<ano> (+ fallbacks).
4) html_para_texto: recorte do content-core, corte no footer, entidades.
5) ingerir() de cada fonte: contagens, metadados/governança (categoria não
   restrita, confiança alta, fonte oficial), teto por execução respeitado e
   tolerância a erro por item.
6) Idempotência: segunda rodada → inalterados (dedup por chave_origem).
7) Orquestrador: fonte que falha não derruba as outras; resumo por fonte.
8) Gate do scheduler (CONHECIMENTO_INGEST_ENABLED) + job registrado.
9) Contrato do endpoint POST /rag/ingest-fontes-oficiais (rota, roles,
   audit log, background task).
"""
from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urljoin

import app.services.conhecimento_ingest as ci
import app.services.conhecimento_ingest.anpd as anpd
import app.services.conhecimento_ingest.normas_rfb as rfb
from app.services.conhecimento_ingest.base import html_para_texto, limpar_html
from app.core.config import get_settings


# ── Fixtures HTML (shape representativo dos portais) ──────────────────────────

HTML_ANPD_LISTA = """
<html><body>
<nav><a href="/anpd/pt-br">In&iacute;cio</a>
     <a href="https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-publica-novidade">
       ANPD publica novidade sobre regulamenta&ccedil;&atilde;o</a>
     <a href="mailto:faleconosco@anpd.gov.br">Fale conosco</a>
     <a href="javascript:void(0)">Abrir menu</a></nav>
<div id="content-core">
  <ul>
    <li><a href="resolucao-cd-anpd-no-15">Resolu&ccedil;&atilde;o CD/ANPD n&ordm; 15,
        de 24 de abril de 2024 &mdash; Regulamento de Comunica&ccedil;&atilde;o de
        Incidente de Seguran&ccedil;a</a></li>
    <li><a href="https://www.gov.br/anpd/pt-br/documentos-e-publicacoes/guia-cookies.pdf">
        Guia Orientativo &mdash; Cookies e Prote&ccedil;&atilde;o de Dados Pessoais</a></li>
    <li><a href="https://www.exemplo-externo.com.br/guia-lgpd">Guia externo n&atilde;o
        oficial de LGPD</a></li>
    <li><a href="https://www.gov.br/anpd/pt-br/assuntos/regulamentacao/regulamentacoes-da-anpd/pagina-institucional-qualquer">
        Ver hist&oacute;rico</a></li>
  </ul>
</div>
<footer id="doc-footer">Rodap&eacute; institucional gov.br</footer>
</body></html>
"""

HTML_ANPD_ATO = """
<html><body>
<div id="menu"><a href="/anpd">menu enorme de navegacao</a></div>
<div id="content-core">
  <h1>Resolu&ccedil;&atilde;o CD/ANPD n&ordm; 15, de 24 de abril de 2024</h1>
  <p>Aprova o Regulamento de Comunica&ccedil;&atilde;o de Incidente de Seguran&ccedil;a.</p>
  <p>Art. 1&ordm; Fica aprovado o Regulamento de Comunica&ccedil;&atilde;o de Incidente de
  Seguran&ccedil;a com dados pessoais, na forma do Anexo a esta Resolu&ccedil;&atilde;o.</p>
  <p>Art. 2&ordm; O controlador dever&aacute; comunicar &agrave; ANPD e ao titular a
  ocorr&ecirc;ncia de incidente de seguran&ccedil;a que possa acarretar risco ou dano
  relevante aos titulares, em prazo de 3 dias &uacute;teis.</p>
</div>
<footer>Assine nossa newsletter</footer>
</body></html>
"""

HTML_RFB_RESULTADOS = """
<html><body>
<a href="consulta.action?p=2&termoBusca=irpf">2</a>
<table class="resultado">
 <tr><td>
   <a href="link.action?visao=anotado&idAto=131234">Instru&ccedil;&atilde;o Normativa
     RFB n&ordm; 2110, de 17 de outubro de 2022</a>
 </td></tr>
 <tr><td>
   <a href="/sijut2consulta/link.action?visao=compilado&idAto=98765">Solu&ccedil;&atilde;o de
     Consulta Cosit n&ordm; 99001, de 10 de janeiro de 2024</a>
 </td></tr>
 <tr><td>
   <a href="link.action?visao=anotado&idAto=131234">Instru&ccedil;&atilde;o Normativa
     RFB n&ordm; 2110, de 17 de outubro de 2022 (duplicada)</a>
 </td></tr>
</table>
</body></html>
"""

HTML_RFB_ATO = """
<html><body>
<h1>Instru&ccedil;&atilde;o Normativa RFB n&ordm; 2110, de 17 de outubro de 2022</h1>
<p>Disp&otilde;e sobre normas gerais de tributa&ccedil;&atilde;o previdenci&aacute;ria e de
arrecada&ccedil;&atilde;o das contribui&ccedil;&otilde;es sociais destinadas &agrave;
Previd&ecirc;ncia Social e as destinadas a outras entidades ou fundos, administradas
pela Secretaria Especial da Receita Federal do Brasil.</p>
<p>Art. 1&ordm; As normas gerais de tributa&ccedil;&atilde;o previdenci&aacute;ria e de
arrecada&ccedil;&atilde;o ficam estabelecidas conforme esta Instru&ccedil;&atilde;o Normativa.</p>
</body></html>
"""


# ── 1/4. Parsers e helpers ────────────────────────────────────────────────────

def test_extrair_links_anpd_filtra_navegacao_e_externos():
    base = "https://www.gov.br/anpd/pt-br/assuntos/regulamentacao/regulamentacoes-da-anpd"
    links = anpd.extrair_links(HTML_ANPD_LISTA, base)
    urls = [lk["url"] for lk in links]
    # documento HTML relativo resolvido contra a página-índice
    assert any(u.endswith("/resolucao-cd-anpd-no-15") for u in urls)
    # PDF oficial mantido
    assert any(u.endswith("/guia-cookies.pdf") for u in urls)
    # navegação, notícia, mailto, javascript, domínio externo e rótulo genérico: fora
    assert not any("noticias" in u for u in urls)
    assert not any("exemplo-externo" in u for u in urls)
    assert not any(u.startswith(("mailto:", "javascript:")) for u in urls)
    assert not any("pagina-institucional" in u for u in urls)   # rótulo "Ver histórico"
    assert len(links) == 2
    # título com entidades decodificadas
    assert any("Resolução CD/ANPD" in lk["titulo"] for lk in links)


def test_chave_anpd_slug_html_e_pdf():
    assert anpd._chave(
        "https://www.gov.br/anpd/pt-br/assuntos/regulamentacao/resolucao-cd-anpd-no-15"
    ) == "anpd:resolucao-cd-anpd-no-15"
    assert anpd._chave(
        "https://www.gov.br/anpd/pt-br/documentos/Guia-Cookies_v2.PDF"
    ) == "anpd:guia-cookies-v2"
    # URL atípica (path vazio) → hash estável, nunca chave vazia
    k = anpd._chave("https://www.gov.br/")
    assert k.startswith("anpd:") and len(k) > len("anpd:")


def test_html_para_texto_recorta_content_core_e_footer():
    txt = html_para_texto(HTML_ANPD_ATO)
    assert "Regulamento de Comunicação de Incidente" in txt
    assert "Art. 2º" in txt
    assert "menu enorme" not in txt          # fora do content-core
    assert "newsletter" not in txt           # cortado no <footer>


def test_html_para_texto_tolerante_a_lixo():
    assert html_para_texto("") == ""
    assert "so texto" in html_para_texto("<html><body>so texto</body></html>")


def test_limpar_html_unescape():
    assert limpar_html("Guia <b>de</b> prote&ccedil;&atilde;o &amp; cia") == \
        "Guia de proteção & cia"


def test_parse_resultados_rfb_extrai_e_deduplica():
    atos = rfb.parse_resultados(HTML_RFB_RESULTADOS)
    assert len(atos) == 2                          # idAto duplicado colapsa
    assert atos[0]["id_ato"] == "131234"
    assert atos[0]["titulo"].startswith("Instrução Normativa RFB nº 2110")
    assert atos[1]["id_ato"] == "98765"
    assert "Solução de Consulta Cosit" in atos[1]["titulo"]


def test_parse_resultados_rfb_vazio_nao_quebra():
    assert rfb.parse_resultados("") == []
    assert rfb.parse_resultados("<html>nada aqui</html>") == []


def test_chave_rfb_formato_tipo_numero_ano():
    assert rfb._chave(
        "Instrução Normativa RFB nº 2110, de 17 de outubro de 2022", "131234"
    ) == "rfb:instrucao-normativa-rfb:2110:2022"
    assert rfb._chave(
        "Solução de Consulta Cosit nº 99001, de 10 de janeiro de 2024", "98765"
    ) == "rfb:solucao-de-consulta-cosit:99001:2024"


def test_chave_rfb_fallback_por_id():
    # título fora do padrão (sem nº/ano) → fallback determinístico por idAto
    assert rfb._chave("Portaria sem numeração aparente", "555") == "rfb:ato:555"


# ── Infra de mock (sem rede, sem banco) — padrão de test_ingestor_tjmg ────────

class _FakeDB:
    async def commit(self):
        pass

    async def rollback(self):
        pass


def _fake_upsert_factory(upserts: list[dict], *, resultado="novo",
                         erro_em: set[str] | None = None):
    async def fake_upsert(db, **kwargs):
        if erro_em and kwargs["chave_origem"] in erro_em:
            raise RuntimeError("boom")
        upserts.append(kwargs)
        res = resultado(kwargs) if callable(resultado) else resultado
        return res
    return fake_upsert


def _prepara_anpd(monkeypatch, paginas_html: dict[str, str], upserts: list,
                  *, resultado="novo", erro_em=None):
    """Mocka fetch/PDF/pausa do módulo anpd. paginas_html: url → html/None
    (None = fetch levanta)."""
    async def fake_fetch(url, **kw):
        html = paginas_html.get(url)
        if html is None:
            raise RuntimeError(f"pagina indisponivel: {url}")
        return SimpleNamespace(text=html, content=html.encode())
    monkeypatch.setattr(anpd, "fetch", fake_fetch)
    monkeypatch.setattr(anpd, "PAUSA_S", 0)
    monkeypatch.setattr(anpd, "_texto_pdf",
                        lambda raw: "Conteúdo extraído do PDF do guia. " * 20)
    monkeypatch.setattr(
        anpd, "upsert_documento",
        _fake_upsert_factory(upserts, resultado=resultado, erro_em=erro_em))


# ── 5. ingerir() ANPD ─────────────────────────────────────────────────────────

URL_REG = PAGINA_REG = anpd.PAGINAS[0][2]
URL_GUIAS = anpd.PAGINAS[1][2]
# href relativo resolve contra a página-índice (urljoin: sem barra final, o
# último segmento é substituído — comportamento padrão de navegador)
URL_ATO = urljoin(URL_REG, "resolucao-cd-anpd-no-15")
URL_PDF = "https://www.gov.br/anpd/pt-br/documentos-e-publicacoes/guia-cookies.pdf"


async def test_ingerir_anpd_upserta_html_e_pdf(monkeypatch):
    ups: list[dict] = []
    _prepara_anpd(monkeypatch, {
        URL_REG: HTML_ANPD_LISTA,
        URL_GUIAS: "<html><body><div id='content-core'></div></body></html>",
        URL_ATO: HTML_ANPD_ATO,
        # URL_PDF passa por _texto_pdf mockado (fetch devolve bytes)
        URL_PDF: "%PDF-fake",
    }, ups)

    resumo = await anpd.ingerir(_FakeDB())

    assert resumo == {"novos": 2, "atualizados": 0, "inalterados": 0, "erros": 0}
    chaves = {u["chave_origem"] for u in ups}
    assert chaves == {"anpd:resolucao-cd-anpd-no-15", "anpd:guia-cookies"}
    # governança: categoria NÃO restrita, confiança MEDIA (conteúdo raspado),
    # proveniência auto-scraped, fonte = URL oficial
    assert all(u["categoria"] in ("legislacao", "doutrina") for u in ups)
    assert all(u["confianca"] == "media" for u in ups)
    assert all(u["extra"]["proveniencia"] == "auto-scraped" for u in ups)
    assert all(u["fonte"].startswith("https://www.gov.br/") for u in ups)
    assert all(u["extra"]["origem"] == "anpd" for u in ups)
    reso = next(u for u in ups if u["chave_origem"].endswith("no-15"))
    assert "Incidente de Segurança" in reso["conteudo"]
    assert reso["titulo"].startswith("ANPD — Resolução CD/ANPD")


async def test_ingerir_anpd_teto_de_docs(monkeypatch):
    itens = "".join(
        f'<li><a href="resolucao-cd-anpd-no-{i}">Resolu&ccedil;&atilde;o CD/ANPD '
        f'n&ordm; {i}, de 2024</a></li>' for i in range(1, 36)   # 35 links
    )
    lista = f"<html><body><div id='content-core'><ul>{itens}</ul></div></body></html>"
    paginas = {URL_REG: lista, URL_GUIAS: "<html></html>"}
    paginas.update({urljoin(URL_REG, f"resolucao-cd-anpd-no-{i}"): HTML_ANPD_ATO
                    for i in range(1, 36)})
    ups: list[dict] = []
    _prepara_anpd(monkeypatch, paginas, ups)

    resumo = await anpd.ingerir(_FakeDB())

    assert len(ups) == anpd.MAX_DOCS_POR_EXECUCAO == 30    # teto respeitado
    assert resumo["novos"] == 30 and resumo["erros"] == 0


async def test_ingerir_anpd_pagina_fora_do_padrao_nao_derruba(monkeypatch):
    ups: list[dict] = []
    _prepara_anpd(monkeypatch, {
        URL_REG: None,                    # página-índice indisponível → warning
        URL_GUIAS: HTML_ANPD_LISTA,       # a outra seção segue funcionando
        # href relativo agora resolve contra a página de guias
        urljoin(URL_GUIAS, "resolucao-cd-anpd-no-15"): HTML_ANPD_ATO,
        URL_PDF: "%PDF-fake",
    }, ups)
    resumo = await anpd.ingerir(_FakeDB())
    assert resumo["erros"] == 1           # falha contabilizada
    assert resumo["novos"] == 2           # e a outra página foi processada


async def test_ingerir_anpd_erro_de_upsert_isolado(monkeypatch):
    ups: list[dict] = []
    _prepara_anpd(monkeypatch, {
        URL_REG: HTML_ANPD_LISTA, URL_GUIAS: "<html></html>",
        URL_ATO: HTML_ANPD_ATO, URL_PDF: "%PDF-fake",
    }, ups, erro_em={"anpd:resolucao-cd-anpd-no-15"})
    resumo = await anpd.ingerir(_FakeDB())
    assert resumo["erros"] == 1 and resumo["novos"] == 1   # PDF seguiu


async def test_ingerir_anpd_conteudo_curto_pulado(monkeypatch):
    ups: list[dict] = []
    _prepara_anpd(monkeypatch, {
        URL_REG: HTML_ANPD_LISTA, URL_GUIAS: "<html></html>",
        URL_ATO: "<html><body><div id='content-core'>curto</div></body></html>",
        URL_PDF: "%PDF-fake",
    }, ups)
    resumo = await anpd.ingerir(_FakeDB())
    chaves = {u["chave_origem"] for u in ups}
    assert "anpd:resolucao-cd-anpd-no-15" not in chaves    # pulado, sem erro
    assert resumo["erros"] == 0 and resumo["novos"] == 1


# ── 5. ingerir() Normas RFB ───────────────────────────────────────────────────

def _prepara_rfb(monkeypatch, *, resultados_por_termo: dict[str, str],
                 ato_html: str = HTML_RFB_ATO, upserts=None,
                 resultado="novo", termos="IRPF"):
    s = get_settings()
    monkeypatch.setattr(s, "NORMAS_RFB_TERMOS", termos, raising=False)
    monkeypatch.setattr(rfb, "PAUSA_S", 0)

    async def fake_fetch(url, *, params=None, **kw):
        if url.endswith("/consulta.action"):
            html = resultados_por_termo.get((params or {}).get("termoBusca"))
            if html is None:
                raise RuntimeError("portal fora do ar")
            return SimpleNamespace(text=html)
        return SimpleNamespace(text=ato_html)
    monkeypatch.setattr(rfb, "fetch", fake_fetch)
    ups = upserts if upserts is not None else []
    monkeypatch.setattr(rfb, "upsert_documento",
                        _fake_upsert_factory(ups, resultado=resultado))
    return ups


async def test_ingerir_rfb_upserta_com_chave_e_metadados(monkeypatch):
    ups = _prepara_rfb(monkeypatch,
                       resultados_por_termo={"IRPF": HTML_RFB_RESULTADOS})
    resumo = await rfb.ingerir(_FakeDB())
    assert resumo == {"novos": 2, "atualizados": 0, "inalterados": 0, "erros": 0}
    chaves = [u["chave_origem"] for u in ups]
    assert "rfb:instrucao-normativa-rfb:2110:2022" in chaves
    assert "rfb:solucao-de-consulta-cosit:99001:2024" in chaves
    assert all(u["categoria"] == "legislacao_tributaria" for u in ups)
    assert all(u["confianca"] == "media" for u in ups)          # conteúdo raspado
    assert all(u["extra"]["proveniencia"] == "auto-scraped" for u in ups)
    assert all("sijut2consulta/link.action" in u["fonte"] for u in ups)
    assert all(u["extra"]["origem"] == "normas_rfb" for u in ups)
    assert all(u["extra"]["termo_busca"] == "IRPF" for u in ups)
    assert any("tributação previdenciária" in u["conteudo"] for u in ups)


async def test_ingerir_rfb_teto_de_docs(monkeypatch):
    linhas = "".join(
        f'<a href="link.action?visao=anotado&idAto={1000 + i}">Instru&ccedil;&atilde;o '
        f'Normativa RFB n&ordm; {i}, de 1 de janeiro de 2023</a>'
        for i in range(1, 26)    # 25 resultados
    )
    ups = _prepara_rfb(monkeypatch, resultados_por_termo={
        "IRPF": f"<html><body>{linhas}</body></html>",
        "ISS": HTML_RFB_RESULTADOS,    # nem chega a ser consultado após o teto
    }, termos="IRPF,ISS")
    resumo = await rfb.ingerir(_FakeDB())
    assert len(ups) == rfb.MAX_DOCS_POR_EXECUCAO == 20    # teto respeitado
    assert resumo["novos"] == 20 and resumo["erros"] == 0


async def test_ingerir_rfb_termo_com_falha_nao_derruba_os_demais(monkeypatch):
    _prepara_rfb(monkeypatch, resultados_por_termo={
        # "QUEBRADO" ausente do dict → fetch levanta para esse termo
        "IRPF": HTML_RFB_RESULTADOS,
    }, termos="QUEBRADO,IRPF")
    resumo = await rfb.ingerir(_FakeDB())
    assert resumo["erros"] == 1 and resumo["novos"] == 2


async def test_ingerir_rfb_termos_configuraveis_default(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "NORMAS_RFB_TERMOS", "", raising=False)
    assert rfb._termos(s) == rfb.TERMOS_PADRAO
    monkeypatch.setattr(s, "NORMAS_RFB_TERMOS", " ICMS , ITBI ,", raising=False)
    assert rfb._termos(s) == ["ICMS", "ITBI"]


# ── 6. Idempotência (dedup por chave_origem) ──────────────────────────────────

async def test_segunda_rodada_vira_inalterados(monkeypatch):
    ja_vistos: set[str] = set()

    def resultado(kwargs):
        chave = kwargs["chave_origem"]
        if chave in ja_vistos:
            return "inalterado"
        ja_vistos.add(chave)
        return "novo"

    ups = _prepara_rfb(monkeypatch,
                       resultados_por_termo={"IRPF": HTML_RFB_RESULTADOS},
                       resultado=resultado)
    r1 = await rfb.ingerir(_FakeDB())
    r2 = await rfb.ingerir(_FakeDB())
    assert r1["novos"] == 2 and r1["inalterados"] == 0
    assert r2["novos"] == 0 and r2["inalterados"] == 2    # nada re-ingerido
    assert len(ups) == 4                                  # upsert decide, não duplica


# ── 7. Orquestrador ───────────────────────────────────────────────────────────

class _FakeSessao:
    async def __aenter__(self):
        return _FakeDB()

    async def __aexit__(self, *a):
        return False


def _prepara_orquestrador(monkeypatch, fontes):
    monkeypatch.setattr(ci, "_fontes", lambda: fontes)
    monkeypatch.setattr(ci, "_sessao", lambda: _FakeSessao())
    execucoes: list[dict] = []

    async def fake_registrar(db, slug, descricao, categoria_rag=None):
        pass

    async def fake_marcar(db, slug, *, status, novos=0, total=0, erro=None):
        execucoes.append({"slug": slug, "status": status,
                          "novos": novos, "total": total, "erro": erro})
    monkeypatch.setattr(ci, "registrar_fonte", fake_registrar)
    monkeypatch.setattr(ci, "marcar_execucao", fake_marcar)
    return execucoes


async def test_orquestrador_fonte_que_falha_nao_derruba_as_outras(monkeypatch):
    async def fonte_ok(db):
        return {"novos": 3, "atualizados": 1, "inalterados": 2, "erros": 0}

    async def fonte_quebrada(db):
        raise RuntimeError("HTML mudou")

    execucoes = _prepara_orquestrador(monkeypatch, [
        ("quebrada", "Fonte quebrada", "legislacao", fonte_quebrada),
        ("ok", "Fonte ok", "legislacao", fonte_ok),
    ])

    resumo = await ci.executar_ingest_conhecimento()

    assert set(resumo) == {"quebrada", "ok"}              # ambas reportadas
    assert resumo["quebrada"]["status"] == "erro"
    assert "RuntimeError" in resumo["quebrada"]["erro"]
    assert resumo["ok"] == {"novos": 3, "atualizados": 1, "inalterados": 2,
                            "erros": 0, "status": "sucesso"}
    # métricas duráveis no painel (fontes_ingestao)
    m_ok = next(e for e in execucoes if e["slug"] == "ok")
    assert m_ok["novos"] == 4 and m_ok["total"] == 6      # novos+atualizados / +inalterados
    m_q = next(e for e in execucoes if e["slug"] == "quebrada")
    assert m_q["status"] == "erro" and m_q["erro"]


async def test_orquestrador_erros_parciais_status_parcial(monkeypatch):
    async def fonte_parcial(db):
        return {"novos": 1, "atualizados": 0, "inalterados": 0, "erros": 2}

    _prepara_orquestrador(monkeypatch,
                          [("p", "Parcial", "legislacao", fonte_parcial)])
    resumo = await ci.executar_ingest_conhecimento()
    assert resumo["p"]["status"] == "parcial"


def test_fontes_reais_registradas():
    fontes = ci._fontes()
    assert [f[0] for f in fontes] == ci.FONTES_SLUGS == ["anpd", "normas_rfb"]
    # categorias NÃO restritas (ai_service._RESTRICTED_CATS)
    from app.services.ai_service import _RESTRICTED_CATS
    assert all(f[2] not in _RESTRICTED_CATS for f in fontes)


# ── 8. Gate no scheduler ──────────────────────────────────────────────────────

async def test_job_conhecimento_gate(monkeypatch):
    from app.services import scheduler as sch

    chamadas: list[int] = []

    async def fake_exec():
        chamadas.append(1)
        return {}

    monkeypatch.setattr(ci, "executar_ingest_conhecimento", fake_exec)

    monkeypatch.setattr(get_settings(), "CONHECIMENTO_INGEST_ENABLED", False)
    await sch.job_ingestao_conhecimento()
    assert chamadas == []                                 # no-op com gate off

    monkeypatch.setattr(get_settings(), "CONHECIMENTO_INGEST_ENABLED", True)
    await sch.job_ingestao_conhecimento()
    assert chamadas == [1]


def test_gate_default_ligado():
    from app.core.config import Settings
    assert Settings.model_fields["CONHECIMENTO_INGEST_ENABLED"].default is True


def test_job_conhecimento_registrado_no_scheduler():
    import inspect
    from app.services import scheduler as sch
    src = inspect.getsource(sch.start_scheduler)
    assert "job_ingestao_conhecimento" in src and "ing_conhecimento" in src
    # domingo 03h00 UTC
    trecho = src[src.index("job_ingestao_conhecimento"):]
    assert 'day_of_week="sun"' in trecho and 'timezone="UTC"' in trecho


# ── 9. Endpoint POST /rag/ingest-fontes-oficiais ──────────────────────────────

def _rota_ingest_fontes():
    from app.routers.rag import router
    return next(r for r in router.routes
                if getattr(r, "path", "") == "/rag/ingest-fontes-oficiais")


def test_endpoint_registrado_com_post_e_roles():
    import inspect
    from app.routers import rag as rag_router
    rota = _rota_ingest_fontes()
    assert rota.methods == {"POST"} and rota.status_code == 202
    src = inspect.getsource(rag_router.ingest_fontes_oficiais)
    # socio+ (sem advogado) — mesmo conjunto do /rag/seed
    assert '"superadmin", "admin", "socio"' in src


async def test_endpoint_audita_e_agenda_background(monkeypatch):
    from app.routers import rag as rag_router
    import app.models.audit_log as audit_mod

    audits: list[dict] = []

    async def fake_audit(db, user_id=None, user_role=None, **kw):
        audits.append({"user_id": user_id, **kw})
    monkeypatch.setattr(audit_mod, "criar_audit_log", fake_audit)

    class _BG:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn, *a, **k):
            self.tasks.append(fn)

    bg = _BG()
    cu = SimpleNamespace(id="u1", role="socio")
    resp = await rag_router.ingest_fontes_oficiais(bg, db=_FakeDB(), cu=cu)

    assert resp["fontes"] == ["anpd", "normas_rfb"]
    assert "background" in resp["detail"]
    assert bg.tasks == [ci.executar_ingest_conhecimento]  # roda em background
    assert audits and audits[0]["acao"] == "INGESTAO_FONTES_OFICIAIS"
    assert audits[0]["user_id"] == "u1"
