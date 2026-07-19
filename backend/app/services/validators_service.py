# ── app/services/validators_service.py ───────────────────────────────────────
# Validação matemática de CPF/CNPJ (dígitos verificadores, offline)
# + consultas públicas com CADEIA DE FALLBACK (todas gratuitas, sem chave):
#   CNPJ: OpenCNPJ → BrasilAPI → ReceitaWS (timeout 8s cada, resposta única
#         normalizada — campo `fonte` informa qual serviço respondeu).
#   CEP:  BrasilAPI v2 (multi-fonte) → ViaCEP.
from __future__ import annotations
import logging
import re

import httpx

logger = logging.getLogger("ejc.validators")

_TIMEOUT_S = 8


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


# ── CNJ (número único de processo — Res. CNJ 65/2008) ─────────────────────────
# O cálculo do dígito verificador (módulo 97 / ISO 7064) NÃO é reimplementado
# aqui: reutilizamos a ÚNICA implementação canônica do projeto,
# app/services/verificador_jurisprudencia.py::validar_dv_cnj (já usada pelo
# verificador de jurisprudência), para não haver duas versões que possam
# divergir. Import no topo do módulo é seguro — aquele módulo só depende de
# stdlib (asyncio/logging/re/unicodedata), sem risco de ciclo.
from app.services.verificador_jurisprudencia import validar_dv_cnj  # noqa: E402

# Máscara canônica NNNNNNN-DD.AAAA.J.TR.OOOO (20 dígitos com separadores).
_RE_CNJ_MASCARA = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")


def normalizar_cnj(numero: str) -> str:
    """Só os 20 dígitos do número CNJ (aceita com ou sem máscara)."""
    return _digitos(numero)


def validar_cnj(numero: str) -> bool:
    """Valida um número único de processo (CNJ, Res. CNJ 65/2008).

    Aceita COM máscara (``NNNNNNN-DD.AAAA.J.TR.OOOO``) ou só dígitos (20).
    Confere o formato (20 dígitos) e o dígito verificador pelo módulo 97
    (ISO 7064), delegando o cálculo do DV a
    ``verificador_jurisprudencia.validar_dv_cnj`` (fonte única da regra).
    Vazio/``None`` NÃO é validado aqui (retorna ``False``); quem chama decide
    se ausência de número é aceitável.
    """
    if not numero:
        return False
    bruto = numero.strip()
    # Tolerante à máscara: aceita apenas dois formatos — só-dígitos (20) ou a
    # máscara canônica. Isso evita aceitar pontuação arbitrária como válida.
    if not (bruto.isdigit() or _RE_CNJ_MASCARA.match(bruto)):
        return False
    n = _digitos(bruto)
    if len(n) != 20:
        return False
    return validar_dv_cnj(n)


