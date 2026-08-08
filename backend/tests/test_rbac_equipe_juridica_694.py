# ── tests/test_rbac_equipe_juridica_694.py ────────────────────────────────────
# Issue #694 — 15 gates de RBAC na superfície jurídica usavam piso hierárquico
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
# Por isso require_roles(_EQUIPE) continuaria deixando financeiro passar
# (nível 4 >= min(_EQUIPE) = nível de estagiario = 3).
#
# Este arquivo cobre os dois critérios de aceite testáveis da Issue:
#   1) por papel, financeiro recebe 403 em POST /pecas/gerar e nas demais
#      rotas de ato jurídico dos 15 arquivos corrigidos;
#   2) uma varredura (não enumeração manual) que reprova qualquer gate NOVO
#      escrito como piso hierárquico com estagiario em backend/app/routers/.
from __future__ import annotations

import ast
import pathlib
import re

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import EQUIPE_JURIDICA, ROLE_LEVEL, get_current_user, requer_equipe_juridica
from app.models.user import User, UserRole


def _u(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role, full_name="Fulano de Teste")


# Papéis que a Issue #694 exige barrar (financeiro é o achado central; os
# outros dois já eram barrados antes — travados aqui para não regredir).
PAPEIS_FORA_DA_EQUIPE = [UserRole.financeiro, UserRole.secretaria, UserRole.cliente_externo]

PAPEIS_DA_EQUIPE = [
    UserRole.superadmin, UserRole.admin, UserRole.socio,
    UserRole.advogado, UserRole.advogado_auxiliar, UserRole.estagiario,
]


# ── Gate compartilhado (fonte única) ──────────────────────────────────────────

def test_financeiro_tem_nivel_hierarquico_acima_de_estagiario():
    # Documenta a causa-raiz da Issue #694: um piso hierárquico com estagiario
    # SEMPRE libera financeiro, porque ROLE_LEVEL o posiciona acima.
    assert ROLE_LEVEL["financeiro"] > ROLE_LEVEL["estagiario"]
    assert "financeiro" not in EQUIPE_JURIDICA


@pytest.mark.parametrize("role", PAPEIS_DA_EQUIPE)
def test_requer_equipe_juridica_passa_equipe(role):
    requer_equipe_juridica(_u(role))  # não levanta


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
    # Critério de aceite: financeiro recebe 403 em POST /pecas/gerar — o
    # gate mais grave da Issue (único gate de papel do endpoint).
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
    # Regressão: a allowlist não pode ter afrouxado nada para quem já tinha
    # acesso — estagiario continua vendo o catálogo.
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
    """Corpo VÁLIDO de demonstrativo. A Issue #702 (PR #705) tornou `ferramenta`,
    `fontes`, `vigencia_regra` e `versao_regra` obrigatórios e não-brancos — sem
    eles o Pydantic reprova na construção e o teste nunca chega ao gate que quer
    exercitar. `versao_regra` é lida de ramos para não envelhecer no arquivo."""
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
    # gerar_demonstrativo tem QUATRO gates de conteúdo; o de papel agora vem
    # ANTES de todos. Habilita a flag geral para provar que o 403 vem do papel,
    # não da trava desligada por padrão.
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
    # Review do CodeRabbit no PR #706 (Segurança, Major). O gate de papel era o
    # ÚLTIMO da função: `financeiro` com ferramenta NÃO homologada recebia 422
    # com o MOTIVO da não homologação — estado interno vazando para quem não
    # pode nem chamar a rota. Agora a autorização vem primeiro: 403 seco.
    #
    # Prova por negação: se alguém devolver o gate para o fim da função, o
    # status vira 422 e este teste reprova.
    from app.routers import peca_geracao as peca_router

    with pytest.raises(HTTPException) as exc:
        await peca_router.gerar_demonstrativo(
            req=_req_demonstrativo(titulo="Dosimetria"), db=None,
            cu=_u(UserRole.financeiro))
    assert exc.value.status_code == 403, (
        "financeiro recebeu %s — o gate de papel voltou para depois da matriz de "
        "homologação e está vazando o motivo da não homologação" % exc.value.status_code
    )
    assert exc.value.detail == "Acesso negado"


