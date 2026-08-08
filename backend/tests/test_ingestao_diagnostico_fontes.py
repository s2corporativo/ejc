"""Onda 3 — diagnóstico de falhas nas fontes de ingestão (ANPD/RFB/TJMG).

Fecha três cegueiras encontradas em produção:
1) ANPD/RFB terminavam com status="erro" e ultimo_erro NULL no painel — os
   ingestores engoliam as exceções (contador `erros` + warning no log) e o
   orquestrador `executar_ingest_conhecimento` gravava marcar_execucao(erro=None).
   Agora: a ÚLTIMA exceção vira amostra no resumo ("ultimo_erro_amostra") e o
   orquestrador NUNCA grava erro vazio para status="erro".
2) Zero itens brutos na origem ("layout mudou?") terminava como "sucesso" com
   zero registros. Agora: marca "zero_brutos" e vira status="erro" com mensagem
   explícita, que o painel de saúde trata como crítico.
3) O parser do TJMG (_parse_tjmg_html) degradava para [] sem distinguir "rede
   caiu", "HTML veio mas 0 blocos casaram" e "parseou". Agora expõe métricas
   (html_bytes, blocos, rede_falhou) e o ingestor loga os três casos.

Padrão do repo: fakes locais, sem rede e sem banco (mesma infra de
test_conhecimento_ingest.py / test_ingestor_tjmg.py).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import app.services.conhecimento_ingest as ci
import app.services.conhecimento_ingest.anpd as anpd
import app.services.conhecimento_ingest.normas_rfb as rfb
import app.services.ingestors.tjmg as tjmg
import app.services.jurisprudencia_externa as je
from app.core.config import get_settings


# ── Infra de mock (sem rede, sem banco) ───────────────────────────────────────

class _FakeDB:
    async def commit(self):
        pass

    async def rollback(self):
        pass


class _FakeSessao:
    async def __aenter__(self):
        return _FakeDB()

    async def __aexit__(self, *a):
        return False


URL_REG = anpd.PAGINAS[0][2]
URL_GUIAS = anpd.PAGINAS[1][2]

HTML_SEM_LINKS = "<html><body><div id='content-core'>nada aqui</div></body></html>"


def _prepara_anpd(monkeypatch, paginas_html: dict[str, str | None]):
    """paginas_html: url → html (None = fetch levanta RuntimeError)."""
    async def fake_fetch(url, **kw):
        html = paginas_html.get(url)
        if html is None:
            raise RuntimeError(f"pagina indisponivel: {url}")
        return SimpleNamespace(text=html, content=html.encode())
    monkeypatch.setattr(anpd, "fetch", fake_fetch)
    monkeypatch.setattr(anpd, "PAUSA_S", 0)

    async def fake_upsert(db, **kwargs):
        return "novo"
    monkeypatch.setattr(anpd, "upsert_documento", fake_upsert)


def _prepara_rfb(monkeypatch, resultados_por_termo: dict[str, str | None],
                 termos="IRPF"):
    s = get_settings()
    monkeypatch.setattr(s, "NORMAS_RFB_TERMOS", termos, raising=False)
    monkeypatch.setattr(rfb, "PAUSA_S", 0)

    async def fake_fetch(url, *, params=None, **kw):
        html = resultados_por_termo.get((params or {}).get("termoBusca"))
        if html is None:
            raise RuntimeError("portal fora do ar")
        return SimpleNamespace(text=html)
    monkeypatch.setattr(rfb, "fetch", fake_fetch)


# ── 1. Amostra da última exceção chega ao resumo (ANPD/RFB) ───────────────────

async def test_anpd_excecao_de_pagina_vira_amostra_no_resumo(monkeypatch):
    _prepara_anpd(monkeypatch, {URL_REG: None, URL_GUIAS: None})
    resumo = await anpd.ingerir(_FakeDB())
    assert resumo["erros"] == 2
    amostra = resumo["ultimo_erro_amostra"]
    assert "RuntimeError" in amostra and "pagina indisponivel" in amostra


async def test_anpd_amostra_truncada_em_300(monkeypatch):
    async def fake_fetch(url, **kw):
        raise RuntimeError("x" * 1000)
    monkeypatch.setattr(anpd, "fetch", fake_fetch)
    monkeypatch.setattr(anpd, "PAUSA_S", 0)
    resumo = await anpd.ingerir(_FakeDB())
    assert len(resumo["ultimo_erro_amostra"]) <= 300


async def test_rfb_excecao_de_termo_vira_amostra_no_resumo(monkeypatch):
    _prepara_rfb(monkeypatch, {}, termos="QUEBRADO")   # fetch levanta
    resumo = await rfb.ingerir(_FakeDB())
    assert resumo["erros"] == 1
    amostra = resumo["ultimo_erro_amostra"]
    assert "RuntimeError" in amostra and "portal fora do ar" in amostra
    # brutos=0 (nenhum ato veio) → também marcado, sem sobrescrever a amostra
    assert resumo["zero_brutos"] is True


# ── 2. Zero itens brutos NÃO é sucesso (mensagem de layout) ───────────────────

async def test_anpd_zero_links_marca_zero_brutos_com_mensagem_de_layout(monkeypatch):
    _prepara_anpd(monkeypatch, {URL_REG: HTML_SEM_LINKS, URL_GUIAS: HTML_SEM_LINKS})
    resumo = await anpd.ingerir(_FakeDB())
    assert resumo["zero_brutos"] is True
    assert "0 itens brutos na origem" in resumo["ultimo_erro_amostra"]
    assert "layout" in resumo["ultimo_erro_amostra"]


async def test_rfb_zero_atos_marca_zero_brutos_com_mensagem_de_layout(monkeypatch):
    _prepara_rfb(monkeypatch, {"IRPF": "<html>sem resultados</html>"})
    resumo = await rfb.ingerir(_FakeDB())
    assert resumo["erros"] == 0                      # nada levantou exceção...
    assert resumo["zero_brutos"] is True             # ...mas NÃO é sucesso
    assert "0 itens brutos na origem" in resumo["ultimo_erro_amostra"]


# ── 3. Orquestrador: erro nunca vai vazio para marcar_execucao ────────────────

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


async def test_orquestrador_usa_amostra_do_resumo_como_ultimo_erro(monkeypatch):
    async def fonte_com_erros_engolidos(db):
        return {"novos": 0, "atualizados": 0, "inalterados": 0, "erros": 3,
                "ultimo_erro_amostra": "página 'x': TimeoutError: deu ruim"}

    execucoes = _prepara_orquestrador(
        monkeypatch, [("f", "F", "legislacao", fonte_com_erros_engolidos)])
    resumo = await ci.executar_ingest_conhecimento()

    assert resumo["f"]["status"] == "erro"
    assert execucoes[0]["status"] == "erro"
    # A regressão original: aqui chegava erro=None (ultimo_erro null no painel)
    assert execucoes[0]["erro"] == "página 'x': TimeoutError: deu ruim"
    assert resumo["f"]["erro"] == "página 'x': TimeoutError: deu ruim"


async def test_orquestrador_erro_sem_amostra_grava_texto_diagnosticavel(monkeypatch):
    async def fonte_muda(db):   # erros contados, nenhuma amostra (fonte antiga)
        return {"novos": 0, "atualizados": 0, "inalterados": 0, "erros": 2}

    execucoes = _prepara_orquestrador(
        monkeypatch, [("muda", "F", "legislacao", fonte_muda)])
    await ci.executar_ingest_conhecimento()

    assert execucoes[0]["status"] == "erro"
    assert execucoes[0]["erro"]                      # NUNCA vazio
    assert "2 falha(s) sem mensagem" in execucoes[0]["erro"]
    assert "muda" in execucoes[0]["erro"]            # aponta o ingestor


async def test_orquestrador_zero_brutos_vira_erro_nao_sucesso(monkeypatch):
    async def fonte_zerada(db):   # coleta "bem-sucedida" que não viu a origem
        return {"novos": 0, "atualizados": 0, "inalterados": 0, "erros": 0,
                "zero_brutos": True,
                "ultimo_erro_amostra": "0 itens brutos na origem — layout pode ter mudado"}

    execucoes = _prepara_orquestrador(
        monkeypatch, [("z", "F", "legislacao", fonte_zerada)])
    resumo = await ci.executar_ingest_conhecimento()

    assert resumo["z"]["status"] == "erro"           # antes: "sucesso" com zero
    assert "layout" in execucoes[0]["erro"]

    # E o painel de saúde trata como crítico, com a mensagem visível:
    from app.services.ingestao_saude import avaliar_saude_fonte
    from datetime import datetime, timezone
    veredito = avaliar_saude_fonte(
        slug="z", ativo=True, ultima_execucao=datetime.now(timezone.utc),
        ultimo_status=execucoes[0]["status"], ultimo_erro=execucoes[0]["erro"],
        registros_novos=0, registros_total=0,
        execucoes_zeradas_consecutivas=0, ja_produziu=True,
    )
    assert veredito.critico is True
    assert veredito.situacao == "erro"               # não erro_sem_diagnostico
    assert "layout" in veredito.motivo


async def test_orquestrador_status_parcial_carrega_amostra(monkeypatch):
    async def fonte_parcial(db):
        return {"novos": 1, "atualizados": 0, "inalterados": 0, "erros": 1,
                "ultimo_erro_amostra": "rfb:ato:1: ValueError: boom"}

    execucoes = _prepara_orquestrador(
        monkeypatch, [("p", "F", "legislacao", fonte_parcial)])
    resumo = await ci.executar_ingest_conhecimento()
    assert resumo["p"]["status"] == "parcial"
    assert execucoes[0]["erro"] == "rfb:ato:1: ValueError: boom"


async def test_orquestrador_sucesso_nao_registra_erro(monkeypatch):
    async def fonte_ok(db):
        return {"novos": 2, "atualizados": 0, "inalterados": 1, "erros": 0}

    execucoes = _prepara_orquestrador(
        monkeypatch, [("ok", "F", "legislacao", fonte_ok)])
    resumo = await ci.executar_ingest_conhecimento()
    assert resumo["ok"]["status"] == "sucesso"
    assert execucoes[0]["erro"] is None


# ── 4. _parse_tjmg_html expõe métricas de blocos/tamanho ──────────────────────

HTML_TJMG_VALIDO = """
<html><body><table>
  <tr class="resultadoLinha"><td>
    Ac&oacute;rd&atilde;o: 1.0027.23.123456-7/001<br>
    Relator: Des. Jo&atilde;o Pereira<br>
    Ementa: APELA&Ccedil;&Atilde;O C&Iacute;VEL. Dano moral configurado por
    negativa de cobertura. Dever de indenizar reconhecido. Recurso provido.
  </td></tr>
  <tr class="resultadoLinha"><td>
    Ac&oacute;rd&atilde;o: 1.0027.23.777888-9/001<br>
    Relator: Desa. Maria Souza<br>
    Ementa: IRDR. Tese sobre juros remunerat&oacute;rios em contratos
    banc&aacute;rios firmada em incidente repetitivo no TJMG.
  </td></tr>
