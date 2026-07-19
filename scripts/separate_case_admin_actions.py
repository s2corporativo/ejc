#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "frontend/src/pages/CasoDetalhe.tsx"
t = p.read_text(encoding="utf-8")

start_marker = '        {caso.status !== "encerrado" && caso.status !== "arquivado" && ('
end_marker = '        <Link\n          to={`/raio-x?case_id=${caso.id}`}'
if t.count(start_marker) != 1 or t.count(end_marker) != 1:
    raise SystemExit("marcadores das ações administrativas não são únicos")
start = t.index(start_marker)
end = t.index(end_marker, start)
admin = t[start:end]
t = t[:start] + t[end:]

anchor = '      </div>\n\n      <AreasCaso caso={caso} />'
if t.count(anchor) != 1:
    raise SystemExit(f"âncora final esperada 1 vez, encontrada {t.count(anchor)}")
indented = '\n'.join(('    ' + line) if line else line for line in admin.rstrip().splitlines())
container = f'''        <div\n          className="basis-full mt-2 rounded-xl border border-slate-200 bg-slate-50 p-3"\n          aria-label="Encerramento e administração do caso"\n        >\n          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">\n            Encerramento e administração\n          </div>\n          <div className="flex flex-wrap gap-2">\n{indented}\n          </div>\n        </div>\n      </div>\n\n      <AreasCaso caso={{caso}} />'''
t = t.replace(anchor, container, 1)
p.write_text(t, encoding="utf-8")
