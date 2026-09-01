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


def _head_documentado(text: str) -> str | None:
    """Lê o head efetivo do checkout sem obrigar PR a chamar sua branch de main."""
    for padrao in (
        r"\*\*Head canônico desta branch:\*\* `([^`]+)`",
        r"\*\*Head canônico atual da `main`:\*\* `([^`]+)`",
    ):
        match = re.search(padrao, text)
        if match:
            return match.group(1)
    return None


def _proximo_prefixo(text: str) -> int | None:
    for padrao in (
        r"\*\*Próximo prefixo livre após esta branch:\*\* `(\d+)`",
        r"\*\*Próximo prefixo livre:\*\* `(\d+)`",
    ):
        match = re.search(padrao, text)
        if match:
            return int(match.group(1))
    return None


def test_head_documentado_iguala_head_real_do_alembic():
    head = _head_documentado(_ledger_text())
    assert head, "MIGRATION_RESERVATIONS.md precisa declarar o head canônico do checkout"
    assert _script_directory().get_heads() == [head]


def test_proximo_prefixo_e_sucessor_do_head():
    text = _ledger_text()
    head = _head_documentado(text)
    proximo = _proximo_prefixo(text)
    assert head and proximo is not None
    head_prefix = int(head.split("_", 1)[0])
    assert proximo == head_prefix + 1


def test_branch_estrutural_pode_registrar_base_main_sem_confundir_heads():
    text = _ledger_text()
    base = re.search(r"\*\*Head de base confirmado na `main`:\*\* `([^`]+)`", text)
    if base:
        head = _head_documentado(text)
        assert head is not None
        revision = _script_directory().get_revision(head)
        assert revision is not None
        assert revision.down_revision == base.group(1)


def test_migration_148_antiga_esta_explicitamente_revogada():
    text = _ledger_text()
    assert "`148_banco_teses_juridicas`" in text
    assert "Revogada / aposentada" in text
    assert "Não reutilizar 148" in text
