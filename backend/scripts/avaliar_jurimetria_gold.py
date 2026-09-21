#!/usr/bin/env python
"""Avalia o classificador TPU contra um gold set JÁ SANITIZADO.

Formato JSONL por linha:
{"id":"g001","esperado":"procedencia","movimentos":[{"codigo":219,"dataHora":"..."}]}

O avaliador recusa campos de processo/partes/PII. O piloto histórico #1252
não deve ser consumido diretamente: ele contém identificadores processuais e
não constitui, por si só, verdade humana de desfecho.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from app.services.jurimetria_tribunais import tpu_desfechos as tpu

ROTULOS = {
    tpu.PROCEDENCIA,
    tpu.PROCEDENCIA_PARCIAL,
    tpu.IMPROCEDENCIA,
    tpu.ACORDO,
    tpu.SEM_MERITO,
    "indeterminado",
}
PROIBIDOS = {
    "numeroprocesso", "numero_processo", "nr_cnj", "canonical_process",
    "direct_url", "partes", "parte", "cpf", "cnpj", "relator",
}


def validar_item(item: dict) -> None:
    extras = {str(k).replace("-", "_").lower() for k in item} & PROIBIDOS
    if extras:
        raise ValueError(f"gold set contém campo proibido: {sorted(extras)}")
    permitidos = {"id", "esperado", "movimentos"}
    desconhecidos = set(item) - permitidos
    if desconhecidos:
        raise ValueError(f"gold set contém campo não permitido: {sorted(desconhecidos)}")
    if item.get("esperado") not in ROTULOS:
        raise ValueError(f"rótulo esperado inválido: {item.get('esperado')!r}")
    if not isinstance(item.get("movimentos"), list):
        raise ValueError("movimentos precisa ser lista")


def prever(movimentos: list[dict]) -> str:
    resultado = tpu.desfecho_1grau(movimentos)
    return resultado[0] if resultado else "indeterminado"


def avaliar(itens: list[dict]) -> dict:
    matriz: dict[str, Counter] = defaultdict(Counter)
    total = 0
    acertos = 0
    for item in itens:
        validar_item(item)
        esperado = item["esperado"]
        previsto = prever(item["movimentos"])
        matriz[esperado][previsto] += 1
        total += 1
        acertos += int(esperado == previsto)

    rotulos = sorted(ROTULOS)
    por_classe = {}
    for rotulo in rotulos:
        tp = matriz[rotulo][rotulo]
        fp = sum(matriz[outro][rotulo] for outro in rotulos if outro != rotulo)
        fn = sum(matriz[rotulo][outro] for outro in rotulos if outro != rotulo)
        precisao = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precisao * recall / (precisao + recall)
            if precisao is not None and recall is not None and precisao + recall
            else None
        )
        por_classe[rotulo] = {
            "suporte": sum(matriz[rotulo].values()),
            "precisao": round(precisao, 4) if precisao is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
        }

    return {
        "n": total,
        "acuracia": round(acertos / total, 4) if total else None,
        "taxa_indeterminacao": (
            round(sum(col["indeterminado"] for col in matriz.values()) / total, 4)
            if total else None
        ),
        "matriz_confusao": {
            esperado: {previsto: matriz[esperado][previsto] for previsto in rotulos}
            for esperado in rotulos
        },
        "por_classe": por_classe,
    }


def carregar(path: Path) -> list[dict]:
    itens = []
    for numero, linha in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not linha.strip():
            continue
        item = json.loads(linha)
        try:
            validar_item(item)
        except ValueError as exc:
            raise ValueError(f"linha {numero}: {exc}") from exc
        itens.append(item)
    return itens


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gold_jsonl", type=Path)
    args = parser.parse_args()
    print(json.dumps(avaliar(carregar(args.gold_jsonl)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()