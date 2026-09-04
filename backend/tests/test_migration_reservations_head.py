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


def test_head_documentado_iguala_head_real_do_alembic():
    match = re.search(
        r"\*\*Head canônico atual da `main`:\*\* `([^`]+)`",
        _ledger_text(),
    )
    assert match, "MIGRATION_RESERVATIONS.md precisa declarar o head canônico atual"
    assert _script_directory().get_heads() == [match.group(1)]


def test_proximo_prefixo_e_sucessor_do_head():
    text = _ledger_text()
    head_match = re.search(r"\*\*Head canônico atual da `main`:\*\* `([^`]+)`", text)
    next_match = re.search(r"\*\*Próximo prefixo livre:\*\* `(\d+)`", text)
    assert head_match and next_match
    head_prefix = int(head_match.group(1).split("_", 1)[0])
    assert int(next_match.group(1)) == head_prefix + 1


def test_migration_148_antiga_esta_explicitamente_revogada():
    text = _ledger_text()
    assert "`148_banco_teses_juridicas`" in text
    assert "Revogada / aposentada" in text
    assert "Não reutilizar 148" in text
