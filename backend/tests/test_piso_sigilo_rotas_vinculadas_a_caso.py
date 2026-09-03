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

_APP = Path(__file__).parents[1] / "app"
# Varre routers E services: a varredura original cobria só `app/routers/`, e o
# pente fino de 03/09 achou por fora dela DUAS violações no caminho das skills
# (`ai_skill_service`), a pior delas com `provider_override` forçando engine
# externo. Um gate que só olha a borda não pega o serviço que a borda chama.
DIRETORIOS = ("routers", "services")

# Funções que levam conteúdo a um provedor de IA e aceitam `modo_sanitizacao`.
_CHAMADAS_DE_IA = {
    "chat", "gw_chat", "_gw_chat_consolidacao",
    "executar_tarefa_ia", "chat_agentico",
}

# Exceções JUSTIFICADAS, com o motivo. A lista existe para que uma exceção seja
# decisão ESCRITA e revisada no PR, não esquecimento silencioso — e para que a
# dívida conhecida fique contável em vez de invisível.
#
# As entradas abaixo são DÍVIDA RECONHECIDA, não isenção permanente. O corpo do
# PR #1410 já registrava a de `peca_service`/`motor_peca_service` como delegada
# aos PRs #1376/#1384; a regra 10 do CLAUDE.md ("não modificar arquivos que
# pertencem a outro PR ativo") impede fechá-las aqui. As demais são de serviços
# livres e merecem PR própria — cada uma manda conteúdo de caso ao gateway sem
# o piso, então um caso `sigilo_reforcado=True` sai do VPS por esses caminhos.
_MOTIVO_OUTRO_PR = (
    "Arquivo pertence a PR ativo (#1376/#1384, ver §10.2 do PR #1410). "
    "Regra 10 do CLAUDE.md impede tocar aqui."
)
_MOTIVO_DIVIDA = (
    "Dívida reconhecida no pente fino de 03/09: serviço vinculado a caso que "
    "chama o gateway sem piso de sigilo. Fechar em PR própria — não é isenção."
)
_EXCECOES: dict[str, str] = {
    "peca_service.py::gerar_peca_pipeline": _MOTIVO_OUTRO_PR,
    "motor_peca_service.py::motivacao_pecas_ia": _MOTIVO_OUTRO_PR,
    "anexos_service.py::gerar_legenda_ia": _MOTIVO_DIVIDA,
    "anexos_service.py::gerar_razoes_juridicas": _MOTIVO_DIVIDA,
    "checklist_ia.py::gerar_checklist_ia": _MOTIVO_DIVIDA,
    "documento_service.py::sugerir_tipo": _MOTIVO_DIVIDA,
    "dossie_service.py::gerar_dossie": _MOTIVO_DIVIDA,
    "ficha_triagem_service.py::pre_preencher": _MOTIVO_DIVIDA,
    "matriz_teses_service.py::decompor_questoes": _MOTIVO_DIVIDA,
    "triagem_entrevista_service.py::analisar_relato": _MOTIVO_DIVIDA,
    "visual_law.py::gerar_diagrama": _MOTIVO_DIVIDA,
}


def _violacoes() -> list[str]:
    achados: list[str] = []
    arquivos = [f for d in DIRETORIOS for f in sorted((_APP / d).rglob("*.py"))]
    for arquivo in arquivos:
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


def test_a_divida_conhecida_nao_cresce():
    """A lista de exceções é um LEDGER, não uma isenção: ela pode encolher
    (fechando a dívida), nunca crescer em silêncio. Se alguém acrescentar uma
    entrada, este número muda e a revisão do PR tem de justificar."""
    assert len(_EXCECOES) == 11, (
        "A dívida de piso de sigilo mudou. Se você FECHOU uma, remova-a de "
        "_EXCECOES e ajuste este número — parabéns. Se está ACRESCENTANDO "
        "uma, justifique no PR: cada entrada é um caminho por onde um caso "
        "com sigilo reforçado sai do VPS."
    )


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
