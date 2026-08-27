from __future__ import annotations

import json

import app.eval.coleta_fontes as coleta_fontes


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
