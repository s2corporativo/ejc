"""Testes do reconciliador independente EJC x DJEN."""
from __future__ import annotations

import csv
import json
from datetime import date

import pytest

from scripts.djen.reconciliar_amostra import ErroEntrada, reconciliar

CAMPOS = [
    "data_disponibilizacao",
    "numero_processo",
    "tribunal",
    "tipo_comunicacao",
    "comunicacao_id_externo",
]
SEGREDO = "segredo-efemero-de-teste"


def _csv(path, linhas, campos=CAMPOS):
    with path.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(linhas)


def _linha(processo="0" * 20, id_externo="com-1"):
    return {
        "data_disponibilizacao": "2026-07-29",
        "numero_processo": processo,
        "tribunal": "TJMG",
        "tipo_comunicacao": "Intimação",
        "comunicacao_id_externo": id_externo,
    }


def test_amostras_iguais_ficam_conformes_sem_expor_processo(tmp_path):
    ejc = tmp_path / "ejc.csv"
    djen = tmp_path / "djen.csv"
    _csv(ejc, [_linha()])
    _csv(djen, [_linha()])

    relatorio = reconciliar(
        ejc,
        djen,
        date(2026, 7, 29),
        date(2026, 7, 29),
        SEGREDO,
    )

    assert relatorio["resultado"] == "conforme"
    assert relatorio["totais"]["faltantes_no_ejc"] == 0
    serializado = json.dumps(relatorio, ensure_ascii=False)
    assert "0" * 20 not in serializado
    assert "com-1" not in serializado


def test_publicacao_ausente_no_ejc_e_divergencia_mas_saida_e_mascarada(tmp_path):
    ejc = tmp_path / "ejc.csv"
    djen = tmp_path / "djen.csv"
    _csv(ejc, [])
    _csv(djen, [_linha(processo="1" * 20)])

    relatorio = reconciliar(
        ejc,
        djen,
        date(2026, 7, 29),
        date(2026, 7, 29),
        SEGREDO,
    )

    assert relatorio["resultado"] == "divergente"
    assert relatorio["totais"]["faltantes_no_ejc"] == 1
    assert len(relatorio["faltantes_no_ejc"][0]["chave_hmac"]) == 16
    assert "1" * 20 not in json.dumps(relatorio)


def test_identificador_diferente_e_sinalizado(tmp_path):
    ejc = tmp_path / "ejc.csv"
    djen = tmp_path / "djen.csv"
    _csv(ejc, [_linha(id_externo="id-ejc")])
    _csv(djen, [_linha(id_externo="id-djen")])

    relatorio = reconciliar(
        ejc,
        djen,
        date(2026, 7, 29),
        date(2026, 7, 29),
        SEGREDO,
    )

    assert relatorio["resultado"] == "divergente"
    assert relatorio["totais"]["identificadores_divergentes"] == 1


def test_campo_sensivel_extra_e_rejeitado(tmp_path):
    ejc = tmp_path / "ejc.csv"
    djen = tmp_path / "djen.csv"
    campos = [*CAMPOS, "texto"]
    linha = {**_linha(), "texto": "conteúdo que não deve entrar na amostra"}
    _csv(ejc, [linha], campos=campos)
    _csv(djen, [_linha()])

    with pytest.raises(ErroEntrada, match="campos não permitidos"):
        reconciliar(
            ejc,
            djen,
            date(2026, 7, 29),
            date(2026, 7, 29),
            SEGREDO,
        )


def test_processo_fora_do_padrao_e_rejeitado_sem_ecoar_valor(tmp_path):
    ejc = tmp_path / "ejc.csv"
    djen = tmp_path / "djen.csv"
    _csv(ejc, [_linha(processo="123")])
    _csv(djen, [])

    with pytest.raises(ErroEntrada) as exc:
        reconciliar(
            ejc,
            djen,
            date(2026, 7, 29),
            date(2026, 7, 29),
            SEGREDO,
        )

    assert "123" not in str(exc.value)
