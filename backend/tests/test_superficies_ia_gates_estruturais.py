"""Onda 4.2 — Invariante estrutural das superfícies geradoras de conteúdo jurídico.

Objetivo (plano mestre, seção 4.2): uma rota nova que produza conteúdo jurídico
via Núcleo Único de IA deve quebrar o CI se nascer sem os gates canônicos.

Versão 2 — corrige os três achados P1 da review da #1902:

1. DESCOBERTA POR ENDPOINT (antes: varredura de módulo inteiro via
   `isinstance(route, APIRoute)` + marker anywhere-in-module — o que
   subnotificava: o registro explícito envolve as rotas em
   `_EffectiveRouteContext`, não-APIRoute; e sinalizava demais: DELETE de caso
   herdava a marca de IA do próprio módulo). Agora cada endpoint é avaliado
   pelo PRÓPRIO caminho de execução: BFS a partir da fonte da função, com
   resolução de nomes no módulo de CADA função alcançada (globals, atributos
   de objetos-módulo e imports locais no corpo), até 3 saltos — cobrindo o
   padrão canônico router → serviço → núcleo (ex.: routers/checklists.py →
   services/checklist_ia.py → ai_gateway.chat). Terminal: a própria função
   `chat`/`transcrever_audio` de app.services.ai_gateway (cobre alias de
   import tipo `chat as gw_chat`). Marcadores geradores são de CHAMADA
   (`ai_gateway.chat(`), nunca de mero import — readiness/health que só
   sondam status de IA não são superfície geradora.

2. CASE_ID EM MODELOS DE CORPO: a detecção de caso-sensibilidade inspeciona
   path, assinatura e — novo — campos de modelos Pydantic do corpo,
   incluindo aninhamento via `model_fields`/`__args__` (ex.:
   `AnalisarCasoRequest.case_id` recebido por `analisar(req, ...)`).

3. OWNERSHIP POR ENDPOINT (antes: "o módulo contém algum marker de ownership
   em qualquer lugar" — um endpoint novo de case_id herdava o gate de outro
   handler). Agora a Regra C exige marker de ownership no caminho de execução
   do PRÓPRIO endpoint (mesma BFS, com `_filtro_visibilidade` incluído como
   gate canônico de escopo LGPD/RBAC de cases).

Regra A (autenticação) permanece: toda rota de superfície de IA precisa de
`get_current_user` na árvore de dependências da rota.

Combinado com test_rotas_registro_explicito.py (toda rota nova exige entrada
justada no registro explícito), test_agentes_invariantes.py (agentes
normativos exigem fonte e citação), test_ai_gateway_barreira.py (sanitização
antes de provider externo) e test_ai_idor_case_id_gates.py (gates por endpoint
conhecido), este arquivo fecha o ciclo da invariante global de IA.
"""
from __future__ import annotations

import inspect
import re
import sys
from functools import lru_cache

from pydantic import BaseModel

# Chamadas GERADORAS de conteúdo (nunca meros imports — readiness de IA não é
# superfície geradora; e nunca bare "ai_gateway", que pega qualquer menção).
MARKERS_GERADORES = (
    "ai_gateway.chat(",
    "ai_gateway.transcrever_audio(",
    "ai_gateway.gerar_",
    "_gateway_json(",
    "SingleAICore(",
    "single_ai_core.chat(",
)

# Gates canônicos de ownership/sigilo (fonte: AGENTS.md L67-73 e gates
# vigentes em routers/services). `_filtro_visibilidade` é o escopo LGPD/RBAC
# canônico de cases (advogado_responsavel_id/advogado_auxiliar_id dentro).
MARKERS_OWNERSHIP = (
    "verificar_acesso_caso",
    "advogado_responsavel_id",
    "advogado_auxiliar_id",
    "verificar_acesso_cliente",
    "cliente_id_visivel",
    "_preparar_caso",
    "_get_case(",
    "_filtro_visibilidade",
    "AILog.user_id == cu.id",
)

_RESERVADAS = {
    "if", "for", "while", "return", "with", "try", "except", "finally",
    "def", "class", "lambda", "await", "async", "yield", "raise", "not",
    "and", "or", "in", "is", "print", "len", "str", "int", "bool", "float",
    "dict", "list", "set", "tuple", "super", "isinstance", "getattr",
    "setattr", "hasattr", "type", "sorted", "any", "all", "enumerate",
    "range", "zip", "open", "repr", "format", "min", "max", "sum", "abs",
}

_GATEWAY_MOD = "app.services.ai_gateway"
_GERADORES_TERMINAIS = {"chat", "transcrever_audio"}


@lru_cache(maxsize=None)
def _fonte_funcao(fn) -> str:
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return ""


