# ── app/services/ajuizamento/auditoria.py ────────────────────────────────────
# Trilha de auditoria do ajuizamento sobre o AuditLog existente (WORM, LGPD
# art. 37). Registra quem preparou/aprovou/assinou/protocolou, quando, IP
# (capturado pelo ClientIPMiddleware), destino/tribunal, campos transmitidos
# (nomes, nunca valores de PII), hashes e resultado. CPF/CNPJ nunca em claro.
from __future__ import annotations

from typing import Any

from app.models.audit_log import criar_audit_log

ENTIDADE = "judicial_filings"
ENTIDADE_PERFIL = "judicial_integration_profiles"

# acao é String(30) no AuditLog.
ACAO_CRIAR = "AJUIZ_CRIAR"
ACAO_ATUALIZAR = "AJUIZ_ATUALIZAR"
ACAO_VALIDAR = "AJUIZ_VALIDAR"
ACAO_APROVAR = "AJUIZ_APROVAR"
ACAO_ASSINAR = "AJUIZ_ASSINAR"
ACAO_PROTOCOLAR = "AJUIZ_PROTOCOLAR"
ACAO_CONFIRMAR = "AJUIZ_CONFIRMAR"
ACAO_SINCRONIZAR = "AJUIZ_SINCRONIZAR"
ACAO_CANCELAR = "AJUIZ_CANCELAR"
ACAO_PERFIL = "AJUIZ_PERFIL"

_CHAVES_SENSIVEIS = ("documento", "cpf", "cnpj", "senha", "secret", "token", "access_token", "client_secret")


def sanitizar(dados: Any) -> Any:
    """Remove recursivamente valores de chaves sensíveis antes do WORM."""
    if isinstance(dados, dict):
        saida = {}
        for k, v in dados.items():
            kl = str(k).lower()
            if any(s in kl for s in _CHAVES_SENSIVEIS) and not kl.endswith(("_mascarado", "_hash", "_ref", "_id")):
                saida[k] = "[redigido]"
            else:
                saida[k] = sanitizar(v)
        return saida
    if isinstance(dados, (list, tuple)):
        return [sanitizar(i) for i in dados]
    return dados


async def auditar(
    db, cu, acao: str, registro_id: str, *, detalhes: str | None = None,
    dados_antes: dict | None = None, dados_depois: dict | None = None, entidade: str = ENTIDADE,
) -> None:
    role = getattr(getattr(cu, "role", None), "value", None) or str(getattr(cu, "role", "") or "")
    await criar_audit_log(
        db, getattr(cu, "id", None), role, acao, entidade, registro_id,
        detalhes=(detalhes or "")[:4000] or None,
        dados_antes=sanitizar(dados_antes) if dados_antes else None,
        dados_depois=sanitizar(dados_depois) if dados_depois else None,
    )
