"""Paridade entre os formulários do frontend e os handlers das ferramentas.

`frontend/src/pages/ramos/ramosConfig.ts` declara os campos de cada calculadora
das Áreas de Atuação; `app/routers/ramos.py` declara os Query params. Quando os
dois divergem, a ferramenta fica INUTILIZÁVEL — 422 na tela do advogado, muitas
vezes apontando um campo que o formulário nem exibe. Isso já escapou duas vezes:
`tipo=incidente` contra `Literal[..., "incidente_anpd"]`, e `indice_nome`/
`data_base` exigidos pelo backend e ausentes dos formulários de reajuste.

Abordagem: parse textual da config TS (o objeto é literal e regular) comparado
com a introspecção real dos handlers. Fica em pytest, e não em vitest, porque a
fonte da verdade é o backend — só aqui dá para resolver `Literal` e default de
`Query(...)` sem reimplementar FastAPI em TypeScript.

ARMADILHA: `ramos.py` usa `from __future__ import annotations`, então as
anotações chegam como STRING e `get_args()` devolve `()` — o que mascara toda
divergência de Literal e faz um teste ingênuo passar sempre. Por isso usamos
`typing.get_type_hints()` (com `inspect.unwrap`, pois há handlers decorados).
"""
from __future__ import annotations

import inspect
import json
import re
import typing
from pathlib import Path

import pytest
from fastapi import params as fastapi_params

from app.routers import ramos

_CONFIG_TS = (Path(__file__).resolve().parents[2]
              / "frontend/src/pages/ramos/ramosConfig.ts")

# Endpoints fora de ramos.py (outros routers) — paridade não se aplica aqui.
_PREFIXOS_EXTERNOS = ("/analise-bancaria/", "/previdenciario_beneficio/")


# ── Config do frontend ───────────────────────────────────────────────────────
def _bloco_balanceado(texto: str, inicio: int) -> str:
    """Trecho de `texto` a partir do '[' em `inicio` até o ']' que o fecha."""
    profundidade = 0
    for i in range(inicio, len(texto)):
        if texto[i] == "[":
            profundidade += 1
        elif texto[i] == "]":
            profundidade -= 1
            if profundidade == 0:
                return texto[inicio:i + 1]
    raise AssertionError("bloco 'campos: [' sem fechamento na config")


def _parse_config() -> dict[str, list[dict]]:
    """{endpoint: [campo, ...]} lido de ramosConfig.ts.

    Cada ferramenta declara `endpoint: "..."` e, adiante, `campos: [...]`; os
    campos têm `nome`, e opcionalmente `opcoes`, `default` e `mostrarSe`.
    """
    fonte = _CONFIG_TS.read_text(encoding="utf-8")
    ferramentas: dict[str, list[dict]] = {}

    for m in re.finditer(r'endpoint:\s*"([^"]+)"', fonte):
        endpoint = m.group(1)
        prox = fonte.find("campos:", m.end())
        if prox == -1:
            continue
        # `campos` da PRÓPRIA ferramenta: não pode pular para a ferramenta seguinte.
        seguinte = fonte.find("endpoint:", m.end())
        if seguinte != -1 and prox > seguinte:
            ferramentas[endpoint] = []
            continue

        valor = fonte[prox + len("campos:"):].lstrip()
        if valor.startswith("["):
            bloco = _bloco_balanceado(fonte, fonte.index("[", prox))
        else:
            # `campos: _constCompartilhada` — resolve a const declarada no arquivo.
            const = re.match(r"([A-Za-z_$][\w$]*)", valor).group(1)
            decl = re.search(rf"const\s+{re.escape(const)}\s*(?::[^=]+)?=\s*\[", fonte)
            assert decl, f"{endpoint}: const de campos '{const}' não encontrada"
            # decl.end()-1 é o '[' do array — não o de `FerramentaCampo[]` no tipo.
            bloco = _bloco_balanceado(fonte, decl.end() - 1)

        campos: list[dict] = []
        for cm in re.finditer(r'nome:\s*"([^"]+)"', bloco):
            fim = bloco.find('nome:', cm.end())
            trecho = bloco[cm.start(): fim if fim != -1 else len(bloco)]
            opcoes_m = re.search(r"opcoes:\s*(\[[^\]]*\])", trecho)
            default_m = re.search(r'default:\s*("(?:[^"]*)"|[\d.]+|true|false)', trecho)
            campos.append({
                "nome": cm.group(1),
                # o prettier quebra arrays longos e deixa vírgula final: não é JSON.
                "opcoes": (json.loads(re.sub(r",\s*\]", "]", opcoes_m.group(1)))
                           if opcoes_m else None),
                "default": json.loads(default_m.group(1)) if default_m else None,
                "condicional": "mostrarSe:" in trecho,
            })
        ferramentas[endpoint] = campos

    assert len(ferramentas) > 40, (
        f"parse da config falhou: só {len(ferramentas)} ferramentas encontradas"
    )
    return ferramentas


