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

# [B3] Gerar cobrança PIX é ato financeiro do escritório → reservado a perfis
# fiduciários, espelhando fees._req_financeiro_mutacao (mesma tupla). Antes
# qualquer interno gerava BR Code; em módulo financeiro, prefira o piso mais
# estrito (financeiro+gestão), não advogado genérico.
_FINANCEIRO_TOTAL = {"superadmin", "admin", "socio", "financeiro"}


def _req_financeiro(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _FINANCEIRO_TOTAL:
        raise HTTPException(403, "Sem permissão para gerar cobrança PIX")
    return cu


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip()


# Comprimento máximo de uma chave PIX segundo o Banco Central: e-mail vai a 77
# caracteres (o maior dos tipos; EVP tem 36, CNPJ 14, telefone 14, CPF 11).
_MAX_CHAVE_PIX = 77


def _emv(idf: str, value: str) -> str:
    """Campo EMV `ID + tamanho(2 dígitos) + valor`.

    O tamanho ocupa EXATAMENTE dois dígitos — é assim que o app do banco fatia o
    payload. Um valor com mais de 99 caracteres emitiria três dígitos nesse
    espaço (`01130aaa…`) e deslocaria TODO o resto da leitura: o BR Code vira
    lixo estruturado, e o erro só aparece no celular do cliente, na hora de
    pagar. Falhar aqui é a única forma de isso não sair em silêncio.
    """
    if len(value) > 99:
        raise ValueError(
            f"Campo EMV {idf} excede 99 caracteres ({len(value)}) — o BR Code "
            "gerado seria inválido."
        )
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
    # `nome`, `cidade`, `txid` e `descricao` são TRUNCADOS aos limites do padrão
    # — sair mais curto é aceitável e o BR Code segue válido. A CHAVE, não:
    # truncá-la geraria um código que cobra de OUTRA conta (ou de nenhuma). Aqui
    # o certo é recusar.
    chave = (chave or "").strip()
    if not chave:
        raise ValueError("Chave PIX vazia.")
    if len(chave) > _MAX_CHAVE_PIX:
        raise ValueError(
            f"Chave PIX com {len(chave)} caracteres — o máximo do Banco Central "
            f"é {_MAX_CHAVE_PIX} (e-mail). Confira a chave."
        )
    nome = _ascii(nome)[:25] or "RECEBEDOR"
    cidade = _ascii(cidade)[:15] or "CIDADE"
    txid = re.sub(r"[^A-Za-z0-9]", "", txid or "")[:25] or "***"
    mai = _emv("00", "br.gov.bcb.pix") + _emv("01", chave)
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
async def cobranca(body: dict = Body(...), cu: User = Depends(_req_financeiro)):
    chave = (body.get("chave") or "").strip()
    nome = (body.get("nome") or "").strip()
    cidade = (body.get("cidade") or "").strip()
    if not chave or not nome:
        raise HTTPException(422, "Informe a chave PIX e o nome do recebedor")
    try:
        valor = float(body["valor"]) if body.get("valor") not in (None, "", 0) else None
    except Exception:
        raise HTTPException(422, "Valor inválido")
    try:
        brcode = gerar_brcode(
            chave=chave, nome=nome, cidade=cidade or "BRASIL", valor=valor,
            txid=body.get("txid") or "***", descricao=body.get("descricao"),
        )
    except ValueError as e:
        # Entrada que não cabe no padrão EMV: 422, com a razão. Antes, uma chave
        # longa demais gerava um BR Code CORROMPIDO e devolvia 200 — o erro só
        # aparecia no celular do cliente, na hora de pagar.
        raise HTTPException(422, str(e))
    return {"copia_e_cola": brcode, "valor": valor, "chave": chave}
