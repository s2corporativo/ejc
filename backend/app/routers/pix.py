"""Cobrança PIX — gera o BR Code ("copia e cola") padrão EMV do Banco Central, sem gateway.
   A baixa automática (reconciliação) exigiria webhook do PSP/banco — futura.
"""
import re
import unicodedata
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/pix", tags=["Cobrança PIX"])


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


def gerar_brcode(chave: str, nome: str, cidade: str, valor: Optional[float] = None,
                 txid: str = "***", descricao: Optional[str] = None) -> str:
    nome = _ascii(nome)[:25] or "RECEBEDOR"
    cidade = _ascii(cidade)[:15] or "CIDADE"
    txid = re.sub(r"[^A-Za-z0-9]", "", txid or "")[:25] or "***"
    mai = _emv("00", "br.gov.bcb.pix") + _emv("01", chave.strip())
    if descricao:
        mai += _emv("02", _ascii(descricao)[:25])
    payload = _emv("00", "01") + _emv("26", mai) + _emv("52", "0000") + _emv("53", "986")
    if valor and float(valor) > 0:
        payload += _emv("54", f"{float(valor):.2f}")
    payload += _emv("58", "BR") + _emv("59", nome) + _emv("60", cidade)
    payload += _emv("62", _emv("05", txid))
    payload += "6304"
    return payload + _crc16(payload)


@router.post("/cobranca")
async def cobranca(body: dict = Body(...), cu: User = Depends(get_current_user)):
    chave = (body.get("chave") or "").strip()
    nome = (body.get("nome") or "").strip()
    cidade = (body.get("cidade") or "").strip()
    if not chave or not nome:
        raise HTTPException(422, "Informe a chave PIX e o nome do recebedor")
    try:
        valor = float(body["valor"]) if body.get("valor") not in (None, "", 0) else None
    except Exception:
        raise HTTPException(422, "Valor inválido")
    brcode = gerar_brcode(
        chave=chave, nome=nome, cidade=cidade or "BRASIL", valor=valor,
        txid=body.get("txid") or "***", descricao=body.get("descricao"),
    )
    return {"copia_e_cola": brcode, "valor": valor, "chave": chave}
