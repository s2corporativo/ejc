"""Consolidação 12/08/2026 — etapa 2: injeta os imports necessários do antigo
ia_extra.py logo após o bloco de consolidação em ai.py.

ai.py já fornece: logging, Optional, APIRouter/Depends/HTTPException, get_db,
get_current_user, User, AILog, AIStatusHITL, rate_limit, AsyncSession.
Faltam (do corpo de ia_extra.py): json, uuid4, BaseModel/Field, AITipoUso,
classificar_risco_ia, buscar_contexto_rag/_modelo_log/_tokens_*, gw_chat,
GatewayResponse, BASE_ESTRUTURADA, sanitizar_pii, sanitizar_ou_abortar,
get_settings.
"""
from __future__ import annotations
import sys

ROUTERS = "/home/ubuntu/ejc/backend/app/routers"
TARGET = f"{ROUTERS}/ai.py"
MARKER = "# ══ CONSOLIDAÇÃO 12/08/2026: conteúdo migrado de ia_extra.py ══"

IMPORTS = """
# ── Imports do módulo consolidado (ia_extra) ────────────────────────────────
# Necessários APENAS pelo bloco consolidado abaixo: não mexer sem checar o
# bloco `CONSOLIDAÇÃO 12/08/2026`.
import json as _json_consolidacao
from uuid import uuid4 as _uuid4_consolidacao
from pydantic import BaseModel as _BaseModel_consolidacao, Field as _Field_consolidacao
from app.core.config import get_settings as _get_settings_consolidacao
from app.models.ai_log import (
    AITipoUso as _AITipoUso_consolidacao,
    classificar_risco_ia as _classificar_risco_ia_consolidacao,
)
from app.services.ai_service import (
    buscar_contexto_rag as _buscar_contexto_rag_consolidacao,
    _modelo_log as _modelo_log_consolidacao,
    _tokens_input as _tokens_input_consolidacao,
    _tokens_output as _tokens_output_consolidacao,
)
from app.services.ai_gateway import (
    chat as _gw_chat_consolidacao,
    GatewayResponse as _GatewayResponse_consolidacao,
)
from app.services.legal_base import BASE_ESTRUTURADA as _BASE_ESTRUTURADA_consolidacao
from app.services.sanitizer import sanitizar_pii as _sanitizar_pii_consolidacao
from app.services.ai_guard import sanitizar_ou_abortar as _sanitizar_ou_abortar_consolidacao
import alias_ia_extra as _alias_ia_extra_consolidacao
"""


def main() -> int:
    with open(TARGET, encoding="utf-8") as fh:
        content = fh.read()

    idx = content.find(MARKER)
    if idx == -1:
        print("ERRO: marcador de consolidação ausente em ai.py", file=sys.stderr)
        return 2
    if "alias_ia_extra" in content:
        print("JÁ INJETADO (guarda alias detectada).", file=sys.stderr)
        return 0

    new = content[: idx] + IMPORTS + content[idx:]
    # Renomear usos dentro do bloco consolidado para os aliases.
    subs = [
        ("json.", "_json_consolidacao."),
        ("uuid4(", "_uuid4_consolidacao("),
        ("BaseModel)", "_BaseModel_consolidacao)"),
        ("BaseModel(", "_BaseModel_consolidacao("),
        ("BaseModel, Field", "_BaseModel_consolidacao, _Field_consolidacao"),
        ("AITipoUso.", "_AITipoUso_consolidacao."),
        ("AITipoUso,", "_AITipoUso_consolidacao,"),
        ("AITipoUso)", "_AITipoUso_consolidacao)"),
        ("classificar_risco_ia(", "_classificar_risco_ia_consolidacao("),
        ("buscar_contexto_rag(", "_buscar_contexto_rag_consolidacao("),
        ("_modelo_log(", "_modelo_log_consolidacao("),
        ("_tokens_input(", "_tokens_input_consolidacao("),
        ("_tokens_output(", "_tokens_output_consolidacao("),
        ("gw_chat(", "_gw_chat_consolidacao("),
        ("GatewayResponse)", "_GatewayResponse_consolidacao)"),
        ("BASE_ESTRUTURADA +", "_BASE_ESTRUTURADA_consolidacao +"),
        ("BASE_ESTRUTURADA,", "_BASE_ESTRUTURADA_consolidacao,"),
        ("sanitizar_pii(", "_sanitizar_pii_consolidacao("),
        ("sanitizar_ou_abortar(", "_sanitizar_ou_abortar_consolidacao("),
        ("settings = get_settings()", "_settings_consolidacao = _get_settings_consolidacao()"),
        ("settings.AI_ENABLED", "_settings_consolidacao.AI_ENABLED"),
        ("settings.GROQ_MODEL", "_settings_consolidacao.GROQ_MODEL"),
    ]
    bloco = new[idx:]
    for old, novo in subs:
        bloco = bloco.replace(old, novo)
    # O alias importado não existe de fato — substituir a linha pelo bloco real.
    new = new.replace("import alias_ia_extra as _alias_ia_extra_consolidacao\n", "")
    new = content[: idx] + IMPORTS.replace("import alias_ia_extra as _alias_ia_extra_consolidacao\n", "") + bloco
    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(new)
    print("Imports injetados no bloco consolidado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
