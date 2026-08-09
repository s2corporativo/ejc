"""As migrations reais novas precisam passar no mesmo gate usado no deploy.

O classificador de compatibilidade nasceu depois de boa parte do histórico do
Alembic; por isso a regressão funciona como catraca a partir da revisão 132.
Uma migration nova que reprovar aqui também reprovaria a produção somente após
o merge, situação que este teste impede.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_migration_compatibility.py"
VERSIONS = ROOT / "backend" / "alembic" / "versions"

SPEC = importlib.util.spec_from_file_location("migration_gate_real", SCRIPT)
assert SPEC and SPEC.loader
_modulo = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = _modulo
SPEC.loader.exec_module(_modulo)

PRIMEIRA_REVISAO_SOB_A_CATRACA = 132


def _numeradas() -> list[tuple[int, Path]]:
    saida: list[tuple[int, Path]] = []
    for caminho in sorted(VERSIONS.glob("*.py")):
        casa = re.match(r"(\d+)_", caminho.name)
        if casa:
            saida.append((int(casa.group(1)), caminho))
    return saida


def test_a_catraca_alcanca_alguma_migration():
    numeros = [n for n, _ in _numeradas()]
    assert numeros
    assert max(numeros) >= PRIMEIRA_REVISAO_SOB_A_CATRACA


def test_migrations_novas_passam_no_gate_de_deploy():
    revisoes = {rev.path: rev for rev in _modulo._load_revisions(VERSIONS).values()}
    reprovadas: list[str] = []
    conferidas = 0

    for numero, caminho in _numeradas():
        if numero < PRIMEIRA_REVISAO_SOB_A_CATRACA:
            continue
        revisao = revisoes.get(caminho)
        assert revisao is not None, f"{caminho.name} não foi carregada pelo gate"
        conferidas += 1
        achados, _politica = _modulo._classify(revisao)
        if achados:
            reprovadas.append(f"{caminho.name}: {'; '.join(achados)}")

    assert conferidas
    assert not reprovadas, (
        "migration reprovada pelo gate real de deploy:\n  "
        + "\n  ".join(reprovadas)
    )


def test_seed_de_tribunais_e_idempotente_por_construcao():
    caminho = VERSIONS / "132_processo_eletronico_mni.py"
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))

    chamadas = {
        _modulo._op_call_name(no)
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
    }
    assert "bulk_insert" not in chamadas

    nomes = {no.id for no in ast.walk(arvore) if isinstance(no, ast.Name)}
    assert "uuid4" not in nomes

    sql = " ".join(
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str)
    ).upper()
    assert "INSERT INTO TRIBUNAIS" in sql
    assert "NOT EXISTS" in sql
    assert _modulo._assignment(arvore, "deployment_policy") == "additive_data_backfill"
    assert _modulo._assignment(arvore, "data_backfill_targets") == ("tribunais",)