# ── Handlers do backend ──────────────────────────────────────────────────────
def _rotas_ramos() -> dict[str, callable]:
    """{path da ferramenta: handler} a partir das rotas registradas no router."""
    return {
        rota.path: rota.endpoint
        for rota in ramos.router.routes
        if "/ferramentas/" in getattr(rota, "path", "")
    }


def _params_do_handler(handler) -> dict[str, dict]:
    """{param: {obrigatorio, literais}} do handler, com anotações RESOLVIDAS."""
    fn = inspect.unwrap(handler)
    hints = typing.get_type_hints(fn)          # resolve `from __future__ import annotations`
    params: dict[str, dict] = {}

    for p in inspect.signature(fn).parameters.values():
        if p.name in ("db", "cu", "request", "response"):
            continue
        anot = hints.get(p.name)
        # Literal direto ou dentro de Optional[...]
        literais: tuple = typing.get_args(anot) if typing.get_origin(anot) is typing.Literal else ()
        if not literais:
            for arg in typing.get_args(anot):
                if typing.get_origin(arg) is typing.Literal:
                    literais = typing.get_args(arg)
                    break

        default = p.default
        if isinstance(default, fastapi_params.Query):
            # Pydantic v2: Query(...) guarda PydanticUndefined, NÃO Ellipsis —
            # comparar com `...` faz todo param parecer opcional e o teste vira
            # decoração. `is_required()` é a fonte correta.
            obrigatorio = default.is_required()
        else:
            obrigatorio = default is inspect.Parameter.empty

        params[p.name] = {"obrigatorio": obrigatorio, "literais": literais}
    return params


def _pares() -> list[tuple[str, list[dict], dict]]:
    """(endpoint, campos do form, params do handler) das ferramentas de ramos.py."""
    rotas = _rotas_ramos()
    pares = []
    for endpoint, campos in _parse_config().items():
        if endpoint.startswith(_PREFIXOS_EXTERNOS) or endpoint not in rotas:
            continue
        pares.append((endpoint, campos, _params_do_handler(rotas[endpoint])))
    assert len(pares) > 40, f"poucos pares resolvidos ({len(pares)}) — parse quebrou?"
    return pares


_PARES = _pares()
_IDS = [e for e, _, _ in _PARES]


# ── Testes ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("endpoint,campos,params", _PARES, ids=_IDS)
def test_campo_do_formulario_existe_no_handler(endpoint, campos, params):
    """Campo fantasma: o form manda um parâmetro que o handler não conhece."""
    fantasmas = [c["nome"] for c in campos if c["nome"] not in params]
    assert not fantasmas, (
        f"{endpoint}: o formulário envia {fantasmas}, que o handler não aceita. "
        f"Params válidos: {sorted(params)}"
    )


@pytest.mark.parametrize("endpoint,campos,params", _PARES, ids=_IDS)
def test_parametro_obrigatorio_esta_no_formulario(endpoint, campos, params):
    """Obrigatório sem campo na tela = 422 em todo clique em Calcular."""
    nomes = {c["nome"] for c in campos}
    faltando = [p for p, meta in params.items() if meta["obrigatorio"] and p not in nomes]
    assert not faltando, (
        f"{endpoint}: o handler exige {faltando}, mas o formulário não oferece esses "
        f"campos — a ferramenta responde 422 em qualquer uso."
    )


@pytest.mark.parametrize("endpoint,campos,params", _PARES, ids=_IDS)
def test_opcoes_do_select_sao_aceitas_pelo_handler(endpoint, campos, params):
    """Opção de select fora do Literal: o usuário escolhe e recebe 422."""
    for campo in campos:
        literais = params.get(campo["nome"], {}).get("literais") or ()
        if not campo["opcoes"] or not literais:
            continue
        invalidas = [o for o in campo["opcoes"] if o not in literais]
        assert not invalidas, (
            f"{endpoint}, campo '{campo['nome']}': as opções {invalidas} não são "
            f"aceitas pelo handler. Valores válidos: {list(literais)}"
        )


@pytest.mark.parametrize("endpoint,campos,params", _PARES, ids=_IDS)
def test_default_do_formulario_e_aceito_pelo_handler(endpoint, campos, params):
    """Default fora do Literal quebra a ferramenta antes do primeiro clique."""
    for campo in campos:
        literais = params.get(campo["nome"], {}).get("literais") or ()
        if campo["default"] is None or not literais:
            continue
        assert campo["default"] in literais, (
            f"{endpoint}, campo '{campo['nome']}': default {campo['default']!r} não é "
            f"aceito pelo handler. Valores válidos: {list(literais)}"
        )
