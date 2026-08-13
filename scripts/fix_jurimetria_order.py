"""Move as defs _req_staff/_req_socio (trazidas do jurimetria_extra.py
consolidado) para ANTES da definição do `router` em jurimetria.py, evitando
NameError em import-time (as rotas do próprio arquivo e outros testes
referem o `router` antes das defs). 12/08/2026."""
import re

p = "/home/ubuntu/ejc/backend/app/routers/jurimetria.py"
s = open(p, encoding="utf-8").read()

# trecho consolidado: do comentário âncora até o fim de def _req_socio
ancora = "# ── Prelúdio do módulo consolidado (jurimetria_extra) ───────────────"
i0 = s.find(ancora)
assert i0 > 0, "âncora não encontrada"
fim = s.find("def _req_socio(cu: User", i0)
fim = s.find("\n", s.find("return cu", fim)) + 1  # fim da def _req_socio
bloco = s[i0:fim]

# retirar o bloco da posição atual
resto = s[:i0] + s[fim:]

# localizar a posição da definição do router
ir = resto.find('router = APIRouter(prefix="/jurimetria"')
assert ir > 0, "router não encontrado"

resto = resto[:ir] + bloco + "\n\n" + resto[ir:]
open(p, "w", encoding="utf-8").write(resto)
print("defs _req_staff/_req_socio movidas para antes do router")
