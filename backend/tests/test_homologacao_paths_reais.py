# -*- coding: utf-8 -*-
"""Todo path da matriz de homologação tem que existir no app.

Achado do review do CodeRabbit no PR #1316, generalizado: o probe
`portal_nao_usa_datajud` batia em `/api/datajud/health`, que **não existe**.
Ele passava assim mesmo — o 403 vinha do `AuthMiddleware` sobre um caminho
inexistente —, e um probe que passa sem exercitar endpoint nenhum é pior que
probe ausente: ele dá a impressão de cobertura que não há.

`validar_matriz()` já checa estrutura e semântica (tipos, actors, expected,
negativo obrigatório) mas nunca conferiu se o path corresponde a uma rota
real. É essa lacuna que este teste fecha — para toda a matriz, não só para o
caso que apareceu.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MATRIZ = ROOT / "qa" / "homologacao" / "matriz_homologacao.json"


def _segmentos(path: str) -> list[str]:
    return [s for s in path.split("?", 1)[0].split("/") if s]


def _e_placeholder(seg: str) -> bool:
    return seg.startswith("{") and seg.endswith("}")


def _casa(path_matriz: str, path_rota: str) -> bool:
    """Casa o path da matriz contra o padrão da rota do FastAPI.

    Um segmento parametrizado da ROTA (`{case_id}`) casa com qualquer segmento
    da matriz — placeholder dela (`{cnj_teste}`, substituído em execução) ou
    literal (um CNJ fixo, por exemplo). O inverso não vale: placeholder da
    matriz sobre segmento literal da rota seria path inventado.
    """
    seg_m, seg_r = _segmentos(path_matriz), _segmentos(path_rota)
    if len(seg_m) != len(seg_r):
        return False
    return all(_e_placeholder(r) or r == m for m, r in zip(seg_m, seg_r))


@pytest.fixture(scope="module")
def rotas_do_app() -> list[str]:
    from app.main import app

    return [r.path for r in app.routes if getattr(r, "path", "").startswith("/api")]


@pytest.fixture(scope="module")
def passos() -> list[tuple[str, str, str]]:
    matriz = json.loads(MATRIZ.read_text(encoding="utf-8"))
    return [
        (cenario["id"], passo["nome"], passo["path"])
        for cenario in matriz["cenarios"]
        for passo in cenario.get("passos", [])
        if passo.get("path")
    ]


def test_matriz_tem_passos(passos):
    """Anti-vácuo do próprio arquivo: sem passos, o teste abaixo não guarda nada.

    São 41 passos com path hoje (H01–H15); o piso fica folgado de propósito —
    ele existe para pegar matriz vazia ou não carregada, não para travar a
    contagem exata a cada passo novo.
    """
    assert len(passos) >= 40


def test_todo_path_da_matriz_existe_no_app(passos, rotas_do_app):
    orfaos = [
        f"{cid}/{nome}: {path}"
        for cid, nome, path in passos
        if not any(_casa(path, rota) for rota in rotas_do_app)
    ]
    assert not orfaos, (
        "path de homologação sem rota correspondente no app — o probe passa sem "
        "exercitar endpoint nenhum (403/404 do middleware) e finge cobertura:\n  "
        + "\n  ".join(orfaos)
    )


def test_casa_rejeita_path_inventado(rotas_do_app):
    """Guarda do próprio comparador: se `_casa` virasse permissivo demais, o
    teste acima passaria a aceitar exatamente o que ele existe para pegar."""
    assert any(_casa("/api/datajud/process/00008323520188130024", r) for r in rotas_do_app)
    assert not any(_casa("/api/datajud/health", r) for r in rotas_do_app)
    # Placeholder da matriz não pode inventar segmento literal da rota.
    assert not _casa("/api/{qualquer}/process/{x}", "/api/datajud/process/{numero_cnj}")
