"""Isolamento e cleanup do runner E2E (AI-005) — consolidação 2026-07-29.

O runner `qa/e2e/run_fictitious_smoke.py` roda contra staging (às vezes
compartilhado). A auditoria confirmou que ele NÃO apagava registro alheio, mas
também que:

  • o cleanup ficava fora de `try/finally` — qualquer exceção no meio do fluxo
    abortava a execução ANTES de limpar, deixando cliente/caso/documento
    fictícios no ambiente e sem sequer gravar o relatório;
  • o cleanup do caso chamava `DELETE /api/cases/{id}` sem `motivo`, e o router
    exige `motivo` com no mínimo 5 caracteres (routers/cases.py) — ou seja,
    respondia 422 em TODA execução e o caso nunca era removido;
  • os dados fictícios eram idênticos a cada execução (mesmo CPF, mesmo número
    de processo), o que forçava o fallback "achar pelo marcador" e fazia uma
    execução operar sobre o registro de outra.

Não havia nenhum teste do runner. Estes cobrem as invariantes de isolamento sem
subir a stack: o módulo é carregado direto do arquivo e o cleanup é exercitado
com um cliente HTTP falso que registra as chamadas.
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
    """Carrega o runner como módulo (ele não é um pacote importável)."""
    pytest.importorskip("httpx")
    spec = importlib.util.spec_from_file_location("run_fictitious_smoke", RUNNER)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["run_fictitious_smoke"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class _RespostaFake:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}
        self.text = "{}"
        self.headers = {}

    def json(self):
        return self._payload


class _ClienteFake:
    """Registra (método, url) de cada chamada; nunca toca a rede."""

    def __init__(self):
        self.chamadas: list[tuple[str, str]] = []

    def request(self, method, url, **kw):
        self.chamadas.append((method, url))
        return _RespostaFake(200)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def deletes(self) -> list[str]:
        return [u for m, u in self.chamadas if m == "DELETE"]


# ── 1. Identidade exclusiva por execução ─────────────────────────────────────

class TestIdentidadeDaExecucao:
    def test_marcador_carrega_o_run_id(self, smoke):
        assert smoke.MARKER_RUN.startswith(smoke.MARKER)
        assert smoke.MARKER_RUN != smoke.MARKER
        assert smoke.RUN_ID and smoke.RUN_ID in smoke.MARKER_RUN

    def test_cpf_da_execucao_tem_digitos_verificadores_validos(self, smoke):
        for run_id in ("a1b2c3d4", "00000000", "deadbeef", "ffffffff"):
            cpf = smoke._cpf_da_execucao(run_id)
            assert len(cpf) == 11 and cpf.isdigit()
            assert len(set(cpf)) > 1, "CPF de dígitos repetidos é recusado"
            corpo = [int(c) for c in cpf[:9]]
            for i in range(2):
                soma = sum(d * p for d, p in
                           zip(corpo, range(len(corpo) + 1, 1, -1)))
                resto = (soma * 10) % 11
                assert int(cpf[9 + i]) == (0 if resto == 10 else resto)
                corpo.append(int(cpf[9 + i]))

    def test_execucoes_diferentes_geram_dados_diferentes(self, smoke):
        assert smoke._cpf_da_execucao("aaa") != smoke._cpf_da_execucao("bbb")
        assert (smoke._processo_da_execucao("aaa")
                != smoke._processo_da_execucao("bbb"))

    def test_personalizacao_reescreve_cpf_processo_e_marcador(self, smoke):
        original = {
            "nome": f"{smoke.MARKER} Maria Teste",
            "cpf": smoke.CPF_MATRIZ,
            "numero_processo": smoke.PROCESSO_MATRIZ,
            "aninhado": [{"titulo": f"{smoke.MARKER} doc"}],
        }
        novo = smoke._personalizar(original)
        assert novo["cpf"] != smoke.CPF_MATRIZ
        assert novo["numero_processo"] != smoke.PROCESSO_MATRIZ
        assert smoke.MARKER_RUN in novo["nome"]
        assert smoke.MARKER_RUN in novo["aninhado"][0]["titulo"]
        # Não altera o dicionário de origem nem duplica o sufixo ao reaplicar.
        assert original["cpf"] == smoke.CPF_MATRIZ
        assert smoke._personalizar(novo)["nome"] == novo["nome"]


# ── 2. Cleanup remove só o que esta execução criou ───────────────────────────

class TestCleanupIsolado:
    def test_preserva_registro_preexistente(self, smoke):
        """O núcleo do AI-005: um registro localizado pelo marcador (não criado
        aqui) NUNCA pode ser apagado."""
        state = smoke.SuiteState(base_url="http://staging.local")
        state.client_id = "CLIENTE-PREEXISTENTE"
        state.case_id = "CASO-PREEXISTENTE"
        state.document_id = "DOC-PREEXISTENTE"
        # `criados_nesta_execucao` vazio = nada foi criado por nós.
        cliente = _ClienteFake()
        smoke._cleanup(cliente, state)

        assert cliente.deletes() == [], "não pode apagar dado de outra execução"
        assert len(state.nao_coberto) == 3
        for item in state.nao_coberto:
            assert "preexistente" in item["motivo"]

    def test_remove_apenas_os_ids_da_execucao(self, smoke):
        state = smoke.SuiteState(base_url="http://staging.local")
        state.client_id = "MEU-CLIENTE"
        state.case_id = "CASO-DE-OUTRO"          # não registrado
        state.document_id = "MEU-DOC"
        state.criados_nesta_execucao = {"MEU-CLIENTE", "MEU-DOC"}
        cliente = _ClienteFake()
        smoke._cleanup(cliente, state)

        deletes = " ".join(cliente.deletes())
        assert "MEU-CLIENTE" in deletes and "MEU-DOC" in deletes
        assert "CASO-DE-OUTRO" not in deletes

    def test_delete_de_caso_envia_motivo(self, smoke):
        """routers/cases.py exige `motivo` (min 5 chars) e responde 422 sem ele:
        sem isso o caso fictício ficava no ambiente a cada execução."""
        state = smoke.SuiteState(base_url="http://staging.local")
        state.case_id = "CASO-1"
        state.criados_nesta_execucao = {"CASO-1"}
        cliente = _ClienteFake()
        smoke._cleanup(cliente, state)

        url = next(u for u in cliente.deletes() if "/api/cases/" in u)
        assert "motivo=" in url
        motivo = url.split("motivo=", 1)[1]
        assert len(motivo) >= 5

    def test_e_idempotente(self, smoke):
        """Rodar duas vezes não quebra nem muda o conjunto de alvos."""
        def _rodar():
            state = smoke.SuiteState(base_url="http://staging.local")
            state.client_id = "C1"
            state.criados_nesta_execucao = {"C1"}
            cliente = _ClienteFake()
            smoke._cleanup(cliente, state)
            return cliente.deletes()

        assert _rodar() == _rodar()

    def test_sem_ids_nao_emite_nenhum_delete(self, smoke):
        state = smoke.SuiteState(base_url="http://staging.local")
        cliente = _ClienteFake()
        smoke._cleanup(cliente, state)
        assert cliente.deletes() == []


# ── 3. Cleanup sobrevive a falha parcial ─────────────────────────────────────

class TestCleanupNoFinally:
    def test_fluxo_esta_dentro_de_try_finally(self, smoke):
        """Guarda estrutural: o cleanup precisa estar no `finally` de `main`,
        senão uma exceção no meio do fluxo deixa resíduo no staging."""
        import ast
        import inspect

        arvore = ast.parse(inspect.getsource(smoke.main))
        finallys = [n for n in ast.walk(arvore) if isinstance(n, ast.Try) and n.finalbody]
        assert finallys, "main() precisa de try/finally"
        chamadas = {
            n.func.id
            for bloco in finallys for corpo in bloco.finalbody
            for n in ast.walk(corpo)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "_cleanup" in chamadas, "_cleanup precisa rodar no finally"
        assert "_write_report" in chamadas, "relatório precisa rodar no finally"


# ── 4. Relatório não vaza segredo nem PII ────────────────────────────────────

class TestRedacaoDoRelatorio:
    def test_redige_pii_em_lista_aninhada(self, smoke):
        """A redação anterior só olhava o nível de cima: a lista de clientes sob
        `data` — com o CPF DECIFRADO — ia inteira para o relatório."""
        bruto = {
            "data": [
                {"nome": "Fulano", "cpf": "52998224725",
                 "email": "f@example.test", "telefone": "31999990001"},
            ],
            "access_token": "token-secreto",
        }
        limpo = smoke._redigir(bruto)
        serializado = str(limpo)
        assert "52998224725" not in serializado
        assert "f@example.test" not in serializado
        assert "31999990001" not in serializado
        assert "token-secreto" not in serializado
        # `nome` também é redigido: o relatório podia sair com o nome completo
        # do titular junto do endereço e das observações do escritório.
        assert limpo["data"][0]["nome"] == "***"
        # Campo neutro segue legível — a redação não apaga o relatório inteiro.
        assert smoke._redigir({"status_code": 200})["status_code"] == 200

    def test_corpo_nao_json_tambem_e_redigido(self, smoke):
        """O fallback `resp.text[:800]` devolvia o corpo CRU: um erro HTML de
        proxy ou um CSV de exportação entrava íntegro no relatório."""
        bruto = ("Erro ao processar cliente 529.982.247-25 "
                 "(contato: fulano@example.test, tel 31999990001)")
        limpo = smoke._redigir_texto(bruto)
        assert "529.982.247-25" not in limpo
        assert "fulano@example.test" not in limpo
        assert "31999990001" not in limpo
        assert "Erro ao processar cliente" in limpo

    def test_nao_entra_em_loop_com_estrutura_profunda(self, smoke):
        profundo: dict = {"n": {}}
        atual = profundo["n"]
        for _ in range(30):
            atual["n"] = {}
            atual = atual["n"]
        assert smoke._redigir(profundo) is not None


# ── 5. H-4: guardas que faltavam no motor da matriz e no cleanup ─────────────

class _RespostaConfig:
    """Cliente falso com resposta programável por (método, prefixo de url)."""

    def __init__(self, regras=None, default=(200, None)):
        self.regras = regras or {}
        self.default = default
        self.chamadas: list[tuple[str, str]] = []

    def request(self, method, url, **kw):
        self.chamadas.append((method, url))
        for (m, prefixo), (status, payload) in self.regras.items():
            if m == method and str(url).startswith(prefixo):
                return _RespostaFake(status, payload)
        return _RespostaFake(*self.default)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestCleanupProvaRemocao:
    def test_relê_o_recurso_apos_delete(self, smoke):
        """404 no DELETE era aceito sem prova. Agora o cleanup RELÊ o recurso."""
        state = smoke.SuiteState(base_url="http://staging.local")
        state.client_id = "C1"
        state.criados_nesta_execucao = {"C1"}
        cliente = _RespostaConfig(default=(404, None))
        smoke._cleanup(cliente, state)

        gets = [u for m, u in cliente.chamadas if m == "GET"]
        assert any("C1" in u for u in gets), "cleanup precisa reler o recurso"

    def test_recurso_que_sobrevive_ao_delete_vira_falha(self, smoke):
        """DELETE respondeu ok, mas o GET seguinte ainda encontra o registro:
        o ambiente ficou sujo e o relatório não pode dizer que limpou."""
        state = smoke.SuiteState(base_url="http://staging.local")
        state.client_id = "C1"
        state.criados_nesta_execucao = {"C1"}
        cliente = _RespostaConfig(default=(200, {"id": "C1"}))
        smoke._cleanup(cliente, state)

        falhas = [r for r in state.results if not r.ok]
        assert any("cleanup_nao_removeu" in r.name for r in falhas)


class TestMatrizNaoExecutaMetodoDestrutivo:
    def test_delete_na_matriz_e_recusado(self, smoke):
        """A guarda de isolamento vive no _cleanup; o motor da matriz executava
        qualquer método. Um DELETE de path fixo apagaria registro alheio."""
        state = smoke.SuiteState(base_url="http://staging.local")
        matriz = {"modules": [{"module_key": "casos", "api_checks": [
            {"method": "DELETE", "path": "/api/cases/qualquer", "expected": [200]},
        ]}]}
        cliente = _RespostaConfig()
        smoke._matrix_smoke(cliente, state, matriz)

        assert cliente.chamadas == [], "nenhuma requisição pode ter sido emitida"
        assert any("metodo_destrutivo_na_matriz" in r.name
                   for r in state.results if not r.ok)

    def test_post_da_matriz_entra_no_rastreio(self, smoke):
        """POST fora dos fluxos dedicados também cria recurso — sem registrar o
        id ele nunca entra no cleanup e vira resíduo permanente."""
        state = smoke.SuiteState(base_url="http://staging.local")
        matriz = {"modules": [{"module_key": "etiquetas", "api_checks": [
            {"method": "POST", "path": "/api/etiquetas/", "expected": [200, 201]},
        ]}]}
        cliente = _RespostaConfig(default=(201, {"id": "E9"}))
        smoke._matrix_smoke(cliente, state, matriz)

        assert "E9" in state.criados_nesta_execucao
        assert ("etiquetas", "/api/etiquetas/", "E9") in state.extras_criados

    def test_residuo_da_matriz_e_declarado_no_relatorio(self, smoke):
        state = smoke.SuiteState(base_url="http://staging.local")
        state.extras_criados = [("etiquetas", "/api/etiquetas/", "E9")]
        smoke._cleanup(_RespostaConfig(), state)

        assert any(item.get("path") == "/api/etiquetas/" and "E9" in item["motivo"]
                   for item in state.nao_coberto)

    def test_post_sem_id_e_denunciado(self, smoke):
        state = smoke.SuiteState(base_url="http://staging.local")
        matriz = {"modules": [{"module_key": "etiquetas", "api_checks": [
            {"method": "POST", "path": "/api/etiquetas/", "expected": [200, 201]},
        ]}]}
        smoke._matrix_smoke(_RespostaConfig(default=(201, {"ok": True})), state, matriz)

        assert any("id_ausente" in r.name for r in state.results if not r.ok)
