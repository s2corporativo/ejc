"""Predicao local de jurimetria.

Este modulo e deliberadamente pequeno e sem acesso a banco. Ele fornece:
- codificacao numerica estavel para features juridicas basicas;
- preditor opcional a partir de um artefato local serializado;
- fallback seguro quando nenhum modelo treinado existir.

A saida nunca deve ser tratada como promessa de resultado juridico.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "jurimetria_provimento.pkl"

TRIBUNAIS_MAP: dict[str, int] = {
    "STF": 1,
    "STJ": 2,
    "TST": 3,
    "TRF1": 11,
    "TRF2": 12,
    "TRF3": 13,
    "TRF4": 14,
    "TRF5": 15,
    "TRF6": 16,
    "TJMG": 31,
    "TJSP": 32,
    "TJRJ": 33,
    "TJRS": 34,
    "TJPR": 35,
}

GRAU_MAP: dict[str, int] = {
    "G1": 1,
    "1": 1,
    "1G": 1,
    "G2": 2,
    "2": 2,
    "2G": 2,
    "SUPERIOR": 3,
}


def _int_or_default(value: Any, default: int = -1) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _encode_features(
    classe: int | str | None,
    assunto: int | str | None,
    tribunal: str | None,
    dias_estimados: int | str | None,
    grau: str | None,
) -> np.ndarray:
    """Codifica atributos de entrada para um vetor numerico (1, 5)."""
    tribunal_key = (tribunal or "").strip().upper()
    grau_key = (grau or "").strip().upper()
    dias = max(0, min(_int_or_default(dias_estimados, 0), 3650))
    return np.array(
        [[
            _int_or_default(classe),
            _int_or_default(assunto),
            TRIBUNAIS_MAP.get(tribunal_key, -1),
            dias,
            GRAU_MAP.get(grau_key, -1),
        ]],
        dtype=float,
    )


def _load_model() -> Any | None:
    if not MODEL_PATH.exists():
        return None
    with MODEL_PATH.open("rb") as fh:
        return pickle.load(fh)


def prever_provimento(
    classe: int | str | None,
    assunto: int | str | None,
    tribunal: str | None,
    dias_estimados: int | str | None,
    grau: str | None,
) -> dict[str, Any]:
    """Preve provimento quando houver modelo treinado localmente.

    Sem modelo, retorna indisponivel de forma explicita. Isso evita falsa
    confianca e mantem conformidade com etica OAB: a predicao e apenas apoio.
    """
    model = _load_model()
    if model is None:
        return {
            "disponivel": False,
            "mensagem": "Modelo de jurimetria ainda nao treinado.",
        }

    features = _encode_features(classe, assunto, tribunal, dias_estimados, grau)
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(features)[0]
        probabilidade = float(max(proba))
    else:
        pred = model.predict(features)[0]
        probabilidade = float(pred)

    return {
        "disponivel": True,
        "probabilidade_provimento": round(probabilidade * 100, 2),
        "aviso": "Estimativa estatistica sem garantia de resultado. Requer revisao humana.",
    }
