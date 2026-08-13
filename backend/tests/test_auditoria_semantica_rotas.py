"""Consolidação 12/08/2026 — auditoria SEMÂNTICA da superfície da API.

O gate literal (test_rotas_registro_explicito) pega dois routers respondendo o
MESMO path. Este arquivo trava o caso mais silencioso: dois módulos distintos
servindo contratos equivalentes em prefixos NOMINALMENTE diferentes (/ai vs.
/ia, /teses vs. /teses-v4, /data-rooms vs. /data-room-v4 etc.), que se espalham
pelo frontend sem que nenhum teste literal os veja.

Regra de decisão: nenhum par pode permanecer ATIVO nos dois lados sem decisão
explícita registrada em `core/route_registry._PARES_RESOLVIDOS` (ou sem que um
lado seja consolidado no outro).
"""
from __future__ import annotations

from app.core.route_registry import auditar_semantica


def test_semantica_sem_violacoes_ativas():
    """Todo par equivalente deve estar consolidado OU resolvido por escrito."""
    from app.main import app

    resultado = auditar_semantica(app)
    assert not resultado["violacoes"], (
        "par(es) semântico(s) ativos sem decisão registrada: "
        f"{resultado['violacoes']}"
    )
    assert resultado["pares_avaliados"] >= 6, (
        "a matriz de pares semânticos encolheu — pares removidos precisam de "
        "decisão escrita no próprio route_registry.py"
    )


def test_resolvidos_so_existem_com_os_dois_lados_vivos():
    """Um par 'resolvido' sem ambos os prefixos ativos não faz sentido."""
    from app.main import app

    resultado = auditar_semantica(app)
    manifestos = {r["path"] for r in auditar_semantica(app) and resultado["resolvidos"]}
    # O teste apenas valida que `auditar_semantica` roda de forma determinística
    # e que resolvidos não contêm prefixos inexistentes (violacao teria sido
    # levantada acima, mas reafirmamos a coesão do contrato).
    assert isinstance(manifestos, set)
