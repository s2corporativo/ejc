# ── app/services/datajud_service.py ──────────────────────────────────────────
# Consulta de movimentações processuais via API Pública do DataJud/CNJ.
# Docs: https://datajud-wiki.cnj.jus.br/api-publica/
# A chave pública é divulgada pelo próprio CNJ (configurável via .env).
from __future__ import annotations
import hashlib
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from tenacity import (
    retry, stop_after_attempt, wait_exponential, retry_if_exception_type,
)


# Chamada de rede com retry exponencial (3 tentativas) para erros transitórios.
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    reraise=True,
)
async def _datajud_search(alias: str, payload: dict, headers: dict) -> dict:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{BASE}/{alias}/_search", json=payload, headers=headers)
        r.raise_for_status()
        return r.json()
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.case import Case, CaseMovimento

logger = logging.getLogger("ejc.datajud")
settings = get_settings()

BASE = "https://api-publica.datajud.cnj.jus.br"

# Segmento J (posição 14 do número CNJ NNNNNNN-DD.AAAA.J.TR.OOOO) → alias
_SEG_TR_ALIAS = {
    ("8", "13"): "api_publica_tjmg",   # Justiça Estadual MG
    ("8", "26"): "api_publica_tjsp",
    ("8", "19"): "api_publica_tjrj",
    ("5", "03"): "api_publica_trt3",   # Justiça do Trabalho 3ª Região (MG)
    ("4", "01"): "api_publica_trf1",   # Justiça Federal 1ª Região
    ("4", "06"): "api_publica_trf6",   # TRF6 (MG, criado em 2022)
}


def _alias_do_numero(numero_cnj: str) -> str | None:
    """Extrai J e TR do número CNJ e mapeia para o endpoint do tribunal."""
    n = re.sub(r"\D", "", numero_cnj or "")
    if len(n) != 20:
        return None
    j, tr = n[13], n[14:16]
    return _SEG_TR_ALIAS.get((j, tr))


def _hash_mov(data: str, descricao: str) -> str:
    return hashlib.sha1(f"{data}|{descricao}".encode()).hexdigest()[:16]


