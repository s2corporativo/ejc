"""Cobrança PIX — BR Code estático padrão EMV/Banco Central, sem gateway.

A geração não representa liquidação. Baixa/reconciliação exige PSP/webhook e
continua fora deste módulo. O ato de gerar é auditado sem persistir a chave PIX
ou a descrição da cobrança no log imutável.
"""
from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.user import User

router = APIRouter(prefix="/pix", tags=["Cobrança PIX"])

_FINANCEIRO_TOTAL = {"superadmin", "admin", "socio", "financeiro"}
_Q2 = Decimal("0.01")


def _req_financeiro(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _FINANCEIRO_TOTAL:
        raise HTTPException(403, "Sem permissão para gerar cobrança PIX")
    return cu


class PixCobrancaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chave: str = Field(min_length=1, max_length=77)
    nome: str = Field(min_length=1, max_length=100)
    cidade: str = Field(default="BRASIL", max_length=100)
    valor: Optional[Decimal] = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    txid: str = Field(default="***", max_length=25)
    descricao: Optional[str] = Field(default=None, max_length=140)

    @field_validator("chave", "nome", "cidade")
    @classmethod
    def _sem_vazio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("campo não pode ser vazio")
        return value


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip()


def _emv(idf: str, value: str) -> str:
    return f"{idf}{len(value):02d}{value}"


def _crc16(payload: str) -> str:
    crc = 0xFFFF
    for ch in payload.encode("utf-8"):
        crc ^= ch << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def gerar_brcode(
    chave: str,
    nome: str,
    cidade: str,
    valor: Optional[Decimal] = None,
    txid: str = "***",
    descricao: Optional[str] = None,
) -> str:
    nome = _ascii(nome)[:25] or "RECEBEDOR"
    cidade = _ascii(cidade)[:15] or "CIDADE"
    txid = re.sub(r"[^A-Za-z0-9]", "", txid or "")[:25] or "***"
    mai = _emv("00", "br.gov.bcb.pix") + _emv("01", chave.strip())
    if descricao:
        mai += _emv("02", _ascii(descricao)[:25])
    payload = _emv("00", "01") + _emv("26", mai) + _emv("52", "0000") + _emv("53", "986")
    if valor is not None and valor > 0:
        valor_q = valor.quantize(_Q2, rounding=ROUND_HALF_UP)
        payload += _emv("54", format(valor_q, ".2f"))
    payload += _emv("58", "BR") + _emv("59", nome) + _emv("60", cidade)
    payload += _emv("62", _emv("05", txid))
    payload += "6304"
    return payload + _crc16(payload)


@router.post("/cobranca")
async def cobranca(
    body: PixCobrancaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro),
):
    brcode = gerar_brcode(
        chave=body.chave,
        nome=body.nome,
        cidade=body.cidade or "BRASIL",
        valor=body.valor,
        txid=body.txid,
        descricao=body.descricao,
    )
    # LGPD/minimização: não gravar chave PIX, nome do recebedor nem descrição
    # em audit_logs WORM. Para rastrear o ato bastam usuário, valor e TXID
    # sanitizado; a geração não prova pagamento.
    txid_audit = re.sub(r"[^A-Za-z0-9]", "", body.txid or "")[:25] or "***"
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "pix_cobranca",
        detalhes=f"BR Code PIX estático gerado; txid={txid_audit}",
        dados_depois={
            "valor": str(body.valor.quantize(_Q2, rounding=ROUND_HALF_UP)) if body.valor is not None else None,
            "txid": txid_audit,
            "liquidacao_confirmada": False,
        },
    )
    await db.commit()
    return {
        "copia_e_cola": brcode,
        "valor": body.valor,
        # A chave não precisa ser ecoada: ela já veio do cliente e o BR Code a
        # contém. Evita ampliar a exposição desnecessária na resposta.
        "liquidacao_confirmada": False,
    }
