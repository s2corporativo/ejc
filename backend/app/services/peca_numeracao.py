# ── app/services/peca_numeracao.py ───────────────────────────────────────────
# Numeração/versionamento de peças jurídicas (Fase D — controle no rodapé).
#
# Cada peça gerada recebe um CÓDIGO estável por RAMO do direito, no formato
#   EJC-<SIGLA>-<NNN>            (ex.: EJC-CIV-001, EJC-TRAB-042)
# gravado em LegalDoc.codigo_peca. O contador é ATÔMICO por ramo (tabela
# peca_codigo_contador + INSERT ... ON CONFLICT ... RETURNING), sem corrida
# entre requisições simultâneas.
#
# A "linha de controle" do rodapé (código | título | versão | revisão | status)
# é montada AQUI e usada APENAS no RENDER (PDF/DOCX). NUNCA entra no prompt ou
# no corpo gerado pela IA (Regra 9 do padrão-ouro: o rodapé é do SISTEMA).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Sigla curta por ramo — cobre as 17 chaves de AREAS_DIREITO (peca_service).
# Ramo desconhecido → 3 primeiras letras em maiúsculas (fallback determinístico).
ABREV_AREA: dict[str, str] = {
    "trabalhista": "TRAB",
    "civil": "CIV",
    "previdenciario": "PREV",
    "tributario": "TRIB",
    "criminal": "CRIM",
    "consumidor": "CDC",
    "administrativo": "ADM",
    "familia": "FAM",
    "empresarial": "EMP",
    "ambiental": "AMB",
    "bancario": "BANC",
    "imobiliario": "IMOB",
    "sucessoes": "SUC",
    "constitucional": "CONST",
    "juizados": "JEC",
    "digital_lgpd": "LGPD",
    "transito": "TRAN",
}

# Rótulo legível do status da peça (PecaStatus) para a linha de controle.
STATUS_LABEL: dict[str, str] = {
    "rascunho": "Rascunho",
    "em_revisao": "Em revisão",
    "corrigida": "Corrigida",
    "aprovada": "Aprovada",
    "final": "Final",
    "protocolada": "Protocolada",
}


def sigla_area(area: str | None) -> str:
    """Sigla do ramo para o código da peça. Fallback: 3 primeiras letras UPPER."""
    chave = (area or "").strip().lower()
    if chave in ABREV_AREA:
        return ABREV_AREA[chave]
    limpa = "".join(c for c in chave if c.isalnum())
    return (limpa[:3].upper() or "GEN")


def status_label(status: Any) -> str:
    """Rótulo legível de um PecaStatus (enum), string ou None."""
    if status is None:
        return "—"
    valor = getattr(status, "value", status)
    return STATUS_LABEL.get(str(valor), str(valor).replace("_", " ").capitalize())


async def proximo_codigo_peca(db: AsyncSession, area: str | None) -> str:
    """Reserva o próximo código da peça para o ramo, de forma ATÔMICA.

    Usa UPSERT com RETURNING: o INSERT ... ON CONFLICT DO UPDATE incrementa e
    devolve o novo valor numa única instrução, serializada por linha no
    PostgreSQL — duas requisições concorrentes para o mesmo ramo recebem
    números distintos, sem corrida. Formato: ``EJC-<SIGLA>-<NNN>`` (NNN com
    zero-padding de 3 dígitos; passa de 999 sem truncar).
    """
    chave = (area or "").strip().lower() or "geral"
    row = await db.execute(
        text(
            "INSERT INTO peca_codigo_contador (area, ultimo) VALUES (:a, 1) "
            "ON CONFLICT (area) DO UPDATE "
            "SET ultimo = peca_codigo_contador.ultimo + 1 "
            "RETURNING ultimo"
        ),
        {"a": chave},
    )
    n = int(row.scalar_one())
    return f"EJC-{sigla_area(area)}-{n:03d}"


def _fmt_data(valor: Any) -> str:
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y")
    if valor:
        return str(valor)
    return "—"


def linha_controle(
    *,
    codigo_peca: str | None,
    titulo: str | None,
    versao: int | None = 1,
    status: Any = None,
    revisado_em: Any = None,
) -> str:
    """Monta a linha de controle do rodapé (render-only).

    Formato: ``EJC-<RAMO>-<NNN> | <título> | vX.0 | revisada em <data> | <status>``.
    Degrada sem quebrar quando faltam campos (peças antigas sem código).
    """
    codigo = (codigo_peca or "EJC-—").strip()
    tit = (titulo or "Peça jurídica").strip()
    v = f"v{int(versao or 1)}.0"
    data = _fmt_data(revisado_em)
    rev = f"revisada em {data}" if revisado_em else "revisão pendente"
    return f"{codigo} | {tit} | {v} | {rev} | {status_label(status)}"
