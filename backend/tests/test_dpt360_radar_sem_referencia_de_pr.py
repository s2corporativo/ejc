"""O payload do Radar DPT360 não expõe referências internas de desenvolvimento.

Referência a PR em `dependencias_pendentes` chegava ao usuário final como se
fosse pendência funcional; o gate de vigência normativa do RAG já existe em
`app/services/ai/reranker.py`.
"""
import ast
import re
from pathlib import Path

RADAR = Path(__file__).resolve().parents[1] / "app" / "modules" / "dpt360" / "radar_service.py"
REF_PR = re.compile(r"\bPR\s*#\d+|#\d{3,5}\b")


def _literais(caminho: Path) -> list[str]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    docstrings = {
        id(no.body[0].value)
        for no in ast.walk(arvore)
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and no.body
        and isinstance(no.body[0], ast.Expr)
        and isinstance(no.body[0].value, ast.Constant)
    }
    return [
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in docstrings
    ]


def test_radar_nao_expoe_referencia_de_pr():
    vazados = [s for s in _literais(RADAR) if REF_PR.search(s)]
    assert vazados == []


def test_radar_nao_declara_dependencia_pendente_inexistente():
    fonte = RADAR.read_text(encoding="utf-8")
    assert '"dependencias_pendentes": []' in fonte
