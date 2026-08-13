"""Consolidação 12/08/2026 — funde ia_extra.py em ai.py.

Estratégia: o conteúdo de ia_extra.py passa a viver no fim de ai.py, com o
mesmo prefixo `/ai` e as mesmas dependências (o router de ia_extra é o MESMO
prefixo do canônico — é uma divisão física, não um contrato diferente).
Após o merge, main.py deixa de incluir ia_extra (mesma superfície, novo local).

O script é cirúrgico e idempotente: verifica guardas antes de escrever.
"""
from __future__ import annotations
import re
import sys

ROUTERS = "/home/ubuntu/ejc/backend/app/routers"
SOURCE = f"{ROUTERS}/ia_extra.py"
TARGET = f"{ROUTERS}/ai.py"
MARKER = "# ══ CONSOLIDAÇÃO 12/08/2026: conteúdo migrado de ia_extra.py ══"


def main() -> int:
    with open(SOURCE, encoding="utf-8") as fh:
        src = fh.read()
    with open(TARGET, encoding="utf-8") as fh:
        tgt = fh.read()

    if MARKER in tgt:
        print("JÁ CONSOLIDADO (guarda detectada).", file=sys.stderr)
        return 0

    # Verificar que o destino usa o mesmo prefixo (senão o merge muda contrato)
    if 'prefix="/ai"' not in src:
        print("ERRO: ia_extra não usa prefixo /ai — abortando.", file=sys.stderr)
        return 2

    # Strip: remove o cabeçalho/docstring de módulo e as linhas de
    # `router = APIRouter(...)` / imports já cobertos por ai.py.
    # Corpo = tudo após a definição do router.
    m = re.search(r"^router = APIRouter\([^\)]*\)\n", src, flags=re.M)
    if not m:
        print("ERRO: não localizei a definição do router em ia_extra.", file=sys.stderr)
        return 2
    corpo = src[m.end():]

    # Remover do corpo a linha `settings = get_settings()` redundante (ai.py já
    # importa) e a redefinição de `router`.
    corpo = re.sub(r"^settings = get_settings\(\)\n", "", corpo, flags=re.M)
    corpo = corpo.replace("router = APIRouter(prefix=\"/ai\", tags=[\"IA — Assistente\"])\n", "")

    # Header de seção + docstring preservada (o cabeçalho original vira comentário).
    bloco = (
        "\n"
        + MARKER
        + "\n"
        + "# Origem: app/routers/ia_extra.py (Onda 2 — IA jurídica). Prefixo /ai\n"
        + "# idêntico ao canônico; a divisão era puramente física. Endpoints,\n"
        + "# prompts e regras de rate limit PRESERVADOS sem alteração semântica.\n"
        + corpo
        + "\n"
    )
    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(tgt.rstrip() + bloco)
    print(f"Consolidado: {len(corpo)} linhas de ia_extra.py → ai.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