</table></body></html>
"""

HTML_TJMG_LAYOUT_NOVO = ("<html><body>" +
                         "<section class='novoLayout'>conteúdo qualquer sem a "
                         "classe esperada</section>" * 30 + "</body></html>")


def test_parse_tjmg_metricas_html_valido():
    met: dict = {}
    itens = je._parse_tjmg_html(HTML_TJMG_VALIDO, met)
    assert len(itens) == 2
    assert met["blocos"] == 2
    assert met["html_bytes"] == len(HTML_TJMG_VALIDO)


def test_parse_tjmg_metricas_layout_que_nao_casa_reporta_blocos_zero():
    met: dict = {}
    itens = je._parse_tjmg_html(HTML_TJMG_LAYOUT_NOVO, met)
    assert itens == []
    assert met["blocos"] == 0                    # nenhum bloco casou o padrão
    assert met["html_bytes"] > 0                 # ...mas o HTML VEIO
    assert met["html_bytes"] == len(HTML_TJMG_LAYOUT_NOVO)


def test_parse_tjmg_metricas_html_vazio():
    met: dict = {}
    assert je._parse_tjmg_html("", met) == []
    assert met == {"html_bytes": 0, "blocos": 0}


def test_parse_tjmg_sem_metricas_preserva_compatibilidade():
    # Demais chamadores (busca ao vivo, federação, crawler) chamam sem métricas
    assert je._parse_tjmg_html(HTML_TJMG_LAYOUT_NOVO) == []
    assert len(je._parse_tjmg_html(HTML_TJMG_VALIDO)) == 2


async def test_buscar_tjmg_rede_falhou_marca_metricas(monkeypatch):
    class _CliRedeCaida:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise RuntimeError("conexao recusada")

    monkeypatch.setattr(je.httpx, "AsyncClient", _CliRedeCaida)
    met: dict = {}
    assert await je.buscar_tjmg("dano moral", metricas=met) == []
    assert met == {"rede_falhou": True, "html_bytes": 0, "blocos": 0}


# ── 5. Ingestor TJMG distingue e loga os três zeros ───────────────────────────

def _prepara_ingestor_tjmg(monkeypatch, fake_buscar):
    s = get_settings()
    monkeypatch.setattr(s, "TJMG_INGEST_TEMAS", "tema1", raising=False)
    monkeypatch.setattr(s, "TJMG_INGEST_JANELA_DIAS", 0, raising=False)
    monkeypatch.setattr(s, "TJMG_INGEST_MAX_POR_TEMA", 50, raising=False)
    monkeypatch.setattr(tjmg, "buscar_tjmg", fake_buscar)

    async def fake_upsert(db, **kwargs):
        return "novo"
    monkeypatch.setattr(tjmg, "upsert_documento", fake_upsert)


async def test_ingestor_tjmg_loga_falha_de_rede(monkeypatch, caplog):
    async def fake_buscar(palavras, por_pagina=10, *, metricas=None, **kw):
        if metricas is not None:
            metricas.update(rede_falhou=True, html_bytes=0, blocos=0)
        return []

    _prepara_ingestor_tjmg(monkeypatch, fake_buscar)
    with caplog.at_level(logging.INFO, logger="ejc.ingestao.tjmg"):
        assert await tjmg.ingerir(_FakeDB()) == (0, 0)
    assert any("falha de rede" in r.message for r in caplog.records)
    assert not any("layout" in r.message for r in caplog.records)


async def test_ingestor_tjmg_loga_layout_quando_html_veio_sem_blocos(monkeypatch, caplog):
    async def fake_buscar(palavras, por_pagina=10, *, metricas=None, **kw):
        if metricas is not None:
            metricas.update(rede_falhou=False, html_bytes=48_000, blocos=0)
        return []

    _prepara_ingestor_tjmg(monkeypatch, fake_buscar)
    with caplog.at_level(logging.INFO, logger="ejc.ingestao.tjmg"):
        assert await tjmg.ingerir(_FakeDB()) == (0, 0)
    layout = [r for r in caplog.records if "layout" in r.getMessage()]
    assert layout and layout[0].levelno == logging.WARNING
    # O tamanho do HTML entra na mensagem: é ele que separa "a origem não
    # devolveu nada" de "devolveu e o parser não reconheceu".
    assert "48000 bytes" in layout[0].getMessage()


async def test_ingestor_tjmg_brutos_reflete_blocos_da_origem(monkeypatch, caplog):
    """`brutos` do log final = blocos brutos medidos no parser, não itens já
    parseados: 5 blocos vieram, só 1 virou item — o log tem de dizer 5."""
    item = {
        "titulo": "Acórdão TJMG 1.0027.23.123456-7/001",
        "ementa": "APELAÇÃO CÍVEL. Dano moral configurado por negativa de "
                  "cobertura de plano de saúde. Recurso provido.",
        "numero_acordao": "1.0027.23.123456-7/001",
    }

    async def fake_buscar(palavras, por_pagina=10, *, metricas=None, **kw):
        if metricas is not None:
            metricas.update(rede_falhou=False, html_bytes=10_000, blocos=5)
        return [item]

    _prepara_ingestor_tjmg(monkeypatch, fake_buscar)
    with caplog.at_level(logging.INFO, logger="ejc.ingestao.tjmg"):
        novos, total = await tjmg.ingerir(_FakeDB())
    assert (novos, total) == (1, 1)
    final = next(r for r in caplog.records if "blocos brutos" in r.message)
    assert final.getMessage().startswith("TJMG execução: 5 blocos brutos")


async def test_ingestor_tjmg_fake_sem_metricas_nao_quebra(monkeypatch):
    """Compatibilidade: buscar_tjmg substituído que ignora `metricas` (fakes
    antigos) degrada para a contagem por len(itens), sem exceção."""
    async def fake_buscar(palavras, por_pagina=10, **kw):
        return []

    _prepara_ingestor_tjmg(monkeypatch, fake_buscar)
    assert await tjmg.ingerir(_FakeDB()) == (0, 0)
