"""Achado #4 do review do PR #708 (chatgpt-codex-connector, r3714845121):

Se uma variável de ambiente apontar para a conta ERRADA (ex.:
`EJC_TEST_EMAIL_FINANCEIRO` autentica um `admin`), o runner calculava as
expectativas com o `actual_role` retornado pelo login mas REGISTRAVA a
célula sob o `role_key` esperado — podendo reportar cobertura completa sem
nunca ter exercitado o papel de fato. Estes testes cobrem a correção em
`qa/e2e/run_fictitious_smoke.py`: `_papel_confere`/`_papel_gestao_confere`
(unidade, puras) e o comportamento fim a fim de `_matriz_rbac` quando o
login devolve um papel divergente do esperado.

Segue o padrão de carregamento de `test_e2e_smoke_isolamento.py`: o runner
não é um pacote importável, então é carregado direto do arquivo.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RUNNER = (Path(__file__).resolve().parents[2] / "qa" / "e2e"
          / "run_fictitious_smoke.py")


@pytest.fixture(scope="module")
def smoke():
    pytest.importorskip("httpx")
    spec = importlib.util.spec_from_file_location("run_fictitious_smoke_papel", RUNNER)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["run_fictitious_smoke_papel"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class _RespostaFake:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = "{}"
        self.headers = {}

    def json(self):
        return self._payload


class _ClienteLoginFake:
    """Simula `httpx.Client`: todo POST /api/auth/login devolve o mesmo
    token/role fixos; GET (sondagem) devolve 200 vazio (a amostra é
    monkeypatchada para vazia nestes testes — não é o alvo aqui)."""

    def __init__(self, role_no_login: str, token: str = "tok-fake"):
        self._role = role_no_login
        self._token = token
        self.logins: list[tuple[str, dict]] = []

    def post(self, path, json=None, timeout=None):
        self.logins.append((path, json or {}))
        return _RespostaFake(200, {"access_token": self._token, "role": self._role})

    def get(self, path, headers=None, timeout=None):
        return _RespostaFake(200, {})

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ── Unidade: as duas funções puras ───────────────────────────────────────────


class TestPapelConfere:
    def test_aceita_quando_o_papel_bate(self, smoke):
        assert smoke._papel_confere("financeiro", "financeiro") is True

    def test_recusa_quando_o_papel_diverge(self, smoke):
        assert smoke._papel_confere("financeiro", "admin") is False

    def test_recusa_quando_actual_role_e_none(self, smoke):
        """Login sem campo `role` na resposta — nunca cai no fallback
        silencioso `actual_role or role_key` que existia antes da correção."""
        assert smoke._papel_confere("financeiro", None) is False


class TestPapelGestaoConfere:
    @pytest.mark.parametrize("papel", ["superadmin", "admin", "socio"])
    def test_aceita_papeis_de_gestao(self, smoke, papel):
        assert smoke._papel_gestao_confere(papel) is True

    @pytest.mark.parametrize("papel", ["advogado", "estagiario", "secretaria",
                                        "financeiro", "cliente_externo", None])
    def test_recusa_papeis_fora_da_gestao(self, smoke, papel):
        assert smoke._papel_gestao_confere(papel) is False


# ── Fim a fim: _matriz_rbac não conta cobertura para credencial errada ──────


class TestMatrizRbacRejeitaCredencialErrada:
    def _preparar(self, smoke, monkeypatch, *, papel_no_login: str):
        # Amostra vazia: o alvo destes testes é o pareamento de papel no
        # login, não a sondagem GET em si (já coberta em test_rbac_matrix.py).
        monkeypatch.setattr(smoke.rbac_matrix, "discover_gates", lambda *_a, **_kw: [])
        monkeypatch.setattr(smoke.rbac_matrix, "selecionar_amostra_get", lambda *_a, **_kw: ([], []))
        cliente = _ClienteLoginFake(role_no_login=papel_no_login)
        monkeypatch.setattr(smoke.httpx, "Client", lambda **_kw: cliente)
        monkeypatch.setenv("EJC_TEST_EMAIL_FINANCEIRO", "financeiro-teste@example.test")
        monkeypatch.setenv("EJC_TEST_PASSWORD_FINANCEIRO", "senha-teste")
        for role_key, email_var, password_var in smoke.PAPEIS_MATRIZ:
            if role_key == "financeiro":
                continue
            monkeypatch.delenv(email_var, raising=False)
            monkeypatch.delenv(password_var, raising=False)
        state = smoke.SuiteState(base_url="http://staging.local")
        state.access_token = None  # gestão fica faltante — fora do escopo deste teste
        state.user = {}
        return state, cliente

    def test_credencial_apontando_para_conta_errada_nao_conta_como_testada(self, smoke, monkeypatch):
        """`EJC_TEST_EMAIL_FINANCEIRO` autentica um 'admin' de verdade — a
        célula NÃO pode entrar em `celulas_por_papel['financeiro']` nem em
        `papeis_testados`, e precisa aparecer como FALTANTE com o motivo
        explícito (não um erro genérico de login)."""
        state, cliente = self._preparar(smoke, monkeypatch, papel_no_login="admin")
        smoke._matriz_rbac("http://staging.local", state)

        assert "financeiro" not in state.rbac_matrix["celulas"]
        assert "financeiro" in state.rbac_matrix["papeis_faltantes"]
        assert "financeiro" not in state.rbac_matrix["papeis_testados"]
        # O login FOI de fato tentado (não é credencial ausente).
        assert cliente.logins, "o runner precisa ter tentado o login"
        motivos = [item["motivo"] for item in state.nao_coberto if item["module_key"] == "rbac.financeiro"]
        assert motivos and "admin" in motivos[0] and "financeiro" in motivos[0]
        falha_registrada = [
            r for r in state.results
            if r.name == "rbac.login.financeiro.papel_confere" and not r.ok
        ]
        assert falha_registrada, "a divergência de papel precisa virar um resultado FAIL explícito"

    def test_credencial_correta_e_testada_normalmente(self, smoke, monkeypatch):
        """Controle: quando o papel retornado bate com o esperado, a célula
        É contabilizada — a correção não pode reprovar o caso são."""
        state, cliente = self._preparar(smoke, monkeypatch, papel_no_login="financeiro")
        smoke._matriz_rbac("http://staging.local", state)

        assert "financeiro" in state.rbac_matrix["celulas"]
        assert "financeiro" in state.rbac_matrix["papeis_testados"]
        assert "financeiro" not in state.rbac_matrix["papeis_faltantes"]


# ── Achado #3 do review do PR #708 (r3714845132): 422 após gate via Depends ──


class _ClienteSondaFake:
    """`_sondar_papel` só usa `.get(path, headers=..., timeout=...)`."""

    def __init__(self, status_code: int):
        self._status_code = status_code

    def get(self, path, headers=None, timeout=None):
        return _RespostaFake(self._status_code, {})


def _gate_negado(smoke, *, via_depends: bool):
    """Gate com `min_level` alto o bastante para negar qualquer papel de
    teste usado abaixo (todos < nível de `superadmin`)."""
    return smoke.rbac_matrix.RouteGate(
        module_key="teste", method="GET", path="/api/teste/protegido",
        gate_kind="require_roles", allowed_roles=("superadmin",),
        min_level=smoke.rbac_matrix.ROLE_LEVEL["superadmin"],
        source_file="teste.py", source_line=1, via_depends=via_depends,
    )


class TestSondarPapel422ViaDepends:
    def test_422_com_via_depends_true_e_gate_frouxo_nao_inconclusivo(self, smoke):
        """Gate resolvido via `Depends(...)` roda ANTES da validação de
        query — um papel negado que recebe 422 não devia ser possível se o
        gate estivesse funcionando; tratar como sucesso esconderia o bypass
        (exatamente o cenário do achado #3 do review)."""
        gate = _gate_negado(smoke, via_depends=True)
        state = smoke.SuiteState(base_url="http://staging.local")
        celulas = smoke._sondar_papel(
            _ClienteSondaFake(422), "financeiro", "tok", "financeiro", [gate], state,
        )
        assert celulas[0]["ok"] is False
        falha = next(r for r in state.results if r.name == "rbac.financeiro")
        assert falha.ok is False
        assert not falha.degraded, "isto é uma FALHA, não um degradado tolerável"

    def test_422_com_via_depends_false_continua_inconclusivo(self, smoke):
        """Gate só verificado no CORPO do handler: 422 por query faltante
        pode mesmo mascarar o gate para qualquer papel — continua
        inconclusivo (comportamento preexistente, não pode regredir)."""
        gate = _gate_negado(smoke, via_depends=False)
        state = smoke.SuiteState(base_url="http://staging.local")
        celulas = smoke._sondar_papel(
            _ClienteSondaFake(422), "financeiro", "tok", "financeiro", [gate], state,
        )
        assert celulas[0]["ok"] is True
        falha = next(r for r in state.results if r.name == "rbac.financeiro")
        assert falha.ok is True
        assert falha.degraded is True

    def test_422_com_esperado_200_continua_inconclusivo_mesmo_via_depends(self, smoke):
        """Papel PERMITIDO recebendo 422 não é um achado de RBAC (a rota
        simplesmente exige query que a sonda não enviou) — `via_depends` só
        muda o tratamento quando `esperado == 403`."""
        gate = smoke.rbac_matrix.RouteGate(
            module_key="teste", method="GET", path="/api/teste/liberado",
            gate_kind="require_roles", allowed_roles=("financeiro",),
            min_level=smoke.rbac_matrix.ROLE_LEVEL["financeiro"],
            source_file="teste.py", source_line=1, via_depends=True,
        )
        state = smoke.SuiteState(base_url="http://staging.local")
        celulas = smoke._sondar_papel(
            _ClienteSondaFake(422), "financeiro", "tok", "financeiro", [gate], state,
        )
        assert celulas[0]["ok"] is True
        assert celulas[0]["esperado"] == 200