async def test_demonstrativo_equipe_ainda_ve_motivo_da_nao_homologacao():
    # Contraprova: para quem PERTENCE à equipe, o 422 com o diagnóstico
    # específico continua chegando — mover a autorização para o topo não pode
    # ter engolido a mensagem útil ao advogado.
    from app.routers import peca_geracao as peca_router

    with pytest.raises(HTTPException) as exc:
        await peca_router.gerar_demonstrativo(
            req=_req_demonstrativo(titulo="Dosimetria"), db=None,
            cu=_u(UserRole.advogado))
    assert exc.value.status_code == 422
    assert exc.value.detail["codigo"] == "ferramenta_nao_homologada"


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
    ficha_router._exigir_piso(_u(UserRole.estagiario))  # não levanta


# ── jurimetria_extra.py / memoria_institucional.py — dependencies _req_staff ─

def test_jurimetria_extra_req_staff_financeiro_403():
    from app.routers.jurimetria_extra import _req_staff
    with pytest.raises(HTTPException) as exc:
        _req_staff(_u(UserRole.financeiro))
    assert exc.value.status_code == 403


def test_jurimetria_extra_req_staff_estagiario_passa():
    from app.routers.jurimetria_extra import _req_staff
    assert _req_staff(_u(UserRole.estagiario)).role == UserRole.estagiario


def test_memoria_institucional_req_staff_financeiro_403():
    from app.routers.memoria_institucional import _req_staff
    with pytest.raises(HTTPException) as exc:
        _req_staff(_u(UserRole.financeiro))
    assert exc.value.status_code == 403


def test_memoria_institucional_req_staff_estagiario_passa():
    from app.routers.memoria_institucional import _req_staff
    assert _req_staff(_u(UserRole.estagiario)).role == UserRole.estagiario


