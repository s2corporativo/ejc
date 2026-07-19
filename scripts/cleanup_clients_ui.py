#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "frontend/src/pages/Clientes.tsx"
t = p.read_text(encoding="utf-8")

changes = {
    'placeholder="Senha inicial (mín. 8)"': 'placeholder="Senha inicial (mín. 10, com letra, número e símbolo)"',
    'toast.error(\n                      "Acesso criado! Informe o e-mail e a senha inicial ao cliente.",\n                    );': 'toast.success(\n                      "Acesso criado! Informe o e-mail e a senha inicial ao cliente.",\n                    );',
}
for old, new in changes.items():
    count = t.count(old)
    if count != 1:
        raise SystemExit(f"marcador esperado 1 vez, encontrado {count}: {old[:40]}")
    t = t.replace(old, new, 1)

p.write_text(t, encoding="utf-8")
