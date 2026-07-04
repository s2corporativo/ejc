# ── app/core/api_key_auth.py ─────────────────────────────────────────────────
# Autenticação por API key de serviço (header X-API-Key) — Fase 2 IA/RAG.
#
# Uso: integradores externos (n8n, scripts) que abastecem a base de
# conhecimento sem um usuário JWT. A chave em claro segue o padrão dos tokens
# de reset de senha do projeto (security_service.py): `secrets.token_urlsafe`
# + SHA-256 hex no banco — NUNCA armazenada em claro.
#
# Segurança:
#   - lookup por hash (índice único) + comparação constant-time (hmac);
#   - 401 para chave ausente/desconhecida/revogada/inativa;
#   - 403 para chave válida sem o escopo exigido;
#   - `last_used_at` atualizado a cada uso (auditoria de chaves órfãs).
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.api_key import ApiKey

PREFIXO_CHAVE = "ejc_"


def gerar_chave() -> tuple[str, str, str]:
    """Gera uma chave nova. Retorna (chave_em_claro, hash_sha256, prefixo).

    A chave em claro só existe neste momento — o chamador deve exibi-la UMA
    única vez ao admin; o banco guarda apenas o hash e o prefixo.
    """
    chave = PREFIXO_CHAVE + secrets.token_urlsafe(32)
    return chave, hash_chave(chave), chave[:12]


def hash_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def require_api_key(escopo: str):
    """Dependency factory: valida o header X-API-Key e exige o escopo dado.

    `dependencies=[Depends(require_api_key("knowledge:write"))]` ou como
    parâmetro para receber o objeto ApiKey autenticado.
    """

    async def _dep(
        x_api_key: str | None = Header(
            default=None, alias="X-API-Key",
            description="Chave de API de serviço (formato ejc_...)",
        ),
        db: AsyncSession = Depends(get_db),
    ) -> ApiKey:
        exc = HTTPException(
            status_code=401,
            detail="API key ausente, inválida ou revogada",
            headers={"WWW-Authenticate": "ApiKey"},
        )
        if not x_api_key:
            raise exc

        h = hash_chave(x_api_key)
        ak = (await db.execute(
            select(ApiKey).where(ApiKey.chave_hash == h)
        )).scalar_one_or_none()
        # Comparação constant-time do hash (defesa em profundidade — o lookup
        # por índice já é por igualdade exata, mas não deixamos a resposta
        # depender de comparação não-constante em Python).
        if ak is None or not hmac.compare_digest(ak.chave_hash, h):
            raise exc
        if not ak.ativo or ak.revoked_at is not None:
            raise exc
        if escopo not in ak.escopos():
            raise HTTPException(
                status_code=403,
                detail=f"API key sem o escopo exigido: {escopo}",
            )

        ak.last_used_at = datetime.now(timezone.utc)
        await db.commit()
        return ak

    return _dep