# ── Helpers booleanos _is_staff/_pode_ver/_pode_usar_estilo — 9 arquivos ──────
# Cada entrada é (módulo, nome_da_função, atributo_de_papel_no_arg). Todas
# aceitam um único argumento posicional User/objeto com .role e retornam bool.
_HELPERS_BOOL = [
    ("app.routers.dossie_estrategico", "_pode_ver"),
    ("app.routers.advogado_estilo", "_pode_usar_estilo"),
    ("app.routers.teses", "_is_staff"),
    ("app.routers.teses_v4", "_is_staff"),
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
    # Regressão: ninguém que já tinha acesso pode ter perdido.
    import importlib
    mod = importlib.import_module(modulo)
    helper = getattr(mod, funcao)
    assert helper(_u(UserRole.estagiario)) is True, (
        f"{modulo}.{funcao} passou a barrar estagiario — gate afrouxado ao contrário"
    )


@pytest.mark.parametrize("modulo,funcao", _HELPERS_BOOL)
def test_helper_bool_barra_secretaria_e_cliente_externo(modulo, funcao):
    # Nunca mudou: secretaria/cliente_externo já ficavam abaixo do piso.
    import importlib
    mod = importlib.import_module(modulo)
    helper = getattr(mod, funcao)
    assert helper(_u(UserRole.secretaria)) is False
    assert helper(_u(UserRole.cliente_externo)) is False


# ── Teste de VARREDURA (não enumeração manual) ────────────────────────────────
# Reprova qualquer gate NOVO escrito como piso hierárquico com estagiario em
# backend/app/routers/. Mesmo desenho de guarda que test_middleware_auth_
# invariant.py usa para o invariante de auth (regex sobre o código-fonte).
#
# GRANDFATHER: os 7 sítios (6 arquivos) que a Issue #694 também lista mas que
# esta correção NÃO tocou porque pertencem a PRs abertos concorrentes
# (bank_analysis.py, entrada_universal.py, checklists.py, prompts_juridicos.py,
# ai.py, users.py).
#
# Rastreado por OCORRÊNCIA individual (arquivo::função), não por arquivo
# inteiro (review do Codex no PR #706): pular o arquivo inteiro tinha dois
# defeitos — (a) um gate hierárquico NOVO adicionado a um arquivo
# grandfatherizado (ex. um segundo piso em ai.py) não seria pego, porque o
# arquivo inteiro era ignorado; (b) se um PR concorrente corrigisse a
# ocorrência conhecida sem atualizar esta lista, o arquivo ficaria
# permanentemente sem a proteção da varredura, já que continuaria na lista de
# exclusão para sempre.
#
# A âncora é a FUNÇÃO, não o número da linha (ver _GRANDFATHER_ISSUE_694).
# Qualquer ocorrência num arquivo grandfatherizado cuja função NÃO esteja no
# conjunto é violação NOVA (assert `infratores`); e qualquer função listada
# aqui que não tenha mais o padrão falha como baseline desatualizado (assert
# `baseline_desatualizado`), forçando quem corrigiu a remover a entrada em vez
# de deixá-la esquecida.
#
# Limitação aceita: se um mesmo PR remover o piso de uma função E adicionar
# outro na MESMA função, os dois conjuntos continuam iguais e a troca passa.
# Cobrir isso exigiria comparar o corpo da função, não sua identidade — custo
# alto para um caso que o review de diff pega trivialmente.
_ROUTERS = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers"
# rglob + as duas formas de acesso (índice e .get) — review do CodeRabbit no PR
# #706. Hoje não há router em subdiretório nem uso de ROLE_LEVEL.get("estagiario")
# no repositório: a ampliação é PREVENTIVA, não corrige violação existente. Sem
# ela, um gate hierárquico novo escrito em app/routers/<sub>/x.py, ou com .get(),
# passaria pela varredura sem virar `infratores`.
_PADRAO_PISO_ESTAGIARIO = re.compile(
    r"""ROLE_LEVEL\s*(?:
        \[\s*["']estagiario["']\s*\]
        |\.get\(\s*["']estagiario["']\s*(?:,[^)]*)?\)
    )""",
    re.VERBOSE,
)
# Ancorado pela FUNÇÃO que contém a ocorrência, não pelo número da linha.
# A primeira versão desta lista fixava `arquivo:linha` e quebrou o CI do PR
# #706 sem nenhuma mudança de gate: a `main` avançou (PRs #735/#736), o
# `entrada_universal.py` cresceu e as duas ocorrências conhecidas escorregaram
# de 175/258 para 266/356. Número de linha não identifica um gate — identifica
# uma posição no arquivo, que qualquer merge desloca. O nome da função é
# estável sob deslocamento e continua específico o bastante para que uma
# ocorrência NOVA numa função diferente do mesmo arquivo seja pega.
_GRANDFATHER_ISSUE_694: dict[str, frozenset[str]] = {
    "bank_analysis.py": frozenset({"gerar_peca"}),
    "entrada_universal.py": frozenset({"meta", "processar"}),
    "checklists.py": frozenset({"_pode_editar"}),
    "prompts_juridicos.py": frozenset({"listar_prompts"}),
    "ai.py": frozenset({"assistente_estrategico", "visual_law"}),
    "users.py": frozenset({"obter_avatar"}),
}


def _funcao_que_contem(tree: ast.Module, linha: int) -> str:
    """Nome da função MAIS INTERNA que contém `linha` (ou "<módulo>")."""
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
        "libera 'financeiro' (nível 4 > estagiario nível 3) para ato/acervo "
        "jurídico (Issue #694). Use EQUIPE_JURIDICA/requer_equipe_juridica de "
        "app.core.security (allowlist exata) em vez de comparação hierárquica:\n  "
        + "\n  ".join(infratores)
    )
    assert not baseline_desatualizado, (
        "Ocorrência grandfatherizada da Issue #694 (_GRANDFATHER_ISSUE_694) não "
        "existe mais nessa função — ou o PR concorrente que a corrigiu esqueceu "
        "de remover a entrada daqui, ou a função foi renomeada. Atualize "
        "_GRANDFATHER_ISSUE_694 (remova a função, ou o arquivo inteiro se não "
        "sobrar nenhuma):\n  " + "\n  ".join(baseline_desatualizado)
    )


