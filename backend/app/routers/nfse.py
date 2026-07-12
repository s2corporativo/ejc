# ── app/routers/nfse.py ──────────────────────────────────────────────────────
# NFS-e — emissão fiscal a partir de um honorário/recebível (ou avulsa).
#
# Emissão fiscal é AÇÃO SENSÍVEL: tudo gated por NFSE_ENABLED (503 se off) e por
# credenciais configuradas (422 se faltam); emissão/cancelamento exigem socio+ e
# geram audit log ANTES e DEPOIS (a trilha do "antes" é commitada antes de tocar
# o provedor, para não se perder se a chamada externa falhar). Idempotência:
# referencia = fee-<id> — não emite segunda nota para um honorário já em curso.
#
#   GET  /nfse/status          — advogado+  (booleans/ambiente p/ gate da UI)
#   POST /nfse/emitir          — socio+     (rate limit; audit; idempotente)
#   GET  /nfse/{id}            — advogado+  (atualiza do provedor se processando)
#   GET  /nfse/{id}/pdf        — advogado+  (DANFSe)
#   GET  /nfse/{id}/xml        — advogado+
#   POST /nfse/{id}/cancelar   — socio+     (motivo; audit)
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.fee import Fee
from app.models.nfse import NFSeStatus, NotaFiscalServico
from app.models.user import User
from app.services import nfse as nfse_service
from app.services.nfse import NFSePedidoEmissao, NFSeResultado, NFSeTomador

logger = logging.getLogger("ejc.nfse")

router = APIRouter(prefix="/nfse", tags=["NFS-e (emissão fiscal)"])

# socio+ = socio, admin, superadmin (hierarquia ROLE_LEVEL). advogado+ inclui advogado.
_SOCIO_MAIS = require_roles(["socio"])
_ADVOGADO_MAIS = require_roles(["advogado"])

# Status em que uma nota "ocupa" a referência (idempotência do fee).
_STATUS_ATIVOS = (NFSeStatus.processando.value, NFSeStatus.autorizada.value)


# ── Schemas ────────────────────────────────────────────────────────────────────

class TomadorIn(BaseModel):
    documento: str = Field(description="CPF ou CNPJ (com ou sem máscara)")
    nome: str
    email: str | None = None
    cod_municipio_ibge: str | None = None
    uf: str | None = None
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    bairro: str | None = None


class EmitirIn(BaseModel):
    """Informe fee_id (emite a partir do honorário) OU dados avulsos
    (tomador + valor + descrição)."""
    fee_id: str | None = None
    tomador: TomadorIn | None = None
    valor: Decimal | None = None
    descricao: str | None = None
    competencia: str | None = Field(default=None, description="YYYY-MM-DD; default = hoje")

    @model_validator(mode="after")
    def _valida(self):
        if not self.fee_id and not (self.tomador and self.valor is not None and self.descricao):
            raise ValueError(
                "Informe fee_id OU (tomador + valor + descricao) para nota avulsa."
            )
        return self


class CancelarIn(BaseModel):
    motivo: str = Field(min_length=3, description="Justificativa do cancelamento")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _role(cu: User) -> str:
    return getattr(cu.role, "value", str(cu.role))


def _nota_dict(n: NotaFiscalServico) -> dict:
    """Projeção segura da nota (sem segredos)."""
    return {
        "id": n.id,
        "fee_id": n.fee_id,
        "client_id": n.client_id,
        "provider": n.provider,
        "provider_id": n.provider_id,
        "referencia": n.referencia,
        "ambiente": n.ambiente,
        "status": n.status,
        "numero": n.numero,
        "chave_acesso": n.chave_acesso,
        "valor": str(n.valor) if n.valor is not None else None,
        "descricao": n.descricao,
        "pdf_url": n.pdf_url,
        "xml_url": n.xml_url,
        "mensagem_erro": n.mensagem_erro,
    }


