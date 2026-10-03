"""Contratos dos diagnósticos históricos, sem stack, credencial ou banco real.

Somente funções selecionadas são carregadas: vários scripts históricos têm
efeitos no import. EJC_SCRIPTS_QA_SOURCE permite repetir os mesmos cenários
contra as fontes anteriores à refatoração, sem revertê-las na árvore compartilhada.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.getenv("EJC_SCRIPTS_QA_SOURCE", str(ROOT)))
_SPEC = importlib.util.spec_from_file_location("ejc_qa_inventory_shared", ROOT / "scripts/inventory/_shared.py")
_shared = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_shared)


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = (
            {"access_token": "fictitious-token"} if payload is None else payload
        )
        self.text = "fictitious response"

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Http:
    def __init__(self, *responses):
        self.responses = iter(responses or [Response()])
        self.calls = []
        self.headers = {}

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return next(self.responses)

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return next(self.responses)


def functions(name, names, **inputs):
    path = Path("scripts/inventory") / name
    tree = ast.parse((SOURCE / path).read_text(encoding="utf-8"))
    selected = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names
    ]
    assert {n.name for n in selected} == set(names)
    # Annotations never import application modules; no module-level code runs.
    future = ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations")], level=0
    )
    module = ast.fix_missing_locations(
        ast.Module(body=[future, *selected], type_ignores=[])
    )
    namespace = {"_shared": _shared, "__file__": str(ROOT / path), **inputs}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("script", ["m05_tenant_tests.py", "m06_clientes_tests.py"])
def test_cpf_sintetico_tem_digitos_verificadores(script):
    ns = functions(script, ["_cpf_valido"], random=random.Random(20261003))
    for _ in range(5):
        raw = ns["_cpf_valido"]()
        digits = [int(c) for c in raw if c.isdigit()]
        assert len(raw) == 14 and len(digits) == 11
        for length in (9, 10):
            remainder = (
                sum(d * w for d, w in zip(digits[:length], range(length + 1, 1, -1)))
                % 11
            )
            assert digits[length] == (0 if remainder < 2 else 11 - remainder)


@pytest.mark.parametrize("script", ["m07_casos_tests.py", "debug_dup_cnj.py"])
def test_cnj_sintetico_tem_modulo_97_valido(script):
    ns = functions(script, ["cnj_valido"], random=random.Random(20261003))
    raw = ns["cnj_valido"]()
    number, rest = raw.split("-")
    dv, year, branch, court, origin = rest.split(".")
    assert int(number + year + branch + court + origin + dv) % 97 == 1


@pytest.mark.parametrize(
    "script,func,mode",
    [
        ("m16_agenda_tarefas_tests.py", "token", "token"),
        ("m17_peças_tests.py", "tok", "token"),
        ("m18_templates_tests.py", "tok", "token"),
        ("m19_estilo_advogado_tests.py", "tok", "token"),
        ("m20_biblioteca_tests.py", "tok", "token"),
        ("m21_ingestao_rag_tests.py", "login", "rag"),
        ("m22_retrieval_acl_tests.py", "login", "rag"),
        ("m09_procuracoes_tests.py", "h", "headers"),
        ("m10_documentos_tests.py", "h", "headers"),
        ("m11_versionamento_tests.py", "_h", "pwd"),
        ("m12_andamentos_tests.py", "_h", "pwd"),
    ],
)
def test_login_repete_rate_limit_e_cacheia_sem_nova_requisicao(
    script, func, mode, monkeypatch
):
    http = Http(Response(429), Response())
    delays, cache = [], {}
    # M16 importa time no corpo. Patch do módulo também cobre esse contrato.
    monkeypatch.setattr("time.sleep", delays.append)
    ns = functions(
        script,
        [func],
        BASE="http://localhost",
        SENHA="fictitious-password",
        PWD="fictitious-password",
        S=http,
        requests=http,
        time=SimpleNamespace(sleep=delays.append),
        TOKENS=cache,
        _TOKENS=cache,
        HEADERS={"Content-Type": "application/json"},
    )
    result = ns[func]("qa@example.invalid")
    assert result == (
        "fictitious-token"
        if mode in ("token", "rag")
        else {
            **({"Content-Type": "application/json"} if mode == "headers" else {}),
            "Authorization": "Bearer fictitious-token",
        }
    )
    assert ns[func]("qa@example.invalid") == result
    assert len(http.calls) == 2
    assert http.calls[0][2]["json"] == {
        "email": "qa@example.invalid",
        "password": "fictitious-password",
    }
    assert (
        delays
        == {"token": [18], "rag": [45], "headers": [18, 45], "pwd": [18, 45]}[mode]
    )


@pytest.mark.parametrize(
    "script,func,attempts",
    [
        ("m20_biblioteca_tests.py", "tok", 4),
        ("m21_ingestao_rag_tests.py", "login", 2),
        ("m11_versionamento_tests.py", "_h", 6),
    ],
)
def test_login_rate_limit_persistente_falha_sem_token(script, func, attempts):
    http = Http(*(Response(429) for _ in range(attempts)))
    cache, delays = {}, []
    ns = functions(
        script,
        [func],
        BASE="http://localhost",
        SENHA="fictitious-password",
        PWD="fictitious-password",
        S=http,
        requests=http,
        TOKENS=cache,
        _TOKENS=cache,
        time=SimpleNamespace(sleep=delays.append),
    )
    with pytest.raises(SystemExit):
        ns[func]("qa@example.invalid")
    assert not cache and len(http.calls) == attempts


@pytest.mark.parametrize(
    "script",
    [
        "m34_honorarios_propostas_tests.py",
        "m35_financeiro_tests.py",
        "m36_timesheet_tests.py",
    ],
)
@pytest.mark.parametrize("token_field", ["access_token", "token", "access"])
def test_authed_alias_cliente_e_campos_de_token(script, token_field):
    http = Http(Response(429), Response(payload={token_field: "fictitious-token"}))
    delays, cache = [], {}
    ns = functions(
        script,
        ["authed"],
        API="http://localhost",
        S=http,
        SENHA="fictitious-password",
        _TOKENS=cache,
        time=SimpleNamespace(sleep=delays.append),
    )
    assert ns["authed"]("cliente_externo") is None
    assert http.calls[-1][2]["json"]["email"] == "ejc_qa_auth_cliente@golocal.ejc"
    assert http.headers["Authorization"] == "Bearer fictitious-token"
    http.headers.clear()
    assert ns["authed"]("cliente_externo") is None
    assert http.headers["Authorization"] == "Bearer fictitious-token"
    assert len(http.calls) == 2 and delays == [18, 45]


@pytest.mark.parametrize(
    "script",
    [
        "m27_chat_juridico_tests.py",
        "m28_case_intelligence_tests.py",
        "m29_dossie_estrategico_tests.py",
        "m30_matriz_teses_tests.py",
    ],
)
def test_authed_credenciais_explicitas_e_falha_registrada(script):
    http, failures, delays = Http(Response(401)), [], []
    ns = functions(
        script,
        ["authed"],
        API="http://localhost",
        S=http,
        _TOKENS={},
        CRED={"socio": ("qa@example.invalid", "fictitious-password")},
        _fail=failures.append,
        sys=sys,
        time=SimpleNamespace(sleep=delays.append),
    )
    with pytest.raises(SystemExit) as exc:
        ns["authed"]("socio")
    assert exc.value.code == 1
    assert failures == ["login socio: HTTP 401"] and delays == [16]
    assert "Authorization" not in http.headers


@pytest.mark.parametrize(
    "script",
    [
        "m34_honorarios_propostas_tests.py",
        "m35_financeiro_tests.py",
        "m36_timesheet_tests.py",
    ],
)
def test_get_preserva_parametros_e_limite_de_retries(script):
    http, delays = Http(Response(429), Response(429), Response(200)), []
    ns = functions(script, ["get"], S=http, time=SimpleNamespace(sleep=delays.append))
    result = ns["get"](
        "http://localhost/api/fees",
        params={"page": 2},
        headers={"X-Test": "fictitious"},
    )
    assert result.status_code == 200 and delays == [12, 12]
    assert len(http.calls) == 3
    for _, _, kwargs in http.calls:
        assert kwargs == {
            "timeout": 20,
            "params": {"page": 2},
            "headers": {"X-Test": "fictitious"},
        }


@pytest.mark.parametrize(
    "script,counts",
    [
        ("m09_procuracoes_tests.py", {"TOTAL": 2, "OK": 1}),
        ("m10_documentos_tests.py", {"TOTAL": 2, "OK": 1}),
        ("m11_versionamento_tests.py", {"total": 2, "ok_total": 1}),
        ("m12_andamentos_tests.py", {"total": 2, "ok_total": 1}),
        ("m15_calendario_tests.py", {"TOTAL": 2, "FALHAS": 1}),
        ("m16_agenda_tarefas_tests.py", {"TOTAL": 2, "FALHAS": 1}),
        ("m17_peças_tests.py", {"TOTAL": 2, "FALHAS": 1}),
        ("m18_templates_tests.py", {"TOTAL": 2, "FALHAS": 1}),
        ("m19_estilo_advogado_tests.py", {"TOTAL": 2, "FALHAS": 1}),
        ("m20_biblioteca_tests.py", {"TOTAL": 2, "FALHAS": 1}),
        ("m21_ingestao_rag_tests.py", {"PASS": 1, "FAIL": 1}),
        ("m22_retrieval_acl_tests.py", {"PASS": 1, "FAIL": 1}),
    ],
)
def test_contadores_e_mensagens_de_resultado(script, counts, capsys):
    ns = functions(script, ["chk"], **dict.fromkeys(counts, 0))
    ns["chk"]("success", True)
    ns["chk"]("failure", False, "fictitious detail")
    assert {key: ns[key] for key in counts} == counts
    output = capsys.readouterr().out
    assert "PASS" in output and "FAIL" in output and "fictitious detail" in output


@pytest.mark.parametrize(
    "script",
    [
        "m28_case_intelligence_tests.py",
        "m29_dossie_estrategico_tests.py",
        "m30_matriz_teses_tests.py",
    ],
)
@pytest.mark.parametrize("envelope", [None, "data", "clientes", "items"])
def test_cliente_id_usa_somente_cliente_qa_e_cache(script, envelope):
    items = [
        {"id": "ignored", "nome": "not QA"},
        {"id": "fictitious-id", "razao_social": "EJC_QA Company"},
    ]
    http = Http(Response(payload=items if envelope is None else {envelope: items}))
    auth, cache = [], [None]
    ns = functions(
        script,
        ["_cliente_id"],
        API="http://localhost",
        S=http,
        _CLIENTE_ID=cache,
        _fail=lambda message: pytest.fail(message),
        authed=auth.append,
    )
    assert ns["_cliente_id"]() == "fictitious-id"
    assert ns["_cliente_id"]() == "fictitious-id"
    assert auth == ["socio"] and len(http.calls) == 1


def test_credencial_ausente_falha_explicitamente(monkeypatch):
    monkeypatch.delenv("EJC_QA_PASSWORD", raising=False)
    ns = functions("m34_honorarios_propostas_tests.py", ["_qa_pw"])
    with pytest.raises(RuntimeError, match="EJC_QA_PASSWORD.*M34"):
        ns["_qa_pw"]("M34")
