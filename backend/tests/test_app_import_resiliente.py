"""Resiliência do import de `app.main` à AUSÊNCIA de SDKs opcionais.

Princípio de design dominante do EJC: tudo que é externo é opt-in (default OFF)
e degrada graciosamente sem derrubar o app. Um SDK opcional ausente
(google-api-python-client, python-docx, fpdf2, beautifulsoup4/lxml) NÃO pode
quebrar `import app.main` na fase de import de módulo — a falha deve ocorrer
apenas quando a função que precisa do SDK é efetivamente chamada.

Estratégia: a simulação de ausência roda em SUBPROCESSO isolado (um meta_path
finder que bloqueia os pacotes-alvo), para não poluir o sys.modules da sessão
pytest — no espírito de fakes locais por arquivo, sem harness global.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]

# Trecho injetado no topo de cada subprocesso: bloqueia os SDKs opcionais
# forçando ImportError em qualquer import (inclusive submódulos).
_BLOQUEADOR = """
import sys

_BLOQUEADOS = {bloqueados!r}

class _BloqueiaSDK:
    def find_spec(self, name, path=None, target=None):
        raiz = name.split(".", 1)[0]
        if raiz in _BLOQUEADOS:
            raise ImportError(f"SDK opcional bloqueado no teste: {{name}}")
        return None

for _m in list(sys.modules):
    if _m.split(".", 1)[0] in _BLOQUEADOS:
        del sys.modules[_m]
sys.meta_path.insert(0, _BloqueiaSDK())
"""


def _rodar_sem_sdks(bloqueados: set[str], corpo: str) -> subprocess.CompletedProcess:
    """Executa `corpo` num subprocesso com `bloqueados` indisponíveis."""
    script = _BLOQUEADOR.format(bloqueados=bloqueados) + textwrap.dedent(corpo)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
    )


# ── (a) import direto, no processo do teste ─────────────────────────────────────
def test_import_app_main_funciona():
    """No ambiente com todos os SDKs, `app.main` importa e expõe `app`."""
    import app.main

    assert app.main.app is not None
    assert type(app.main.app).__name__ == "FastAPI"


def test_modulos_guardados_importam():
    """Os módulos que hard-importavam SDK opcional agora sempre importam."""
    import app.services.backup_drive_auth  # noqa: F401
    import app.services.google_drive_service  # noqa: F401
    import app.services.ingestors.planalto  # noqa: F401
    import app.services.raio_x_export_service  # noqa: F401


# ── (b) ausência simulada dos SDKs opcionais, em subprocesso isolado ────────────
_SDKS_OPCIONAIS = {"google", "googleapiclient", "docx", "fpdf", "bs4"}


def test_app_main_importa_sem_sdks_opcionais():
    """`import app.main` sobe mesmo sem NENHUM dos SDKs opcionais instalados."""
    res = _rodar_sem_sdks(
        _SDKS_OPCIONAIS,
        """
        import app.main
        assert app.main.app is not None
        print("APP_MAIN_OK")
        """,
    )
    assert res.returncode == 0, res.stderr
    assert "APP_MAIN_OK" in res.stdout


def test_funcoes_degradam_graciosamente_sem_sdk():
    """Cada função que exige o SDK levanta RuntimeError claro quando chamada."""
    res = _rodar_sem_sdks(
        _SDKS_OPCIONAIS,
        """
        import app.services.raio_x_export_service as rx
        import app.services.google_drive_service as gdrive
        import app.services.backup_drive_auth as bkp
        import app.services.ingestors.planalto as planalto

        casos = [
            ("raio_x.gerar_pdf", lambda: rx.gerar_pdf("t", {})),
            ("raio_x.gerar_docx", lambda: rx.gerar_docx("t", {})),
            ("gdrive.get_drive_client", gdrive.get_drive_client),
            ("bkp.build_credentials", bkp.build_credentials),
            ("planalto.extrair_texto", lambda: planalto.extrair_texto_planalto("<html></html>")),
        ]
        for nome, fn in casos:
            try:
                fn()
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"{nome} deveria levantar RuntimeError sem o SDK")
        print("DEGRADACAO_OK")
        """,
    )
    assert res.returncode == 0, res.stderr
    assert "DEGRADACAO_OK" in res.stdout
