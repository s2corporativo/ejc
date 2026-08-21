from __future__ import annotations

from pathlib import Path

PATCH = Path("scripts/pr1199_v4_patch.py")
source = PATCH.read_text(encoding="utf-8")
old = '''replace_once(
    "backend/app/routers/legal_docs.py",
    '    escopo_cli = None\\n    if d.case_id:\\n',
    '    escopo_cli = getattr(d, "client_id", None)\\n    if d.case_id:\\n',
)
'''
new = '''_p = "backend/app/routers/legal_docs.py"
_text = read(_p)
_old_scope = '    escopo_cli = None\\n    if d.case_id:\\n'
_new_scope = '    escopo_cli = getattr(d, "client_id", None)\\n    if d.case_id:\\n'
_scope_count = _text.count(_old_scope)
if _scope_count != 2:
    raise SystemExit(
        f"{_p}: esperado 2 escopos de validação, encontrados {_scope_count}"
    )
write(_p, _text.replace(_old_scope, _new_scope))
'''
if source.count(old) != 1:
    raise SystemExit("bloco de escopo a ajustar não é único no patch v4")
source = source.replace(old, new, 1)
exec(compile(source, str(PATCH), "exec"), {"__name__": "__main__"})
Path("scripts/pr1199_v4_runner.py").unlink(missing_ok=True)
