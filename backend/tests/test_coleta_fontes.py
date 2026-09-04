from __future__ import annotations

import json
from datetime import date

import pytest

import app.eval.coleta_fontes as coleta_fontes
from app.eval.coleta_fontes import (
    ErroDeColeta,
    Fonte,
    baixar,
    carregar_registro,
    coletar_fonte,
    extrair_artigos,
    html_para_texto,
    natureza_do_documento,
)

URL_ORIGINAL = (
    "https://www2.camara.leg.br/legin/fed/lei/2002/"
    "lei-10406-10-janeiro-2002-432893-publicacaooriginal-1-pl.html"
)


def test_natureza_ignora_o_menu_do_portal_e_falha_fechada():
    """Regressão: a primeira versão lia o corpo da página e errava.

    O portal da Câmara tem "Texto compilado" no menu de navegação. Varrer o
    texto classificava publicação original como compilada e marcava
    `prova_vigencia=true` numa fonte que não prova vigência nenhuma.
    """
    chrome = "Portal da Câmara dos Deputados Texto compilado Texto consolidado Menu"
    assert natureza_do_documento(URL_ORIGINAL, chrome) == "publicacao_original"

    compilado = "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"
    assert natureza_do_documento(compilado, "") == "texto_compilado"

    # Sem sinal inequívoco na URL, não se afirma vigência.
    assert natureza_do_documento("https://www.stj.jus.br/qualquer", "compilado") == "indeterminada"


def test_extrai_artigo_pedido_sem_confundir_com_numero_maior():
    texto = (
        "Art. 14. Dispositivo procurado, com corpo suficiente para ser reconhecido. "
        "Art. 140. Outro dispositivo, que não pode ser devolvido no lugar do 14. "
        "Art. 27. Terceiro dispositivo com texto bastante para o corte."
    )
    achados = extrair_artigos(texto, ["14", "27"])

    assert "Dispositivo procurado" in achados["14"]
    assert "Outro dispositivo" not in achados["14"]
    assert "Terceiro dispositivo" in achados["27"]


def test_html_para_texto_preserva_o_dispositivo_e_descarta_marcacao():
    bruto = b"<html><style>p{color:red}</style><p>Art. 186. Aquele que&nbsp;violar direito</p></html>"
    texto = html_para_texto(bruto)
    assert "Art. 186. Aquele que violar direito" in texto
    assert "color" not in texto


def test_recusa_fonte_fora_de_dominio_oficial():
    fonte = Fonte(apelido="x", titulo="t", url="https://example.com/lei", artigos=["1"])
    with pytest.raises(ErroDeColeta, match="domínio oficial"):
        coletar_fonte(fonte, baixador=lambda _: b"<p>Art. 1. algo</p>")


def test_recusa_http_sem_tls():
    fonte = Fonte(apelido="x", titulo="t", url="http://www.planalto.gov.br/lei", artigos=["1"])
    with pytest.raises(ErroDeColeta):
        coletar_fonte(fonte, baixador=lambda _: b"<p>Art. 1. algo</p>")


def test_coleta_fixa_hash_e_nao_assina_curadoria():
    """A ferramenta prova a fonte; quem atesta gabarito e vigência é humano."""
    fonte = Fonte(apelido="cc", titulo="Código Civil", url=URL_ORIGINAL, artigos=["186"])
    corpo = b"<p>Art. 186. Aquele que violar direito e causar dano comete ato ilicito.</p>"

    registro = coletar_fonte(fonte, hoje=date(2026, 8, 23), baixador=lambda _: corpo)

    assert registro["hash_sha256"] == __import__("hashlib").sha256(corpo).hexdigest()
    assert registro["consultada_em"] == "2026-08-23"
    assert "Art. 186" in registro["artigos"]["186"]
    assert registro["natureza"] == "publicacao_original"
    assert registro["prova_vigencia"] is False
    assert registro["vigencia_conferida_em"] is None
    assert registro["conferida_por"] is None


def test_artigo_ausente_e_reportado_em_vez_de_silenciado():
    fonte = Fonte(apelido="cc", titulo="Código Civil", url=URL_ORIGINAL, artigos=["186", "999"])
    registro = coletar_fonte(
        fonte, baixador=lambda _: b"<p>Art. 186. Texto suficiente do dispositivo.</p>"
    )
    assert registro["artigos_nao_encontrados"] == ["999"]


def test_resposta_vazia_falha_em_vez_de_registrar_fonte_vazia():
    fonte = Fonte(apelido="cc", titulo="Código Civil", url=URL_ORIGINAL, artigos=["186"])
    with pytest.raises(ErroDeColeta, match="vazia"):
        coletar_fonte(fonte, baixador=lambda _: b"")


def test_recusa_documento_que_nao_e_a_norma_declarada():
    """URL que responde 200 servindo outra lei não pode entrar calada no acervo.

    A disciplina "só registra URL com conteúdo conferido" estava escrita no
    registro e dependia de quem editasse o JSON. Aqui ela é do código.
    """
    fonte = Fonte(
        apelido="ctn",
        titulo="Lei 5.172/1966 — Código Tributário Nacional",
        url=URL_ORIGINAL,
        artigos=["173"],
        verificar_texto=["LEI N", "5.172"],
    )
    corpo = b"<p>LEI N 10.406, DE 10 DE JANEIRO DE 2002. Art. 173. Outro texto qualquer.</p>"

    with pytest.raises(ErroDeColeta, match="não é a norma que o registro declara"):
        coletar_fonte(fonte, baixador=lambda _: corpo)


