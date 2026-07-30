#!/usr/bin/env python3
"""Reconcilia uma amostra do EJC com consulta independente no DJEN/CNJ.

Entradas contêm somente metadados mínimos. O relatório nunca inclui número de
processo ou identificador externo em claro: divergências recebem HMAC truncado.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA = "ejc.djen.reconciliacao.v1"
CAMPOS = {
    "data_disponibilizacao",
    "numero_processo",
    "tribunal",
    "tipo_comunicacao",
    "comunicacao_id_externo",
}
OBRIGATORIOS = {
    "data_disponibilizacao",
    "numero_processo",
    "tribunal",
    "tipo_comunicacao",
}
MAX_LINHAS = 5000
ENV_CHAVE = "DJEN_RECONCILIACAO_CHAVE"


class ErroEntrada(ValueError):
    """Entrada inválida sem ecoar conteúdo potencialmente confidencial."""


@dataclass(frozen=True, slots=True)
class Registro:
    chave_composta: str
    id_externo: str


@dataclass(frozen=True, slots=True)
class Amostra:
    registros: tuple[Registro, ...]
    sha256: str


def _texto(valor: str) -> str:
    decomposto = unicodedata.normalize("NFKD", valor or "")
    sem_acentos = "".join(
        caractere for caractere in decomposto if not unicodedata.combining(caractere)
    )
    return re.sub(r"\s+", " ", sem_acentos).strip().upper()


def _processo(valor: str, linha: int) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) != 20:
        raise ErroEntrada(
            f"linha {linha}: numero_processo deve conter exatamente 20 dígitos"
        )
    return digitos


def _data_iso(valor: str, linha: int, inicio: date, fim: date) -> str:
    try:
        data = date.fromisoformat((valor or "").strip())
    except ValueError as exc:
        raise ErroEntrada(
            f"linha {linha}: data_disponibilizacao deve usar AAAA-MM-DD"
        ) from exc
    if not inicio <= data <= fim:
        raise ErroEntrada(f"linha {linha}: data fora do período declarado")
    return data.isoformat()


def _ler_csv(path: Path, inicio: date, fim: date) -> Amostra:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    registros: list[Registro] = []

    with path.open("r", encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        cabecalho = {str(campo or "").strip() for campo in (leitor.fieldnames or [])}
        faltantes = OBRIGATORIOS - cabecalho
        extras = cabecalho - CAMPOS
        if faltantes:
            raise ErroEntrada(
                "cabeçalho incompleto; faltam: " + ", ".join(sorted(faltantes))
            )
        if extras:
            raise ErroEntrada(
                "cabeçalho contém campos não permitidos: " + ", ".join(sorted(extras))
            )

        for numero_linha, bruto in enumerate(leitor, start=2):
            if len(registros) >= MAX_LINHAS:
                raise ErroEntrada(f"amostra excede o limite de {MAX_LINHAS} linhas")
            linha = {
                str(chave or "").strip(): str(valor or "").strip()
                for chave, valor in bruto.items()
            }
            data_disp = _data_iso(
                linha["data_disponibilizacao"], numero_linha, inicio, fim
            )
            processo = _processo(linha["numero_processo"], numero_linha)
            tribunal = _texto(linha["tribunal"])
            tipo = _texto(linha["tipo_comunicacao"])
            if not tribunal or not tipo:
                raise ErroEntrada(
                    f"linha {numero_linha}: tribunal e tipo_comunicacao são obrigatórios"
                )
            id_externo = _texto(linha.get("comunicacao_id_externo", ""))
            composta = "|".join((data_disp, processo, tribunal, tipo))
            registros.append(Registro(composta, id_externo))

    return Amostra(tuple(registros), digest)


def _hmac(chave: bytes, valor: str) -> str:
    return hmac.new(chave, valor.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _divergencias(
    chave: bytes,
    contador: Counter[str],
) -> list[dict[str, int | str]]:
    return [
        {"chave_hmac": _hmac(chave, f"composta:{item}"), "ocorrencias": quantidade}
        for item, quantidade in sorted(contador.items())
    ]


def _ids_por_chave(registros: Iterable[Registro]) -> dict[str, set[str]]:
    saida: dict[str, set[str]] = defaultdict(set)
    for registro in registros:
        if registro.id_externo:
            saida[registro.chave_composta].add(registro.id_externo)
    return dict(saida)


def reconciliar(
    arquivo_ejc: Path,
    arquivo_djen: Path,
    inicio: date,
    fim: date,
    chave_hmac: str,
) -> dict:
    """Produz relatório sanitizado; não persiste nem retorna campos brutos."""
    if inicio > fim:
        raise ErroEntrada("período inválido: início posterior ao fim")
    if len(chave_hmac) < 16:
        raise ErroEntrada(f"{ENV_CHAVE} deve conter ao menos 16 caracteres")

    segredo = chave_hmac.encode("utf-8")
    ejc = _ler_csv(arquivo_ejc, inicio, fim)
    djen = _ler_csv(arquivo_djen, inicio, fim)

    contador_ejc = Counter(item.chave_composta for item in ejc.registros)
    contador_djen = Counter(item.chave_composta for item in djen.registros)
    faltantes = contador_djen - contador_ejc
    extras = contador_ejc - contador_djen

    ids_ejc = _ids_por_chave(ejc.registros)
    ids_djen = _ids_por_chave(djen.registros)
    ids_divergentes = []
    for composta in sorted(set(ids_ejc) & set(ids_djen)):
        if ids_ejc[composta] != ids_djen[composta]:
            ids_divergentes.append(
                {"chave_hmac": _hmac(segredo, f"composta:{composta}")}
            )

    repetidas_ejc = Counter(
        {item: qtd for item, qtd in contador_ejc.items() if qtd > 1}
    )
    repetidas_djen = Counter(
        {item: qtd for item, qtd in contador_djen.items() if qtd > 1}
    )

    resultado = (
        "conforme"
        if not faltantes and not extras and not ids_divergentes
        else "divergente"
    )
    return {
        "schema": SCHEMA,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
        "resultado": resultado,
        "fontes": {
            "ejc": {"linhas": len(ejc.registros), "sha256": ejc.sha256},
            "djen_oficial": {"linhas": len(djen.registros), "sha256": djen.sha256},
        },
        "totais": {
            "faltantes_no_ejc": sum(faltantes.values()),
            "extras_no_ejc": sum(extras.values()),
            "identificadores_divergentes": len(ids_divergentes),
        },
        "faltantes_no_ejc": _divergencias(segredo, faltantes),
        "extras_no_ejc": _divergencias(segredo, extras),
        "identificadores_divergentes": ids_divergentes,
        "chaves_repetidas": {
            "ejc": _divergencias(segredo, repetidas_ejc),
            "djen_oficial": _divergencias(segredo, repetidas_djen),
        },
        "privacidade": (
            "Números de processo e identificadores externos não integram este "
            "relatório; chaves de divergência são HMAC truncados."
        ),
    }


def _gravar_atomico(path: Path, relatorio: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conteudo = json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporario:
        temporario.write(conteudo)
        temporario.flush()
        os.fsync(temporario.fileno())
        temp_path = Path(temporario.name)
    os.replace(temp_path, path)


def _data_arg(valor: str) -> date:
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use AAAA-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcilia amostra independente EJC x DJEN sem expor dados brutos."
    )
    parser.add_argument("--ejc", required=True, type=Path, help="CSV sanitizado do EJC")
    parser.add_argument(
        "--djen", required=True, type=Path, help="CSV da consulta manual oficial"
    )
    parser.add_argument("--inicio", required=True, type=_data_arg)
    parser.add_argument("--fim", required=True, type=_data_arg)
    parser.add_argument("--saida", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        chave = os.environ.get(ENV_CHAVE, "")
        relatorio = reconciliar(args.ejc, args.djen, args.inicio, args.fim, chave)
        _gravar_atomico(args.saida, relatorio)
    except (ErroEntrada, OSError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "resultado": relatorio["resultado"],
                "totais": relatorio["totais"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if relatorio["resultado"] == "conforme" else 2


if __name__ == "__main__":
    raise SystemExit(main())
