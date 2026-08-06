"""Regressão do prefixo /v1 duplicado (achado P0 da auditoria 2026-07, PR #652 fatia A).

Os routers montam-se internamente sob /api (main.py, API = "/api"); o contrato
público /api/v1 existe apenas pela reescrita do APIVersionCompatibilityMiddleware
(/api/v1/x → /api/x). Um router com prefixo próprio "/v1/..." fica montado em
/api/v1/... interno: o caminho canônico /api/v1/x é reescrito para /api/x — que
não existe — e a rota só responde no defeituoso /api/v1/v1/x. Foi o caso de 8
routers (despesas, office-contracts, partner-withdrawals, kanban, regulatorio,
datajud, whatsapp, pending-items). Estes testes impedem a volta da classe.
"""

from app.main import app
from app.utils.api_contract import _internal_api_url
from tests.test_rotas_registro_explicito import RELOCACOES_PREFIXO_V1


def _paths() -> set[str]:
    return {r.path for r in app.routes if getattr(r, "path", None)}


def test_nenhuma_rota_interna_carrega_prefixo_v1():
    """Superfície interna livre de /v1: o versionamento é só do middleware."""
    rotas = _paths()
    assert len(rotas) > 300, f"poucas rotas extraídas do app ({len(rotas)}) — import quebrado?"
    ofensoras = sorted(p for p in rotas if p == "/api/v1" or p.startswith("/api/v1/"))
    assert not ofensoras, (
        "Router montado com prefixo /v1 próprio — o caminho canônico /api/v1/... "
        "será reescrito pelo APIVersionCompatibilityMiddleware para /api/... e "
        "responderá 404; a rota só existiria em /api/v1/v1/... Remova o /v1 do "
        f"prefixo do router: {ofensoras}"
    )


def test_superficie_canonica_dos_oito_routers_resolve():
    """O path público /api/v1/x dos 33 endpoints realocados casa rota interna real.

    Deriva de RELOCACOES_PREFIXO_V1 (fonte única, também usada para provar que a
    relocação preservou auth em test_rotas_registro_explicito.py) — evita manter
    uma segunda lista hardcoded que envelhece por conta própria.
    """
    rotas = _paths()
    sem_rota = [
        publico
        for publico, _ in RELOCACOES_PREFIXO_V1
        if _internal_api_url(publico) not in rotas
    ]
    assert not sem_rota, (
        "Caminho canônico sem rota interna correspondente (404 em produção "
        f"após a reescrita do middleware): {sem_rota}"
    )


def test_mapa_de_modulos_detecta_rota_para_todo_prefixo_declarado():
    """`GET /system-modules/mapa` subdetectava rotas por prefixo desalinhado.

    `gerar_mapa_modulos` casa `backend_prefixes` contra os paths INTERNOS do app;
    prefixo escrito na forma pública (`/api/v1/despesas`) não casa nada e o
    módulo aparece com zero endpoints — foi o que a auditoria registrou como
    "mapa subdetecta rotas". Prefixo sem rota agora reprova aqui.
    """
    from app.services.module_registry import MODULE_REGISTRY

    rotas = _paths()
    orfaos = [
        (str(item["module_key"]), str(prefixo))
        for item in MODULE_REGISTRY
        for prefixo in item.get("backend_prefixes", [])
        if not any(rota.startswith(str(prefixo)) for rota in rotas)
    ]
    assert not orfaos, (
        "backend_prefixes sem nenhuma rota real correspondente — o mapa de "
        f"módulos reportará zero endpoints para: {orfaos}"
    )