def test_registra_o_que_foi_verificado_quando_o_documento_confere():
    fonte = Fonte(
        apelido="cc",
        titulo="Código Civil",
        url=URL_ORIGINAL,
        artigos=["186"],
        verificar_texto=["LEI N", "10.406"],
    )
    corpo = b"<p>LEI N 10.406, DE 10 DE JANEIRO DE 2002. Art. 186. Aquele que violar direito.</p>"

    registro = coletar_fonte(fonte, baixador=lambda _: corpo)

    assert registro["verificado_contem"] == ["LEI N", "10.406"]
    assert "Art. 186" in registro["artigos"]["186"]


# ── Achados do review do Codex sobre ea439071 ──────────────────────────────


def test_recusa_redirecionamento_para_fora_de_dominio_oficial(monkeypatch):
    """`urlopen` segue redirect sozinho; sem conferir `geturl()` a proveniência vira ficção.

    Os marcadores de `verificar_texto` não cobrem este caso: a página externa
    pode reproduzir o texto da lei e casar todos eles.
    """

    class RespostaRedirecionada:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def geturl(self):
            return "https://cdn.exemplo.com/copia-da-lei"

        def read(self):
            return b"LEI N 8.078, DE 11 DE SETEMBRO DE 1990. Art. 14. Texto identico."

    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: RespostaRedirecionada()
    )
    with pytest.raises(ErroDeColeta, match="redirecionamento para fora"):
        baixar("https://www2.camara.leg.br/legin/qualquer")


def test_artigo_com_sufixo_e_com_milhar_pontuado():
    """`170-A` e `1.022` são corriqueiros; capturar só os dígitos iniciais errava nos dois sentidos."""
    texto = (
        "Art. 170. Dispositivo base, com corpo suficiente para não ser descartado. "
        "Art. 170-A. Dispositivo sufixado, também com corpo suficiente. "
        "Art. 1.022. Milhar pontuado, com corpo suficiente para o corte."
    )

    # Pedir o base não pode devolver o sufixado.
    assert "Art. 170. Dispositivo base" in extrair_artigos(texto, ["170"])["170"]
    assert "sufixado" not in extrair_artigos(texto, ["170"])["170"]

    # O sufixado precisa ser encontrável.
    assert "sufixado" in extrair_artigos(texto, ["170-A"])["170-A"]

    # Milhar pontuado ou não são o mesmo artigo.
    assert "Milhar" in extrair_artigos(texto, ["1.022"])["1.022"]
    assert "Milhar" in extrair_artigos(texto, ["1022"])["1022"]


def test_registro_sem_marcador_de_identidade_e_recusado(tmp_path):
    """Sem `verificar_texto`, a coleta aceitaria qualquer página do domínio.

    Como muitos diplomas compartilham os mesmos números de artigo, uma URL
    oficial errada povoaria o registro com artigos de outra norma.
    """
    reg = tmp_path / "registro.json"
    reg.write_text(
        json.dumps(
            {
                "fontes": [
                    {
                        "apelido": "com",
                        "titulo": "t",
                        "url": "https://www2.camara.leg.br/a",
                        "verificar_texto": ["LEI N"],
                    },
                    {"apelido": "sem", "titulo": "t", "url": "https://www2.camara.leg.br/b"},
                    {
                        "apelido": "vazio",
                        "titulo": "t",
                        "url": "https://www2.camara.leg.br/c",
                        "verificar_texto": ["  "],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ErroDeColeta) as exc:
        carregar_registro(reg)

    assert "sem" in str(exc.value)
    assert "vazio" in str(exc.value)
    assert "com" not in str(exc.value).split(":")[1].split(".")[0]


def test_falha_parcial_nao_publica_registro_truncado(tmp_path, monkeypatch, capsys):
    """Uma fonte falhando não pode substituir um registro completo por um truncado.

    Antes, `main` retornava 0 quando ao menos uma fonte tinha sido coletada, e a
    escrita já havia trocado o arquivo pelo subconjunto — automação ou curador
    leriam o parcial como completo. Falha de rede durante coleta é esperada.
    """
    saida = tmp_path / "fontes.json"
    saida.write_text('{"fontes": ["COMPLETO"]}', encoding="utf-8")
    registro = tmp_path / "registro.json"
    registro.write_text(
        json.dumps(
            {
                "fontes": [
                    {
                        "apelido": "boa",
                        "titulo": "t",
                        "url": "https://www2.camara.leg.br/a",
                        "verificar_texto": ["LEI"],
                    },
                    {
                        "apelido": "ruim",
                        "titulo": "t",
                        "url": "https://www2.camara.leg.br/b",
                        "verificar_texto": ["LEI"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    def coleta_meio_quebrada(fonte, **_):
        if fonte.apelido == "ruim":
            raise OSError("rede caiu no meio da coleta")
        return {"apelido": fonte.apelido, "prova_vigencia": False, "artigos": {},
                "artigos_nao_encontrados": [], "hash_sha256": "x" * 64}

    monkeypatch.setattr(coleta_fontes, "coletar_fonte", coleta_meio_quebrada)

    codigo = coleta_fontes.main(["--registro", str(registro), "--saida", str(saida)])

    assert codigo == 1
    assert saida.read_text(encoding="utf-8") == '{"fontes": ["COMPLETO"]}'
