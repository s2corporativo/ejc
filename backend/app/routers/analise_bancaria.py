"""Análise de documento jurídico por área — lê PDF/texto e aponta riscos e cláusulas questionáveis.
   Áreas: bancario, consumidor, trabalhista, empresarial, default. Usa o gateway de IA.
   Respeita: NUNCA inventa lei/jurisprudência, NUNCA promete resultado.
"""
import json
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import ai_gateway

router = APIRouter(prefix="/analise-bancaria", tags=["Análise de Documento"])

REGRAS = (
    "REGRAS INVIOLÁVEIS: (1) NÃO invente súmulas, leis, números de processo ou jurisprudência — só cite base "
    "legal se tiver certeza; senão escreva 'verificar'. (2) NUNCA prometa resultado. (3) Não afirme que algo É "
    "ilegal — diga 'pode ser questionável' e por quê."
)

AREA_PROMPTS = {
    "bancario": (
        "Você é analista de DIREITO BANCÁRIO. Analise o contrato bancário/financeiro buscando: taxa de juros e "
        "capitalização (anatocismo), comissão de permanência cumulada, venda casada e tarifas (TAC/TEC/seguro/"
        "avaliação), IOF financiado, CET, e cláusulas abusivas (CDC art. 51). " + REGRAS
    ),
    "consumidor": (
        "Você é analista de DIREITO DO CONSUMIDOR. Analise o contrato/documento de consumo buscando: cláusulas "
        "abusivas (CDC art. 51), multa/rescisão desproporcional, cobrança indevida, fidelização excessiva, "
        "negativa de cobertura (planos de saúde), reajuste abusivo, garantia/vício do produto e desequilíbrio "
        "contratual. " + REGRAS
    ),
    "trabalhista": (
        "Você é analista de DIREITO DO TRABALHO. Analise o contrato/CCT/documento trabalhista buscando: jornada e "
        "horas extras, verbas e descontos irregulares, cláusulas restritivas, terceirização, trabalho intermitente/"
        "teletrabalho, estabilidade e indícios de assédio. " + REGRAS
    ),
    "empresarial": (
        "Você é analista de DIREITO EMPRESARIAL/CONTRATUAL. Analise o contrato empresarial buscando: riscos "
        "jurídicos, cláusulas desequilibradas, multas/garantias, foro, rescisão, confidencialidade, "
        "responsabilidade e lacunas. " + REGRAS
    ),
    "tributario": (
        "Você é analista de DIREITO TRIBUTÁRIO. Analise o auto de infração / cobrança / documento fiscal buscando: "
        "vícios formais (fundamentação, prazo, competência), decadência/prescrição, base de cálculo e alíquota, "
        "multas desproporcionais, e teses de defesa administrativa/judicial. " + REGRAS
    ),
    "ambiental": (
        "Você é analista de DIREITO AMBIENTAL. Analise o auto de infração ambiental (IBAMA/ICMBio/estadual) / TAC / "
        "licença buscando: vícios formais, ausência de fundamentação técnica, desproporcionalidade da multa, "
        "prazos e nulidades, e caminhos (defesa, conversão de multa, TAC). " + REGRAS
    ),
    "default": (
        "Você é analista jurídico. Analise o contrato/documento buscando riscos, cláusulas questionáveis e "
        "lacunas. " + REGRAS
    ),
}

FORMATO = (
    "\n\nResponda APENAS em JSON válido com este formato:\n"
    "{\n"
    '  "resumo": "<2-3 frases>",\n'
    '  "juros": {"taxa_identificada": "<ou null>", "capitalizacao": "<sim/nao/indefinido>", "observacao": "<...>"},\n'
    '  "tarifas_encargos": [{"item": "<...>", "risco": "alto|medio|baixo", "motivo": "<...>"}],\n'
    '  "clausulas_questionaveis": [{"clausula": "<trecho/resumo>", "risco": "alto|medio|baixo", "fundamento": "<base legal ou verificar>"}],\n'
    '  "pontos_de_atencao": ["<...>"],\n'
    '  "base_legal_sugerida": ["<apenas se tiver certeza; senao vazio>"],\n'
    '  "proxima_acao": "<sugestao pratica para o advogado>"\n'
    "}\n"
    "Para áreas não-bancárias, o campo 'juros' pode vir com taxa_identificada=null."
)


