"""Expõe `logger` ao bloco consolidado de app/routers/ai.py (o bloco usa
`logger.exception(...)` mas o módulo define `_logger`). Alias mínimo e
localizado logo antes do primeiro uso. 12/08/2026."""
p = "/home/ubuntu/ejc/backend/app/routers/ai.py"
s = open(p, encoding="utf-8").read()
if "logger = _logger" not in s:
    idx = s.find("CONSOLIDAÇ")
    if idx == -1:
        # localizar início do bloco consolidado (primeiro `import` do bloco)
        idx = s.find("from app.core.config import get_settings as _get_settings_consolidacao")
    linha = s.find("\n", idx)
    s = s[:linha] + "\nlogger = _logger  # alias para o bloco consolidado\n" + s[linha:]
    open(p, "w", encoding="utf-8").write(s)
    print("logger aliased")
else:
    print("já aliased")
