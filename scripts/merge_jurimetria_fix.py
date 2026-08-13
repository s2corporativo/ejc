"""Consolidação 12/08/2026 — etapa 2: injeta o prelúdio do antigo
jurimetria_extra.py (funções _req_staff/_req_socio + imports ausentes)
imediatamente após o marcador de consolidação em jurimetria.py.

Os nomes recebem sufixo _je para não colidir com o módulo canônico.
"""
from __future__ import annotations
import re
import sys

TARGET = "/home/ubuntu/ejc/backend/app/routers/jurimetria.py"
MARKER = "# ══ CONSOLIDAÇÃO 12/08/2026: conteúdo migrado de jurimetria_extra.py ══"

PRELUDE = """
# ── Prelúdio do módulo consolidado (jurimetria_extra) ───────────────────────
# Cobertura APENAS do bloco `CONSOLIDAÇÃO 12/08/2026` abaixo; não mexer sem
# checar o bloco.
from app.core.security import requer_equipe_juridica as _je_requer_equipe_juridica
from app.services.jurimetria import MIN_AMOSTRA as _je_MIN_AMOSTRA


def _je_req_staff(cu: User = Depends(get_current_user)) -> User:
    # MESMO gate de papel de jurimetria.py (_is_staff = EQUIPE_JURIDICA).
    # Issue #694: allowlist EXATA — financeiro NÃO passa aqui mesmo com
    # ROLE_LEVEL acima de estagiario.
    _je_requer_equipe_juridica(cu, "Acesso restrito à equipe do escritório")
    return cu


def _je_req_socio(cu: User = Depends(get_current_user)) -> User:
    # Métricas de êxito consolidadas = mesmo nível do overview de jurimetria.py.
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Apenas sócios têm acesso a métricas de êxito")
    return cu


"""


def main() -> int:
    with open(TARGET, encoding="utf-8") as fh:
        s = fh.read()
    idx = s.find(MARKER)
    if idx == -1:
        print("ERRO: marcador ausente.", file=sys.stderr)
        return 2
    if "_je_req_socio" in s:
        print("JÁ INJETADO (guarda detectada).", file=sys.stderr)
        return 0

    bloco = s[idx:]
    # Aplicar aliases no corpo consolidado
    subs = [
        ("_req_socio", "_je_req_socio"),
        ("_req_staff", "_je_req_staff"),
        ("MIN_AMOSTRA", "_je_MIN_AMOSTRA"),
    ]
    for old, novo in subs:
        bloco = bloco.replace(old, novo)
    new = s[:idx] + PRELUDE + bloco
    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(new)
    print("Prelúdio injetado no bloco consolidado de jurimetria.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
