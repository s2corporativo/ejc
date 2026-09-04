"""Regressão do incidente de 04/09/2026 — API muda por boot travado.

SINTOMA MEDIDO EM PRODUÇÃO (https://ejc.depaulateixeira.adv.br):

    GET /               → 200 em 0,49 s   (SPA estático, nginx :8080)
    GET /api/health     → sem resposta    (0 bytes em 45 s)
    GET /api/naoexiste  → 504 em 120,58 s (= proxy_read_timeout do nginx)

Rota INEXISTENTE também travava. Um 404 não toca banco, não toca IA, não toca
nada — se nem ele saía, o processo ASGI não estava atendendo requisição alguma.
E o 504 (em vez de 502 imediato) provava que a porta 8000 aceitava a conexão:
container de pé, uvicorn com o socket em bind, boot preso ANTES do `yield`.

CAUSA: nenhum passo do `lifespan` tinha teto de tempo. `check_db()` abria
conexão sem prazo; um Postgres alcançável porém travado (lock, disco cheio,
saturação da VPS compartilhada) prendia o startup para sempre. O `try/except`
que existia nos outros passos não cobria isso: travamento não levanta exceção.

CONTRATO TRAVADO AQUI: passo de boot lento ou quebrado DEGRADA (loga e segue),
nunca impede a API de responder. Sistema de pé com feriados desatualizados é
infinitamente melhor que sistema mudo.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


# ── Contrato do executor de passo de boot ────────────────────────────────────

@pytest.mark.asyncio
async def test_passo_de_boot_devolve_padrao_quando_trava():
    """O passo pendura para sempre; o boot NÃO pode pendurar junto."""
    from app.main import _passo_de_boot

    async def _travado():
        await asyncio.Event().wait()  # nunca resolve — é o Postgres travado

    from app.core.config import get_settings
    settings = get_settings()
    original = settings.STARTUP_STEP_TIMEOUT_SECONDS
    settings.STARTUP_STEP_TIMEOUT_SECONDS = 0.05
    try:
        resultado = await asyncio.wait_for(
            _passo_de_boot("travado", _travado, padrao="degradado"),
            timeout=5,  # se o teto interno falhar, o teste falha aqui
        )
    finally:
        settings.STARTUP_STEP_TIMEOUT_SECONDS = original

    assert resultado == "degradado"


@pytest.mark.asyncio
async def test_passo_de_boot_devolve_padrao_quando_levanta():
    """Exceção no passo também degrada — não derruba o lifespan."""
    from app.main import _passo_de_boot

    async def _quebrado():
        raise RuntimeError("cofre indisponível")

    assert await _passo_de_boot("quebrado", _quebrado, padrao=0) == 0


@pytest.mark.asyncio
async def test_passo_de_boot_devolve_valor_no_caminho_feliz():
    from app.main import _passo_de_boot

    async def _ok():
        return 42

    assert await _passo_de_boot("ok", _ok, padrao=0) == 42


# ── Contrato da sonda do banco ───────────────────────────────────────────────

class _EngineFalso:
    """Engine mínimo: `AsyncEngine.connect` é read-only, então trocamos o
    objeto inteiro no módulo em vez do atributo."""

    def __init__(self, conexao_factory):
        self._conexao_factory = conexao_factory

    def connect(self):
        return self._conexao_factory()

    async def dispose(self, close: bool = True):  # usado no retry de loop
        return None


@pytest.mark.asyncio
async def test_check_db_devolve_false_quando_banco_trava(monkeypatch):
    """Banco alcançável e mudo → False rápido, não espera para sempre.

    É o caso exato do incidente: `engine.connect()` não devolve. Antes, o
    `except Exception` não pegava (travar não é levantar) e o boot morria ali.
    """
    from app.core import database

    class _ConexaoTravada:
        async def __aenter__(self):
            await asyncio.Event().wait()

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(database, "engine", _EngineFalso(_ConexaoTravada))

    resultado = await asyncio.wait_for(database.check_db(timeout=0.05), timeout=5)
    assert resultado is False


@pytest.mark.asyncio
async def test_check_db_timeout_zero_desativa_teto(monkeypatch):
    """`0` desliga o teto (asyncio.timeout(None)) sem estourar na hora.

    Sem o guarda `limite > 0`, `asyncio.timeout(0)` expiraria imediatamente e
    o "desativar" viraria "reprovar sempre" — inversão silenciosa do contrato.
    """
    from app.core import database

    class _ConexaoOk:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def execute(self, *_a, **_k):
            return None

    monkeypatch.setattr(database, "engine", _EngineFalso(_ConexaoOk))
    assert await database.check_db(timeout=0) is True


# ── Guarda estrutural: nenhum passo novo pode nascer sem teto ────────────────

def test_lifespan_nao_tem_await_desprotegido():
    """Todo `await` do lifespan passa por `_passo_de_boot` (ou é o `yield`).

    Guarda contra a regressão pelo lado do futuro: alguém acrescenta um passo
    de boot novo com `await servico.carregar()` solto e reintroduz o travamento
    sem perceber. Este teste falha no PR, não em produção.
    """
    arvore = ast.parse((RAIZ / "app" / "main.py").read_text(encoding="utf-8"))
    lifespan = next(
        no for no in ast.walk(arvore)
        if isinstance(no, ast.AsyncFunctionDef) and no.name == "lifespan"
    )

    def _nome_chamado(alvo) -> str | None:
        if not isinstance(alvo, ast.Call):
            return None
        if isinstance(alvo.func, ast.Name):
            return alvo.func.id
        if isinstance(alvo.func, ast.Attribute):
            return alvo.func.attr
        return None

    # Fábricas passadas a `_passo_de_boot(...)` já rodam sob o teto — o `await`
    # dentro DELAS é protegido. Coletamos os nomes para não acusar falso
    # positivo, mas seguimos varrendo qualquer outra função aninhada.
    protegidas = set()
    for no in ast.walk(lifespan):
        if isinstance(no, ast.Call) and _nome_chamado(no) == "_passo_de_boot":
            for arg in no.args[1:2]:
                if isinstance(arg, ast.Name):
                    protegidas.add(arg.id)

    permitidos = {"_passo_de_boot", "flush"}  # flush = shutdown, já em try/except

    def _varrer(no, dentro_de_protegida: bool, achados: list):
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.AsyncFunctionDef, ast.FunctionDef)):
                _varrer(filho, filho.name in protegidas, achados)
                continue
            if isinstance(filho, ast.Await) and not dentro_de_protegida:
                nome = _nome_chamado(filho.value)
                if nome not in permitidos:
                    achados.append((filho.lineno, nome or "await anônimo"))
            _varrer(filho, dentro_de_protegida, achados)

    desprotegidos: list = []
    _varrer(lifespan, False, desprotegidos)

    assert not desprotegidos, (
        "await sem teto de tempo no lifespan — passo de boot novo precisa ir "
        f"por _passo_de_boot(): {desprotegidos}. Ver o cabeçalho deste arquivo."
    )


def test_timeout_de_boot_e_configuravel_e_tem_default_util():
    from app.core.config import Settings

    campo = Settings.model_fields["STARTUP_STEP_TIMEOUT_SECONDS"]
    assert campo.default > 0, "default 0 desligaria o teto que este arquivo protege"
    assert campo.default <= 60, (
        "teto acima de 60 s aproxima do proxy_read_timeout de 120 s do nginx — "
        "o boot precisa terminar MUITO antes de o usuário ver 504"
    )
