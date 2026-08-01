"""Compatibilidade temporária do aplicador com Python 3.12.

É carregado apenas pelo processo do patcher em scripts/maintenance e remove a
si próprio ao terminar. Não integra a aplicação EJC. O arquivo existe somente
para materializar o commit funcional e será excluído no mesmo fluxo.
"""
from __future__ import annotations

import atexit
from pathlib import Path
import re
import sys

_original_subn = re.subn


def _subn_preservando_reposicao(pattern, repl, string, count=0, flags=0):
    try:
        return _original_subn(pattern, repl, string, count=count, flags=flags)
    except re.error as exc:
        if not isinstance(repl, str) or "bad escape" not in str(exc):
            raise
        return _original_subn(
            pattern,
            lambda _match: repl,
            string,
            count=count,
            flags=flags,
        )


re.subn = _subn_preservando_reposicao

if any("apply_legal_doc_flow_fix.py" in arg for arg in sys.argv):
    _self = Path(__file__)
    atexit.register(lambda: _self.unlink(missing_ok=True))
