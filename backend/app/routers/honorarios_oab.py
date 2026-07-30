"""
honorarios_oab.py — Estimador de honorários ESTRUTURADO (P2.1).
POST /api/honorarios-oab/estimar  → mínimo / recomendado / estratégico + contrato
sugerido + memória de cálculo, ANCORADO somente em itens estruturados, vigentes
e com fonte oficial OAB/MG verificável. GET /api/honorarios-oab/tabela expõe os
itens elegíveis e o critério de fonte (transparência).

REGRAS (CLAUDE.md): nunca inventa item da tabela; nunca promete resultado; tudo
é referência — o advogado define o valor final.
"""
import json
import re
from datetime import date
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import ROLE_LEVEL, get_current_user, requer_advogado
from app.models.audit_log import criar_audit_log
from app.models.fee_proposal import FeeProposal
from app.models.redesign import TabelaOABHonorario
from app.models.user import User
from app.services import ai_gateway, fee_proposal_service
from app.services.geracao_documental import (
    _area_str,
    _item_dict,
    _itens_oab_vigentes,
)
from app.core.rate_limit import rate_limit

router = APIRouter(prefix="/honorarios-oab", tags=["Honorários OAB"])

REGRAS = (
    "REGRAS: (1) Cite SOMENTE itens que aparecem textualmente no contexto da tabela; "
    "se não houver item específico, não preencha valores e registre a insuficiência. "
    "(2) NUNCA invente número de item ou referência de mercado. "
    "(3) NUNCA prometa resultado. (4) Tudo é referência; o advogado define o valor final."
)

_DOMINIO_OFICIAL_OABMG = "oabmg.org.br"
_FONTE_URL_RE = re.compile(r"https://[^\\s<>()\\[\\]{}]+", re.IGNORECASE)
MENSAGEM_TABELA_INDISPONIVEL = (
    "Estimativa indisponível: não há item vigente da tabela oficial OAB/MG "
    "com vigência informada e fonte HTTPS no domínio oabmg.org.br para esta área. "
    "Cadastre e valide a fonte oficial antes de calcular valores."
)


def _fonte_oabmg_oficial(fonte: Optional[str]) -> bool:
    """Aceita somente URL HTTPS hospedada no domínio institucional da OAB/MG."""
    for candidata in _FONTE_URL_RE.findall(fonte or ""):
        url = candidata.rstrip(".,;:!?)")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme == "https"
            and (
                host == _DOMINIO_OFICIAL_OABMG
                or host.endswith(f".{_DOMINIO_OFICIAL_OABMG}")
            )
        ):
            return True
    return False


def _item_oab_verificado(item: TabelaOABHonorario) -> bool:
    """Barreira de uso: origem oficial, vigência conhecida e valor verificável."""
    return bool(
        item.vigencia_inicio
        and _fonte_oabmg_oficial(item.fonte)
        and (item.valor_minimo is not None or item.percentual is not None)
    )


class EstimativaIn(BaseModel):
    area: str
    tipo_acao: str = Field(min_length=2, max_length=200)
    valor_causa: Optional[float] = None
    complexidade: str = "media"           # baixa | media | alta
    tempo_meses: Optional[int] = None
    num_atos: Optional[int] = None
    instancia: Optional[str] = None        # 1grau | 2grau | superior
    observacoes: Optional[str] = None


def _parse_json(txt: str) -> Optional[dict]:
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def _contexto_oab(
    db: AsyncSession,
    area: str,
    tipo_acao: str,
) -> tuple[str, list[TabelaOABHonorario]]:
    """Usa somente itens estruturados, vigentes e com fonte oficial verificável."""
    _ = tipo_acao  # preservado no contrato da API; seleção é restrita à área
    itens = await _itens_oab_vigentes(db, area, date.today(), limite=20)
    verificados = [item for item in itens if _item_oab_verificado(item)]
    contexto = "\n".join(
        f"- {json.dumps(_item_dict(item), ensure_ascii=False, sort_keys=True)}"
        for item in verificados
    )
    return contexto, verificados


