# ── tests/test_rbac_equipe_juridica_694.py ────────────────────────────────────
# Issue #694 — gates de RBAC na superfície jurídica usavam piso hierárquico
# `ROLE_LEVEL.get(...) < ROLE_LEVEL["estagiario"]` (ou o `>=` equivalente).
# Como `financeiro` (nível 4) fica NUMERICAMENTE ACIMA de `estagiario` (nível 3)
# em ROLE_LEVEL (app/core/security.py), esse piso liberava `financeiro` para
# praticar/ler ato jurídico — geração de peça por IA, teses, jurisprudência,
# dossiê estratégico, provas, jurimetria, memória institucional etc.
#
# A correção substitui o piso por EQUIPE_JURIDICA — allowlist EXATA (sem
# fallback hierárquico; ver docstring de requer_equipe_juridica em
# app/core/security.py). Note-se que require_roles() (a dependency factory
# genérica do repositório) NÃO serve para isso: ela cai para comparação
# hierárquica quando o papel não está na lista literal — é o MESMO defeito,
# documentado em test_bloco6_rbac_papel.py::test_fin_gate_passa_nivel_suficiente.
from __future__ import annotations

import ast
import asyncio
import pathlib
import re

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import (
    EQUIPE_JURIDICA,
    ROLE_LEVEL,
    get_current_user,
    require_roles_exact,
    requer_equipe_juridica,
)
from app.models.user import User, UserRole


def _u(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role, full_name="Fulano de Teste")


PAPEIS_FORA_DA_EQUIPE = [UserRole.financeiro, UserRole.secretaria, UserRole.cliente_externo]

PAPEIS_DA_EQUIPE = [
    UserRole.superadmin, UserRole.admin, UserRole.socio,
    UserRole.advogado, UserRole.advogado_auxiliar, UserRole.estagiario,
]


# ── Gate compartilhado (fonte única) ──────────────────────────────────────────

def test_financeiro_tem_nivel_hierarquico_acima_de_estagiario():
    assert ROLE_LEVEL["financeiro"] > ROLE_LEVEL["estagiario"]
    assert "financeiro" not in EQUIPE_JURIDICA


def test_require_roles_exact_nao_promove_papel_fora_da_allowlist():
    checker = require_roles_exact(["estagiario"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(checker(_u(UserRole.financeiro)))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", PAPEIS_DA_EQUIPE)
def test_requer_equipe_juridica_passa_equipe(role):
    requer_equipe_juridica(_u(role))


@pytest.mark.parametrize("role", PAPEIS_FORA_DA_EQUIPE)
def test_requer_equipe_juridica_barra_fora_da_equipe(role):
    with pytest.raises(HTTPException) as exc:
        requer_equipe_juridica(_u(role))
    assert exc.value.status_code == 403


# ── peca_geracao.py — GET /pecas/meta e POST /pecas/gerar (endpoint real) ────

def _client_pecas(role: UserRole) -> TestClient:
    from app.routers import peca_geracao as peca_router
    app = FastAPI()
    app.include_router(peca_router.router)
    app.dependency_overrides[get_current_user] = lambda: _u(role)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_pecas_gerar_financeiro_403():
    client = _client_pecas(UserRole.financeiro)
    body = {
        "tipo_peca": "peticao_inicial",
        "area_direito": "civel",
        "descricao_fatos": "x" * 60,
        "pedidos": "y" * 15,
    }
    r = client.post("/pecas/gerar", json=body)
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("role", [UserRole.secretaria, UserRole.cliente_externo])
def test_pecas_gerar_fora_da_equipe_403(role):
    client = _client_pecas(role)
    body = {
        "tipo_peca": "peticao_inicial",
        "area_direito": "civel",
        "descricao_fatos": "x" * 60,
        "pedidos": "y" * 15,
    }
    r = client.post("/pecas/gerar", json=body)
    assert r.status_code == 403, r.text


def test_pecas_meta_financeiro_403():
    client = _client_pecas(UserRole.financeiro)
    r = client.get("/pecas/meta")
    assert r.status_code == 403, r.text


def test_pecas_meta_estagiario_passa():
    client = _client_pecas(UserRole.estagiario)
    r = client.get("/pecas/meta")
    assert r.status_code == 200, r.text


async def test_pecas_deep_research_financeiro_403():
    from app.routers import peca_geracao as peca_router
    req = peca_router.DeepResearchRequest(tese="x" * 15, fatos="y" * 25)
    with pytest.raises(HTTPException) as exc:
        await peca_router.deep_research_juridica(req=req, db=None, cu=_u(UserRole.financeiro))
    assert exc.value.status_code == 403


def _req_demonstrativo(**over):
    from app.routers import peca_geracao as peca_router
    from app.routers.ramos import VERSAO_REGRA_ATUAL

    base = dict(
        titulo="Demonstrativo teste",
        ferramenta="/penal/ferramentas/dosimetria",
        fontes=["CP art. 59"],
        vigencia_regra="desde 1940-12-07",
        versao_regra=VERSAO_REGRA_ATUAL,
    )
    base.update(over)
    return peca_router.DemonstrativoRequest(**base)


async def test_pecas_demonstrativo_financeiro_403(monkeypatch):
    from app.routers import peca_geracao as peca_router
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED=True),
    )
    with pytest.raises(HTTPException) as exc:
        await peca_router.gerar_demonstrativo(
            req=_req_demonstrativo(), db=None, cu=_u(UserRole.financeiro))
    assert exc.value.status_code == 403
    assert exc.value.detail == "Acesso negado"


