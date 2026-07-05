# ── app/services/sociedades_service.py ───────────────────────────────────────
# Lógica pura da gestão societária de CLIENTES: máscara de documento (LGPD),
# preparo de PII (reuso de services/pii_crypto — mesmo padrão do models/client.py)
# e cálculo de cap table. Sem dependência de banco — testável isoladamente.
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.services.pii_crypto import normalizar_documento, encrypt, hash_documento


def mascarar_documento(doc: str | None) -> str | None:
    """Máscara de exibição do documento do sócio — ÚNICA forma que sai na API.

    CPF  (11 díg.): ***.456.789-**            (miolo visível, extremos ocultos)
    CNPJ (14 díg.): 12.345.678/****-**        (raiz visível — dado público de PJ)
    Outros tamanhos: mantém só os 4 últimos caracteres visíveis.
    """
    d = normalizar_documento(doc)
    if not d:
        return None
    if len(d) == 11:   # CPF
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:   # CNPJ
        return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/****-**"
    return "*" * max(len(d) - 4, 1) + d[-4:]


def preparar_documento_socio(doc: str | None) -> dict:
    """Campos LGPD do documento do sócio (padrão Bloco 6a de clients):
    ciphertext Fernet + índice cego HMAC + máscara de exibição.
    Texto puro NUNCA integra o retorno além do necessário para gravação segura."""
    d = normalizar_documento(doc)
    return {
        "documento_enc": encrypt(d),
        "documento_hash": hash_documento(d),
        "documento_mascarado": mascarar_documento(d),
    }


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v)) if v is not None else Decimal("0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def calcular_percentual(quotas, total_quotas) -> float:
    """% de participação sobre o total de quotas DECLARADAS no quadro."""
    q, t = _dec(quotas), _dec(total_quotas)
    if t <= 0:
        return 0.0
    return round(float(q / t * 100), 2)


def montar_cap_table(capital_social, quotas_socios: list) -> dict:
    """Cap table da sociedade.

    alerta_percentual: no padrão brasileiro (LTDA/SLU/SS) o capital social se
    divide em quotas — normalmente 1 quota = R$ 1,00. Se a soma das quotas
    declaradas dos sócios diverge do capital social registrado, ou o quadro
    está incompleto (sócio não cadastrado) ou o capital/quotas foi digitado
    errado — os percentuais calculados podem não refletir o contrato social.
    None = sem divergência detectável (inclui capital não informado).
    """
    total = sum((_dec(q) for q in quotas_socios), Decimal("0"))
    capital = _dec(capital_social) if capital_social is not None else None

    alerta = None
    if capital is not None and capital > 0 and total != capital:
        alerta = (
            f"Soma das quotas declaradas ({total}) difere do capital social "
            f"({capital}). Quadro societário possivelmente incompleto ou "
            f"valores divergentes do contrato social — os percentuais são "
            f"calculados sobre as quotas declaradas."
        )

    return {
        "total_quotas": float(total),
        "capital_social": float(capital) if capital is not None else None,
        "alerta_percentual": alerta,
    }
