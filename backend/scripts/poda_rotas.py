#!/usr/bin/env python
"""Poda de rotas guiada por telemetria (S4, análise E2E 03/09/2026).

    python scripts/poda_rotas.py --dias 90 [--markdown saida.md]

Cruza o inventário real de rotas do app com a telemetria de uso
(`services/route_usage` — a mesma fonte de GET /architecture/uso-rotas) e
com os consumidores no frontend (grep em frontend/src). NÃO remove nada:
produz o relatório de candidatas para a decisão do titular. Ciclo sugerido:
90 dias sem uso → entra em API_ROTAS_DEPRECIADAS (header Deprecation/Sunset)
→ remoção na janela seguinte, com entrada em REMOCOES_INTENCIONAIS do ledger.

ALCANCE (revisão 03/09/2026): `route_usage` só conta as rotas de
`ROTAS_MONITORADAS` — o middleware descarta as demais no caminho quente. Rota
FORA dessa lista tem contagem zero porque NUNCA foi medida, não porque esteja
ociosa. O relatório, portanto, só lista candidatas DENTRO da lista monitorada;
para avaliar uma rota nova é preciso antes incluí-la em `ROTAS_MONITORADAS` e
esperar a janela.

Sem banco alcançável, usa só a telemetria em memória do processo (parcial) e
diz isso no cabeçalho do relatório.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO = os.path.abspath(os.path.join(RAIZ, ".."))
sys.path.insert(0, RAIZ)
os.environ.setdefault("APP_ENV", "development")

_PUBLICAS = ("/api/health", "/api/auth/", "/api/portal/", "/api/webhooks/", "/api/rag/knowledge-base")


def _rotas() -> list[tuple[str, str]]:
    from app.main import app

    out = []
    for r in app.routes:
        path = getattr(r, "path", "")
        for m in getattr(r, "methods", None) or ():
            if m in ("HEAD", "OPTIONS") or not path.startswith("/api"):
                continue
            out.append((m, path))
    return sorted(set(out))


async def _uso(desde: datetime) -> tuple[dict[str, dict], str]:
    """Rotas COM uso no período, indexadas pelo template SEM o prefixo /api.

    O agregado de `route_usage` publica `rota` (já normalizada por
    `_normalizar`: sem `/api`, sem barra final) e agrega por rota — não há
    `metodo` na linha agregada nem chave `path`. Ler `path`/`metodo` produzia
    a chave `("", "")` para todas as linhas: NENHUMA rota casava e o relatório
    declarava o app inteiro ocioso. Casamos por path normalizado, que é o
    grão real da medição.
    """
    from app.services import route_usage

    try:
        agg = await route_usage.agregado_persistido(desde)
        fonte = "persistida"
    except Exception:  # HistoricoIndisponivel, banco fora, etc.
        agg = route_usage.agregado(desde.isoformat())
        fonte = "memoria"
    if agg.get("historico_indisponivel"):
        # Zero aqui significaria "não li o histórico", não "ninguém usou".
        fonte = "INDISPONÍVEL"
    usados: dict[str, dict] = {}
    for linha in agg.get("rotas") or []:
        rota = str(linha.get("rota") or "")
        if rota and int(linha.get("total") or 0) > 0:
            usados[rota] = linha
    return usados, fonte


def _consumidores(path: str) -> list[str]:
    """Arquivos do frontend que citam o path (template {x} vira curinga)."""
    sem_prefixo = re.sub(r"^/api(/v1)?", "", path)
    padrao = re.escape(sem_prefixo)
    padrao = re.sub(r"\\\{[^}]+\\\}", r"[^\"'`/]+", padrao)
    if not sem_prefixo or sem_prefixo == "/":
        return []
    try:
        res = subprocess.run(
            ["grep", "-rlE", padrao, os.path.join(REPO, "frontend", "src"), "--include=*.ts", "--include=*.tsx"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return []
    return [os.path.relpath(p, REPO) for p in res.stdout.split() if ".test." not in p]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=90)
    ap.add_argument("--markdown", default="")
    args = ap.parse_args()

    from app.services.route_usage import ROTAS_MONITORADAS, _normalizar

    desde = datetime.now(timezone.utc) - timedelta(days=args.dias)
    rotas = _rotas()
    uso, fonte = asyncio.run(_uso(desde))

    if fonte == "INDISPONÍVEL":
        print("Histórico de telemetria indisponível — sem base para declarar rota ociosa. "
              "Nenhum relatório gerado.", file=sys.stderr)
        return 2

    # Só rota MEDIDA entra no relatório: fora de ROTAS_MONITORADAS a contagem é
    # zero por ausência de medição, e listá-la como candidata autorizaria
    # remover endpoint em uso diário.
    monitoradas = [(m, p) for m, p in rotas if _normalizar(p) in ROTAS_MONITORADAS]
    nao_medidas = len(rotas) - len(monitoradas)

    sem_uso_sem_consumidor, sem_uso_com_consumidor = [], []
    for m, p in monitoradas:
        if p.startswith(_PUBLICAS):
            continue
        if _normalizar(p) in uso:
            continue
        cons = _consumidores(p)
        (sem_uso_com_consumidor if cons else sem_uso_sem_consumidor).append((m, p, cons))

    linhas = [
        f"# Poda de rotas — candidatas ({args.dias} dias sem uso)",
        "",
        f"Gerado em {datetime.now(timezone.utc).isoformat(timespec='seconds')} · telemetria: **{fonte}**"
        + (" (parcial: só o processo atual)" if fonte == "memoria" else ""),
        f"Rotas no app: {len(rotas)} · MEDIDAS (ROTAS_MONITORADAS): {len(monitoradas)} · "
        f"com uso no período: {len(uso)}",
        "",
        f"> As outras {nao_medidas} rotas do app **não são medidas** por `route_usage` e "
        "por isso NÃO aparecem aqui: contagem zero nelas significa ausência de medição, "
        "não ausência de uso. Para avaliar uma delas, inclua-a em `ROTAS_MONITORADAS` e "
        "espere a janela.",
        "",
        f"## Sem uso e sem consumidor no frontend ({len(sem_uso_sem_consumidor)}) — candidatas diretas",
        "",
        "| Método | Rota |", "|---|---|",
        *[f"| {m} | `{p}` |" for m, p, _ in sem_uso_sem_consumidor],
        "",
        f"## Sem uso mas com consumidor no frontend ({len(sem_uso_com_consumidor)}) — investigar a tela antes",
        "",
        "| Método | Rota | Consumidores |", "|---|---|---|",
        *[f"| {m} | `{p}` | {', '.join(c[:3])}{' …' if len(c) > 3 else ''} |" for m, p, c in sem_uso_com_consumidor],
        "",
        "Próximo passo: copiar as candidatas aprovadas para `API_ROTAS_DEPRECIADAS` "
        "(`METODO /api/caminho`, `*` como prefixo) com `API_ROTAS_SUNSET`; remover na janela seguinte.",
    ]
    texto = "\n".join(linhas) + "\n"
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as fh:
            fh.write(texto)
        print(f"Relatório gravado em {args.markdown}")
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
