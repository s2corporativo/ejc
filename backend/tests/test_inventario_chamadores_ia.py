"""Testes do inventario de chamadores de IA (I2, Fase 0): medicao, sem allowlist."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "inventario_chamadores_ia", BACKEND / "scripts" / "inventario_chamadores_ia.py"
)
inv = importlib.util.module_from_spec(_spec)
sys.modules["inventario_chamadores_ia"] = inv
_spec.loader.exec_module(inv)


def _analisar(fonte: str, modulo: str = "app.routers.x", reexports=None):
    return inv.analisar_fonte(fonte, "app/routers/x.py", modulo, False, reexports)


def test_detecta_import_com_alias_e_modulo():
    regs = _analisar(
        "from app.services.ai_gateway import chat as gw_chat\n"
        "from app.services import ai_gateway\n"
        "async def a():\n    return await gw_chat(messages=[])\n"
        "async def b():\n    return await ai_gateway.executar_tarefa_ia(1, 'm')\n"
        "async def c():\n    return await ai_gateway.chat_agentico()\n"
    )
    assert [(r["funcao"], r["alvo"]) for r in regs] == [
        ("a", "ai_gateway.chat"),
        ("b", "ai_gateway.executar_tarefa_ia"),
        ("c", "ai_gateway.chat_agentico"),
    ]
    assert regs[0]["linha"] == 4


def test_ignora_comentarios_docstrings_e_homonimos():
    regs = _analisar(
        "from app.services import ai_gateway\n"
        "def a(chat):\n"
        "    '''ai_gateway.chat(...) so em docstring'''\n"
        "    # ai_gateway.chat(x)\n"
        "    return chat(1)\n"
        "def b(db):\n    return db.chat(1)\n"
    )
    assert regs == []


def test_orquestrador_e_run_ai_task_com_import_relativo():
    regs = inv.analisar_fonte(
        "from ..ai.core.orchestrator import orchestrator, run_ai_task\n"
        "async def a():\n    return await orchestrator.run(tarefa=1)\n"
        "async def b():\n    return await run_ai_task(x=1)\n",
        "app/services/foo/bar.py",
        "app.services.foo.bar",
    )
    assert [(r["alvo"], r["usa_orquestrador"]) for r in regs] == [
        ("orchestrator.run", "sim"),
        ("run_ai_task", "sim"),
    ]


def test_flags_log_e_citacoes_diretos_no_corpo():
    regs = _analisar(
        "from app.services.ai_gateway import chat, registrar_log_resposta\n"
        "from app.services.citation_gate import validar_citacoes\n"
        "async def a(db):\n"
        "    r = await chat(messages=[])\n"
        "    await registrar_log_resposta(db, r)\n"
        "    await validar_citacoes(db, r)\n"
    )
    assert len(regs) == 1
    assert regs[0]["registra_log"] == "sim"
    assert regs[0]["citacoes"] == "sim"
    # Chama simbolos de app.* sem orquestrador: ausencia nao provada.
    assert regs[0]["usa_orquestrador"] == "nao_determinado"


def test_flag_indireto_via_helper_do_mesmo_modulo():
    regs = _analisar(
        "from app.services.ai_gateway import chat\n"
        "from app.services.ai_guard import registrar_ai_log\n"
        "async def _loga(db):\n    await registrar_ai_log(db)\n"
        "async def a(db):\n    await chat(messages=[])\n    await _loga(db)\n"
    )
    assert regs[0]["registra_log"] == "indireto"


def test_nao_determinado_quando_ha_chamada_a_app_sem_prova():
    regs = _analisar(
        "from app.services.ai_gateway import chat\n"
        "from app.services.outro import ajudante\n"
        "async def a(db):\n    await chat(messages=[])\n    await ajudante(db)\n"
    )
    assert regs[0]["registra_log"] == "nao_determinado"
    assert regs[0]["citacoes"] == "nao_determinado"


def test_nao_quando_ausencia_provada():
    regs = _analisar(
        "from app.services.ai_gateway import chat\n"
        "async def a():\n    return await chat(messages=[])\n"
    )
    assert (regs[0]["registra_log"], regs[0]["citacoes"]) == ("nao", "nao")


def test_metodo_de_classe_funcao_aninhada_e_nivel_de_modulo():
    regs = _analisar(
        "from app.services.ai_gateway import chat\n"
        "class S:\n"
        "    async def m(self):\n"
        "        async def interna():\n            return await chat()\n"
        "        return await interna()\n"
        "r = chat()\n"
    )
    assert [r["funcao"] for r in regs] == ["S.m", "<modulo>"]


def test_reexport_em_outro_modulo():
    regs = _analisar(
        "from app.services import ai_service\n"
        "async def a():\n    return await ai_service.gw_chat()\n",
        reexports={"app.services.ai_service.gw_chat": "app.services.ai_gateway.chat"},
    )
    assert regs and regs[0]["alvo"] == "ai_gateway.chat"


def test_inventario_roda_no_repo_sem_erro():
    registros, erros = inv.inventariar(BACKEND / "app")
    assert erros == []
    assert registros, "esperado ao menos um chamador de IA em backend/app"
    alvos = {r["alvo"] for r in registros}
    assert "ai_gateway.chat" in alvos
    assert "orchestrator.run" in alvos
    resumo = inv.resumir(registros)
    assert resumo["pontos_de_chamada_fora_do_nucleo"] > 0
    assert "| Arquivo:linha |" in inv.tabela_markdown(registros)