def _tomador_de(cliente: Client | None, override: TomadorIn | None) -> NFSeTomador:
    """Monta o tomador do body (override) ou do cadastro do cliente.

    Os campos de documento do cliente podem estar apenas cifrados (cpf_enc/
    cnpj_enc) — nesses casos o cadastro não expõe o número em claro e o
    tomador precisa ser informado no body (documento é obrigatório na DPS).
    """
    if override is not None:
        return NFSeTomador(**override.model_dump())
    if cliente is None:
        raise HTTPException(
            status_code=422,
            detail="Sem tomador: informe o objeto `tomador` no body.",
        )
    documento = (cliente.cnpj or cliente.cpf or "").strip()
    nome = (cliente.razao_social or cliente.nome or "").strip()
    if not documento or not nome:
        raise HTTPException(
            status_code=422,
            detail=(
                "Cliente sem documento/nome em claro para a nota. Informe o "
                "objeto `tomador` no body (documento é obrigatório na DPS)."
            ),
        )
    return NFSeTomador(
        documento=documento, nome=nome, email=cliente.email,
        uf=cliente.estado, cep=cliente.cep,
        logradouro=cliente.logradouro, numero=cliente.numero, bairro=cliente.bairro,
    )


def _aplicar_resultado(n: NotaFiscalServico, r: NFSeResultado) -> None:
    n.status = r.status or n.status
    n.provider_id = r.provider_id or n.provider_id
    n.numero = r.numero or n.numero
    n.chave_acesso = r.chave_acesso or n.chave_acesso
    n.ambiente = r.ambiente or n.ambiente
    n.pdf_url = r.pdf_url or n.pdf_url
    n.xml_url = r.xml_url or n.xml_url
    n.mensagem_erro = "; ".join(r.mensagens) if r.mensagens else n.mensagem_erro


def _provider_ou_http():
    """get_provider() traduzindo erros de gate para HTTPException (503/422)."""
    try:
        return nfse_service.get_provider()
    except (nfse_service.NFSeDesabilitadaError, nfse_service.NFSeConfigError) as e:
        code, detail = nfse_service.http_status_para_erro(e)
        raise HTTPException(status_code=code, detail=detail)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
async def status_nfse(cu: User = Depends(_ADVOGADO_MAIS)):
    """Gate da UI — {enabled, configured, ambiente, provedor}, sem segredos."""
    return nfse_service.status_atual()


@router.post("/emitir", dependencies=[Depends(rate_limit("nfse_emitir", 6))])
async def emitir_nfse(
    body: EmitirIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_SOCIO_MAIS),
):
    """Emite uma NFS-e a partir de um honorário (fee_id) ou avulsa."""
    provider = _provider_ou_http()

    fee = None
    client_id = None
    if body.fee_id:
        fee = await db.get(Fee, body.fee_id)
        if fee is None or getattr(fee, "deleted_at", None) is not None:
            raise HTTPException(status_code=404, detail="Honorário não encontrado.")
        referencia = f"fee-{fee.id}"
        # Idempotência: já existe nota em curso/autorizada para este honorário?
        existente = await db.scalar(
            select(NotaFiscalServico).where(
                NotaFiscalServico.referencia == referencia,
                NotaFiscalServico.status.in_(_STATUS_ATIVOS),
            )
        )
        if existente is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Já existe NFS-e ({existente.status}) para este honorário "
                    f"(nota {existente.id}). Cancele-a antes de reemitir."
                ),
            )
        cliente = await db.get(Client, fee.client_id) if fee.client_id else None
        tomador = _tomador_de(cliente, body.tomador)
        valor = body.valor if body.valor is not None else fee.valor
        descricao = body.descricao or fee.descricao
        client_id = fee.client_id
    else:
        referencia = f"avulso-{uuid4().hex[:16]}"
        tomador = _tomador_de(None, body.tomador)
        valor = body.valor
        descricao = body.descricao

    if valor is None or not descricao:
        raise HTTPException(
            status_code=422,
            detail="Honorário sem valor/descrição — informe valor e descricao no body.",
        )

    pedido = NFSePedidoEmissao(
        referencia=referencia, tomador=tomador,
        descricao=descricao, valor=Decimal(str(valor)), competencia=body.competencia,
    )

    # Audit ANTES (durável): registra a INTENÇÃO de emitir antes de tocar o
    # provedor — se a chamada externa falhar, a tentativa fica na trilha.
    await criar_audit_log(
        db, cu.id, _role(cu), "NFSE_EMITIR", "nfse", None,
        detalhes=f"ref={referencia} ambiente={nfse_service.status_atual()['ambiente']}",
        dados_depois={"referencia": referencia, "fee_id": body.fee_id,
                      "valor": str(valor), "descricao": descricao},
    )
    await db.commit()

    try:
        resultado = await provider.emitir(pedido)
    except (nfse_service.NFSeConfigError, nfse_service.NFSeDesabilitadaError,
            nfse_service.NFSeProviderError) as e:
        code, detail = nfse_service.http_status_para_erro(e)
        raise HTTPException(status_code=code, detail=detail)

    nota = NotaFiscalServico(
        id=str(uuid4()),
        fee_id=body.fee_id, client_id=client_id,
        provider="nuvemfiscal", provider_id=resultado.provider_id,
        referencia=referencia, ambiente=resultado.ambiente or nfse_service.status_atual()["ambiente"],
        status=resultado.status, numero=resultado.numero, chave_acesso=resultado.chave_acesso,
        valor=Decimal(str(valor)), descricao=descricao,
        xml_url=resultado.xml_url, pdf_url=resultado.pdf_url,
        mensagem_erro="; ".join(resultado.mensagens) if resultado.mensagens else None,
        created_by=cu.id,
    )
    db.add(nota)
    await criar_audit_log(
        db, cu.id, _role(cu), "NFSE_EMITIDA", "nfse", nota.id,
        detalhes=f"status={resultado.status} provider_id={resultado.provider_id}",
        dados_depois={"status": resultado.status, "provider_id": resultado.provider_id,
                      "numero": resultado.numero},
    )
    await db.commit()
    return _nota_dict(nota)


