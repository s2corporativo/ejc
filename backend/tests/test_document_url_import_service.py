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