@router.get("/tabela")
async def itens_tabela(
    area: str = "",
    tipo: str = "",
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Expõe somente itens vigentes cuja fonte oficial pode ser verificada."""
    _, itens = await _contexto_oab(db, area, tipo)
    return {
        "disponivel": bool(itens),
        "itens": [_item_dict(item) for item in itens],
        "criterio_fonte": "HTTPS no domínio oficial oabmg.org.br e vigência informada",
        "mensagem": None if itens else MENSAGEM_TABELA_INDISPONIVEL,
    }


@router.post("/estimar", dependencies=[Depends(rate_limit("honorarios-estimar", 15))])
async def estimar(
    body: EstimativaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    ctx_txt, itens = await _contexto_oab(db, body.area, body.tipo_acao)
    if not itens:
        # Fail closed: sem fonte oficial vigente, nenhuma IA é chamada e nenhum
        # valor genérico de mercado é produzido.
        raise HTTPException(status_code=503, detail=MENSAGEM_TABELA_INDISPONIVEL)

    sys = "Você estima honorários ancorado na TABELA OAB/MG verificada. " + REGRAS
    ctx_bloco = f"TABELA OAB/MG (itens estruturados e vigentes):\n{ctx_txt}"
    fund = (
        '"fundamento": "<item EXATO do contexto que embasa; '
        'se insuficiente, explique sem calcular>",'
    )

    fatores = (
        f"Área: {body.area} | Tipo de ação: {body.tipo_acao} | "
        f"Valor da causa: {body.valor_causa} | Complexidade: {body.complexidade} | "
        f"Tempo estimado: {body.tempo_meses} meses | Nº de atos: {body.num_atos} | "
        f"Instância: {body.instancia or 'não informada'}"
        + (f" | Obs: {body.observacoes}" if body.observacoes else "")
    )
    user = (
        f"{ctx_bloco}\n\nFATORES DO CASO:\n{fatores}\n\n"
        "Calcule três cenários considerando complexidade, tempo e nº de atos. "
        "Responda APENAS JSON: {"
        '"minimo": "<valor ou regra>", '
        '"recomendado": "<valor ou faixa>", '
        '"estrategico": "<valor ou faixa>", '
        + fund
        + " "
        '"memoria_calculo": "<como chegou aos valores, em 1-2 frases>", '
        '"contrato_sugerido": "<estrutura contratual sem promessa de resultado>", '
        '"tabela_oficial_disponivel": true}'
    )

    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        task_type="analise_juridica",
        temperature=0.2,
        max_tokens=800,
    )
    data = _parse_json(resp.texto) or {"_bruto": resp.texto[:800]}
    data["tabela_oficial_disponivel"] = True
    data["_aviso"] = (
        "Estimativa de referência ancorada em itens vigentes com fonte oficial "
        "verificada. Exige revisão humana; o advogado define o valor final."
    )
    return data


# ── Gestão da tabela estruturada (P0.4) ───────────────────────────────────────
# tabela_oab_honorarios é versionada por vigência (models/redesign.py):
# nova vigência = NOVOS registros (fechar vigencia_fim dos antigos), nunca
# sobrescrever. Entrada manual dos itens que o seed não importou (layout de
# 2 colunas do PDF) — `fonte` OBRIGATÓRIA (nunca inventar valor/vigência).
# Restrito a sócio+, com auditoria.

def _req_socio(cu: User = Depends(get_current_user)) -> User:
    role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    if ROLE_LEVEL.get(role, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(status_code=403, detail="Acesso restrito a sócios/administração")
    return cu


def _item_out(i: TabelaOABHonorario) -> dict:
    """Shape de GESTÃO (CRUD sócio+) = shape de consulta VERBATIM
    (geracao_documental._item_dict, fonte única dos campos comuns) + campos
    administrativos (id/área/observações/ativo)."""
    return {
        **_item_dict(i),
        "id": i.id,
        "area_juridica": i.area_juridica,
        "observacoes": i.observacoes,
        "ativo": bool(i.ativo),
    }


class ItemOABIn(BaseModel):
    """Entrada manual de item da tabela — valores VERBATIM da fonte oficial."""
    item_codigo: str = Field(min_length=1, max_length=30)
    descricao: str = Field(min_length=3, max_length=300)
    area_juridica: Optional[str] = Field(None, max_length=50)
    valor_minimo: Optional[float] = Field(None, ge=0)
    percentual: Optional[float] = Field(None, ge=0, le=100)
    unidade: Optional[str] = Field(None, max_length=30)
    # Obrigatória: o sistema nunca presume início de vigência.
    vigencia_inicio: date
    observacoes: Optional[str] = Field(None, max_length=2000)
    fonte: str = Field(min_length=5, max_length=300)  # documento/URL oficial OAB/MG

    @field_validator("fonte")
    @classmethod
    def _fonte_identificavel(cls, v: str) -> str:
        v = v.strip()
        if not _fonte_oabmg_oficial(v):
            raise ValueError(
                "fonte deve conter URL HTTPS no domínio oficial oabmg.org.br"
            )
        return v


class EncerrarVigenciaIn(BaseModel):
    # Data informada pelo usuário — o sistema não presume o fim da vigência.
    vigencia_fim: date
    motivo: Optional[str] = Field(None, max_length=300)


@router.get("/itens")
async def listar_itens(
    area: str = "",
    incluir_encerrados: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Itens estruturados da tabela OAB/MG (transparência/gestão)."""
    q = select(TabelaOABHonorario)
    if not incluir_encerrados:
        q = q.where(TabelaOABHonorario.ativo.is_(True))
    if area:
        q = q.where(TabelaOABHonorario.area_juridica.ilike(f"%{area}%"))
    q = q.order_by(TabelaOABHonorario.item_codigo,
                   TabelaOABHonorario.vigencia_inicio.desc().nullslast()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return {"total": len(rows), "itens": [_item_out(i) for i in rows]}


@router.post("/itens", status_code=201,
             dependencies=[Depends(rate_limit("oab-itens", 30))])
async def criar_item(
    body: ItemOABIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_socio),
):
    """Cadastra manualmente um item da tabela (fonte obrigatória, auditado).

    Versionamento: se já existe item ATIVO com mesmo código e vigência aberta
    (QUALQUER fonte), é preciso encerrar a vigência anterior antes — nunca
    sobrescrever nem criar item paralelo que "sombreie" o vigente.
    """
    dup = (await db.execute(
        select(TabelaOABHonorario).where(
            TabelaOABHonorario.item_codigo == body.item_codigo,
            TabelaOABHonorario.ativo.is_(True),
            TabelaOABHonorario.vigencia_fim.is_(None),
        ).limit(1)
    )).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(
            status_code=409,
            detail=("Já existe item ativo com este código em vigência aberta "
                    f"(fonte: {dup.fonte}). Encerre a vigência anterior antes de "
                    "registrar a nova (versionamento)."),
        )

    item = TabelaOABHonorario(
        id=str(uuid4()),
        item_codigo=body.item_codigo,
        descricao=body.descricao,
        area_juridica=body.area_juridica,
        valor_minimo=body.valor_minimo,
        percentual=body.percentual,
        # VERBATIM da fonte: sem default — item só-percentual não ganha "R$".
        unidade=body.unidade,
        vigencia_inicio=body.vigencia_inicio,
        vigencia_fim=None,
        fonte=body.fonte,
        observacoes=body.observacoes,
        ativo=True,
    )
    db.add(item)
    await criar_audit_log(
        db, cu.id, cu.role.value if hasattr(cu.role, "value") else str(cu.role),
        "CREATE", "tabela_oab_honorarios", item.id,
        detalhes=f"Entrada manual item {body.item_codigo} (fonte: {body.fonte})",
        dados_depois=_item_out(item),
    )
    await db.commit()
    return _item_out(item)


@router.post("/itens/{item_id}/encerrar-vigencia",
             dependencies=[Depends(rate_limit("oab-itens", 30))])
async def encerrar_vigencia(
    item_id: str,
    body: EncerrarVigenciaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_socio),
):
    """Encerra a vigência de um item (versionamento): fecha vigencia_fim e
    desativa — os valores históricos NUNCA são alterados/sobrescritos."""
    item = (await db.execute(
        select(TabelaOABHonorario).where(TabelaOABHonorario.id == item_id)
    )).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item da tabela não encontrado")
    if item.vigencia_fim is not None:
        raise HTTPException(status_code=409, detail="Vigência deste item já está encerrada")
    if item.vigencia_inicio and body.vigencia_fim < item.vigencia_inicio:
        raise HTTPException(status_code=422,
                            detail="vigencia_fim anterior à vigencia_inicio do item")

    antes = _item_out(item)
    item.vigencia_fim = body.vigencia_fim
    item.ativo = False
    await criar_audit_log(
        db, cu.id, cu.role.value if hasattr(cu.role, "value") else str(cu.role),
        "UPDATE", "tabela_oab_honorarios", item.id,
        detalhes=("Encerramento de vigência"
                  + (f" — motivo: {body.motivo}" if body.motivo else "")),
        dados_antes=antes, dados_depois=_item_out(item),
    )
    await db.commit()
    return _item_out(item)


