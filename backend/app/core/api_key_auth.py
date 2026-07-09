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

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import _consumir
from app.models.api_key import ApiKey
from app.services.security_service import obter_ip_real

PREFIXO_CHAVE = "ejc_"
# Chaves geradas hoje têm cerca de 47 caracteres. O teto abaixo é folgado para
# compatibilidade futura, mas rejeita headers arbitrariamente grandes antes de
# hash/lookup no banco.
MAX_CHAVE_API_CHARS = 128

# Rate limit PRÉ-auth por IP (auditoria M-1): requisições com X-API-Key
# ausente/inválida também consomem cota — sem isso, um atacante brutalizaria
# o lookup de chaves (e o banco) sem nunca ser limitado, pois os limites por
# chave (rag_public) só valem para chave VÁLIDA.
MAX_TENTATIVAS_IP_MIN = 60


def gerar_chave() -> tuple[str, str, str]:
    """Gera uma chave nova. Retorna (chave_em_claro, hash_sha256, prefixo).

    A chave em claro só existe neste momento — o chamador deve exibi-la UMA
    única vez ao admin; o banco guarda apenas o hash e o prefixo.
    """
    chave = PREFIXO_CHAVE + secrets.token_urlsafe(32)
    return chave, hash_chave(chave), chave[:12]


def hash_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def _normalizar_header_api_key(x_api_key: str | None) -> str | None:
    """Validação sintática barata antes de hash e lookup no banco.

    Mantém resposta indistinguível para chave ausente/inválida, mas evita que
    headers gigantes ou formatos claramente alheios ao padrão `ejc_...` sejam
    processados até o banco. O `.strip()` tolera espaços acidentais de cópia.
    """
    if not x_api_key:
        return None
    chave = x_api_key.strip()
    if not chave:
        return None
    if len(chave) > MAX_CHAVE_API_CHARS:
        return None
    if not chave.startswith(PREFIXO_CHAVE):
        return None
    return chave


def require_api_key(escopo: str):
    """Dependency factory: valida o header X-API-Key e exige o escopo dado.

    `dependencies=[Depends(require_api_key("knowledge:write"))]` ou como
    parâmetro para receber o objeto ApiKey autenticado.
    """

    async def _dep(
        request: Request,
        x_api_key: str | None = Header(
            default=None, alias="X-API-Key",
            description="Chave de API de serviço (formato ejc_...)",
        ),
        db: AsyncSession = Depends(get_db),
    ) -> ApiKey:
        # ANTES de qualquer lookup no banco: cota por IP real (anti-DoS/brute
        # force pré-auth — auditoria M-1). 429 mesmo sem chave válida.
        _consumir("api_key_preauth",
                  f"ip:{obter_ip_real(request)}", MAX_TENTATIVAS_IP_MIN)

        exc = HTTPException(
            status_code=401,
            detail="API key ausente, inválida ou revogada",
            headers={"WWW-Authenticate": "ApiKey"},
        )
        chave = _normalizar_header_api_key(x_api_key)
        if chave is None:
            raise exc

        h = hash_chave(chave)
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