async def test_demonstrativo_financeiro_nao_descobre_estado_de_homologacao():
    from app.routers import peca_geracao as peca_router

    with pytest.raises(HTTPException) as exc:
        await peca_router.gerar_demonstrativo(
            req=_req_demonstrativo(titulo="Dosimetria"), db=None,
            cu=_u(UserRole.financeiro))
    assert exc.value.status_code == 403
    assert exc.value.detail == "Acesso negado"


async def test_demonstrativo_equipe_ainda_ve_motivo_da_nao_homologacao():
    from app.routers import peca_geracao as peca_router

    with pytest.raises(HTTPException) as exc:
        await peca_router.gerar_demonstrativo(
            req=_req_demonstrativo(titulo="Dosimetria"), db=None,
            cu=_u(UserRole.advogado))
    assert exc.value.status_code == 422
    assert exc.value.detail["codigo"] == "ferramenta_nao_homologada"


# ── bank_analysis.py — Issue #772: saídas jurídicas laterais ─────────────────

async def test_bank_analysis_gerar_peca_financeiro_403_antes_do_db():
    from app.routers import bank_analysis as bank_router

    with pytest.raises(HTTPException) as exc:
        await bank_router.gerar_peca(
            analysis_id="analysis-1", payload=None, db=None,
            cu=_u(UserRole.financeiro),
        )
    assert exc.value.status_code == 403
    assert "equipe jurídica" in str(exc.value.detail).lower()


async def test_bank_analysis_documento_juridico_financeiro_403_antes_do_db():
    from app.routers import bank_analysis as bank_router

    with pytest.raises(HTTPException) as exc:
        await bank_router.documento(
            analysis_id="analysis-1", payload={"tipo": "peticao"}, db=None,
            cu=_u(UserRole.financeiro),
        )
    assert exc.value.status_code == 403
    assert "equipe jurídica" in str(exc.value.detail).lower()


def test_bank_analysis_nao_usa_mais_piso_hierarquico_para_gerar_peca():
    fonte = (_ROUTERS / "bank_analysis.py").read_text(encoding="utf-8")
    assert "requer_equipe_juridica" in fonte
    tree = ast.parse(fonte)
    gerar = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "gerar_peca"
    )
    trecho = ast.get_source_segment(fonte, gerar) or ""
    assert "ROLE_LEVEL" not in trecho
    assert "requer_equipe_juridica" in trecho


# ── provas.py — GET /provas/matriz ────────────────────────────────────────────

async def test_provas_matriz_financeiro_403():
    from app.routers import provas as provas_router
    with pytest.raises(HTTPException) as exc:
        await provas_router.matriz_provas_referencia(
            case_id="case-1", area=None, pedidos=None, db=None, cu=_u(UserRole.financeiro),
        )
    assert exc.value.status_code == 403


# ── novos_modulos.py — GET /due-diligence/templates ───────────────────────────

async def test_novos_modulos_due_diligence_financeiro_403():
    from app.routers import novos_modulos as nm_router
    with pytest.raises(HTTPException) as exc:
        await nm_router.listar_templates(dd_type=None, db=None, cu=_u(UserRole.financeiro))
    assert exc.value.status_code == 403


