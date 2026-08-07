# ── app/services/tribunal_registry.py ────────────────────────────────────────
# Resolve o Tribunal (catálogo `tribunais`, migração 132) a partir do número
# CNJ do processo. Fase A: só TJMG (1º/2º grau) está seedado — outros
# tribunais retornam None até serem cadastrados (não é erro: quem chama
# decide o que fazer com "tribunal não habilitado ao MNI").
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.processo_eletronico import Tribunal

# Formato CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO
_PADRAO_CNJ = re.compile(
    r"^\d{7}-?\d{2}\.?\d{4}\.?(?P<j>\d)\.?(?P<tr>\d{2})\.?\d{4}$"
)


def extrair_codigo_tribunal(numero_cnj: str) -> str | None:
    """Extrai o código "TR" (2 dígitos) do número CNJ, ou None se o formato
    não bater. Aceita com ou sem pontuação (dígitos apenas também funciona,
    desde que tenha exatamente 20 dígitos)."""
    if not numero_cnj:
        return None
    limpo = numero_cnj.strip()
    m = _PADRAO_CNJ.match(limpo)
    if m:
        return m.group("tr")
    # Fallback: só dígitos, 20 no total — extrai posicionalmente.
    digitos = re.sub(r"\D", "", limpo)
    if len(digitos) == 20:
        return digitos[14:16]
    return None


def extrair_grau(numero_cnj: str) -> str | None:
    """Extrai o dígito "J" (segmento de justiça) — usado só como pista; o grau
    real (1º/2º) na Justiça Estadual normalmente sai do órgão julgador, não
    do número. Fase A assume 1º grau por padrão quando não há outra pista;
    quem chamar pode sobrescrever explicitamente."""
    if not numero_cnj:
        return None
    limpo = numero_cnj.strip()
    m = _PADRAO_CNJ.match(limpo)
    if m:
        return m.group("j")
    return None


async def resolver_tribunal(
    db: AsyncSession, numero_cnj: str, grau: str = "1",
) -> Tribunal | None:
    """Resolve o registro de Tribunal habilitado ao MNI para este número CNJ
    e grau. Retorna None se o código não for reconhecido ou não houver
    tribunal ativo cadastrado (não lança — o chamador decide: 404, task de
    erro, etc)."""
    codigo = extrair_codigo_tribunal(numero_cnj)
    if not codigo:
        return None
    result = await db.execute(
        select(Tribunal).where(
            Tribunal.codigo_tribunal == codigo,
            Tribunal.grau == grau,
            Tribunal.ativo.is_(True),
        )
    )
    return result.scalar_one_or_none()
