"""Trava anti-drift: catálogo backend ↔ registro de rotas do frontend (§7.1).

O backend mantém o catálogo CURADO de módulos em
`app/services/module_registry.py` (`frontend_route` de cada módulo); o
frontend mantém a fonte da verdade de roteamento em
`frontend/src/config/moduleRegistry.tsx` (`STAFF_ROUTES` + `LEGACY_REDIRECTS`).
São duas listas mantidas à mão em linguagens diferentes — exatamente o tipo de
cópia que envelhece em silêncio (pente fino E2E de 30/08/2026, §7.1: nada
quebrava quando uma rota era consolidada no frontend e o catálogo backend
continuava apontando para o alias aposentado).

Este teste lê o .tsx ESTATICAMENTE (regex sobre o fonte, sem Node), no mesmo
padrão de `test_status_caso_paridade_frontend.py`, e garante:

  (a) todo `frontend_route` do backend corresponde a uma rota canônica de
      STAFF_ROUTES (ignorando querystring `?tab=`/`?modo=`/`?tipo=` — o path
      base precisa existir) ou a uma exceção explícita documentada abaixo;
  (b) nenhum `frontend_route` aponta para um `from:` de LEGACY_REDIRECTS
      (alias aposentado — o catálogo deve usar a rota canônica `to:`);
  (c) o drift de chaves entre os dois registros é DECLARADO: as diferenças
      conhecidas ficam em allowlists comentadas — drift NOVO quebra o teste.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.module_registry import MODULE_REGISTRY

ARQUIVO_TSX = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "config"
    / "moduleRegistry.tsx"
)

# (a) Rotas do catálogo backend que NÃO são páginas de STAFF_ROUTES de
# propósito — cada entrada documenta por quê. Nova exceção só entra aqui com
# justificativa, nunca por conveniência.
ROTAS_FORA_DE_STAFF_ROUTES: dict[str, str] = {
    # O Portal do Cliente é uma superfície própria para `cliente_externo`
    # (PortalLayout/rotas de portal), fora do registro de rotas da equipe
    # interna (STAFF_ROUTES) — o catálogo backend o lista mesmo assim porque
    # o mapa de módulos cobre o sistema inteiro, não só a área staff.
    "/portal": "superfície do cliente externo, roteada fora de STAFF_ROUTES",
}

# (c) module_keys do catálogo backend sem `key` homônima em STAFF_ROUTES.
# O catálogo backend é um agregado CURADO: vários módulos são ABAS de um
# workspace do frontend (uma única rota/`key`), não páginas próprias.
BACKEND_SEM_KEY_NO_FRONTEND: set[str] = {
    "atendimento",       # aba de /atividades (?tab=relacionamento)
    "honorarios",        # aba de /financeiro (?tab=honorarios)
    "ia",                # aba de /inteligencia (?tab=ia)
    "ferramentas-ia",    # aba de /inteligencia (?tab=ferramentas)
    "conhecimento",      # aba de /inteligencia (?tab=conhecimento)
    "jurimetria",        # aba de /inteligencia (?tab=jurimetria)
    "radar-regulatorio", # modo de /radar (?modo=digest)
    "portal",            # superfície do cliente externo (ver exceção acima)
    # Consolidação 30/08/2026: as páginas /legado/* viraram LEGACY_REDIRECTS
    # para /atividades?tipo=... — os módulos seguem catalogados no backend
    # como filtros da Central de Atividades, sem key própria no frontend.
    "prazos",            # filtro de /atividades (?tipo=prazo)
    "tarefas",           # filtro de /atividades (?tipo=tarefa)
    "intimacoes",        # filtro de /atividades (?tipo=intimacao)
}

# (c) `key`s de STAFF_ROUTES sem módulo homônimo no catálogo backend.
# O catálogo é um SUBCONJUNTO curado por módulo de negócio; o frontend
# registra também rotas de navegação/detalhe/utilitárias que não são módulos.
FRONTEND_SEM_MODULO_NO_BACKEND: set[str] = {
    # Detalhe/edição de registros (sub-rotas do módulo pai já catalogado)
    "caso-novo", "caso-detalhe", "caso-jornada", "caso-entrevista",
    "cliente-detalhe", "cadastro-manual", "ramo-detalhe",
    # Workspaces/casca cujo conteúdo já está catalogado por módulo
    # (a consolidação do "DPT360 triplo" aposentou dpt360-subroutes/
    #  dpt360-company-detail: as sub-rotas ficaram em ModuleRoute.subPaths
    #  do próprio módulo dpt360 — auditoria §2.6 #7)
    "atividades", "atividades-dia", "radar", "entrada",
    "dpt360",
    # Telas utilitárias/administrativas sem módulo de negócio próprio
    "configuracoes", "ajuda", "lixeira", "ferramentas", "prompts",
    "governanca-ia", "banco-teses", "raio-x-processo",
    # Workspace tributário (#1550 reconstruído como satélite): carteira de
    # casos por ?area=tributario + fontes oficiais; conteúdo de negócio já
    # catalogado via módulos de casos/áreas. Porta no hub /ferramentas.
    "tributario",
}


def _bloco(fonte: str, inicio: str, fim: str) -> str:
    assert inicio in fonte, f"marcador {inicio!r} não encontrado em {ARQUIVO_TSX.name}"
    return fonte.split(inicio, 1)[1].split(fim, 1)[0]


@pytest.fixture(scope="module")
def fonte_tsx() -> str:
    assert ARQUIVO_TSX.exists(), f"fonte do frontend ausente: {ARQUIVO_TSX}"
    return ARQUIVO_TSX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def staff_paths(fonte_tsx: str) -> list[str]:
    bloco = _bloco(fonte_tsx, "export const STAFF_ROUTES", "export const LEGACY_REDIRECTS")
    paths = re.findall(r'path:\s*"([^"]+)"', bloco)
    assert len(paths) > 30, "STAFF_ROUTES encolheu demais — extração pode ter quebrado"
    return paths


@pytest.fixture(scope="module")
def staff_keys(fonte_tsx: str) -> set[str]:
    bloco = _bloco(fonte_tsx, "export const STAFF_ROUTES", "export const LEGACY_REDIRECTS")
    return set(re.findall(r'key:\s*"([^"]+)"', bloco))


@pytest.fixture(scope="module")
def legacy_froms(fonte_tsx: str) -> set[str]:
    bloco = _bloco(fonte_tsx, "export const LEGACY_REDIRECTS", "function routeBase")
    froms = set(re.findall(r'from:\s*"([^"]+)"', bloco))
    assert froms, "LEGACY_REDIRECTS vazio — extração pode ter quebrado"
    return froms


def _path_base(route: str) -> str:
    """`/financeiro?tab=societaria` -> `/financeiro` (compara ignorando query)."""
    return route.split("?", 1)[0] or "/"


def _casa_pattern(pattern: str, path: str) -> bool:
    """Espelha o matcher mínimo do frontend (routePatternMatches): igualdade,
    sufixo `/*` e segmentos `:param`."""
    if pattern == path:
        return True
    if pattern.endswith("/*"):
        base = pattern[:-2]
        return path == base or path.startswith(base + "/")
    esperados = [s for s in pattern.split("/") if s]
    reais = [s for s in path.split("/") if s]
    if len(esperados) != len(reais):
        return False
    return all(e.startswith(":") or e == r for e, r in zip(esperados, reais))


# ── (a) todo frontend_route existe como rota canônica do frontend ────────────


def test_frontend_route_do_backend_existe_em_staff_routes(staff_paths):
    sem_match: list[tuple[str, str]] = []
    for mod in MODULE_REGISTRY:
        rota = str(mod["frontend_route"])
        if rota in ROTAS_FORA_DE_STAFF_ROUTES:
            continue
        base = _path_base(rota)
        if not any(_casa_pattern(p, base) for p in staff_paths):
            sem_match.append((str(mod["module_key"]), rota))
    assert not sem_match, (
        "frontend_route do catálogo backend sem rota correspondente em "
        f"STAFF_ROUTES (moduleRegistry.tsx): {sem_match} — atualize o catálogo "
        "para a rota canônica atual ou documente a exceção em "
        "ROTAS_FORA_DE_STAFF_ROUTES."
    )


def test_excecoes_de_rota_continuam_necessarias(staff_paths):
    """Exceção que passou a existir em STAFF_ROUTES vira lixo documental —
    remove-se da allowlist em vez de deixá-la mascarar um futuro conflito."""
    for rota in ROTAS_FORA_DE_STAFF_ROUTES:
        base = _path_base(rota)
        assert not any(_casa_pattern(p, base) for p in staff_paths), (
            f"{rota} agora existe em STAFF_ROUTES — remova a exceção de "
            "ROTAS_FORA_DE_STAFF_ROUTES."
        )


# ── (b) nenhum frontend_route aponta para alias aposentado ───────────────────


def test_frontend_route_nao_usa_alias_de_legacy_redirects(legacy_froms):
    apontando_para_legado = [
        (str(mod["module_key"]), str(mod["frontend_route"]))
        for mod in MODULE_REGISTRY
        if _path_base(str(mod["frontend_route"])) in legacy_froms
        or str(mod["frontend_route"]) in legacy_froms
    ]
    assert not apontando_para_legado, (
        "catálogo backend aponta para rota APOSENTADA (from: de "
        f"LEGACY_REDIRECTS): {apontando_para_legado} — troque pela rota "
        "canônica (o `to:` do redirect correspondente)."
    )


# ── (c) drift de chaves declarado, nunca silencioso ──────────────────────────


def test_drift_de_module_keys_e_o_declarado(staff_keys):
    backend_keys = {str(m["module_key"]) for m in MODULE_REGISTRY}

    backend_sem_front = backend_keys - staff_keys
    front_sem_backend = staff_keys - backend_keys

    novos_no_backend = backend_sem_front - BACKEND_SEM_KEY_NO_FRONTEND
    assert not novos_no_backend, (
        "module_key novo no catálogo backend sem key correspondente em "
        f"STAFF_ROUTES: {sorted(novos_no_backend)} — registre a rota no "
        "frontend ou documente na allowlist BACKEND_SEM_KEY_NO_FRONTEND "
        "(com o porquê)."
    )

    novos_no_front = front_sem_backend - FRONTEND_SEM_MODULO_NO_BACKEND
    assert not novos_no_front, (
        "key nova em STAFF_ROUTES sem módulo no catálogo backend: "
        f"{sorted(novos_no_front)} — catalogue o módulo em "
        "module_registry.py ou documente na allowlist "
        "FRONTEND_SEM_MODULO_NO_BACKEND (com o porquê)."
    )

    # Allowlist não pode acumular entradas mortas: se o drift sumiu (os dois
    # lados convergiram), a entrada sai da lista.
    mortas_backend = BACKEND_SEM_KEY_NO_FRONTEND - backend_sem_front
    assert not mortas_backend, (
        f"entradas obsoletas em BACKEND_SEM_KEY_NO_FRONTEND: {sorted(mortas_backend)}"
    )
    mortas_front = FRONTEND_SEM_MODULO_NO_BACKEND - front_sem_backend
    assert not mortas_front, (
        f"entradas obsoletas em FRONTEND_SEM_MODULO_NO_BACKEND: {sorted(mortas_front)}"
    )