def test_grandfather_nao_cobre_os_15_arquivos_corrigidos():
    # Trava a lista de exceção: nenhum dos 15 arquivos desta Issue pode estar
    # no grandfather (senão o teste acima pararia de proteger o que acabamos
    # de corrigir).
    arquivos_corrigidos = {
        "peca_geracao.py", "dossie_estrategico.py", "provas.py",
        "advogado_estilo.py", "teses.py", "teses_v4.py",
        "jurisprudencia_interna.py", "jurisprudencia_externa.py",
        "precedentes_jurisprudencia.py", "jurimetria.py", "jurimetria_extra.py",
        "memoria_institucional.py", "consumidor_monitor.py", "ficha_triagem.py",
        "novos_modulos.py",
    }
    assert arquivos_corrigidos.isdisjoint(_GRANDFATHER_ISSUE_694)
    assert len(arquivos_corrigidos) == 15


# ── Os gates compartilhados só valem chamados no CORPO ────────────────────────
# `requer_equipe_juridica`/`requer_advogado` recebem `cu` como argumento comum,
# não como dependency. Sob `Depends(...)` o FastAPI monta a rota EM SILÊNCIO e
# trata `cu` e `detail` como query params de string — verificado: a rota vira
# 403 permanente e o cliente escolhe a mensagem de erro pela URL. Anotar `cu`
# NÃO impede (o FastAPI resolve o forward ref mesmo assim); só um teste impede.
_GATES_DE_CORPO = ("requer_equipe_juridica", "requer_advogado")


def _apelidos_de_gate(tree: ast.Module) -> dict[str, str]:
    """Mapeia nome LOCAL -> nome canônico do gate, resolvendo alias de import
    (`from app.core.security import requer_advogado as _req`). Sem isto, trocar
    o nome no import escaparia da varredura."""
    apelidos = {g: g for g in _GATES_DE_CORPO}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for a in node.names:
            if a.name in _GATES_DE_CORPO and a.asname:
                apelidos[a.asname] = a.name
    return apelidos


def _nome_de(no: ast.expr) -> str | None:
    """`x` -> "x"; `mod.x` -> "x" (o atributo final é o que identifica o gate)."""
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
            # `Depends(...)` e `fastapi.Depends(...)` — o atributo final decide.
            if not (isinstance(node, ast.Call) and _nome_de(node.func) == "Depends"):
                continue
            # Alvo por posição OU pelo nomeado `dependency=`.
            alvos = list(node.args) + [
                kw.value for kw in node.keywords if kw.arg == "dependency"
            ]
            if not alvos:
                continue
            # `security.requer_advogado` resolve pelo atributo; alias pelo import.
            local = _nome_de(alvos[0])
            nome_gate = apelidos.get(local)
            if nome_gate in _GATES_DE_CORPO:
                infratores.append(
                    f"{nome}::{_funcao_que_contem(tree, node.lineno)} -> Depends({local})"
                )
    assert not infratores, (
        "Gate compartilhado de app.core.security usado como Depends(). O FastAPI "
        "aceita isso em silêncio e transforma `cu`/`detail` em query params: a "
        "rota passa a responder 403 SEMPRE, com a mensagem de erro escolhida "
        "pelo cliente na URL. Chame no CORPO do handler:\n  "
        + "\n  ".join(infratores)
    )
