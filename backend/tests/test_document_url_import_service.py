import pytest

from app.services import document_url_import_service as svc


def test_validar_url_importavel_rejeita_localhost(monkeypatch):
    with pytest.raises(svc.URLImportError):
        svc.validar_url_importavel("http://localhost/admin")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/doc",
        "https://user:pass@example.com/segredo",
    ],
)
def test_validar_url_importavel_rejeita_esquemas_e_credenciais(url):
    with pytest.raises(svc.URLImportError):
        svc.validar_url_importavel(url)


def test_extrair_html_simples_obtem_titulo_descricao_e_texto():
    html = """
    <html>
      <head>
        <title>Informativo Jurídico Teste</title>
        <meta name="description" content="Resumo do informativo">
        <script>window.evil = true</script>
      </head>
      <body>
        <article>
          <h1>Tema STF</h1>
          <p>Este é um trecho juridicamente relevante sobre repercussão geral.</p>
        </article>
      </body>
    </html>
    """

    titulo, descricao, canonical, texto = svc.extrair_html_simples(html, "https://exemplo.com/x")

    assert titulo == "Informativo Jurídico Teste"
    assert descricao == "Resumo do informativo"
    assert canonical is None
    assert "Tema STF" in texto
    assert "repercussão geral" in texto
    assert "window.evil" not in texto


@pytest.mark.asyncio
async def test_importar_url_juridica_retorna_bloqueado_quando_fetch_falha(monkeypatch):
    async def fake_fetch(url):
        raise svc.URLImportError("O site bloqueou a importação automática.")

    monkeypatch.setattr(svc, "_fetch_bytes_seguro", fake_fetch)

    result = await svc.importar_url_juridica("https://informativos.trilhante.com.br/informativos/informativo-1216-stf")

    assert result.bloqueado is True
    assert "bloqueou" in (result.aviso or "")
    assert result.texto == ""
    assert result.dossie == ""


@pytest.mark.asyncio
async def test_importar_url_juridica_html_monta_dossie(monkeypatch):
    html = b"""
    <html><head><title>Informativo STF</title></head>
    <body><h1>Decisao STF</h1><p>Pedido, processo, tese juridica, prazo e prova documental.</p></body></html>
    """

    async def fake_fetch(url):
        return url, 200, "text/html; charset=utf-8", html

    monkeypatch.setattr(svc, "_fetch_bytes_seguro", fake_fetch)

    result = await svc.importar_url_juridica("https://stf.jus.br/exemplo")

    assert result.bloqueado is False
    assert result.titulo == "Informativo STF"
    assert "Decisao STF" in result.texto
    assert "Pedido" in result.dossie
    assert result.metadados["chars"] > 0


# ── SSRF por DNS rebinding: conectar no IP validado, não no nome (DADOS-018) ──
# Validar resolvia o host uma vez; o cliente HTTP resolvia OUTRA vez ao
# conectar. Entre as duas consultas cabe o ataque: DNS hostil devolve IP
# público para a checagem e IP interno para a conexão.

import pytest as _pytest

import app.services.document_url_import_service as _svc


def test_validacao_devolve_o_ip_para_quem_vai_conectar(monkeypatch):
    """A correção depende de o IP ATRAVESSAR a fronteira validação→conexão.
    Se a função voltar a devolver só a URL, o pinning se perde em silêncio."""
    monkeypatch.setattr(_svc, "_resolver_ips", lambda h: ["93.184.216.34"])
    url, host, ip = _svc.validar_e_fixar_url("https://exemplo.gov.br/lei.pdf")
    assert url == "https://exemplo.gov.br/lei.pdf"
    assert host == "exemplo.gov.br"
    assert ip == "93.184.216.34"


def test_dominio_com_ip_publico_e_interno_e_recusado_inteiro(monkeypatch):
    """Resposta DNS mista é a forma mais barata do ataque: basta um dos IPs ser
    interno para a URL inteira cair — não se escolhe "o público entre eles"."""
    monkeypatch.setattr(_svc, "_resolver_ips", lambda h: ["93.184.216.34", "169.254.169.254"])
    with _pytest.raises(_svc.URLImportError):
        _svc.validar_e_fixar_url("https://exemplo.gov.br/lei.pdf")


@_pytest.mark.parametrize(
    "url,ip,esperado",
    [
        ("https://exemplo.gov.br/a/b?c=1", "93.184.216.34", "https://93.184.216.34/a/b?c=1"),
        ("http://exemplo.gov.br:8080/x", "93.184.216.34", "http://93.184.216.34:8080/x"),
        ("https://exemplo.gov.br/x", "2001:db8::1", "https://[2001:db8::1]/x"),
    ],
)
def test_url_reescrita_no_ip_preserva_porta_caminho_e_query(url, ip, esperado):
    """Reescrever mal a URL trocaria um problema de segurança por um de
    funcionamento — IPv6 precisa de colchetes, porta e query não podem sumir."""
    assert _svc._url_no_ip(url, ip) == esperado


def test_validar_url_importavel_mantem_o_contrato_antigo(monkeypatch):
    """A função pública continua devolvendo só a URL: quem já a usava não muda."""
    monkeypatch.setattr(_svc, "_resolver_ips", lambda h: ["93.184.216.34"])
    assert _svc.validar_url_importavel("https://exemplo.gov.br/x") == "https://exemplo.gov.br/x"
