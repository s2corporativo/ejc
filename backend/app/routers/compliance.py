"""
compliance.py — Compliance/LGPD (#88 Termo de consentimento de uso de IA).
Gera o termo (template, SEM IA) preenchido com cliente/caso, para assinatura e
arquivamento. Não substitui orientação jurídica — é documento operacional.
"""
from __future__ import annotations
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.case import Case
from app.models.client import Client

router = APIRouter(prefix="/compliance", tags=["Compliance / LGPD"])

_TERMO = """TERMO DE CONSENTIMENTO PARA USO DE INTELIGÊNCIA ARTIFICIAL

Escritório: De Paula Teixeira Advogados Associados (Betim/MG).
Cliente: {cliente}
Caso (ref. interna): {numero} — {titulo}
Data: {data}

Pelo presente, o(a) Cliente declara estar ciente e CONSENTIR que o escritório
utilize ferramentas de Inteligência Artificial como APOIO ao trabalho jurídico
(triagem, organização de informações, pesquisa e elaboração de minutas), nos
seguintes termos:

1. Todo conteúdo produzido por IA é RASCUNHO e passa por revisão obrigatória do
   advogado responsável (Provimento OAB) antes de qualquer uso.
2. Dados pessoais são tratados conforme a LGPD (Lei 13.709/2018); antes de
   qualquer processamento externo, informações identificáveis são anonimizadas.
3. A IA NÃO substitui o julgamento profissional do advogado nem garante resultado.
4. O Cliente pode, a qualquer tempo, revogar este consentimento por escrito.

_________________________________      _________________________________
Cliente                                 Advogado(a) responsável (OAB)
"""


@router.get("/cases/{case_id}/termo-consentimento-ia")
async def termo_consentimento_ia(case_id: str, db: AsyncSession = Depends(get_db),
                                 cu: User = Depends(get_current_user)):
    case = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None)))).scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Caso não encontrado")
    client = (await db.execute(
        select(Client).where(Client.id == case.client_id))).scalar_one_or_none()
    nome = "[NOME DO CLIENTE]"
    if client:
        nome = client.nome or client.razao_social or nome
    texto = _TERMO.format(
        cliente=nome,
        numero=case.numero_interno or "—",
        titulo=case.titulo or "—",
        data=date.today().strftime("%d/%m/%Y"),
    )
    return {
        "case_id": case_id,
        "cliente": nome,
        "termo": texto,
        "instrucao": "Imprimir, colher assinaturas (cliente + advogado) e arquivar no caso (Documentos).",
    }
