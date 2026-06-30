"""
citation_check.py — Verificador anti-alucinação de citações (#46).

Extrai súmulas e artigos citados num texto (peça/parecer gerado por IA) e
confirma CADA UM contra o RAG (base oficial já ingerida: ~1.500 súmulas STF/STJ/TST
+ códigos). Citações NÃO confirmadas são sinalizadas para verificação manual (OAB).

VERIFICAÇÃO = lookup EXATO (chave_origem / título), não busca semântica — porque
verificar existência exige precisão, não similaridade. 100% local (sem IA externa).
"""
from __future__ import annotations
import re

from sqlalchemy import text

# "Súmula 7 do STF", "Súmula Vinculante 11", "Súmula 297 STJ", "súmula nº 54/TST"
_RE_SUMULA = re.compile(
    r"s[úu]mula(?:\s+vinculante)?\s+(?:n[ºo°.]*\s*)?(\d{1,4})\s*"
    r"(?:[\-/]?\s*(?:d[oae]\s+)?)?(stf|stj|tst|tjmg)?",
    re.IGNORECASE,
)
# "art. 927 do CC", "artigo 5º CF", "art. 333 CPC", "art. 71 da Lei 9.605/98"
_RE_ARTIGO = re.compile(
    r"\bart(?:igo)?s?\.?\s*(\d{1,4})[º°ªa]?(?:[\-,]?[A-Z])?\b[^.;\n]{0,45}?"
    r"\b(cf|cpc|cc|clt|cdc|cpp|cp|ctn|lei\s*n?[ºo°.]*\s*[\d.]+\/?\d*)\b",
    re.IGNORECASE,
)


async def _existe_sumula(db, num: str, orgao: str) -> str | None:
    """Lookup exato por chave_origem (ingestão nova) + fallback por título."""
    keys = [f"sumula:{orgao}:{num}"] if orgao else \
           [f"sumula:{t}:{num}" for t in ("STF", "STJ", "TST")]
    row = (await db.execute(text(
        "SELECT titulo FROM knowledge_docs "
        "WHERE deleted_at IS NULL AND chave_origem = ANY(:k) LIMIT 1"
    ), {"k": keys})).first()
    if row:
        return row[0]
    # Fallback p/ docs de formato antigo: título "Súmula N ..." (boundary via ' %')
    params = {"t": f"Súmula {num} %"}
    cond = ""
    if orgao:
        cond = " AND titulo ILIKE :org"
        params["org"] = f"%{orgao}%"
    row = (await db.execute(text(
        "SELECT titulo FROM knowledge_docs WHERE deleted_at IS NULL "
        "AND categoria LIKE 'sumula%' AND titulo ILIKE :t" + cond + " LIMIT 1"
    ), params)).first()
    return row[0] if row else None


async def _existe_artigo(db, num: str) -> str | None:
    """Procura o artigo no conteúdo da legislação ingerida (códigos no RAG)."""
    row = (await db.execute(text(
        "SELECT kd.titulo FROM knowledge_chunks kc "
        "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
        "WHERE kd.deleted_at IS NULL AND kd.categoria = 'legislacao' "
        "AND (kc.conteudo ILIKE :a1 OR kc.conteudo ILIKE :a2) LIMIT 1"
    ), {"a1": f"%Art. {num} %", "a2": f"%Art. {num}º%"})).first()
    return row[0] if row else None


async def verificar_citacoes(db, texto: str) -> dict:
    """Relatório de verificação das citações encontradas no texto."""
    texto = texto or ""
    achados: list[dict] = []
    seen: set = set()

    for m in _RE_SUMULA.finditer(texto):
        num, orgao = m.group(1), (m.group(2) or "").upper()
        key = ("sumula", num, orgao)
        if key in seen:
            continue
        seen.add(key)
        achados.append({"tipo": "sumula", "num": num, "orgao": orgao,
                        "rotulo": f"Súmula {num}" + (f" {orgao}" if orgao else "")})

    for m in _RE_ARTIGO.finditer(texto):
        num, dipl = m.group(1), (m.group(2) or "").upper()
        key = ("artigo", num, dipl)
        if key in seen:
            continue
        seen.add(key)
        achados.append({"tipo": "artigo", "num": num, "orgao": dipl,
                        "rotulo": f"art. {num} {dipl}".strip()})

    resultados = []
    for c in achados:
        if c["tipo"] == "sumula":
            fonte = await _existe_sumula(db, c["num"], c["orgao"])
        else:
            fonte = await _existe_artigo(db, c["num"])
        resultados.append({"citacao": c["rotulo"], "tipo": c["tipo"],
                           "encontrada": fonte is not None, "fonte": fonte})

    conf = sum(1 for r in resultados if r["encontrada"])
    return {
        "total": len(resultados),
        "confirmadas": conf,
        "nao_encontradas": len(resultados) - conf,
        "citacoes": resultados,
        "aviso": ("Citações NÃO confirmadas na base oficial devem ser verificadas "
                  "manualmente antes do protocolo (responsabilidade do advogado — OAB). "
                  "A base cobre súmulas STF/STJ/TST e a legislação já ingerida."),
    }