@router.get("/{nota_id}")
async def obter_nfse(
    nota_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Consulta a nota; se `processando`, tenta atualizar do provedor."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if nota.status == NFSeStatus.processando.value and nota.provider_id:
        try:
            provider = nfse_service.get_provider()
            resultado = await provider.consultar(nota.provider_id)
            _aplicar_resultado(nota, resultado)
            await db.commit()
        except nfse_service.NFSeError:
            # Falha ao atualizar não derruba a leitura — devolve o estado salvo.
            logger.info("[nfse] falha ao atualizar nota %s do provedor", nota_id)
    return _nota_dict(nota)


@router.get("/{nota_id}/pdf")
async def baixar_pdf_nfse(
    nota_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Stream do DANFSe (PDF) da nota."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if not nota.provider_id:
        raise HTTPException(status_code=409, detail="Nota ainda não emitida no provedor.")
    provider = _provider_ou_http()
    try:
        pdf = await provider.baixar_pdf(nota.provider_id)
    except nfse_service.NFSeError as e:
        code, detail = nfse_service.http_status_para_erro(e)
        raise HTTPException(status_code=code, detail=detail)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="nfse-{nota.numero or nota.id}.pdf"'},
    )


@router.get("/{nota_id}/xml")
async def baixar_xml_nfse(
    nota_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """XML autorizado da nota."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if not nota.provider_id:
        raise HTTPException(status_code=409, detail="Nota ainda não emitida no provedor.")
    provider = _provider_ou_http()
    try:
        xml = await provider.baixar_xml(nota.provider_id)
    except nfse_service.NFSeError as e:
        code, detail = nfse_service.http_status_para_erro(e)
        raise HTTPException(status_code=code, detail=detail)
    return Response(
        content=xml, media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="nfse-{nota.numero or nota.id}.xml"'},
    )


@router.post("/{nota_id}/cancelar")
async def cancelar_nfse(
    nota_id: str,
    body: CancelarIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_SOCIO_MAIS),
):
    """Cancela a nota no provedor (motivo obrigatório; audit)."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if not nota.provider_id:
        raise HTTPException(status_code=409, detail="Nota ainda não emitida no provedor.")
    provider = _provider_ou_http()

    await criar_audit_log(
        db, cu.id, _role(cu), "NFSE_CANCELAR", "nfse", nota.id,
        detalhes=f"motivo={body.motivo}", dados_antes={"status": nota.status},
    )
    await db.commit()

    try:
        resultado = await provider.cancelar(nota.provider_id, body.motivo)
    except nfse_service.NFSeError as e:
        code, detail = nfse_service.http_status_para_erro(e)
        raise HTTPException(status_code=code, detail=detail)

    _aplicar_resultado(nota, resultado)
    await criar_audit_log(
        db, cu.id, _role(cu), "NFSE_CANCELADA", "nfse", nota.id,
        detalhes=f"status={nota.status}", dados_depois={"status": nota.status},
    )
    await db.commit()
    return _nota_dict(nota)
