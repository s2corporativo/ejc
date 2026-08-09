# ── app/services/juris_import/tcu.py ─────────────────────────────────────────
# Conector TCU — Dados Abertos oficiais, acórdãos.
#
# A API expõe paginação por início/quantidade. Para busca temática on-demand o
# EJC percorre NO MÁXIMO 5 páginas de 100 registros e filtra localmente título +
# sumário. Nunca varre o acervo inteiro nem baixa PDFs automaticamente.
from __future__ import annotations

import logging
import re

from app.integrations.tcu_client import TcuPublicClient
from app.services.juris_import.base import (
    JulgadoNormalizado,
    no_ano,
    normalizar_termos,
    texto_normalizado,
)

logger = logging.getLogger("ejc.juris_import.tcu")

_PAGINAS_MAX = 5
_POR_PAGINA = 100
_client = TcuPublicClient(timeout_s=30.0)


def _data_iso(valor: object) -> str | None:
    s = str(valor or "").strip()
    if not s:
        return None
    m = re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def normalizar_registro(rec: dict) -> JulgadoNormalizado | None:
    numero = str(rec.get("numero") or rec.get("chave") or "").strip()
    titulo = str(rec.get("titulo") or "").strip()
    sumario = str(rec.get("sumario") or "").strip()
    if not numero or not (titulo or sumario):
        return None
    ementa = "\n\n".join(x for x in (titulo, sumario) if x)[:20000]
    url = str(rec.get("url") or rec.get("url_pdf") or "").strip()
    if not url.startswith("https://"):
        return None
    return JulgadoNormalizado(
        tribunal="TCU",
        numero=numero,
        data=_data_iso(rec.get("data_sessao")),
        ementa=ementa,
        url_fonte=url,
        orgao_julgador=str(rec.get("colegiado") or "").strip() or None,
        relator=str(rec.get("relator") or "").strip() or None,
        classe=str(rec.get("tipo") or "Acórdão").strip() or "Acórdão",
        area_juridica="Administrativo",
        chave_principal=(
            f"tcu:{rec.get('chave')}" if rec.get("chave") else f"tcu:{numero}"
        ),
    )


async def buscar(
    consulta: str,
    tribunal: str | None = None,
    limite: int = 20,
    ano: int | None = None,
) -> list[JulgadoNormalizado]:
    trib = (tribunal or "").strip().upper()
    if trib and trib != "TCU":
        return []
    termos = normalizar_termos(consulta)
    if not termos:
        return []
    limite = max(1, min(int(limite), 100))
    resultados: list[JulgadoNormalizado] = []
    vistos: set[str] = set()

    for pagina in range(_PAGINAS_MAX):
        if len(resultados) >= limite:
            break
        try:
            itens = await _client.listar_acordaos(
                inicio=pagina * _POR_PAGINA,
                quantidade=_POR_PAGINA,
            )
        except Exception as exc:  # degradação: página posterior não derruba as já lidas
            logger.warning("TCU página %s: %s: %s", pagina, type(exc).__name__, exc)
            break
        if not itens:
            break
        for rec in itens:
            alvo = texto_normalizado(
                f"{rec.get('titulo') or ''} {rec.get('sumario') or ''}"
            )
            if not all(t in alvo for t in termos):
                continue
            julgado = normalizar_registro(rec)
            if julgado is None or not no_ano(julgado.data, ano):
                continue
            chave = julgado.chave_dedup()
            if chave in vistos:
                continue
            vistos.add(chave)
            resultados.append(julgado)
            if len(resultados) >= limite:
                break
    return resultados