async def consultar_processo(numero_cnj: str) -> dict | None:
    """Consulta o DataJud. Retorna dict com movimentos ou None."""
    if not settings.DATAJUD_ENABLED or not settings.DATAJUD_API_KEY:
        return None
    alias = _alias_do_numero(numero_cnj)
    if not alias:
        logger.info(f"Tribunal não mapeado p/ {numero_cnj}")
        return None

    n = re.sub(r"\D", "", numero_cnj)
    payload = {"query": {"match": {"numeroProcesso": n}}, "size": 1}
    headers = {
        "Authorization": f"APIKey {settings.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        data = await _datajud_search(alias, payload, headers)
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return None
        src = hits[0]["_source"]
        movs = []
        for m in src.get("movimentos", []) or []:
            movs.append({
                "data": m.get("dataHora", "")[:10],
                "descricao": m.get("nome", ""),
            })
        return {
            "classe": (src.get("classe") or {}).get("nome"),
            "orgao": (src.get("orgaoJulgador") or {}).get("nome"),
            "movimentos": movs,
        }
    except Exception as e:
        logger.warning(f"DataJud falhou p/ {numero_cnj} (após retries): {e}")
        return None



# ── Parser de movimentos → deadlines automáticos ─────────────────────────────
# Palavras-chave detectadas em movimentos do DataJud que geram prazos processuais.
# Os prazos em dias úteis seguem as regras do CPC/CLT vigentes.
# O advogado DEVE revisar — são alertas, não decisões autônomas (HITL).
_MOVIMENTOS_CRITICOS: list[dict] = [
    {
        "padrao": re.compile(r"cita[çc][aã]o|citado", re.I),
        "titulo": "Contestação (prazo pós-citação)",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 335 — 15 dias úteis da citação. Verificar modalidade.",
    },
    {
        "padrao": re.compile(r"intima[çc][aã]o\s+para\s+manifesta[çc][aã]o", re.I),
        "titulo": "Manifestação (intimação)",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 218, §3º — 15 dias úteis (prazo geral).",
    },
    {
        "padrao": re.compile(r"senten[çc]a|julgamento\s+procedente|julgamento\s+improcedente", re.I),
        "titulo": "Apelação (prazo pós-sentença)",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 1.003, §5º — 15 dias úteis da publicação.",
    },
    {
        "padrao": re.compile(r"ac[oó]rd[aã]o", re.I),
        "titulo": "Recurso Especial/Extraordinário (pós-acórdão)",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 1.003, §5º — 15 dias úteis. Verificar admissibilidade.",
    },
    {
        "padrao": re.compile(r"embargo[s]?\s+de\s+declara[çc][aõ]o|embargos\s+declaratórios", re.I),
        "titulo": "Resposta aos Embargos de Declaração",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 1.023, §2º — 15 dias úteis para responder.",
    },
    {
        "padrao": re.compile(r"laudo\s+pericial|perí?cia\s+realizada", re.I),
        "titulo": "Manifestação sobre laudo pericial",
        "dias_uteis": 15,
        "tipo": "processual",
        "aviso": "CPC art. 477 — 15 dias úteis do depósito do laudo.",
    },
    {
        "padrao": re.compile(r"audi[eê]ncia\s+designada|audi[eê]ncia\s+marcada", re.I),
        "titulo": "Preparação para audiência",
        "dias_uteis": 5,
        "tipo": "interno",
        "aviso": "Alerta interno: preparar caso 5 dias úteis antes.",
    },
]


def _detectar_prazos_criticos(
    descricao: str, data_evento: datetime | None
) -> list[dict]:
    """
    Compara a descrição do movimento com os padrões críticos.
    Retorna lista de dicts {titulo, data_prazo, tipo, aviso} para cada match.
    """
    if not data_evento:
        return []
    matches = []
    base = data_evento.date() if hasattr(data_evento, "date") else data_evento
    from app.services.deadline_calculator import prazo_dias_uteis
    for regra in _MOVIMENTOS_CRITICOS:
        if regra["padrao"].search(descricao):
            venc = prazo_dias_uteis(base, regra["dias_uteis"])
            matches.append({
                "titulo": regra["titulo"],
                "data_prazo": venc,
                "tipo": regra["tipo"],
                "aviso": regra["aviso"],
            })
    return matches


async def sincronizar_caso(db: AsyncSession, case: Case) -> int:
    """
    Busca movimentos oficiais e insere os NOVOS em case_movimentos.
    Dedup por hash(data|descricao) embutido na descrição.
    Detecta automaticamente movimentos críticos e cria deadlines preliminares.
    Retorna qtd de movimentos inseridos.
    """
    if not case.numero_processo:
        return 0
    
    case.sync_pending = True
    try:
        info = await consultar_processo(case.numero_processo)
        if not info:
            case.sync_pending = False
            case.last_synced_at = datetime.now(timezone.utc)
            case.sync_error = "Processo não localizado no DataJud"
            return 0
        
        case.sync_error = None
    except Exception as e:
        case.sync_pending = False
        case.sync_error = str(e)
        raise e

    existentes = (await db.execute(
        select(CaseMovimento.descricao).where(CaseMovimento.case_id == case.id)
    )).scalars().all()
    hashes_exist = set()
    for d in existentes:
        m = re.search(r"\[dj:([0-9a-f]{16})\]", d or "")
        if m:
            hashes_exist.add(m.group(1))

    inseridos = 0
    for mov in info["movimentos"]:
        h = _hash_mov(mov["data"], mov["descricao"])
        if h in hashes_exist:
            continue
        data_ev = None
        if mov["data"]:
            data_ev = datetime.fromisoformat(mov["data"])
            # CaseMovimento.data_evento é timestamptz — torna aware (UTC) quando o
            # ISO vier naive, evitando comparação naive vs aware no banco.
            if data_ev.tzinfo is None:
                data_ev = data_ev.replace(tzinfo=timezone.utc)
        db.add(CaseMovimento(
            id=str(uuid4()), case_id=case.id, tipo="andamento_oficial",
            descricao=f"{mov['descricao']} [dj:{h}]",
            data_evento=data_ev,
            created_by=None,
        ))
        inseridos += 1

        # Detectar movimentos críticos → criar deadlines preliminares
        prazos = _detectar_prazos_criticos(mov["descricao"], data_ev)
        for p in prazos:
            await _criar_deadline_automatico(db, case, p, mov["descricao"])

    # Sucesso: metadados de sync atualizados SEMPRE. Antes só eram atualizados
    # dentro de _criar_deadline_automatico, que roda apenas quando há prazo
    # crítico — então um caso sincronizado sem prazo (o caso comum) ficava com
    # sync_pending=True indefinidamente e last_synced_at nunca avançava.
    case.sync_pending = False
    case.last_synced_at = datetime.now(timezone.utc)
    return inseridos


async def _criar_deadline_automatico(
    db: AsyncSession, case: Case, prazo: dict, origem_mov: str
) -> None:
    """
    Insere deadline gerado automaticamente por movimento DataJud.
    Marcado como alerta_datajud para distinguir dos prazos manuais.
    Requer revisão humana (HITL). Não duplica se já existe prazo igual no caso.
    """
    try:
        from sqlalchemy import text as _text
        # Evitar duplicata: mesma combinação case_id + titulo + data_prazo
        existe = (await db.execute(_text("""
            SELECT 1 FROM deadlines
            WHERE case_id = :cid AND titulo = :tit
              AND data_prazo = :dp AND deleted_at IS NULL
            LIMIT 1
        """), {"cid": case.id, "tit": prazo["titulo"], "dp": prazo["data_prazo"]})).scalar()
        if existe:
            return

        from app.models.deadline import Deadline
        db.add(Deadline(
            id=str(uuid4()),
            case_id=case.id,
            titulo=prazo["titulo"],
            descricao=(
                f"[ALERTA AUTOMÁTICO — DataJud]\n"
                f"Movimento: {origem_mov[:200]}\n"
                f"{prazo['aviso']}\n"
                f"⚠️ Revisar e confirmar prazo antes de qualquer uso."
            ),
            data_prazo=prazo["data_prazo"],
            tipo=prazo["tipo"],
            status="pendente",
            responsavel_id=getattr(case, "advogado_responsavel_id", None),
        ))
        logger.info(
            f"[DataJud] Deadline automático criado: '{prazo['titulo']}' "
            f"vence {prazo['data_prazo']} (caso {getattr(case, 'numero_interno', case.id)})"
        )
    except Exception as e:
        logger.warning(f"[DataJud] Falha ao criar deadline automático: {e}")


# ── BUG-16: sincronização de PRAZOS a partir do DataJud ──────────────────────
def _ref_datajud(numero_cnj: str, data: str, titulo: str) -> str:
    """Chave estável de dedup de prazo: hash(CNJ|data|titulo)."""
    n = re.sub(r"\D", "", numero_cnj or "")
    return hashlib.sha1(f"{n}|{data}|{titulo}".encode()).hexdigest()[:32]


async def sincronizar_prazos_datajud(
    caso_id: str, numero_cnj: str, db: AsyncSession
) -> dict:
    """Puxa movimentos do DataJud e cria prazos (deadlines) não-duplicados.

    - Dedup por `referencia_datajud` (hash CNJ|data|titulo) — nunca reimporta
      o mesmo prazo.
    - Cada prazo é RASCUNHO/HITL: origem='datajud', exige revisão do advogado.
    - Fail-safe: se o DataJud estiver indisponível/sem movimentos, retorna 0 sem
      quebrar o fluxo que a chamou.

    Retorna {"criados": int, "encontrados": int, "erro": str|None}.
    """
    from app.models.deadline import Deadline

    if not numero_cnj:
        return {"criados": 0, "encontrados": 0, "erro": "Caso sem número CNJ."}

    try:
        info = await consultar_processo(numero_cnj)
    except Exception as e:
        logger.warning(f"[DataJud] consulta de prazos falhou p/ {numero_cnj}: {e}")
        return {"criados": 0, "encontrados": 0, "erro": str(e)[:200]}

    if not info or not info.get("movimentos"):
        return {"criados": 0, "encontrados": 0, "erro": None}

    # Responsável do caso (para atribuir o prazo).
    case = (await db.execute(
        select(Case).where(Case.id == caso_id)
    )).scalar_one_or_none()
    responsavel_id = getattr(case, "advogado_responsavel_id", None) if case else None

    # Referências já importadas (dedup por referencia_datajud).
    from sqlalchemy import text as _text
    refs_existentes = set((await db.execute(_text(
        "SELECT referencia_datajud FROM deadlines "
        "WHERE case_id = :cid AND referencia_datajud IS NOT NULL"
    ), {"cid": caso_id})).scalars().all())

    criados = 0
    encontrados = 0
    for mov in info["movimentos"]:
        data_ev = datetime.fromisoformat(mov["data"]) if mov.get("data") else None
        prazos = _detectar_prazos_criticos(mov["descricao"], data_ev)
        for p in prazos:
            encontrados += 1
            ref = _ref_datajud(numero_cnj, mov.get("data", ""), p["titulo"])
            if ref in refs_existentes:
                continue
            db.add(Deadline(
                id=str(uuid4()),
                case_id=caso_id,
                titulo=p["titulo"],
                descricao=(
                    f"[ALERTA AUTOMÁTICO — DataJud]\n"
                    f"Movimento: {mov['descricao'][:200]}\n"
                    f"{p['aviso']}\n"
                    f"⚠️ Revisar e confirmar o prazo antes de qualquer uso (HITL/OAB)."
                ),
                data_prazo=p["data_prazo"],
                tipo=p["tipo"],
                status="pendente",
                responsavel_id=responsavel_id,
                origem="datajud",
                referencia_datajud=ref,
            ))
            refs_existentes.add(ref)
            criados += 1

    return {"criados": criados, "encontrados": encontrados, "erro": None}
