"""Lista rotas OpenAPI relacionadas a movimentos/andamentos/sincronizar."""
import json
import subprocess

out = subprocess.run(['curl', '-sS', '-m', '8',
                      'http://127.0.0.1:8000/api/openapi.json'],
                     capture_output=True, text=True)
spec = json.loads(out.stdout)
paths = spec.get('paths', {})
found = [p for p in paths if ('movimento' in p or 'sincronizar' in p
                              or 'andamentos' in p)]
print('total paths:', len(paths), '| movimentos-like:', len(found))
for p in sorted(found):
    for m in paths[p]:
        print(m.upper(), p)
