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
from app.core.ai_brain import ai_brain

router = APIRouter(prefix="/intelligence-v3", tags=["Intelligence"])

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
    # Auditoria obrigatória (LGPD/OAB): este endpoint passava pelo shim legado
    # (ai_brain.generate) sem gravar AILog (furo #4a). Trocamos por
    # processar_demanda, que percorre o MESMO caminho de modelo que
    # generate("principal") — tipo "juridico_profundo" → task "analise_juridica"
    # via core.ai_brain._chamar_central — e apenas EXPÕE o modelo real usado,
    # permitindo o rastro obrigatório. A resposta ao cliente é idêntica
    # ({"resumo_executivo": <mesmo texto>}), inclusive no caminho de erro.
    res = await ai_brain.processar_demanda(prompt, tipo="juridico_profundo")
    analise = res["resposta"]

    if res.get("status") == "sucesso":
        from app.services.ai_guard import registrar_ai_log
        from app.models.ai_log import AITipoUso
        from app.services.sanitizer import sanitizar_pii
        # LGPD: só o prompt SANITIZADO entra no AILog (o próprio shim já sanitiza
        # antes de enviar ao provider; aqui sanitizamos o que registramos).
        prompt_log, pii = sanitizar_pii(prompt)
        await registrar_ai_log(
            db, user_id=cu.id, tipo_uso=AITipoUso.outro, case_id=None,
            prompt_sanitizado=prompt_log, pii_removida=pii,
            resposta=analise, modelo=res.get("modelo_utilizado"),
        )
    return {"resumo_executivo": analise}
