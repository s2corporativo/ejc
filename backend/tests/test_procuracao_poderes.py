# Testes dos PODERES da minuta de procuração: a geração deve refletir EXATAMENTE
# o cadastro (tipo_poderes / permite_substabelecimento / poderes_especiais) e
# NUNCA outorgar substabelecimento/renúncia que o cliente não concedeu.
from app.models.case import Case
from app.models.client import Client
from app.services.documental import _procuracao, _clausula_poderes


def _cli() -> Client:
    return Client(id="cli1", nome="Joao da Silva", cpf="00000000000")


def _case() -> Case:
    return Case(id="caso1", titulo="Cobranca Indevida", client_id="cli1")


# ── _clausula_poderes (unidade, sem depender de Case/Client) ──────────────────

def test_ad_judicia_sem_substab_nao_contem_substabelecer_nem_renunciar():
    titulo, corpo = _clausula_poderes("ad_judicia", permite_substabelecimento=False, poderes_especiais=None)
    assert titulo == "PROCURACAO AD JUDICIA"
    assert "ET EXTRA" not in titulo
    assert "substabelecer" not in corpo.lower()
    assert "renunciar" not in corpo.lower()


def test_ad_judicia_com_substab_inclui_substabelecer_mas_nao_renunciar():
    # substabelecimento é gate independente dos poderes especiais do art. 105.
    _, corpo = _clausula_poderes("ad_judicia", permite_substabelecimento=True, poderes_especiais=None)
    assert "substabelecer" in corpo.lower()
    assert "renunciar" not in corpo.lower()


def test_et_extra_sem_substab_inclui_renunciar_mas_nao_substabelecer():
    titulo, corpo = _clausula_poderes("ad_judicia_et_extra", permite_substabelecimento=False, poderes_especiais=None)
    assert titulo == "PROCURACAO AD JUDICIA ET EXTRA"
    assert "renunciar" in corpo.lower()
    assert "substabelecer" not in corpo.lower()


def test_et_extra_com_substab_inclui_ambos():
    _, corpo = _clausula_poderes("ad_judicia_et_extra", permite_substabelecimento=True, poderes_especiais=None)
    assert "renunciar" in corpo.lower()
    assert "substabelecer" in corpo.lower()


def test_especiais_usa_texto_informado_e_nao_vaza_art_105():
    _, corpo = _clausula_poderes(
        "especiais", permite_substabelecimento=False,
        poderes_especiais="levantar valores em conta judicial e assinar acordo extrajudicial",
    )
    assert "levantar valores em conta judicial" in corpo
    # não injeta automaticamente o rol do art. 105
    assert "renunciar ao direito sobre que se funda" not in corpo
    assert "substabelecer" not in corpo.lower()


def test_especiais_sem_texto_gera_placeholder_visivel():
    _, corpo = _clausula_poderes("especiais", permite_substabelecimento=False, poderes_especiais=None)
    assert "[especificar os poderes especiais outorgados]" in corpo


# ── _procuracao (texto completo da minuta) ────────────────────────────────────

def test_minuta_ad_judicia_do_cadastro_nao_outorga_poderes_nao_concedidos():
    texto = _procuracao(
        _case(), _cli(), "Dra. Fulana",
        tipo_poderes="ad_judicia", permite_substabelecimento=False, poderes_especiais=None,
    )
    assert "PROCURACAO AD JUDICIA" in texto
    assert "ET EXTRA" not in texto
    assert "substabelecer" not in texto.lower()
    assert "renunciar" not in texto.lower()
    # dados variáveis preservados
    assert "Cobranca Indevida" in texto


def test_minuta_et_extra_permite_false_remove_substabelecimento():
    texto = _procuracao(
        _case(), _cli(), "Dra. Fulana",
        tipo_poderes="ad_judicia_et_extra", permite_substabelecimento=False,
    )
    assert "renunciar" in texto.lower()
    assert "substabelecer" not in texto.lower()


def test_minuta_default_conservador_ad_judicia_sem_art_105():
    # Chamada SEM parâmetros de poderes (fluxo de gerar_documentos_iniciais):
    # DEFAULT CONSERVADOR alinhado ao kit documental — ad_judicia, SEM os
    # poderes especiais do art. 105 do CPC (renúncia/transação/quitação).
    # Substabelecimento segue o padrão do escritório (default True, como no
    # KitDocumentalIn). O comportamento histórico (et extra por omissão) foi
    # descontinuado.
    texto = _procuracao(_case(), _cli(), "Dra. Fulana")
    assert "PROCURACAO AD JUDICIA" in texto
    assert "ET EXTRA" not in texto
    assert "renunciar" not in texto.lower()
    assert "transigir" not in texto.lower()
    assert "substabelecer" in texto.lower()


def test_caminho_amplo_explicito_continua_disponivel():
    # O escopo amplo (art. 105 + substabelecimento) segue disponível, mas SÓ
    # com marcação explícita — mesmo vocabulário do kit documental.
    texto = _procuracao(
        _case(), _cli(), "Dra. Fulana",
        tipo_poderes="ad_judicia_et_extra", permite_substabelecimento=True,
    )
    assert "AD JUDICIA ET EXTRA" in texto
    assert "renunciar" in texto.lower()
    assert "substabelecer" in texto.lower()


def test_defaults_do_fluxo_legado_iguais_ao_kit_documental():
    # Paridade de contrato: o fluxo legado (gerar_documentos_iniciais /
    # POST /cases/{id}/gerar-documentos) usa EXATAMENTE os defaults
    # conservadores do kit documental (KitDocumentalIn).
    import inspect

    from app.routers.kit_documental import KitDocumentalIn
    from app.services.documental import gerar_documentos_iniciais

    kit = KitDocumentalIn()
    sig = inspect.signature(gerar_documentos_iniciais)
    assert sig.parameters["tipo_poderes"].default == kit.tipo_poderes == "ad_judicia"
    assert sig.parameters["permite_substabelecimento"].default is kit.permite_substabelecimento
    assert sig.parameters["poderes_especiais"].default is kit.poderes_especiais is None

    sig_proc = inspect.signature(_procuracao)
    assert sig_proc.parameters["tipo_poderes"].default == "ad_judicia"


def test_minuta_sem_caso_usa_foro_restrito():
    texto = _procuracao(
        None, _cli(), "Dra. Fulana",
        tipo_poderes="ad_judicia", permite_substabelecimento=False,
        foro_restrito="Comarca de Sete Lagoas/MG",
    )
    assert "Comarca de Sete Lagoas/MG" in texto
    assert "substabelecer" not in texto.lower()