def _parse_json(txt: str) -> Optional[dict]:
    if not txt:
        return None
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def _analisar(texto: str, area: str = "default") -> dict:
    if len(texto.strip()) < 120:
        raise HTTPException(422, "Texto do documento muito curto para análise (mín. 120 caracteres)")
    sys = AREA_PROMPTS.get(area, AREA_PROMPTS["default"]) + FORMATO
    user_msg = "DOCUMENTO A ANALISAR (pode estar truncado):\n\n" + texto[:14000]
    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
        task_type="analise_juridica", temperature=0.2, max_tokens=1800,
    )
    data = _parse_json(resp.texto) or {"resumo": resp.texto[:1500], "_bruto": True}
    data["_aviso"] = ("Análise gerada por IA como apoio — revisão obrigatória do advogado. "
                      "Em contratos bancários, compare a taxa com o painel 'Taxas de Juros' do Banco Central.")
    data["_modelo"] = resp.modelo
    return data


@router.post("/contrato")
async def analisar_documento(
    file: Optional[UploadFile] = File(None),
    texto: Optional[str] = Form(None),
    area: str = Form("default"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Recebe um PDF (file) OU texto (texto) + área, e retorna a análise estruturada."""
    conteudo = (texto or "").strip()
    if file is not None:
        raw = await file.read()
        try:
            import fitz
            with fitz.open(stream=raw, filetype="pdf") as pdf:
                conteudo = "".join(page.get_text() for page in pdf)
        except Exception as e:
            raise HTTPException(422, f"Falha ao ler o PDF: {str(e)[:120]}")
    if not conteudo:
        raise HTTPException(422, "Envie um PDF ou cole o texto do documento")
    return await _analisar(conteudo, area)


_OLINDA_DIA = "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/TaxasJurosDiariaPorInicioPeriodo"


async def _olinda_get(params: dict) -> list:
    import httpx
    params = {**params, "$format": "json"}
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(_OLINDA_DIA, params=params)
        r.raise_for_status()
        return r.json().get("value", [])


@router.get("/modalidades")
async def modalidades(cu: User = Depends(get_current_user)):
    """Modalidades de crédito do BACEN (série diária) — agrupadas por segmento PF/PJ, período mais recente."""
    try:
        ult = await _olinda_get({"$top": "1", "$orderby": "InicioPeriodo desc", "$select": "InicioPeriodo"})
        if not ult:
            raise HTTPException(404, "Sem dados no BACEN")
        periodo = ult[0]["InicioPeriodo"]
        rows = await _olinda_get({
            "$filter": f"InicioPeriodo eq '{periodo}'",
            "$select": "Modalidade,Segmento", "$top": "8000",
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Falha ao consultar BACEN: {str(e)[:100]}")
    vistos = {}
    for x in rows:
        m, seg = x.get("Modalidade"), x.get("Segmento")
        if m:
            vistos[(seg, m)] = True
    lista = [{"segmento": seg, "modalidade": m} for (seg, m) in sorted(vistos)]
    return {"periodo": periodo, "modalidades": lista}


@router.get("/taxa-media")
async def taxa_media(modalidade: str, segmento: Optional[str] = None, periodo: Optional[str] = None, cu: User = Depends(get_current_user)):
    """Taxa média de mercado (BACEN, série diária) — min/média/máx das instituições no período mais recente."""
    mod = modalidade.replace("'", "''")
    filt = f"Modalidade eq '{mod}'"
    if segmento:
        filt += f" and Segmento eq '{segmento.replace(chr(39), chr(39)+chr(39))}'"
    try:
        rows = await _olinda_get({"$filter": filt, "$top": "1500"})
    except Exception as e:
        raise HTTPException(502, f"Falha ao consultar BACEN: {str(e)[:100]}")
    rows = [x for x in rows if x.get("TaxaJurosAoMes") is not None]
    if not rows:
        raise HTTPException(404, "Modalidade sem dados no BACEN")
    ultimo = max(x.get("InicioPeriodo", "") for x in rows)
    do = [x for x in rows if x.get("InicioPeriodo") == ultimo]
    am = [float(x["TaxaJurosAoMes"]) for x in do]
    aa = [float(x["TaxaJurosAoAno"]) for x in do if x.get("TaxaJurosAoAno") is not None]
    return {
        "modalidade": modalidade, "segmento": segmento,
        "periodo": ultimo, "instituicoes": len(do),
        "ao_mes": {"min": round(min(am), 2), "media": round(sum(am) / len(am), 2), "max": round(max(am), 2)},
        "ao_ano": {"min": round(min(aa), 2), "media": round(sum(aa) / len(aa), 2), "max": round(max(aa), 2)} if aa else None,
        "fonte": "Banco Central do Brasil — Taxas de Juros (Olinda, série diária)",
    }