async def _get_json(url: str) -> dict | list | None:
    """GET com timeout curto; None para status != 200 (indireção única —
    testes mockam aqui, sem rede)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as c:
        r = await c.get(url)
        if r.status_code != 200:
            return None
        return r.json()


# ── CEP: BrasilAPI v2 → ViaCEP ────────────────────────────────────────────────

async def _cep_brasilapi(cep: str) -> dict | None:
    d = await _get_json(f"https://brasilapi.com.br/api/cep/v2/{cep}")
    if not isinstance(d, dict) or not d.get("cep"):
        return None
    return {
        "cep": d.get("cep"), "logradouro": d.get("street"),
        "bairro": d.get("neighborhood"), "cidade": d.get("city"),
        "estado": d.get("state"), "fonte": "brasilapi",
    }


async def _cep_viacep(cep: str) -> dict | None:
    d = await _get_json(f"https://viacep.com.br/ws/{cep}/json/")
    if not isinstance(d, dict) or d.get("erro"):
        return None
    return {
        "cep": d.get("cep"), "logradouro": d.get("logradouro"),
        "bairro": d.get("bairro"), "cidade": d.get("localidade"),
        "estado": d.get("uf"), "fonte": "viacep",
    }


async def consultar_cep(cep: str) -> dict | None:
    """Consulta CEP com fallback: BrasilAPI v2 → ViaCEP. None se não achar."""
    cep = _digitos(cep)
    if len(cep) != 8:
        return None
    for fonte in (_cep_brasilapi, _cep_viacep):
        try:
            data = await fonte(cep)
            if data:
                return data
        except Exception as exc:
            # Não registrar URL/CEP nem a mensagem do cliente HTTP.
            logger.warning(
                "consultar_cep: fonte %s falhou (tipo=%s) — tentando a próxima",
                fonte.__name__, type(exc).__name__,
            )
    return None


# ── CNPJ: OpenCNPJ → BrasilAPI → ReceitaWS ────────────────────────────────────

def _fmt_tel(ddd, numero) -> str | None:
    if not numero:
        return None
    return f"{ddd}{numero}" if ddd else str(numero)


async def _cnpj_opencnpj(cnpj: str) -> dict | None:
    d = await _get_json(f"https://api.opencnpj.org/{cnpj}")
    if not isinstance(d, dict) or not d.get("razao_social"):
        return None
    tel = None
    tels = d.get("telefones") or []
    if tels and isinstance(tels[0], dict):
        tel = _fmt_tel(tels[0].get("ddd"), tels[0].get("numero"))
    return {
        "cnpj": cnpj,
        "razao_social": d.get("razao_social"),
        "nome_fantasia": d.get("nome_fantasia"),
        "situacao": d.get("situacao_cadastral"),
        "cep": d.get("cep"), "logradouro": d.get("logradouro"),
        "numero": d.get("numero"), "bairro": d.get("bairro"),
        "cidade": d.get("municipio"), "estado": d.get("uf"),
        "telefone": tel,
        "fonte": "opencnpj",
    }


async def _cnpj_brasilapi(cnpj: str) -> dict | None:
    d = await _get_json(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
    if not isinstance(d, dict) or not d.get("razao_social"):
        return None
    return {
        "cnpj": cnpj,
        "razao_social": d.get("razao_social"),
        "nome_fantasia": d.get("nome_fantasia"),
        "situacao": d.get("descricao_situacao_cadastral"),
        "cep": d.get("cep"), "logradouro": d.get("logradouro"),
        "numero": d.get("numero"), "bairro": d.get("bairro"),
        "cidade": d.get("municipio"), "estado": d.get("uf"),
        "telefone": d.get("ddd_telefone_1"),
        "fonte": "brasilapi",
    }


async def _cnpj_receitaws(cnpj: str) -> dict | None:
    # ReceitaWS gratuito: 3 req/min — por isso é o ÚLTIMO da cadeia.
    d = await _get_json(f"https://receitaws.com.br/v1/cnpj/{cnpj}")
    if not isinstance(d, dict) or d.get("status") == "ERROR" or not d.get("nome"):
        return None
    return {
        "cnpj": cnpj,
        "razao_social": d.get("nome"),
        "nome_fantasia": d.get("fantasia"),
        "situacao": d.get("situacao"),
        "cep": d.get("cep"), "logradouro": d.get("logradouro"),
        "numero": d.get("numero"), "bairro": d.get("bairro"),
        "cidade": d.get("municipio"), "estado": d.get("uf"),
        "telefone": d.get("telefone"),
        "fonte": "receitaws",
    }


async def consultar_cnpj(cnpj: str) -> dict | None:
    """Dados cadastrais públicos da Receita, com fallback em cadeia:
    OpenCNPJ (50 req/s) → BrasilAPI → ReceitaWS (3/min). Resposta normalizada
    única; None se nenhuma fonte responder."""
    cnpj = _digitos(cnpj)
    if not validar_cnpj(cnpj):
        return None
    for fonte in (_cnpj_opencnpj, _cnpj_brasilapi, _cnpj_receitaws):
        try:
            data = await fonte(cnpj)
            if data:
                return data
        except Exception as exc:
            # Exceções httpx incluem a URL; a URL contém o CNPJ consultado.
            logger.warning(
                "consultar_cnpj: fonte %s falhou (tipo=%s) — tentando a próxima",
                fonte.__name__, type(exc).__name__,
            )
    return None