# ── FASE 4: Proposta de Honorários imutável com aprovação (HITL) ─────────────
# Motor DETERMINÍSTICO (fee_proposal_service): sugestão ancorada no item OAB
# vigente (verbatim; sem item → nada preenchido automaticamente); proposta
# APROVADA é imutável (mudança = nova versão); contrato completo só a partir
# de proposta aprovada. Restrito a advogado+ com ownership do caso e rate limit.

def _req_advogado(cu: User = Depends(get_current_user)) -> User:
    # Proposta/aprovação de honorários é ato jurídico: advogado+ (nível >= 6).
    requer_advogado(cu)
    return cu


class FaixaIn(BaseModel):
    valor: Optional[float] = Field(None, ge=0)
    memoria_calculo: Optional[str] = Field(None, max_length=2000)


class FaixasIn(BaseModel):
    minimo_etico: FaixaIn = FaixaIn()
    recomendado: FaixaIn = FaixaIn()
    estrategico: FaixaIn = FaixaIn()


class ParcelamentoIn(BaseModel):
    """Parcelamento estruturado — validado na ENTRADA (422), nunca 500 tardio
    quando _forma_pagamento monta o texto do contrato."""
    entrada: Optional[float] = Field(None, ge=0)
    num_parcelas: Optional[int] = Field(None, ge=1)
    valor_parcela: Optional[float] = Field(None, ge=0)
    descricao: Optional[str] = Field(None, max_length=500)


