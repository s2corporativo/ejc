"""Paridade Settings ⊆ .env.example (F3 da análise E2E 03/09/2026).

Todo campo de `Settings` precisa ter uma entrada `NOME=` (ou `# NOME=`) no
`.env.example`; sem isso o operador não tem onde descobrir o nome da variável
(caso real: AUD27-P1-5 mandava "religar RAG_AUTO_REEMBED_ENABLED" e a
variável não estava documentada). O inverso (entrada no exemplo sem campo)
é tolerado: variáveis de nível compose/container vivem lá de propósito.
"""
from __future__ import annotations

import os
import re

from app.core.config import Settings

# Campos internos/derivados — não são configuração de operador.
_ALLOWLIST = {
    "ALGORITHM",          # JWT fixo (HS256), não configurável
    "APP_NAME",
    "APP_VERSION",
    "DATABASE_URL",       # derivado de POSTGRES_* pelo compose
    "DATABASE_URL_SYNC",  # idem
    "UPLOAD_DIR",         # caminho interno do container
}


def _chaves_env_example() -> set[str]:
    raiz = os.path.join(os.path.dirname(__file__), "..", "..")
    with open(os.path.join(raiz, ".env.example"), encoding="utf-8") as fh:
        conteudo = fh.read()
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", conteudo, re.M))


def test_todo_campo_de_settings_esta_documentado_no_env_example():
    chaves = _chaves_env_example()
    faltantes = sorted(
        nome
        for nome in Settings.model_fields
        if nome.isupper() and nome not in chaves and nome not in _ALLOWLIST
    )
    assert not faltantes, (
        "Campos de Settings sem entrada no .env.example (documente com "
        f"comentário e default igual ao do código): {faltantes}"
    )


def test_allowlist_nao_envelhece():
    """Campo da allowlist que deixou de existir em Settings deve sair dela."""
    orfaos = sorted(n for n in _ALLOWLIST if n not in Settings.model_fields)
    assert not orfaos, f"allowlist cita campos inexistentes: {orfaos}"