def _bfs_markers(endpoint, markers, max_nos: int = 128) -> bool:
    """Há algum marker no caminho de execução do endpoint?

    BFS determinística e cotada: fonte própria → funções chamadas, resolvidas
    no `__module__` de CADA função alcançada (globals do módulo dela, atributos
    de objetos-módulo e imports `from app.x import y` feitos no próprio corpo),
    até 3 saltos. Terminal: as funções geradoras canônicas do gateway (cobre
    alias de import `chat as gw_chat`). Subnotificar aqui = rota insegura fora
    da invariante; sinalizar demais = CRUD comum vira falso IA (por isso a
    varredura é por endpoint, não por módulo).
    """
    vistos_ids: set[int] = set()
    marcado = False
    profund = {id(endpoint): 0}
    ordem = [endpoint]

    def expand(fn) -> None:
        nonlocal marcado
        fid = id(fn)
        if fid in vistos_ids:
            return
        vistos_ids.add(fid)
        # Terminal: chegou ao gerador canônico do gateway (alias gw_chat etc.)
        if (getattr(fn, "__module__", "") == _GATEWAY_MOD
                and getattr(fn, "__name__", "") in _GERADORES_TERMINAIS):
            marcado = True
            return
        src = _fonte_funcao(fn)
        if not src:
            return
        if any(mk in src for mk in markers):
            marcado = True
            return
        if len(vistos_ids) > max_nos:
            return
        fmod = sys.modules.get(getattr(fn, "__module__", None))
        nomes = {n for n in re.findall(r"\b([a-zA-Z_]\w*)\s*\(", src)
                 if n not in _RESERVADAS}
        for nome in nomes:
            obj = getattr(fmod, nome, None) if fmod else None
            if obj is not None and callable(obj) and id(obj) not in profund:
                profund[id(obj)] = profund[fid] + 1
                if profund[id(obj)] <= 3:
                    ordem.append(obj)
        for base, attr in re.findall(r"\b([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\s*\(", src):
            if base in _RESERVADAS:
                continue
            obj_base = getattr(fmod, base, None) if fmod else None
            sub = getattr(obj_base, attr, None) if obj_base is not None else None
            if (sub is not None and callable(sub) and not inspect.ismodule(sub)
                    and id(sub) not in profund):
                profund[id(sub)] = profund[fid] + 1
                if profund[id(sub)] <= 3:
                    ordem.append(sub)
        # imports locais no corpo: `from app.x.y import a, b` (por linha:
        # captura gulosa de [\w\s,]+ engolia o corpo da função junto)
        for mbase, mnomes in re.findall(
                r"from\s+(app\.[\w\.]+)\s+import\s+([^\n(]+)", src):
            alvo = sys.modules.get(mbase)
            if alvo is None:
                continue
            for mn in (x.strip().split(" as ")[0].strip()
                       for x in mnomes.split(",")):
                if not re.fullmatch(r"[a-zA-Z_]\w*", mn or ""):
                    continue
                sub = getattr(alvo, mn, None)
                if (sub is not None and callable(sub) and not inspect.ismodule(sub)
                        and id(sub) not in profund):
                    profund[id(sub)] = profund[fid] + 1
                    if profund[id(sub)] <= 3:
                        ordem.append(sub)

    while ordem:
        expand(ordem.pop(0))
        if marcado:
            return True
    return marcado


def _aceita_case(endpoint, path: str) -> bool:
    """case_id no path, na assinatura OU em campos de modelos Pydantic do corpo
    (incluindo aninhamento) — achado P1: `AnalisarCasoRequest.case_id`."""
    if "case_id" in path:
        return True
    try:
        # eval_str: com `from __future__ import annotations` (PEP 563) a
        # anotação chega como STRING — sem eval, model_fields nunca é visto
        sig = inspect.signature(endpoint, eval_str=True)
    except (TypeError, ValueError, NameError):
        try:
            sig = inspect.signature(endpoint)
        except (TypeError, ValueError):
            return False
    if "case_id" in sig.parameters:
        return True
    fila: list = []
    vistos: set[int] = set()
    passos = 0
    for p in sig.parameters.values():
        if p.annotation is not inspect.Parameter.empty:
            fila.append(p.annotation)
    while fila and passos < 60:
        ann = fila.pop(0)
        passos += 1
        if id(ann) in vistos:
            continue
        vistos.add(id(ann))
        fields = getattr(ann, "model_fields", None)
        if fields:
            if "case_id" in fields:
                return True
            fila.extend(f.annotation for f in fields.values()
                        if f.annotation is not None)
        fila.extend(a for a in (getattr(ann, "__args__", ()) or ())
                    if a is not None)
    return False


def _deps_nomes(route) -> set[str]:
    out: set[str] = set()

    def flat(dep, d: int = 0) -> None:
        if dep is None or d > 6:
            return
        call = getattr(dep, "call", None)
        if call is not None:
            out.add(getattr(call, "__name__", type(call).__name__))
        for sub in getattr(dep, "dependencies", []) or []:
            flat(sub, d + 1)

    flat(getattr(route, "dependant", None))
    return out


def _rotas_com_endpoint(app):
    """Rotas efetivas por duck-typing. O registro explícito (§4.1) envolve as
    rotas em `_EffectiveRouteContext`, que NÃO é APIRoute — `isinstance` perde
    a totalidade das rotas reais (achado raiz da v1). Padrão canônico já usado
    por test_rotas_registro_explicito.py."""
    for r in app.routes:
        ep = getattr(r, "endpoint", None)
        if ep is not None and getattr(r, "dependant", None) is not None:
            yield r, ep


