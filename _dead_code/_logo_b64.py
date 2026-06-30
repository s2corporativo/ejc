# ── app/services/_logo_b64.py ─────────────────────────────────────────────────
# Carrega a logomarca De Paula Teixeira de app/assets/logo.png e expõe em base64
# para a geração de PDF (WeasyPrint). O binário NÃO fica embutido no código.
import base64
import os
from functools import lru_cache

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")


@lru_cache(maxsize=1)
def _carregar_logo_b64() -> str:
    try:
        with open(os.path.abspath(_LOGO_PATH), "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""  # ausência do logo nunca pode derrubar a geração de PDF


# Símbolo público mantido para compatibilidade com pdf_service.
LOGO_B64 = _carregar_logo_b64()
