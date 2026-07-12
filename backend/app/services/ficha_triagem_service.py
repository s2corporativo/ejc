# ── app/services/ficha_triagem_service.py ────────────────────────────────────
# Ficha de Triagem pré-peça — GATE de qualidade da Jornada do Caso.
#
# pre_preencher()  → monta o RASCUNHO dos 12 campos da ficha via IA de triagem
#                    (mesmo pipeline de triagem_entrevista: sanitizar → gateway
#                    task_type="triagem" → parse JSON defensivo → registrar_ai_log),
#                    com provas_disponiveis pré-preenchidas de forma DETERMINÍSTICA
#                    a partir do acervo probatório do caso. NÃO persiste (rascunho
#                    de apoio, HITL) — o advogado revisa e chama salvar().
# obter()          → ficha corrente do caso (ou None).
# salvar()         → UPSERT (uma ficha por caso); confirmar=True → status
#                    'confirmada' (abre o gate de geração de peça). Audit log.
# ficha_confirmada() → helper do gate em peca_geracao.
# resumo_para_prompt() → texto compacto dos campos p/ ancorar a peça na triagem.
#
# Todo o pré-preenchimento é ESTIMATIVA / RASCUNHO (HITL obrigatório — OAB
# Prov. 205/2021). A peça só nasce de uma ficha CONFIRMADA pelo advogado.
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit_log import criar_audit_log
from app.models.ai_log import AITipoUso
from app.models.case import Case
from app.models.ficha_triagem import FichaTriagem
from app.models.prova import Prova

settings = get_settings()
logger = logging.getLogger("ejc.ficha_triagem")

# Os 12 campos do pré-preenchimento por IA (cada um com confiança 0-100).
# provas_disponiveis é DETERMINÍSTICO (acervo do caso), não vem da IA.
CAMPOS_TRIAGEM: tuple[str, ...] = (
    "competencia",
    "rito",
    "legitimidade_ativa",
    "legitimidade_passiva",
    "prescricao_decadencia",
    "tutela_urgencia",
    "tutela_fundamento",
    "provas_disponiveis",
    "provas_faltantes",
    "valor_causa",
    "risco_processual",
    "pedidos_principais",
)

# Campos vindos da IA (JSON) — provas_disponiveis é derivado do acervo.
_CAMPOS_IA: tuple[str, ...] = tuple(c for c in CAMPOS_TRIAGEM if c != "provas_disponiveis")

# Todos os campos persistíveis (salvar aceita este conjunto).
_CAMPOS_TEXTO: tuple[str, ...] = (
    "competencia", "rito", "legitimidade_ativa", "legitimidade_passiva",
    "prescricao_decadencia", "tutela_fundamento", "provas_disponiveis",
    "provas_faltantes", "valor_causa", "risco_nota",
    "pedidos_principais", "pedidos_subsidiarios",
)

_RISCOS_VALIDOS = {"baixo", "medio", "alto"}

_AVISO_ESTIMATIVA = (
    "Pré-preenchimento gerado por IA a partir dos dados do caso — RASCUNHO, "
    "NÃO é parecer jurídico. Revisão e confirmação do advogado obrigatórias "
    "(OAB Prov. 205/2021)."
)

