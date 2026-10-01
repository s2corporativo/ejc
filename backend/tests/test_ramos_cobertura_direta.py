"""Cobertura DIRETA dos routers compostos `ramos_vitrine` e
`ramos_ferramentas_complementares` (lacuna apontada pela Task 23 do worklog).

O agregador app/routers/ramos.py monta o router canônico de Áreas de Atuação
por CÓPIA de rotas: loops `add_api_route` copiam (path, métodos, dependências,
response_model, status_code, tags, summary) de cada sub-router. Essa mecânica
não tinha teste específico para estes dois ramos (~40 endpoints).

Três camadas de garantia:

1. MECÂNICA DE CÓPIA — cada rota do módulo base aparece no agregador com o
   MESMO path/métodos e o mesmo endpoint (o selo de não homologadas usa
   @wraps, preservando __qualname__/__module__). Contagem real contada no
   código: 22 rotas em ramos_vitrine e 18 em ramos_ferramentas_complementares
   — sendo que /tributario/ferramentas/auto-infracao-prazos NÃO é copiada do
   módulo de ferramentas: o agregador exclui essa cópia explicitamente e monta
   no lugar a versão versionada de ramos_tributario_paf (mesmo path, handler
   do módulo PAF). A paridade abaixo é dinâmica (compara base↔agregador), os
   números exatos são o piso de sanidade documentado hoje.

2. SANEAMENTO — nenhum (path, método) duplicado dentro do agregador e nenhum
   path compartilhado entre vitrine e ferramentas (colisão silenciosa viria
   de um caminho absoluto digitado errado num dos módulos).

3. COMPORTAMENTO LEVE — os handlers dos dois ramos são cálculos puros: não
   usam get_db/criar_audit_log (imports do módulo são apenas reexport p/
   compat) e a ÚNICA dependência FastAPI de todos os 40 endpoints é
   `require_roles_exact(_EQUIPE)`, que por sua vez depende de
   `get_current_user`. Num app de teste mínimo (SEM o AuthMiddleware global
   de app/main.py — mesmo padrão de isolamento do test_routes_smoke.py), um
   dependency_overrides em `get_current_user` basta para exercitar 200/403/
   404/405/422 sem Postgres nem JWT real.

Sem infra pesada: nada de Postgres (RUN_DB_TESTS), nada de lifespan.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.routers import ramos as agregador
from app.routers import ramos_ferramentas_complementares as ferramentas
from app.routers import ramos_tributario_paf as paf
from app.routers import ramos_vitrine as vitrine
from app.services.homologacao_ferramentas import normalizar_caminho_ferramenta

CONTAGEM_VITRINE = 22
CONTAGEM_FERRAMENTAS = 18


def _rotas(router):
    """Mapa {(path, frozenset(métodos)): rota} de um APIRouter."""
    return {
        (r.path, frozenset(getattr(r, "methods", ()))): r
        for r in router.routes
        if getattr(r, "path", None)
    }


ROTAS_VITRINE = _rotas(vitrine.router)
ROTAS_FERRAMENTAS = _rotas(ferramentas.router)
ROTAS_AGREGADOR = _rotas(agregador.router)

# ════════════════════════════════════════════════════════════════════════════
# 1. MECÂNICA DE CÓPIA — paridade base → agregador
# ════════════════════════════════════════════════════════════════════════════


def test_contagens_reais_dos_dois_ramos():
    """Piso de sanidade: a contagem REAL contada no código dos dois módulos.

    Se isto quebrar, alguém adicionou/removeu ferramenta sem passar pelo
    inventário — e a paridade dinâmica abaixo deixaria de significar o que
    a Task 23 catalogou (22 + 18).
    """
    assert len(ROTAS_VITRINE) == CONTAGEM_VITRINE, (
        f"ramos_vitrine tem {len(ROTAS_VITRINE)} rotas "
        f"(esperado {CONTAGEM_VITRINE}) — atualize CONTAGEM_VITRINE junto com o inventário"
    )
    assert len(ROTAS_FERRAMENTAS) == CONTAGEM_FERRAMENTAS, (
        f"ramos_ferramentas_complementares tem {len(ROTAS_FERRAMENTAS)} rotas "
        f"(esperado {CONTAGEM_FERRAMENTAS}) — atualize CONTAGEM_FERRAMENTAS junto com o inventário"
    )


def test_vitrine_todas_as_rotas_copiadas_para_o_agregador():
    """Cada rota da vitrine existe no agregador com mesmo path/métodos/endpoint.

    A cópia preserva o endpoint original (ou wrapper @wraps dele, quando o
    selo de não homologada é aplicado — __qualname__/__module__ sobrevivem).
    """
    faltantes = [
        (path, "+".join(sorted(metodos)))
        for (path, metodos) in ROTAS_VITRINE
        if (path, metodos) not in ROTAS_AGREGADOR
    ]
    assert not faltantes, f"rotas da vitrine ausentes no agregador: {faltantes}"

    divergentes = []
    for (path, metodos), rota_base in ROTAS_VITRINE.items():
        rota_agregada = ROTAS_AGREGADOR[(path, metodos)]
        if rota_agregada.endpoint.__qualname__ != rota_base.endpoint.__qualname__:
            divergentes.append(path)
    assert not divergentes, (
        f"endpoints da vitrine divergem entre módulo e agregador: {divergentes}"
    )


def test_ferramentas_todas_as_rotas_copiadas_para_o_agregador():
    """Os 18 paths das ferramentas existem no agregador (um via versão PAF).

    Exceção documentada em ramos.py: a cópia do histórico
    /tributario/ferramentas/auto-infracao-prazos é EXCLUÍDA do loop de
    ferramentas e o PAF versionado monta no lugar — o path segue presente,
    agora apontando para o handler de ramos_tributario_paf.
    """
    faltantes = [
        (path, "+".join(sorted(metodos)))
        for (path, metodos) in ROTAS_FERRAMENTAS
        if (path, metodos) not in ROTAS_AGREGADOR
    ]
    assert not faltantes, f"rotas de ferramentas ausentes no agregador: {faltantes}"

    substituida = paf.ROTA_AUTO_INFRACAO
    diretas = [p for (p, _) in ROTAS_FERRAMENTAS if p != substituida]
    divergentes = []
    for path in diretas:
        rota_base = next(r for (p, _), r in ROTAS_FERRAMENTAS.items() if p == path)
        rota_agregada = next(
            r for (p, _), r in ROTAS_AGREGADOR.items() if p == path
        )
        if rota_agregada.endpoint.__qualname__ != rota_base.endpoint.__qualname__:
            divergentes.append(path)
    assert not divergentes, (
        f"endpoints de ferramentas divergem entre módulo e agregador: {divergentes}"
    )


def test_auto_infracao_no_agregador_e_a_versao_paf():
    """No path da auto de infração, o agregador monta o handler versionado do
    PAF federal — não a cópia histórica de ferramentas_complementares."""
    rota = next(
        r for (p, _), r in ROTAS_AGREGADOR.items() if p == paf.ROTA_AUTO_INFRACAO
    )
    assert rota.endpoint.__module__ == "app.routers.ramos_tributario_paf", (
        "agregador deveria montar o handler versionado do PAF em "
        f"{paf.ROTA_AUTO_INFRACAO}; montou {rota.endpoint.__module__}."
    )


def test_agregador_sem_colisoes_path_metodo():
    """Nenhum (path, método) repetido dentro do agregador.

    add_api_route não reclama de duplicata: a segunda rota apenas entra depois
    na tabela e ganha a requisição por ordem de registro — colisão silenciosa
    que só um teste vê.
    """
    chaves = list(ROTAS_AGREGADOR)
    assert len(chaves) == len(set(chaves)), "duplicata (path, método) no agregador"

    vistos: set[tuple[str, str]] = set()
    colisoes = []
    for rota in agregador.router.routes:
        for metodo in getattr(rota, "methods", ()):
            par = (rota.path, metodo)
            if par in vistos:
                colisoes.append(par)
            vistos.add(par)
    assert not colisoes, f"colisões (path, método) no agregador: {colisoes}"


def test_vitrine_e_ferramentas_sem_colisao_entre_si():
    """Os dois ramos não disputam nenhum path entre si (paths absolutos:
    um typo de caminho num dos módulos colidiria em silêncio)."""
    intersecao = {p for (p, _) in ROTAS_VITRINE} & {p for (p, _) in ROTAS_FERRAMENTAS}
    assert not intersecao, f"paths compartilhados vitrine×ferramentas: {intersecao}"


# ════════════════════════════════════════════════════════════════════════════
# 2. ESTRUTURA — caminhos absolutos, tags, fonte única do gate
# ════════════════════════════════════════════════════════════════════════════


def test_estrutura_caminhos_absolutos_e_tags_areas_de_atuacao():
    """Contrato de montagem: caminhos ABSOLUTOS (o agregador não aplica
    prefixo — quem prefixa é main.py com include_router(prefix='/api')) e tag
    'Áreas de Atuação' preservada rota a rota pela cópia."""
    for (path, metodos), rota in ROTAS_VITRINE.items():
        assert path.startswith("/"), f"path da vitrine não é absoluto: {path}"
        assert "Áreas de Atuação" in rota.tags, f"tag perdida em {path}"
        rota_agregada = ROTAS_AGREGADOR[(path, metodos)]
        # Igualdade de CONJUNTO: o add_api_route(tags=_r.tags) num agregador que
        # também declara tags default DUPIFICA a tag na lista (self.tags + tags
        # do FastAPI) — efeito cosmético conhecido da mecânica de cópia; o que
        # o contrato exige é a tag SEMÂNTICA estar presente, não duplicada.
        assert set(rota_agregada.tags) == set(rota.tags), (
            f"tags divergem na cópia de {path}"
        )

    for (path, _), rota in ROTAS_FERRAMENTAS.items():
        assert path.startswith("/"), f"path de ferramentas não é absoluto: {path}"
        assert "Áreas de Atuação" in rota.tags, f"tag perdida em {path}"

    # Paridade de tags no agregador para as rotas diretas de ferramentas
    # (mesma igualdade de conjunto da vitrine — duplicata cosmética da cópia):
    substituida = paf.ROTA_AUTO_INFRACAO
    for (path, metodos), rota_base in ROTAS_FERRAMENTAS.items():
        if path == substituida:
            continue
        rota_agregada = ROTAS_AGREGADOR[(path, metodos)]
        assert set(rota_agregada.tags) == set(rota_base.tags), (
            f"tags divergem na cópia de {path}"
        )


def test_caminhos_ferramentas_validos_deriva_do_agregador():
    """CAMINHOS_FERRAMENTAS_VALIDOS (fonte única do gate do demonstrativo,
    Issue #702) deve conter os paths normalizados das 22+18 ferramentas —
    derivação do próprio agregador nunca pode divergir das rotas copiadas."""
    esperados = {
        normalizar_caminho_ferramenta(p)
        for p in ({p for (p, _) in ROTAS_VITRINE} | {p for (p, _) in ROTAS_FERRAMENTAS})
    }
    faltantes = esperados - set(agregador.CAMINHOS_FERRAMENTAS_VALIDOS)
    assert not faltantes, (
        f"ferramentas ausentes de CAMINHOS_FERRAMENTAS_VALIDOS: {sorted(faltantes)}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 3. COMPORTAMENTO LEVE — app mínimo, sem AuthMiddleware/DB/JWT
# ════════════════════════════════════════════════════════════════════════════


def _app_agregador() -> FastAPI:
    """FastAPI mínimo com o agregador montado (sem prefixo, paths absolutos).

    Não usa app.main: o AuthMiddleware global decodifica JWT ANTES das
    dependências e dependency_overrides não o atravessa. Sem middleware, o
    override de get_current_user alimenta diretamente o checker de RBAC —
    exatamente a fronteira que estes testes querem exercitar.
    """
    app = FastAPI()
    app.include_router(agregador.router)
    return app


def _instalar_usuario(app: FastAPI, role: str) -> None:
    """Override de get_current_user com um usuário sintético da role dada."""
    usuario = SimpleNamespace(role=role)

    async def _fake_current_user():
        return usuario

    app.dependency_overrides[get_current_user] = _fake_current_user


def _client(role: str = "advogado") -> TestClient:
    app = _app_agregador()
    _instalar_usuario(app, role)
    return TestClient(app, raise_server_exceptions=False)


def test_vitrine_devolucao_dobro_200_com_override_de_auth():
    """Leve: RBAC satisfeito → cálculo real da vitrine sem Postgres nem JWT.

    CDC art. 42 §ún. c/c EAREsp 676.608/RS: HOUVE pagamento, a cobrança foi
    contrária à boa-fé objetiva e não há engano justificável → repetição
    em DOBRO (200.0 sobre 100.0 cobrados indevidamente).
    """
    resp = _client().get(
        "/consumidor/ferramentas/devolucao-dobro",
        params={
            "valor_cobrado_indevidamente": 100.0,
            "houve_pagamento": "sim",
            "cobranca_contraria_boa_fe_objetiva": "sim",
            "engano_justificavel": "nao",
        },
    )
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["resultado"] == "dobro"
    assert corpo["restituicao_estimada"] == pytest.approx(200.0)
    assert corpo["aviso"].startswith("MINUTA")  # contrato HITL preservado


def test_vitrine_validacao_422_sem_parametros_obrigatorios():
    """Queries obrigatórias ausentes → 422 da validação (não 500)."""
    resp = _client().get("/consumidor/ferramentas/devolucao-dobro")
    assert resp.status_code == 422


def test_ferramentas_prescricao_consumidor_200_com_override_de_auth():
    """Leve: ferramenta com @_com_regra carimba fontes/vigência e responde 200."""
    resp = _client().get(
        "/civel/ferramentas/prescricao-consumidor",
        params={"data_fato": "2024-01-15", "tipo_vicio": "fato_produto"},
    )
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["instituto"] == "prescrição"
    assert corpo["prazo"] == "5 anos"
    assert corpo["fontes"]  # carimbo do decorator _com_regra presente


def test_ferramentas_auto_infracao_404_paf_200_transicao():
    """Leve: o path versionado do PAF responde pelo handler novo (esfera
    municipal é recusada com 422 SEMÂNTICO — não inferir prazo federal por
    analogia é o contrato do endpoint)."""
    resp = _client().get(
        paf.ROTA_AUTO_INFRACAO,
        params={"data_ciencia": "2026-02-10", "esfera": "municipal"},
    )
    assert resp.status_code == 422
    assert "não é seguro" in resp.json()["detail"].lower()


def test_role_fora_da_equipe_rejeitada_403():
    """require_roles_exact é conjunto FECHADO: 'financeiro' tem nível alto e
    ainda assim não passa — semântica que a cópia de dependências preserva."""
    resp = _client(role="financeiro").get(
        "/consumidor/ferramentas/devolucao-dobro",
        params={
            "valor_cobrado_indevidamente": 100.0,
            "houve_pagamento": "sim",
            "cobranca_contraria_boa_fe_objetiva": "sim",
            "engano_justificavel": "nao",
        },
    )
    assert resp.status_code == 403
    assert "Perfis permitidos" in resp.json()["detail"]


def test_rota_inexistente_no_composto_404():
    resp = _client().get("/consumidor/ferramentas/nao-existe")
    assert resp.status_code == 404


def test_metodo_nao_permitido_405():
    """As 40 rotas dos dois ramos são GET: POST na rota canônica → 405."""
    resp = _client().post(
        "/consumidor/ferramentas/devolucao-dobro",
        params={"valor_cobrado_indevidamente": 100.0},
    )
    assert resp.status_code == 405
