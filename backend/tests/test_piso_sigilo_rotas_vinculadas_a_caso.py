"""Contrato: TODA rota vinculada a um caso que chama a IA repassa o PISO DE
SIGILO do caso ao gateway.

Classe de defeito recorrente — a auditoria do módulo de minutas achou a sexta
ocorrência dela, e o histórico do repositório mostra que ela volta: a Issue
#1194 já tinha fechado `analise_estrategica`, `ai_service`, `ia_defensiva`,
`validador_juridico`, `ai_tools` e `agent/tools/escrita`, um a um. Rota nova
vinculada a caso nasce sem o piso e ninguém percebe, porque tudo funciona: o
conteúdo simplesmente sai do VPS.

Este teste troca a auditoria manual por um invariante verificável. Varre a AST
de `app/routers/` e falha se alguma função que recebe `case_id` chamar o
gateway sem `modo_sanitizacao`. Verificação por inspeção de fonte — mesma
técnica que `test_ai_prompt_injection_delimitadores.py` e
`test_legal_doc_flow_contract.py` já usam: montar o grafo de dependências de
cada handler (Case/db/dossiê/RAG/RBAC) custaria muito mais e cobriria menos,
porque o valor aqui é justamente pegar a rota que AINDA NÃO EXISTE.

Como satisfazer, ao criar uma rota nova vinculada a caso:

    case = await verificar_acesso_caso(db, cu, case_id)   # já devolve o Case
    from app.services.ai.sanitization_policy import modo_sigilo_do_caso
    modo_sigilo = modo_sigilo_do_caso(case)
    resp = await chat(..., modo_sanitizacao=modo_sigilo)

Sem o objeto `Case` à mão, use a irmã assíncrona:
`await modo_sigilo_por_case_id(db, case_id)`.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROUTERS = Path(__file__).parents[1] / "app" / "routers"

# Funções que levam conteúdo a um provedor de IA e aceitam `modo_sanitizacao`.
_CHAMADAS_DE_IA = {
    "chat", "gw_chat", "_gw_chat_consolidacao",
    "executar_tarefa_ia", "chat_agentico",
}

# Exceções JUSTIFICADAS, com o motivo. Vazio hoje — de propósito: a lista existe
# para que uma exceção futura seja uma decisão escrita e revisada no PR, não um
# esquecimento silencioso. Formato: "arquivo.py::funcao": "motivo".
_EXCECOES: dict[str, str] = {}


def _violacoes() -> list[str]:
    achados: list[str] = []
    for arquivo in sorted(ROUTERS.glob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for fn in ast.walk(arvore):
            if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            argumentos = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
            if "case_id" not in argumentos:
                continue
            if f"{arquivo.name}::{fn.name}" in _EXCECOES:
                continue
            for chamada in ast.walk(fn):
                if not isinstance(chamada, ast.Call):
                    continue
                nome = getattr(chamada.func, "id", None) or \
                    getattr(chamada.func, "attr", None)
                if nome not in _CHAMADAS_DE_IA:
                    continue
                if "modo_sanitizacao" not in {k.arg for k in chamada.keywords}:
                    achados.append(
                        f"{arquivo.name}:{chamada.lineno} — {fn.name}() recebe "
                        f"`case_id` e chama {nome}() sem `modo_sanitizacao`"
                    )
    return achados


def test_toda_rota_de_caso_repassa_o_piso_de_sigilo():
    violacoes = _violacoes()
    assert not violacoes, (
        "Rota(s) vinculada(s) a caso chamando a IA sem o piso de sigilo — um "
        "caso marcado `sigilo_reforcado` sairia do VPS:\n  "
        + "\n  ".join(violacoes)
        + "\n\nVeja o docstring deste arquivo para o padrão de 3 linhas."
    )


def test_a_varredura_realmente_encontra_o_defeito():
    """Guarda do próprio teste: se a heurística parar de casar (renomearam o
    gateway, mudaram a assinatura), o teste acima passaria VAZIO e daria uma
    falsa sensação de cobertura. Aqui provamos que ela ainda acusa o padrão
    defeituoso — com um trecho sintético, não com código de produção."""
    codigo = (
        "async def rota_nova(case_id: str, db=None):\n"
        "    resp = await chat(messages=[], task_type='analise_juridica')\n"
    )
    arvore = ast.parse(codigo)
    fn = arvore.body[0]
    chamadas = [
        c for c in ast.walk(fn)
        if isinstance(c, ast.Call)
        and (getattr(c.func, "id", None) or getattr(c.func, "attr", None))
        in _CHAMADAS_DE_IA
        and "modo_sanitizacao" not in {k.arg for k in c.keywords}
    ]
    assert len(chamadas) == 1


def test_a_varredura_aceita_a_rota_corrigida():
    """Contraprova: com `modo_sanitizacao`, a mesma rota não é acusada."""
    codigo = (
        "async def rota_nova(case_id: str, db=None):\n"
        "    resp = await chat(messages=[], task_type='x', modo_sanitizacao=m)\n"
    )
    fn = ast.parse(codigo).body[0]
    chamadas = [
        c for c in ast.walk(fn)
        if isinstance(c, ast.Call)
        and (getattr(c.func, "id", None) or getattr(c.func, "attr", None))
        in _CHAMADAS_DE_IA
        and "modo_sanitizacao" not in {k.arg for k in c.keywords}
    ]
    assert chamadas == []
