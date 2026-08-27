from __future__ import annotations

import json

import pytest

import app.eval.coleta_fontes as coleta_fontes
from app.eval.coleta_fontes import ErroDeColeta, Fonte, coletar_fonte, extrair_artigos, html_para_texto


def _registro(path, apelidos: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "fontes": [
                    {
                        "apelido": apelido,
                        "titulo": apelido.upper(),
                        "url": f"https://www2.camara.leg.br/{apelido}",
                        "verificar_texto": ["LEI"],
                    }
                    for apelido in apelidos
                ]
            }
        ),
        encoding="utf-8",
    )


def _coleta_falsa(fonte, **_):
    return {
        "apelido": fonte.apelido,
        "titulo": fonte.titulo,
        "prova_vigencia": False,
        "artigos": {},
        "artigos_nao_encontrados": [],
        "hash_sha256": fonte.apelido * 32,
    }


def test_coleta_completa_remove_fonte_aposentada_da_saida(tmp_path, monkeypatch):
    """Sem --apelido, o registro atual é a fonte da verdade da saída."""
    saida = tmp_path / "fontes.json"
    saida.write_text(
        json.dumps(
            {
                "fontes": [
                    {"apelido": "ativa", "hash_sha256": "a" * 64},
                    {"apelido": "aposentada", "hash_sha256": "b" * 64},
                ]
            }
        ),
        encoding="utf-8",
    )
    registro = tmp_path / "registro.json"
    _registro(registro, ["ativa"])
    monkeypatch.setattr(coleta_fontes, "coletar_fonte", _coleta_falsa)

    codigo = coleta_fontes.main(["--registro", str(registro), "--saida", str(saida)])

    assert codigo == 0
    apelidos = [
        f["apelido"]
        for f in json.loads(saida.read_text(encoding="utf-8"))["fontes"]
    ]
    assert apelidos == ["ativa"]


def test_coleta_completa_com_registro_vazio_publica_saida_vazia(tmp_path):
    """Retirar a última fonte do registro também precisa retirar a saída antiga."""
    saida = tmp_path / "fontes.json"
    saida.write_text(
        json.dumps({"fontes": [{"apelido": "aposentada", "hash_sha256": "a" * 64}]}),
        encoding="utf-8",
    )
    registro = tmp_path / "registro.json"
    registro.write_text(json.dumps({"fontes": []}), encoding="utf-8")

    codigo = coleta_fontes.main(["--registro", str(registro), "--saida", str(saida)])

    assert codigo == 0
    payload = json.loads(saida.read_text(encoding="utf-8"))
    assert payload["fontes"] == []


def test_coleta_seletiva_continua_preservando_fontes_existentes(tmp_path, monkeypatch):
    """Com --apelido, a atualização incremental continua sem apagar outras fontes."""
    saida = tmp_path / "fontes.json"
    saida.write_text(
        json.dumps(
            {
                "fontes": [
                    {"apelido": "ativa", "hash_sha256": "a" * 64},
                    {"apelido": "outra", "hash_sha256": "b" * 64},
                ]
            }
        ),
        encoding="utf-8",
    )
    registro = tmp_path / "registro.json"
    _registro(registro, ["ativa"])
    monkeypatch.setattr(coleta_fontes, "coletar_fonte", _coleta_falsa)

    codigo = coleta_fontes.main(
        ["--registro", str(registro), "--saida", str(saida), "--apelido", "ativa"]
    )

    assert codigo == 0
    apelidos = {
        f["apelido"]
        for f in json.loads(saida.read_text(encoding="utf-8"))["fontes"]
    }
    assert apelidos == {"ativa", "outra"}


def test_coleta_seletiva_recusa_saida_previa_corrompida_sem_sobrescrever(tmp_path, monkeypatch):
    """Modo incremental precisa preservar o arquivo se não consegue lê-lo."""
    saida = tmp_path / "fontes.json"
    original = '{"fontes": [INVALIDO]}'
    saida.write_text(original, encoding="utf-8")
    registro = tmp_path / "registro.json"
    _registro(registro, ["ativa"])
    monkeypatch.setattr(coleta_fontes, "coletar_fonte", _coleta_falsa)

    codigo = coleta_fontes.main(
        ["--registro", str(registro), "--saida", str(saida), "--apelido", "ativa"]
    )

    assert codigo == 1
    assert saida.read_text(encoding="utf-8") == original


def test_html_de_blocos_preserva_cabecalhos_de_artigos():
    """div/li/tr também precisam delimitar dispositivos, não só p/br."""
    bruto = (
        b"<div>Art. 14. Primeiro dispositivo com corpo suficientemente longo para teste.</div>"
        b"<li>Art. 15. Segundo dispositivo com corpo suficientemente longo para teste.</li>"
        b"<table><tr><td>Art. 16. Terceiro dispositivo com corpo suficientemente longo.</td></tr></table>"
    )
    texto = html_para_texto(bruto)
    artigos = extrair_artigos(texto, ["14", "15", "16"])

    assert "Primeiro dispositivo" in artigos["14"]
    assert "Segundo dispositivo" in artigos["15"]
    assert "Terceiro dispositivo" in artigos["16"]


def test_ato_alterador_que_cita_norma_na_ementa_nao_passa_por_identidade():
    """Número/data na ementa não transformam a lei alteradora na norma-alvo."""
    fonte = Fonte(
        apelido="ctn",
        titulo="CTN",
        url="https://www2.camara.leg.br/ato",
        artigos=["173"],
        verificar_texto=["LEI N", "5.172", "25 DE OUTUBRO DE 1966"],
    )
    corpo = (
        b"<p>LEI N 99.999, DE 1 DE JANEIRO DE 2020.</p>"
        b"<p>Altera a LEI N 5.172, DE 25 DE OUTUBRO DE 1966, e da outras providencias.</p>"
        b"<p>Art. 173. Texto da lei alteradora, nao do CTN, suficientemente longo.</p>"
    )

    with pytest.raises(ErroDeColeta, match="linha-título"):
        coletar_fonte(fonte, baixador=lambda _: corpo)


def test_linha_titulo_real_com_todos_os_marcadores_passa():
    fonte = Fonte(
        apelido="ctn",
        titulo="CTN",
        url="https://www2.camara.leg.br/ctn",
        artigos=["173"],
        verificar_texto=["LEI N", "5.172", "25 DE OUTUBRO DE 1966"],
    )
    corpo = (
        b"<div>LEI N 5.172, DE 25 DE OUTUBRO DE 1966.</div>"
        b"<div>Art. 173. O direito de a Fazenda constituir o credito extingue-se apos cinco anos.</div>"
    )

    registro = coletar_fonte(fonte, baixador=lambda _: corpo)

    assert "Art. 173" in registro["artigos"]["173"]