_SYSTEM_PROMPT = """Você é assistente interno de TRIAGEM de um escritório de advocacia brasileiro (uso exclusivo por advogados — nunca resposta a cliente).
A partir dos dados de um caso (já sanitizados), pré-preencha uma FICHA DE TRIAGEM técnica PRELIMINAR para o advogado revisar antes de gerar a peça.

REGRAS:
- Baseie-se APENAS nos dados fornecidos. É PROIBIDO inventar lei, súmula, julgado ou fato.
- Se os dados não permitirem avaliar um campo, use valor null e confianca baixa (<40).
- Os percentuais são estimativas técnicas internas de triagem — nunca promessa de resultado.
- risco_processual só pode ser: "baixo", "medio" ou "alto".

Responda APENAS com JSON estrito (sem markdown, sem texto fora do JSON), neste formato:
{
  "competencia": {"valor": "<juízo/vara competente>", "confianca": 0-100},
  "rito": {"valor": "<procedimento: comum, sumaríssimo/JEC, especial...>", "confianca": 0-100},
  "legitimidade_ativa": {"valor": "<quem figura no polo ativo e por quê>", "confianca": 0-100},
  "legitimidade_passiva": {"valor": "<quem figura no polo passivo e por quê>", "confianca": 0-100},
  "prescricao_decadencia": {"valor": "<prazo aplicável + base legal, ou o que falta avaliar>", "confianca": 0-100},
  "tutela_urgencia": {"valor": true|false, "confianca": 0-100},
  "tutela_fundamento": {"valor": "<fumus + periculum, ou null>", "confianca": 0-100},
  "provas_faltantes": {"valor": "<provas típicas que faltam para instruir>", "confianca": 0-100},
  "valor_causa": {"valor": "<estimativa em R$ ou faixa, ou null>", "confianca": 0-100},
  "risco_processual": {"valor": "baixo"|"medio"|"alto", "confianca": 0-100},
  "pedidos_principais": {"valor": "<pedidos principais cabíveis>", "confianca": 0-100}
}"""


# ── Helpers de parse defensivo (padrão triagem_entrevista) ────────────────────

def _parse_json(txt: str) -> Optional[dict]:
    """Extrai o primeiro objeto JSON da resposta da IA (fallback tolerante)."""
    if not txt:
        return None
    try:
        obj = json.loads(txt)
        return obj if isinstance(obj, dict) else None
    except Exception:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
    return None


def _conf(v: Any) -> Optional[int]:
    """Confiança 0-100 ou None — nunca propaga lixo da IA."""
    try:
        return max(0, min(100, int(float(v))))
    except (TypeError, ValueError):
        return None


def _valor_str(v: Any, limite: int = 4000) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v  # tratado à parte (tutela_urgencia)
    if isinstance(v, (str, int, float)):
        s = str(v).strip()
        return s[:limite] or None
    return None


def _contexto_caso(case: Case, provas: list[Prova]) -> str:
    """Contexto DETERMINÍSTICO do caso (só campos do próprio caso) — único insumo
    fático dado à IA (mesmo racional de provas._contexto_sugestao)."""
    area = case.area.value if hasattr(case.area, "value") else str(case.area or "—")
    tipo_acao = (getattr(case, "tipo_acao_prescricao", None)
                 or getattr(case, "extrajudicial_type", None)
                 or getattr(case, "case_type", None)
                 or "não informado")
    linhas = [
        f"Área do direito: {area}",
        f"Título do caso: {case.titulo or '—'}",
        f"Tipo de ação: {tipo_acao}",
        f"Tese principal: {(case.tese_principal or 'não informada').strip()[:2000]}",
        "",
        "Provas JÁ EXISTENTES no caso:",
    ]
    if provas:
        for p in provas:
            fato = (p.fato_probando or "não informado").strip()[:400]
            linhas.append(f"- [{p.tipo}] {p.titulo} — fato probando: {fato}")
    else:
        linhas.append("- (nenhuma prova cadastrada ainda)")
    return "\n".join(linhas)


def _provas_disponiveis_texto(provas: list[Prova]) -> Optional[str]:
    """provas_disponiveis derivado do acervo — determinístico (confiança 100)."""
    if not provas:
        return None
    return "; ".join(
        f"{p.titulo}" + (f" ({p.tipo})" if p.tipo else "") for p in provas
    )[:4000]


# ── pre_preencher ─────────────────────────────────────────────────────────────

