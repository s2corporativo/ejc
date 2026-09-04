#!/usr/bin/env python
# ── scripts/carregar_tpu.py ──────────────────────────────────────────────────
# Carrega a TPU (Tabelas Processuais Unificadas, Res. CNJ 46/2007) para
# `saneamento.tpu_movimento`, SEMPRE como 'nao_classificado'.
#
# A classificação funcional (terminativo/suspensivo/reativador/ordinario) é
# decisão jurídica e NÃO é feita por este script — ele só popula o catálogo
# para que um advogado classifique depois, com fonte e autor registrados
# (colunas `fonte`/`revisado_por`/`revisado_em` de TpuMovimento).
#
# A VERIFICAR antes do uso: a fonte oficial da tabela é o SGT (Sistema de
# Gestão de Tabelas Processuais Unificadas) do CNJ. Defina TPU_FONTE_URL com
# o endpoint, ou informe um arquivo local com --arquivo. O script NÃO adivinha
# a URL — falha explicitamente se nenhuma das duas for fornecida.
#
# Nunca sobrescreve um código já classificado por um advogado: o UPDATE só
# atinge linhas ainda em 'nao_classificado' (mesma cautela do pacote de
# referência ejc-saneamento/scripts/carregar_tpu.py).
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.saneamento import TpuMovimento


def _carregar_registros(caminho: str | None, url: str | None) -> list[dict]:
    if caminho:
        with open(caminho, encoding="utf-8") as fh:
            return json.load(fh)
    if not url:
        sys.exit(
            "ERRO: informe --arquivo ou defina TPU_FONTE_URL.\n"
            "A URL do SGT não é presumida por este script."
        )
    import httpx  # import tardio: só necessário no caminho de rede

    r = httpx.get(url, timeout=60.0)
    r.raise_for_status()
    return r.json()


async def _carregar(linhas: list[tuple[int, str]]) -> int:
    """Upsert em lote — só atualiza nome/atualizado_em de linhas ainda
    `nao_classificado`; nunca sobrescreve classificação já revisada."""
    agora = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        atualizados = 0
        for codigo, nome in linhas:
            existente = (
                await db.execute(select(TpuMovimento).where(TpuMovimento.codigo == codigo))
            ).scalar_one_or_none()
            if existente is None:
                db.add(
                    TpuMovimento(
                        codigo=codigo, nome=nome, classe="nao_classificado",
                        fonte="carga SGT/CNJ",
                    )
                )
                atualizados += 1
            elif existente.classe == "nao_classificado":
                existente.nome = nome
                existente.atualizado_em = agora
                atualizados += 1
            # classe já revisada: nome pode ter mudado no SGT, mas a
            # classificação jurídica é preservada — não é papel deste script.
        await db.commit()
    return atualizados


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arquivo", help="JSON local com [{codigo, nome}, ...]")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    registros = _carregar_registros(args.arquivo, os.getenv("TPU_FONTE_URL"))
    linhas = [
        (int(r["codigo"]), str(r.get("nome", "")).strip())
        for r in registros
        if str(r.get("codigo", "")).strip().isdigit()
    ]
    print(f"{len(linhas)} códigos lidos ({len(registros) - len(linhas)} descartados)")

    if args.dry_run:
        for c, n in linhas[:10]:
            print(f"  {c} | {n}")
        return 0

    atualizados = asyncio.run(_carregar(linhas))
    print(f"carga concluída — {atualizados} código(s) inserido(s)/atualizado(s) como 'nao_classificado'")
    print("PRÓXIMO PASSO: revisão jurídica para classificar os terminativos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
