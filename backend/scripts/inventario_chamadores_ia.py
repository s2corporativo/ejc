#!/usr/bin/env python3
"""Inventario de chamadores de IA (achado I2, Fase 0) — somente medicao.

Varre `backend/app` por AST (nao por grep) e lista cada ponto que chama:

  - ai_gateway.chat / executar_tarefa_ia / chat_agentico
  - orchestrator.run  (SingleAICoreOrchestrator) / run_ai_task

Para cada chamada reporta arquivo:linha, a funcao chamadora (unidade = funcao ou
metodo mais externo que contem a chamada) e flags objetivas, verificaveis no AST:

  usa_orquestrador : a unidade chama orchestrator.run / run_ai_task
  registra_log     : a unidade chama registrar_ai_log / registrar_log_resposta
  citacoes         : a unidade chama validate_citations / validar_citacoes /
                     verificar_citacoes / aplicar_gate_hitl / avaliar_bloqueantes*

Valores das flags:

  sim              provado: ha chamada direta no corpo da unidade
  indireto         a unidade chama funcao do MESMO modulo que contem a chamada
  nao_determinado  nao ha prova no corpo, mas a unidade chama simbolos de app.*
                   (ou usa getattr/despacho dinamico) que poderiam delegar
  nao              ausente no corpo e a unidade nao chama nenhum simbolo de app.*
                   fora do proprio gateway (ausencia provada ao nivel do AST)

Nao infere semantica juridica: so presenca sintatica de chamadas. Nao importa
nem executa o codigo analisado. Uso:

    python scripts/inventario_chamadores_ia.py [--raiz app] [--formato json|md|ambos]
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path

GW = "app.services.ai_gateway"
ORCH_MOD = "app.services.ai.core.orchestrator"

# nome canonico completo -> rotulo do alvo
ALVOS: dict[str, str] = {
    f"{GW}.chat": "ai_gateway.chat",
    f"{GW}.executar_tarefa_ia": "ai_gateway.executar_tarefa_ia",
    f"{GW}.chat_agentico": "ai_gateway.chat_agentico",
    f"{ORCH_MOD}.orchestrator.run": "orchestrator.run",
    f"{ORCH_MOD}.run_ai_task": "run_ai_task",
}
ALVOS_ORQUESTRADOR = {"orchestrator.run", "run_ai_task"}

NOMES_LOG = {"registrar_ai_log", "registrar_log_resposta"}
NOMES_CITACAO = {
    "validate_citations",
    "validar_citacoes",
    "verificar_citacoes",
    "aplicar_gate_hitl",
    "avaliar_bloqueantes",
    "avaliar_bloqueantes_pertinencia",
}
# Modulos de app.* cujas chamadas nao podem delegar governanca de IA.
PREFIXOS_NEUTROS = ("app.models", "app.schemas")


def _modulo_de(caminho: Path, raiz_pkg: Path) -> str:
    rel = caminho.relative_to(raiz_pkg.parent).with_suffix("")
    partes = list(rel.parts)
    if partes[-1] == "__init__":
        partes.pop()
    return ".".join(partes)


def _mapa_imports(arvore: ast.AST, modulo: str, eh_pacote: bool) -> dict[str, str]:
    """nome local -> caminho pontilhado absoluto (imports em qualquer nivel)."""
    mapa: dict[str, str] = {}
    pacote = modulo if eh_pacote else modulo.rpartition(".")[0]
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for a in no.names:
                if a.asname:
                    mapa[a.asname] = a.name
                else:
                    mapa[a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(no, ast.ImportFrom):
            if no.level:
                base = pacote.split(".")
                if no.level > 1:
                    base = base[: len(base) - (no.level - 1)]
                alvo = ".".join(base + ([no.module] if no.module else []))
            else:
                alvo = no.module or ""
            for a in no.names:
                if a.name == "*":
                    continue
                mapa[a.asname or a.name] = f"{alvo}.{a.name}" if alvo else a.name
    return mapa


def _cadeia(no: ast.AST) -> list[str] | None:
    """a.b.c -> ['a','b','c']; None se a raiz nao for um Name."""
    partes: list[str] = []
    while isinstance(no, ast.Attribute):
        partes.append(no.attr)
        no = no.value
    if isinstance(no, ast.Name):
        partes.append(no.id)
        return list(reversed(partes))
    return None


def _resolver(cadeia: list[str], mapa: dict[str, str], modulo: str, locais: set[str]) -> str | None:
    raiz = cadeia[0]
    if raiz in mapa:
        return ".".join([mapa[raiz], *cadeia[1:]])
    if raiz in locais:  # funcao definida no proprio modulo (ex.: dentro do gateway)
        return ".".join([modulo, *cadeia])
    return None


class _Unidade:
    __slots__ = ("nome", "no", "chamadas")

    def __init__(self, nome: str, no: ast.AST | None):
        self.nome = nome
        self.no = no
        self.chamadas: list[tuple[ast.Call, str | None, list[str] | None]] = []


def _unidades(arvore: ast.Module) -> list[_Unidade]:
    """Funcoes/metodos mais externos (classes so entram como prefixo) + <modulo>.

    Chamadas fora de qualquer funcao (nivel de modulo/classe) vao para <modulo>.
    """
    res: list[_Unidade] = []
    modulo_u = _Unidade("<modulo>", None)

    def visitar(no: ast.AST, prefixo: str):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            u = _Unidade(prefixo + no.name, no)
            u.chamadas = [(c, None, None) for c in ast.walk(no) if isinstance(c, ast.Call)]
            res.append(u)
            return
        if isinstance(no, ast.ClassDef):
            prefixo = prefixo + no.name + "."
        elif isinstance(no, ast.Call):
            modulo_u.chamadas.append((no, None, None))
        for filho in ast.iter_child_nodes(no):
            visitar(filho, prefixo)

    visitar(arvore, "")
    res.append(modulo_u)
    return res


def _seguir_reexports(completo: str, reexports: dict[str, str]) -> str:
    """Segue re-exports (`from x import y as z` em outro modulo), ate 3 saltos."""
    for _ in range(3):
        partes = completo.split(".")
        for i in range(len(partes), 1, -1):
            alvo = reexports.get(".".join(partes[:i]))
            if alvo:
                completo = ".".join([alvo, *partes[i:]])
                break
        else:
            return completo
    return completo


def analisar_fonte(
    fonte: str,
    caminho_rel: str,
    modulo: str,
    eh_pacote: bool = False,
    reexports: dict[str, str] | None = None,
) -> list[dict]:
    """Analisa um modulo; devolve um registro por chamada-alvo encontrada."""
    reexports = reexports or {}
    arvore = ast.parse(fonte, filename=caminho_rel)
    mapa = _mapa_imports(arvore, modulo, eh_pacote)
    locais = {
        n.name
        for n in arvore.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    unidades = _unidades(arvore)

    # Calculo por unidade (resolvido uma vez).
    info: dict[str, dict] = {}
    for u in unidades:
        alvos: list[tuple[int, str]] = []
        nomes: set[str] = set()
        chamados_locais: set[str] = set()
        delega_app = False
        dinamico = False
        for call, _, _ in u.chamadas:
            cad = _cadeia(call.func)
            if cad is None:
                continue
            ultimo = cad[-1]
            nomes.add(ultimo)
            if cad[0] in ("getattr",) and len(cad) == 1:
                dinamico = True
            if len(cad) == 1 and cad[0] in locais:
                chamados_locais.add(cad[0])
            if cad[0] in ("self", "cls") and len(cad) == 2:
                chamados_locais.add(cad[1])
            completo = _resolver(cad, mapa, modulo, locais)
            if completo:
                completo = _seguir_reexports(completo, reexports)
            if completo in ALVOS:
                alvos.append((call.lineno, ALVOS[completo]))
            elif completo and completo.startswith("app.") and not completo.startswith(PREFIXOS_NEUTROS):
                delega_app = True
        info[u.nome] = {
            "alvos": alvos,
            "nomes": nomes,
            "locais": chamados_locais,
            "delega_app": delega_app,
            "dinamico": dinamico,
        }

    def tem(nome_unidade: str, conjunto: set[str]) -> bool:
        return bool(info[nome_unidade]["nomes"] & conjunto)

    def orquestra(nome_unidade: str) -> bool:
        return any(rot in ALVOS_ORQUESTRADOR for _, rot in info[nome_unidade]["alvos"])

    por_nome_curto: dict[str, list[str]] = {}
    for n in info:
        por_nome_curto.setdefault(n.rsplit(".", 1)[-1], []).append(n)

    def classificar(nome_unidade: str, direto) -> str:
        if direto(nome_unidade):
            return "sim"
        for chamado in info[nome_unidade]["locais"]:
            for cand in por_nome_curto.get(chamado, []):
                if cand != nome_unidade and direto(cand):
                    return "indireto"
        d = info[nome_unidade]
        if d["delega_app"] or d["dinamico"]:
            return "nao_determinado"
        return "nao"

    registros: list[dict] = []
    for nome, d in info.items():
        for linha, rotulo in d["alvos"]:
            registros.append(
                {
                    "arquivo": caminho_rel,
                    "linha": linha,
                    "funcao": nome,
                    "alvo": rotulo,
                    "usa_orquestrador": classificar(nome, orquestra),
                    "registra_log": classificar(nome, lambda n: tem(n, NOMES_LOG)),
                    "citacoes": classificar(nome, lambda n: tem(n, NOMES_CITACAO)),
                }
            )
    return registros


def inventariar(raiz: Path) -> tuple[list[dict], list[str]]:
    """Varre `raiz` (diretorio `app`). Devolve (registros, erros_de_parse)."""
    registros: list[dict] = []
    erros: list[str] = []
    fontes: list[tuple[str, str, str, bool]] = []
    reexports: dict[str, str] = {}
    for caminho in sorted(raiz.rglob("*.py")):
        rel = caminho.relative_to(raiz.parent).as_posix()
        try:
            fonte = caminho.read_text(encoding="utf-8")
            modulo = _modulo_de(caminho, raiz)
            eh_pacote = caminho.name == "__init__.py"
            mapa = _mapa_imports(ast.parse(fonte, filename=rel), modulo, eh_pacote)
            for nome, alvo in mapa.items():
                reexports[f"{modulo}.{nome}"] = alvo
            fontes.append((fonte, rel, modulo, eh_pacote))
        except (SyntaxError, UnicodeDecodeError) as exc:
            erros.append(f"{rel}: {exc}")
    for fonte, rel, modulo, eh_pacote in fontes:
        registros += analisar_fonte(fonte, rel, modulo, eh_pacote, reexports)
    registros.sort(key=lambda r: (r["arquivo"], r["linha"]))
    return registros, erros


def _nucleo(arquivo: str) -> bool:
    return arquivo in ("app/services/ai_gateway.py",) or arquivo.startswith("app/services/ai/core/")


def resumir(registros: list[dict]) -> dict:
    externos = [r for r in registros if not _nucleo(r["arquivo"])]
    unidades_ext = {(r["arquivo"], r["funcao"]) for r in externos}
    arquivos_ext = {r["arquivo"] for r in externos}

    def unidades(filtro) -> int:
        return len({(r["arquivo"], r["funcao"]) for r in externos if filtro(r)})

    def arquivos(filtro) -> int:
        return len({r["arquivo"] for r in externos if filtro(r)})

    return {
        "pontos_de_chamada_total": len(registros),
        "pontos_de_chamada_fora_do_nucleo": len(externos),
        "arquivos_fora_do_nucleo": len(arquivos_ext),
        "funcoes_chamadoras_fora_do_nucleo": len(unidades_ext),
        "arquivos_por_alvo": {
            a: arquivos(lambda r, a=a: r["alvo"] == a) for a in sorted({r["alvo"] for r in externos})
        },
        "arquivos_com_orquestrador": arquivos(lambda r: r["alvo"] in ALVOS_ORQUESTRADOR),
        "arquivos_com_chamada_direta_ao_gateway": arquivos(lambda r: r["alvo"] not in ALVOS_ORQUESTRADOR),
        "funcoes_por_flag": {
            flag: dict(
                sorted(
                    Counter(
                        v
                        for v in (
                            next(r[flag] for r in externos if (r["arquivo"], r["funcao"]) == k)
                            for k in unidades_ext
                        )
                    ).items()
                )
            )
            for flag in ("usa_orquestrador", "registra_log", "citacoes")
        },
    }


def tabela_markdown(registros: list[dict]) -> str:
    cab = "| Arquivo:linha | Funcao | Alvo | Orquestrador | Log | Citacoes |\n|---|---|---|---|---|---|\n"
    linhas = [
        f"| `{r['arquivo']}:{r['linha']}` | `{r['funcao']}` | `{r['alvo']}` | "
        f"{r['usa_orquestrador']} | {r['registra_log']} | {r['citacoes']} |"
        for r in registros
    ]
    return cab + "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raiz", default=str(Path(__file__).resolve().parents[1] / "app"))
    ap.add_argument("--formato", choices=("json", "md", "ambos"), default="ambos")
    args = ap.parse_args(argv)

    registros, erros = inventariar(Path(args.raiz))
    saida = {"resumo": resumir(registros), "erros_de_parse": erros, "chamadas": registros}
    if args.formato in ("json", "ambos"):
        print(json.dumps(saida, ensure_ascii=False, indent=2))
    if args.formato in ("md", "ambos"):
        print(tabela_markdown(registros))
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