async def pre_preencher(db: AsyncSession, case_id: str, *,
                        user_id: str, user_role: str) -> dict:
    """Monta o RASCUNHO dos 12 campos da ficha via IA de triagem + provas do
    acervo. NÃO persiste (rascunho de apoio); registra AILog (HITL)."""
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada na configuração")

    case = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if case is None:
        raise HTTPException(404, "Caso não encontrado")

    provas = list((await db.execute(
        select(Prova)
        .where(Prova.case_id == case_id, Prova.deleted_at.is_(None))
        .order_by(Prova.ordem, Prova.created_at)
    )).scalars())

    contexto = _contexto_caso(case, provas)

    # LGPD: nomes do caso pseudonimizados de forma REVERSÍVEL na barreira final do
    # gateway antes de qualquer provider externo (padrão sugerir-faltantes).
    from app.services.ai.entidades_caso import entidades_do_caso
    from app.services.ai_gateway import chat as gw_chat
    entidades = await entidades_do_caso(db, case_id) or None

    try:
        resp = await gw_chat(
            messages=[{"role": "system", "content": _SYSTEM_PROMPT},
                      {"role": "user", "content": contexto}],
            task_type="triagem", temperature=0.1, max_tokens=1600,
            entidades=entidades,
        )
    except Exception as e:
        logger.warning(f"pre_preencher: gateway indisponível: {e}")
        raise HTTPException(503, "IA indisponível no momento. Tente novamente.")

    dados = _parse_json(resp.texto)
    campos, confianca = _normalizar_campos(dados, provas)

    # AILog obrigatório (padrão ai_guard) — prompt sanitizado, sem PII.
    from app.services.ai_guard import registrar_ai_log
    from app.services.sanitizer import sanitizar_pii
    prompt_log, pii = sanitizar_pii(contexto)
    ai_log_id = await registrar_ai_log(
        db,
        user_id=user_id,
        tipo_uso=AITipoUso.analise_caso,
        case_id=case_id,
        prompt_sanitizado=("[FICHA_TRIAGEM pré-preenchimento IA]\n" + prompt_log),
        pii_removida=pii,
        resposta=(resp.texto or "")[:4000],
        modelo=f"{resp.provedor}/{resp.modelo}"[:50],
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
    )

    return {
        "status": "rascunho",
        "aviso": _AVISO_ESTIMATIVA,
        "case_id": case_id,
        "campos": campos,
        "confianca": confianca,
        "parse_ok": dados is not None,
        "provedor": resp.provedor,
        "modelo": f"{resp.provedor}/{resp.modelo}",
        "ai_log_id": ai_log_id,
    }


def _normalizar_campos(dados: Optional[dict],
                       provas: list[Prova]) -> tuple[dict, dict]:
    """Sempre devolve os 12 campos + confiança por campo (fallback null)."""
    d = dados or {}
    campos: dict[str, Any] = {}
    confianca: dict[str, Optional[int]] = {}

    for campo in _CAMPOS_IA:
        bruto = d.get(campo) if isinstance(d.get(campo), dict) else {}
        conf = _conf(bruto.get("confianca"))
        if campo == "tutela_urgencia":
            val = bool(bruto.get("valor")) if isinstance(bruto.get("valor"), bool) else False
        elif campo == "risco_processual":
            raw = _valor_str(bruto.get("valor"))
            val = raw.lower() if isinstance(raw, str) and raw.lower() in _RISCOS_VALIDOS else None
        else:
            val = _valor_str(bruto.get("valor"))
        campos[campo] = val
        confianca[campo] = conf

    # provas_disponiveis: DETERMINÍSTICO a partir do acervo (não é da IA).
    disp = _provas_disponiveis_texto(provas)
    campos["provas_disponiveis"] = disp
    confianca["provas_disponiveis"] = 100 if disp else None

    return campos, confianca


# ── obter / salvar / gate helpers ─────────────────────────────────────────────

async def obter(db: AsyncSession, case_id: str) -> Optional[FichaTriagem]:
    """Ficha CORRENTE do caso (uma por caso), ou None."""
    return (await db.execute(
        select(FichaTriagem).where(FichaTriagem.case_id == case_id)
    )).scalar_one_or_none()


