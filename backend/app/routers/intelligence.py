"""
Router EJC Intelligence — Radar de Poder v3.0
Monitoramento dos Três Poderes e Antecipação Estratégica.
"""
import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services.radar_poder import radar_poder

# Mensagem de erro seguro do caminho de IA (antes em core.ai_brain — aposentado;
# auditoria Fase 7: último consumidor migrou ao gateway canônico).
_ERRO_SEGURO_IA = "Erro na comunicação com a IA. Tente novamente em instantes."

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])

@router.get("/radar/legislativo", dependencies=[Depends(rate_limit("radar-legislativo", 10))])
async def radar_legislativo(cu: User = Depends(get_current_user)):
    # Item 5.11: "veterinario" está fora do escopo do escritório (achado da
    # auditoria: "medicamentos veterinários"). "medicamento" é mantido por
    # cobrir projetos de ANVISA/pharma com viés tributário/regulatório.
    keywords = ["tributo", "pis", "cofins", "medicamento", "administrativo"]
    camara, senado = await asyncio.gather(
        radar_poder.monitorar_projetos_lei(keywords),
        radar_poder.monitorar_materias_senado(keywords),
    )
    for p in camara:  # shape da Câmara não traz casa/link — normaliza aditivamente
        p.setdefault("casa", "camara")
        p.setdefault("link", (
            "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao"
            f"?idProposicao={p.get('id')}"
        ))
    return {"alertas_legislativos": camara + senado}

@router.post("/analise-impacto", dependencies=[Depends(rate_limit("analise-impacto", 10))])
async def analise_impacto(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    texto_noticia = payload.get("texto")
    prompt = f"""
    Como especialista em Inteligência Política, analise este fato e gere um Resumo Executivo de Impacto:
    Fato: {texto_noticia}

    Estrutura:
    1. O que mudou?
    2. Qual o impacto imediato para empresas e advogados?
    3. Qual a ação recomendada para o Dr. Clovis?
    """
    # Auditoria obrigatória (LGPD/OAB): AILog com prompt SANITIZADO. O caminho
    # canônico é o gateway central (app.services.ai_gateway.chat) — mesmo caminho
    # de modelo do antigo shim core.ai_brain (aposentado): task_type
    # "analise_juridica" pela cadeia de providers, com barreira final de PII.
    # Em falha: mensagem segura, sem AILog, sem propagar exceção.
    from app.services import ai_gateway as gateway_central
    from app.services.sanitizer import sanitizar_pii

    prompt_limpo, _ = sanitizar_pii(prompt)
    modelo_utilizado: str | None = None
    try:
        resp = await gateway_central.chat(
            [{"role": "user", "content": prompt_limpo}],
            task_type="analise_juridica",
        )
        analise = resp.texto
        modelo_utilizado = f"{resp.provedor}/{resp.modelo}"
    except Exception as exc:  # noqa: BLE001 — erro seguro, nunca propaga
        import logging

        logging.getLogger("ejc.ai_gateway").error(
            "AI Gateway central (analise-impacto): %s: %.200s",
            type(exc).__name__,
            str(exc),
        )
        return {"resumo_executivo": _ERRO_SEGURO_IA}

    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso

    # LGPD: só o prompt SANITIZADO entra no AILog.
    prompt_log, pii = sanitizar_pii(prompt)
    await registrar_ai_log(
        db, user_id=cu.id, tipo_uso=AITipoUso.outro, case_id=None,
        prompt_sanitizado=prompt_log, pii_removida=pii,
        resposta=analise, modelo=modelo_utilizado,
    )
    return {"resumo_executivo": analise}