class PropostaIn(BaseModel):
    """Rascunho de proposta — valores definidos/confirmados pelo ADVOGADO
    (a sugestão determinística do endpoint /sugerir é apenas referência)."""
    faixas: FaixasIn = FaixasIn()
    origem_tabela: Optional[dict] = None      # item OAB verbatim (da sugestão)
    exito_percentual: Optional[float] = Field(None, ge=0, le=100)
    parcelamento: Optional[ParcelamentoIn] = None
    despesas_criterio: Optional[str] = Field(None, max_length=2000)
    justificativa: Optional[str] = Field(None, max_length=4000)


class SugerirPropostaIn(BaseModel):
    """Entrada opcional da sugestão: item OAB escolhido pelo advogado."""
    item_codigo: Optional[str] = Field(None, max_length=30)


class RejeitarPropostaIn(BaseModel):
    motivo: Optional[str] = Field(None, max_length=500)


@router.post("/casos/{case_id}/proposta/sugerir",
             dependencies=[Depends(rate_limit("proposta-honorarios", 15))])
async def sugerir_proposta_honorarios(
    case_id: str,
    body: Optional[SugerirPropostaIn] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_advogado),
):
    """Sugestão DETERMINÍSTICA de faixas (não persiste nada; nunca inventa
    valor — sem item OAB vigente, o mínimo fica None com aviso explícito).
    `item_codigo` opcional escolhe o item OAB (validado contra os vigentes);
    sem ele, a resposta declara a escolha automática e lista os candidatos."""
    case = await verificar_acesso_caso(db, cu, case_id)
    return await fee_proposal_service.sugerir_proposta(
        db, case, _area_str(case),
        item_codigo=(body.item_codigo if body else None))