async def ficha_confirmada(db: AsyncSession, case_id: str) -> Optional[FichaTriagem]:
    """Helper do gate: ficha do caso apenas se status == 'confirmada'."""
    ficha = await obter(db, case_id)
    return ficha if (ficha is not None and ficha.status == "confirmada") else None


async def salvar(db: AsyncSession, case_id: str, dados: dict, *,
                 confirmar: bool, user_id: str, user_role: str) -> FichaTriagem:
    """UPSERT da ficha do caso. confirmar=True → status 'confirmada' (abre o gate
    de geração de peça). Audit FICHA_TRIAGEM_SALVA / FICHA_TRIAGEM_CONFIRMADA."""
    ficha = await obter(db, case_id)
    novo = ficha is None
    if novo:
        ficha = FichaTriagem(id=str(uuid4()), case_id=case_id, created_by=user_id)
        db.add(ficha)

    # Campos texto (só os informados; None explícito limpa o campo).
    for campo in _CAMPOS_TEXTO:
        if campo in dados:
            v = dados[campo]
            setattr(ficha, campo, (str(v).strip()[:8000] or None) if v is not None else None)

    if "tutela_urgencia" in dados:
        ficha.tutela_urgencia = bool(dados["tutela_urgencia"])

    if "risco_processual" in dados:
        rp = dados["risco_processual"]
        rp = rp.lower().strip() if isinstance(rp, str) else None
        ficha.risco_processual = rp if rp in _RISCOS_VALIDOS else None

    if "confianca" in dados and isinstance(dados["confianca"], dict):
        # Só ints 0-100 por chave — nunca persiste lixo.
        ficha.confianca = {
            str(k): c for k, v in dados["confianca"].items()
            if (c := _conf(v)) is not None
        } or None

    ficha.status = "confirmada" if confirmar else "rascunho"

    acao = "FICHA_TRIAGEM_CONFIRMADA" if confirmar else "FICHA_TRIAGEM_SALVA"
    await criar_audit_log(db, user_id, user_role, acao, "fichas_triagem",
                          ficha.id, detalhes=f"caso {case_id} — status {ficha.status}")
    await db.commit()
    return ficha


# ── resumo p/ o prompt de geração ─────────────────────────────────────────────

# Rótulos legíveis dos campos substantivos — SÓ campos estruturados da triagem
# (nunca IDs, created_by, status ou o dict de confiança) para não vazar metadado
# interno no prompt da peça.
_ROTULOS: tuple[tuple[str, str], ...] = (
    ("competencia", "Competência"),
    ("rito", "Rito"),
    ("legitimidade_ativa", "Legitimidade ativa"),
    ("legitimidade_passiva", "Legitimidade passiva"),
    ("prescricao_decadencia", "Prescrição/decadência"),
    ("provas_disponiveis", "Provas disponíveis"),
    ("provas_faltantes", "Provas faltantes"),
    ("valor_causa", "Valor da causa"),
    ("pedidos_principais", "Pedidos principais"),
    ("pedidos_subsidiarios", "Pedidos subsidiários"),
)


def resumo_para_prompt(ficha: FichaTriagem) -> str:
    """Texto compacto dos campos CONFIRMADOS para ancorar a peça na triagem.
    Só campos substantivos (sem IDs, confiança, status ou created_by)."""
    linhas: list[str] = []
    for campo, rotulo in _ROTULOS:
        val = getattr(ficha, campo, None)
        if val is not None and str(val).strip():
            linhas.append(f"- {rotulo}: {str(val).strip()}")

    if ficha.tutela_urgencia:
        fund = (ficha.tutela_fundamento or "").strip()
        linhas.append("- Tutela de urgência: SIM"
                      + (f" — {fund}" if fund else ""))

    if ficha.risco_processual:
        nota = (ficha.risco_nota or "").strip()
        linhas.append(f"- Risco processual: {ficha.risco_processual}"
                      + (f" — {nota}" if nota else ""))

    if not linhas:
        return ""
    return "Enquadramento confirmado na triagem do caso:\n" + "\n".join(linhas)
