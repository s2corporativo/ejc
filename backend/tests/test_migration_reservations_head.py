import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]
LEDGER = BACKEND_DIR / "alembic" / "MIGRATION_RESERVATIONS.md"


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def _ledger_text() -> str:
    return LEDGER.read_text(encoding="utf-8")


def _head_esperado_na_arvore(text: str) -> str:
    branch_match = re.search(
        r"\*\*Head esperado nesta árvore após as migrations do branch:\*\* `([^`]+)`",
        text,
    )
    if branch_match:
        return branch_match.group(1)
    main_match = re.search(
        r"\*\*Head canônico atual da `main`:\*\* `([^`]+)`",
        text,
    )
    assert main_match, "MIGRATION_RESERVATIONS.md precisa declarar o head canônico atual"
    return main_match.group(1)


def test_head_documentado_iguala_head_real_do_alembic():
    assert _script_directory().get_heads() == [_head_esperado_na_arvore(_ledger_text())]


def test_proximo_prefixo_e_sucessor_do_head():
    text = _ledger_text()
    head = _head_esperado_na_arvore(text)
    next_match = re.search(r"\*\*Próximo prefixo livre(?: nesta árvore)?:\*\* `(\d+)`", text)
    assert next_match
    head_prefix = int(head.split("_", 1)[0])
    assert int(next_match.group(1)) == head_prefix + 1


def test_migration_148_antiga_esta_explicitamente_revogada():
    text = _ledger_text()
    assert "`148_banco_teses_juridicas`" in text
    assert "Revogada / aposentada" in text
    assert "Não reutilizar 148" in text