@router.post("/casos/{case_id}/proposta", status_code=201,
             dependencies=[Depends(rate_limit("proposta-honorarios", 15))])
async def criar_proposta_honorarios(
    case_id: str,
    body: PropostaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_advogado),
):
    """Cria RASCUNHO de proposta (versao = max+1 do caso; auditado).

    `origem_tabela.item_codigo` (quando presente) é REvalidado contra os itens
    vigentes da área: sem correspondência, grava `validada=False` com aviso —
    transparência sem bloquear (o advogado define o valor final).
    """
    case = await verificar_acesso_caso(db, cu, case_id)
    dados = body.model_dump()
    origem = dados.get("origem_tabela")
    if isinstance(origem, dict) and str(origem.get("item_codigo") or "").strip():
        from app.services.geracao_documental import _itens_oab_vigentes
        cod = str(origem["item_codigo"]).strip()
        itens = await _itens_oab_vigentes(db, _area_str(case), date.today(),
                                          limite=20)
        if cod in {(i.item_codigo or "").strip() for i in itens}:
            origem["validada"] = True
        else:
            origem["validada"] = False
            origem["aviso_validacao"] = (
                "item_codigo não corresponde a item VIGENTE da Tabela OAB/MG "
                "para a área do caso — confira a fonte (não bloqueante).")
    p = await fee_proposal_service.criar_proposta(db, case.id, cu, dados)
    return fee_proposal_service.proposta_out(p)


@router.get("/casos/{case_id}/proposta")
async def obter_propostas_honorarios(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Proposta aprovada VIGENTE + histórico completo de versões do caso."""
    case = await verificar_acesso_caso(db, cu, case_id)
    vigente = await fee_proposal_service.proposta_aprovada_vigente(db, case.id)
    historico = (await db.execute(
        select(FeeProposal).where(FeeProposal.case_id == case.id)
        .order_by(FeeProposal.versao.desc())
    )).scalars().all()
    return {
        "case_id": case.id,
        "vigente": fee_proposal_service.proposta_out(vigente) if vigente else None,
        "historico": [fee_proposal_service.proposta_out(p) for p in historico],
        "total": len(historico),
    }


@router.post("/propostas/{proposta_id}/aprovar",
             dependencies=[Depends(rate_limit("proposta-honorarios", 15))])
async def aprovar_proposta_honorarios(
    proposta_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_advogado),
):
    """Aprova e CONGELA a proposta (imutável); aprovadas anteriores do caso
    viram 'substituida'. Ownership via caso da proposta; auditado."""
    p = await fee_proposal_service.obter_proposta(db, proposta_id)
    await verificar_acesso_caso(db, cu, p.case_id)
    p = await fee_proposal_service.aprovar(db, proposta_id, cu)
    return fee_proposal_service.proposta_out(p)


@router.post("/propostas/{proposta_id}/rejeitar",
             dependencies=[Depends(rate_limit("proposta-honorarios", 15))])
async def rejeitar_proposta_honorarios(
    proposta_id: str,
    body: Optional[RejeitarPropostaIn] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_advogado),
):
    """Rejeita um RASCUNHO de proposta (auditado)."""
    p = await fee_proposal_service.obter_proposta(db, proposta_id)
    await verificar_acesso_caso(db, cu, p.case_id)
    p = await fee_proposal_service.rejeitar(
        db, proposta_id, cu, motivo=(body.motivo if body else None),
    )
    return fee_proposal_service.proposta_out(p)