# ── ficha_triagem.py — _exigir_piso (usado em toda rota de /triagem/ficha) ───

def test_ficha_triagem_exigir_piso_financeiro_403():
    from app.routers import ficha_triagem as ficha_router
    with pytest.raises(HTTPException) as exc:
        ficha_router._exigir_piso(_u(UserRole.financeiro))
    assert exc.value.status_code == 403


def test_ficha_triagem_exigir_piso_estagiario_passa():
    from app.routers import ficha_triagem as ficha_router
    ficha_router._exigir_piso(_u(UserRole.estagiario))


# ── jurimetria / memória institucional ────────────────────────────────────────

def test_jurimetria_consolidado_req_staff_financeiro_403():
    from app.routers.jurimetria import _req_staff
    with pytest.raises(HTTPException) as exc:
        _req_staff(_u(UserRole.financeiro))
    assert exc.value.status_code == 403


def test_jurimetria_consolidado_req_staff_estagiario_passa():
    from app.routers.jurimetria import _req_staff
    assert _req_staff(_u(UserRole.estagiario)).role == UserRole.estagiario


def test_memoria_institucional_req_staff_financeiro_403():
    from app.routers.memoria_institucional import _req_staff
    with pytest.raises(HTTPException) as exc:
        _req_staff(_u(UserRole.financeiro))
    assert exc.value.status_code == 403


def test_memoria_institucional_req_staff_estagiario_passa():
    from app.routers.memoria_institucional import _req_staff
    assert _req_staff(_u(UserRole.estagiario)).role == UserRole.estagiario


_HELPERS_BOOL = [
    ("app.routers.dossie_estrategico", "_pode_ver"),
    ("app.routers.advogado_estilo", "_pode_usar_estilo"),
    ("app.routers.teses", "_is_staff"),
    ("app.routers.jurisprudencia_interna", "_is_staff"),
    ("app.routers.jurisprudencia_externa", "_is_staff"),
    ("app.routers.precedentes_jurisprudencia", "_is_staff"),
    ("app.routers.jurimetria", "_is_staff"),
    ("app.routers.consumidor_monitor", "_is_staff"),
]


@pytest.mark.parametrize("modulo,funcao", _HELPERS_BOOL)
def test_helper_bool_barra_financeiro(modulo, funcao):
    import importlib
    mod = importlib.import_module(modulo)
    helper = getattr(mod, funcao)
    assert helper(_u(UserRole.financeiro)) is False, (
        f"{modulo}.{funcao} deixa financeiro passar — allowlist da Issue #694 quebrada"
    )


@pytest.mark.parametrize("modulo,funcao", _HELPERS_BOOL)
def test_helper_bool_passa_estagiario(modulo, funcao):
    import importlib
    mod = importlib.import_module(modulo)
    helper = getattr(mod, funcao)
    assert helper(_u(UserRole.estagiario)) is True, (
        f"{modulo}.{funcao} passou a barrar estagiario — gate afrouxado ao contrário"
    )


@pytest.mark.parametrize("modulo,funcao", _HELPERS_BOOL)
def test_helper_bool_barra_secretaria_e_cliente_externo(modulo, funcao):
    import importlib
    mod = importlib.import_module(modulo)
    helper = getattr(mod, funcao)
    assert helper(_u(UserRole.secretaria)) is False
    assert helper(_u(UserRole.cliente_externo)) is False


# ── Teste de VARREDURA (não enumeração manual) ────────────────────────────────
# Todos os gates jurídicos conhecidos da Issue #694 já saíram do grandfather.
# `users.py::obter_avatar` não é superfície jurídica e permanece até migrar para
# uma política semântica própria de staff em frente separada.
_ROUTERS = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers"
_PADRAO_PISO_ESTAGIARIO = re.compile(
    r"""ROLE_LEVEL\s*(?:
        \[\s*["']estagiario["']\s*\]
        |\.get\(\s*["']estagiario["']\s*(?:,[^)]*)?\)
    )""",
    re.VERBOSE,
)
_GRANDFATHER_ISSUE_694: dict[str, frozenset[str]] = {
    "users.py": frozenset({"obter_avatar"}),
}


