"""
qualidade.py — Qualidade jurídica.
#46 verificar-citacoes (lookup exato no RAG) · #48 consistência interna da peça ·
#49 simulador de parte contrária. Aditivo e isolado. IA via ai_gateway (Groq),
com sanitização LGPD antes do envio e tag de RASCUNHO (HITL/OAB).
"""
from __future__ import annotations
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.services.citation_check import verificar_citacoes
from app.services import ai_gateway
from app.services.sanitizer import sanitizar_pii
from app.core.rate_limit import rate_limit

router = APIRouter(prefix="/qualidade", tags=["Qualidade Jurídica"])

_AVISO = ("RASCUNHO gerado por IA — revisão obrigatória do advogado responsável (OAB). "
          "Não substitui a análise humana.")

_SYS_CONSIST = (
    "Você é revisor jurídico sênior. Analise a CONSISTÊNCIA INTERNA da peça: "
    "(1) cada PEDIDO está sustentado pelos FATOS narrados e pela fundamentação? "
    "(2) há CONTRADIÇÕES entre seções? (3) algum pedido ficou sem fundamento ou algum "
    "fato sem consequência? Liste cada problema classificado como CRÍTICO, IMPORTANTE ou "
    "SUGESTÃO, citando a seção. NÃO invente conteúdo — aponte apenas o que está no texto. "
    "Toda saída é rascunho para revisão do advogado."
)
_SYS_ADVERSARIO = (
    "Você assume o papel do ADVOGADO DA PARTE CONTRÁRIA. Diante da tese/argumento do "
    "escritório, produza os CONTRA-ARGUMENTOS mais fortes que a parte adversa levantaria, "
    "as PROVAS que ela pediria e as TESES DEFENSIVAS cabíveis — para que nosso advogado se "
    "prepare. Seja incisivo e realista. NÃO invente lei, súmula ou jurisprudência; se citar, "
    "escreva 'verificar'. NÃO prometa resultado. Saída é rascunho de preparação."
)


async def _log(db, cu, prompt_sanitizado: str, houve_pii: bool, resp) -> str:
    """Auditoria: rastro obrigatório em ai_logs (HITL/LGPD)."""
    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso
    return await registrar_ai_log(
        db, user_id=cu.id, tipo_uso=AITipoUso.outro, case_id=None,
        prompt_sanitizado=prompt_sanitizado[:8000], pii_removida=houve_pii,
        resposta=resp.texto, modelo=f"{resp.provedor}/{resp.modelo}",
        tokens_input=resp.input_tokens, tokens_output=resp.output_tokens,
    )


class VerificarCitacoesReq(BaseModel):
    texto: str = Field(..., min_length=10, max_length=60000)


class ConsistenciaReq(BaseModel):
    texto: str = Field(..., min_length=30, max_length=40000, description="Texto da peça")


class AdversarioReq(BaseModel):
    tese: str = Field(..., min_length=20, max_length=20000, description="Tese/argumento do escritório")
    area: str | None = Field(None, description="Área jurídica (opcional)")


@router.post("/verificar-citacoes", dependencies=[Depends(rate_limit("qualidade-citacoes", 15))])
async def verificar(req: VerificarCitacoesReq, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(require_roles(["estagiario"]))):
    """Confere cada súmula/artigo citado contra a base oficial (RAG)."""
    return await verificar_citacoes(db, req.texto)


@router.post("/consistencia", dependencies=[Depends(rate_limit("qualidade-consistencia", 15))])
async def consistencia(req: ConsistenciaReq, db: AsyncSession = Depends(get_db),
                       cu: User = Depends(require_roles(["estagiario"]))):
    """Analisa coerência interna da peça (pedidos × fatos, contradições)."""
    limpo, houve_pii = sanitizar_pii(req.texto)
    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": _SYS_CONSIST},
                  {"role": "user", "content": limpo[:30000]}],
        task_type="auditoria_peca", temperature=0.2, max_tokens=1600,
    )
    log_id = await _log(db, cu, limpo, houve_pii, resp)
    return {"analise": resp.texto, "modelo": f"{resp.provedor}/{resp.modelo}",
            "is_draft": True, "is_rascunho": True, "aviso": _AVISO,
            "aviso_hitl": _AVISO, "log_id": log_id}


@router.post("/simular-adversario", dependencies=[Depends(rate_limit("qualidade-adversario", 10))])
async def simular_adversario(req: AdversarioReq, db: AsyncSession = Depends(get_db),
                             cu: User = Depends(require_roles(["estagiario"]))):
    """Gera os contra-argumentos da parte contrária para preparar a defesa."""
    limpo, houve_pii = sanitizar_pii(req.tese)
    ctx = f"Área: {req.area}\n\n" if req.area else ""
    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": _SYS_ADVERSARIO},
                  {"role": "user", "content": f"{ctx}TESE DO ESCRITÓRIO:\n{limpo}"}],
        task_type="estrategia", temperature=0.3, max_tokens=1600,
    )
    log_id = await _log(db, cu, limpo, houve_pii, resp)
    return {"contra_argumentos": resp.texto, "modelo": f"{resp.provedor}/{resp.modelo}",
            "is_draft": True, "is_rascunho": True, "aviso": _AVISO,
            "aviso_hitl": _AVISO, "log_id": log_id}