def test_invariante_superficies_ia():
    from app.main import app

    superficies: list[tuple[str, str, object, object]] = []
    for r, ep in _rotas_com_endpoint(app):
        if not _bfs_markers(ep, MARKERS_GERADORES):
            continue
        path = getattr(r, "path", "?")
        for metodo in sorted(getattr(r, "methods", None) or {"GET"}):
            if metodo in ("HEAD", "OPTIONS"):
                continue
            superficies.append((metodo, path, r, ep))

    # A descoberta automática não pode regredir a zero nem perder os routers
    # canônicos de IA. Hoje: 58 superfícies em dezenas de módulos.
    assert len(superficies) >= 20, (
        "invariante de IA perdeu a visibilidade da superfície "
        f"(encontradas {len(superficies)}); revise MARKERS_GERADORES/_bfs_markers"
    )
    modulos = {getattr(ep, "__module__", "") for _, _, _, ep in superficies}
    for canonico in ("app.routers.ai", "app.routers.ai_core"):
        assert canonico in modulos, (
            f"descoberta perdeu o router canônico {canonico}; "
            "a subnotificação esconde rotas de IA da invariante"
        )

    sem_auth: list[str] = []
    com_case_sem_gate: list[str] = []
    n_case = 0

    # Regra A — autenticação obrigatória em TODA rota geradora de IA.
    for metodo, path, r, _ep in superficies:
        if "get_current_user" not in _deps_nomes(r):
            sem_auth.append(f"{metodo} {path}")

    # Regra C — endpoint case-bearing exige gate de ownership NO PRÓPRIO
    # caminho de execução (não "em algum lugar do módulo").
    for metodo, path, _r, ep in superficies:
        if _aceita_case(ep, path):
            n_case += 1
            if not _bfs_markers(ep, MARKERS_OWNERSHIP):
                com_case_sem_gate.append(
                    f"{metodo} {path} "
                    f"({getattr(ep, '__module__', '?')}."
                    f"{getattr(ep, '__name__', '?')})"
                )

    assert n_case >= 5, (
        "descoberta de case-bearing regrediu "
        f"({n_case} rotas); revise _aceita_case"
    )
    assert not sem_auth, (
        "rotas de superfície de IA sem get_current_user: " + ", ".join(sem_auth)
    )
    assert not com_case_sem_gate, (
        "endpoints de IA com case_id sem gate canônico de ownership no próprio "
        "caminho de execução: " + ", ".join(com_case_sem_gate)
    )


# ── Fixtures sintéticas do motor (nível de módulo: o BFS resolve globals,
# como num router real; locais de closure não são visíveis — por desenho) ──


def _st_servico_que_gera():
    from app.services.ai_gateway import chat as gw_alias

    return gw_alias


def _st_endpoint_delegado():
    return _st_servico_que_gera()


def _st_endpoint_direto():
    from app.services.ai_gateway import chat

    return chat(None, [])


def _st_endpoint_case_sem_gate(case_id: str):
    return None


def _st_endpoint_com_gate(case_id: str, db=None, cu=None):
    from app.core.ownership import verificar_acesso_caso

    return verificar_acesso_caso(db, cu, case_id)


class _StReqAninhado(BaseModel):
    case_id: str | None = None


class _StReqCorpo(BaseModel):
    aninhado: _StReqAninhado | None = None


def _st_endpoint_body_model(req: _StReqCorpo):
    return req


def test_motor_descoberta_continua_vivo():
    """Auto-teste do motor: se alguém silenciar o BFS (p. ex., trocar markers
    por nomes que não existem), ESTE teste quebra — a invariante não morre em
    silêncio por um refactor futuro."""
    # 1) Delegação com alias de import do gateway TEM de ser descoberta…
    assert _bfs_markers(_st_endpoint_delegado, MARKERS_GERADORES), (
        "motor perdeu a delegação endpoint→serviço→gateway (alias de import)"
    )

    # 2) …chamada direta ao gateway também…
    assert _bfs_markers(_st_endpoint_direto, MARKERS_GERADORES), (
        "motor perdeu chamada direta ao gateway"
    )

    # 3) …e endpoint case-bearing SEM gate TEM de ser flagrado…
    assert _aceita_case(_st_endpoint_case_sem_gate, "/x/{case_id}")
    assert not _bfs_markers(_st_endpoint_case_sem_gate, MARKERS_OWNERSHIP), (
        "Regra C não sabe mais detectar ausência de gate — invariante vazada"
    )

    # 4) …e COM gate canônico no próprio corpo TEM de passar.
    assert _bfs_markers(_st_endpoint_com_gate, MARKERS_OWNERSHIP), (
        "motor deixou de reconhecer verificar_acesso_caso como gate canônico"
    )

    # 5) case_id escondido em modelo Pydantic de corpo TEM de ser detectado.
    assert _aceita_case(_st_endpoint_body_model, "/x"), (
        "motor não enxerga case_id em modelo de corpo (achado P1 da review)"
    )
