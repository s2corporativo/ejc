# ── app/services/validators_service.py ───────────────────────────────────────
# Validação matemática de CPF/CNPJ (dígitos verificadores, offline)
# + consultas públicas: ViaCEP e BrasilAPI (CNPJ) — sem API key.
from __future__ import annotations
import re
import httpx


def _digitos(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def validar_cpf(cpf: str) -> bool:
    """Validação por dígitos verificadores (módulo 11)."""
    cpf = _digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(cpf[j]) * ((i + 1) - j) for j in range(i))
        dv = (soma * 10 % 11) % 10
        if dv != int(cpf[i]):
            return False
    return True


def validar_cnpj(cnpj: str) -> bool:
    cnpj = _digitos(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(cnpj[i]) * pesos[i] for i in range(pos))
        dv = 11 - soma % 11
        dv = 0 if dv >= 10 else dv
        if dv != int(cnpj[pos]):
            return False
    return True


async def consultar_cep(cep: str) -> dict | None:
    """ViaCEP — público, sem chave."""
    cep = _digitos(cep)
    if len(cep) != 8:
        return None
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.get(f"https://viacep.com.br/ws/{cep}/json/")
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("erro"):
            return None
        return {
            "cep": data.get("cep"), "logradouro": data.get("logradouro"),
            "bairro": data.get("bairro"), "cidade": data.get("localidade"),
            "estado": data.get("uf"),
        }


async def consultar_cnpj(cnpj: str) -> dict | None:
    """BrasilAPI — dados cadastrais públicos da Receita."""
    cnpj = _digitos(cnpj)
    if not validar_cnpj(cnpj):
        return None
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
        if r.status_code != 200:
            return None
        d = r.json()
        return {
            "cnpj": cnpj,
            "razao_social": d.get("razao_social"),
            "nome_fantasia": d.get("nome_fantasia"),
            "situacao": d.get("descricao_situacao_cadastral"),
            "cep": d.get("cep"), "logradouro": d.get("logradouro"),
            "numero": d.get("numero"), "bairro": d.get("bairro"),
            "cidade": d.get("municipio"), "estado": d.get("uf"),
            "telefone": d.get("ddd_telefone_1"),
        }