def _funcao_que_contem(tree: ast.Module, linha: int) -> str:
    melhor, melhor_ini = "<módulo>", -1
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fim = getattr(node, "end_lineno", None) or node.lineno
        if node.lineno <= linha <= fim and node.lineno > melhor_ini:
            melhor, melhor_ini = node.name, node.lineno
    return melhor


def test_nenhum_router_juridico_novo_usa_piso_hierarquico_estagiario():
    infratores = []
    baseline_desatualizado = []
    for arq in sorted(_ROUTERS.rglob("*.py")):
        nome = arq.relative_to(_ROUTERS).as_posix()
        texto = arq.read_text(encoding="utf-8")
        if not _PADRAO_PISO_ESTAGIARIO.search(texto):
            funcoes_encontradas: set[str] = set()
        else:
            tree = ast.parse(texto)
            funcoes_encontradas = {
                _funcao_que_contem(tree, texto[: m.start()].count("\n") + 1)
                for m in _PADRAO_PISO_ESTAGIARIO.finditer(texto)
            }
        funcoes_conhecidas = _GRANDFATHER_ISSUE_694.get(nome, frozenset())
        for fn in sorted(funcoes_encontradas - funcoes_conhecidas):
            infratores.append(f"{nome}::{fn}")
        for fn in sorted(funcoes_conhecidas - funcoes_encontradas):
            baseline_desatualizado.append(f"{nome}::{fn}")
    assert not infratores, (
        "Gate hierárquico com piso ROLE_LEVEL['estagiario'] em router — isso "
        "libera 'financeiro' para ato/acervo jurídico. Use "
        "EQUIPE_JURIDICA/requer_equipe_juridica:\n  " + "\n  ".join(infratores)
    )
    assert not baseline_desatualizado, (
        "Ocorrência grandfatherizada da Issue #694 não existe mais nessa função; "
        "atualize _GRANDFATHER_ISSUE_694:\n  " + "\n  ".join(baseline_desatualizado)
    )


def test_grandfather_nao_cobre_arquivos_corrigidos():
    arquivos_corrigidos = {
        "peca_geracao.py", "dossie_estrategico.py", "provas.py",
        "advogado_estilo.py", "teses.py", "jurisprudencia_interna.py",
        "jurisprudencia_externa.py", "precedentes_jurisprudencia.py",
        "jurimetria.py", "memoria_institucional.py", "consumidor_monitor.py",
        "ficha_triagem.py", "novos_modulos.py", "bank_analysis.py",
        "entrada_universal.py", "checklists.py", "prompts_juridicos.py",
    }
    assert arquivos_corrigidos.isdisjoint(_GRANDFATHER_ISSUE_694)


# ── Os gates compartilhados só valem chamados no CORPO ────────────────────────
_GATES_DE_CORPO = ("requer_equipe_juridica", "requer_advogado")


def _apelidos_de_gate(tree: ast.Module) -> dict[str, str]:
    apelidos = {g: g for g in _GATES_DE_CORPO}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for a in node.names:
            if a.name in _GATES_DE_CORPO and a.asname:
                apelidos[a.asname] = a.name
    return apelidos


def _nome_de(no: ast.expr) -> str | None:
    if isinstance(no, ast.Name):
        return no.id
    if isinstance(no, ast.Attribute):
        return no.attr
    return None


def test_gates_compartilhados_nunca_usados_como_depends():
    infratores = []
    for arq in sorted(_ROUTERS.rglob("*.py")):
        nome = arq.relative_to(_ROUTERS).as_posix()
        texto = arq.read_text(encoding="utf-8")
        if not any(g in texto for g in _GATES_DE_CORPO):
            continue
        tree = ast.parse(texto)
        apelidos = _apelidos_de_gate(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _nome_de(node.func) == "Depends"):
                continue
            alvos = list(node.args) + [
                kw.value for kw in node.keywords if kw.arg == "dependency"
            ]
            if not alvos:
                continue
            local = _nome_de(alvos[0])
            nome_gate = apelidos.get(local)
            if nome_gate in _GATES_DE_CORPO:
                infratores.append(
                    f"{nome}::{_funcao_que_contem(tree, node.lineno)} -> Depends({local})"
                )
    assert not infratores, (
        "Gate compartilhado de app.core.security usado como Depends(). O FastAPI "
        "aceita isso em silêncio e transforma `cu`/`detail` em query params. "
        "Chame no CORPO do handler:\n  " + "\n  ".join(infratores)
    )
