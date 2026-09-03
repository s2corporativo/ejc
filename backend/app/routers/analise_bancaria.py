"""Análise de documento jurídico por área — lê PDF/texto e aponta riscos e cláusulas questionáveis.
   Áreas: bancario, consumidor, trabalhista, empresarial, default. Usa o gateway de IA.
   Respeita: NUNCA inventa lei/jurisprudência, NUNCA promete resultado.
"""
import json
import re
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import ai_gateway, abusividade_service
from app.services.calc import cet as cet_calc
from app.core.rate_limit import rate_limit
from app.core.upload_guard import validar_upload

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
    "digital_lgpd": (
        "Você é analista de DIREITO DIGITAL E PROTEÇÃO DE DADOS. Analise o contrato/documento (contrato de "
        "tratamento de dados, termo de uso, política de privacidade, comunicação de incidente) buscando: base "
        "legal do tratamento (LGPD art. 7º/11) e sua adequação à finalidade, papéis de controlador/operador e "
        "cláusulas de responsabilidade, transferência internacional, prazo de retenção e eliminação, direitos do "
        "titular (art. 18) e canal de atendimento, medidas de segurança (art. 46), e dever de comunicar incidente "
        "à ANPD. " + REGRAS
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


async def _analisar(texto: str, area: str = "default", *, db=None,
                    user_id: str | None = None) -> dict:
    if len(texto.strip()) < 120:
        raise HTTPException(422, "Texto do documento muito curto para análise (mín. 120 caracteres)")
    sys = AREA_PROMPTS.get(area, AREA_PROMPTS["default"]) + FORMATO
    user_msg = "DOCUMENTO A ANALISAR (pode estar truncado):\n\n" + texto[:14000]
    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user_msg}],
        task_type="analise_juridica", temperature=0.2, max_tokens=1800,
    )
    # I9: AILog quando há db+user (o documento pode ter PII → prompt logado
    # SANITIZADO). Erro de gravação PROPAGA (regra do ai_guard).
    if db is not None and user_id:
        from app.models.ai_log import AITipoUso
        from app.services.sanitizer import sanitizar_pii
        prompt_log, pii = sanitizar_pii(user_msg)
        await ai_gateway.registrar_log_resposta(
            db, user_id=user_id, tipo_uso=AITipoUso.analise_caso, resp=resp,
            prompt_sanitizado=f"[ANALISE_BANCARIA area={area}]\n" + prompt_log,
            pii_removida=pii,
        )
    data = _parse_json(resp.texto) or {"resumo": resp.texto[:1500], "_bruto": True}
    data["_aviso"] = ("Análise gerada por IA como apoio — revisão obrigatória do advogado. "
                      "Em contratos bancários, compare a taxa com o painel 'Taxas de Juros' do Banco Central.")
    data["_modelo"] = resp.modelo
    # S8: vocabulário HITL canônico somado às chaves "_aviso"/"_modelo" legadas.
    from app.services.ai.core import hitl_policy
    return hitl_policy.aplicar(data)


@router.post("/contrato", dependencies=[Depends(rate_limit("analise-bancaria", 10))])
async def analisar_documento(
    file: Optional[UploadFile] = File(None),
    texto: Optional[str] = Form(None),
    area: str = Form("default"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Recebe um PDF (file) OU texto (texto) + área, e retorna a análise estruturada."""
    # AI-105 (auditoria 2026-07-26): área desconhecida NÃO cai em silêncio no
    # prompt genérico — o usuário receberia uma análise com viés de outra área
    # acreditando que é da dele. Área inválida → 422 explícito.
    if area not in AREA_PROMPTS:
        raise HTTPException(
            422, f"Área de análise desconhecida: '{area}'. "
                 f"Válidas: {', '.join(sorted(AREA_PROMPTS))}")
    conteudo = (texto or "").strip()
    if file is not None:
        raw = await file.read()
        # Pente fino 2026-07-26: era o único upload sem guarda — lia o arquivo
        # inteiro e jogava direto no fitz. Teto + magic bytes ANTES do parse.
        validar_upload(raw, exigir_pdf=True)
        try:
            import fitz
            with fitz.open(stream=raw, filetype="pdf") as pdf:
                conteudo = "".join(page.get_text() for page in pdf)
        except Exception as e:
            raise HTTPException(422, f"Falha ao ler o PDF: {str(e)[:120]}")
    if not conteudo:
        raise HTTPException(422, "Envie um PDF ou cole o texto do documento")
    return await _analisar(conteudo, area, db=db, user_id=cu.id)


# Consulta Olinda/BCB extraída para app/services/abusividade_service.py (reúso
# pelo motor de abusividade). Endpoints abaixo apenas delegam ao service.


@router.get("/modalidades")
async def modalidades(cu: User = Depends(get_current_user)):
    """Modalidades de crédito do BACEN (série diária) — agrupadas por segmento PF/PJ, período mais recente."""
    try:
        ult = await abusividade_service.olinda_get(
            {"$top": "1", "$orderby": "InicioPeriodo desc", "$select": "InicioPeriodo"})
        if not ult:
            raise HTTPException(404, "Sem dados no BACEN")
        periodo = ult[0]["InicioPeriodo"]
        rows = await abusividade_service.olinda_get({
            "$filter": f"InicioPeriodo eq '{periodo}'",
            "$select": "Modalidade,Segmento", "$top": "8000",
        })
    except HTTPException:
        raise
    except abusividade_service.TaxaMediaIndisponivel as e:
        raise HTTPException(502, f"Falha ao consultar BACEN: {str(e)[:100]}")
    vistos = {}
    for x in rows:
        m, seg = x.get("Modalidade"), x.get("Segmento")
        if m:
            vistos[(seg, m)] = True
    lista = [{"segmento": seg, "modalidade": m} for (seg, m) in sorted(vistos)]
    return {"periodo": periodo, "modalidades": lista,
            "atalhos": sorted(abusividade_service.MODALIDADES_MAP)}


@router.get("/taxa-media")
async def taxa_media(modalidade: str, segmento: Optional[str] = None, periodo: Optional[str] = None, cu: User = Depends(get_current_user)):
    """Taxa média de mercado (BACEN, série diária) — min/média/máx das instituições no período mais recente."""
    try:
        return await abusividade_service.consultar_taxa_media(modalidade, segmento=segmento)
    except abusividade_service.TaxaMediaIndisponivel as e:
        raise HTTPException(502, f"Falha ao consultar BACEN: {str(e)[:100]}")
    except LookupError:
        raise HTTPException(404, "Modalidade sem dados no BACEN")


# ── CET determinístico (Resolução CMN nº 4.881/2020; IN BCB nº 83/2021) ──────
class ParcelaIn(BaseModel):
    valor: float = Field(..., gt=0)
    vencimento: date


class CETIn(BaseModel):
    valor_liberado: float = Field(..., gt=0)
    data_liberacao: date
    # modo 1: fluxo explícito
    parcelas: Optional[list[ParcelaIn]] = None
    # modo 2: série mensal uniforme
    n_parcelas: Optional[int] = Field(None, ge=1, le=600)
    valor_parcela: Optional[float] = Field(None, gt=0)
    primeiro_vencimento: Optional[date] = None
    tarifas_incluidas: float = Field(0, ge=0)
    iof: float = Field(0, ge=0)
    cet_informado_aa_pct: Optional[float] = Field(None, ge=0)

    @model_validator(mode="after")
    def _um_dos_modos(self):
        serie = self.n_parcelas and self.valor_parcela and self.primeiro_vencimento
        if not self.parcelas and not serie:
            raise ValueError("Informe 'parcelas' OU (n_parcelas, valor_parcela, primeiro_vencimento)")
        return self


@router.post("/cet")
async def calcular_cet_endpoint(req: CETIn, cu: User = Depends(get_current_user)):
    """CET determinístico (mensal e anual) via TIR do fluxo de caixa em Decimal,
    com memória de cálculo e verificação de divergência com o CET informado.
    Resolução CMN nº 4.881/2020 · IN BCB nº 83/2021 · CDC arts. 46 e 52.
    Sem IA e sem rate limit (cálculo local). MINUTA — HITL."""
    try:
        return cet_calc.calcular_cet(
            valor_liberado=req.valor_liberado,
            data_liberacao=req.data_liberacao,
            parcelas=[p.model_dump() for p in req.parcelas] if req.parcelas else None,
            n_parcelas=req.n_parcelas,
            valor_parcela=req.valor_parcela,
            primeiro_vencimento=req.primeiro_vencimento,
            tarifas_incluidas=req.tarifas_incluidas,
            iof=req.iof,
            cet_informado_aa_pct=req.cet_informado_aa_pct,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))


# ── Motor de abusividade de juros (REsp 1.061.530/RS, Tema 27) ───────────────
class AbusividadeIn(BaseModel):
    taxa_contrato_am_pct: float = Field(..., gt=0, description="Taxa contratada, % a.m.")
    modalidade: str = Field(..., min_length=2, max_length=160,
                            description="Atalho (ver /modalidades → atalhos) ou nome BCB")
    data_contrato: Optional[date] = None
    segmento: Optional[str] = Field(None, max_length=40)
    # opcionais p/ cenário de expurgo (Price com a taxa média BACEN)
    valor_financiado: Optional[float] = Field(None, gt=0)
    n_parcelas: Optional[int] = Field(None, ge=1, le=600)
    parcela_contratual: Optional[float] = Field(None, gt=0)


@router.post("/abusividade")
async def avaliar_abusividade_endpoint(req: AbusividadeIn, cu: User = Depends(get_current_user)):
    """Compara a taxa contratada com a média BACEN da época da contratação e
    classifica: ≥1,5x = indício forte · 1,2–1,5x = atenção · <1,2x = normal
    (baliza do REsp 1.061.530/RS — caracterização é judicial, HITL). Com
    indício forte + valor/n_parcelas, retorna o cenário de expurgo (Price).
    BCB fora do ar → fail-soft (taxa_media=null + aviso; nunca inventa média)."""
    try:
        return await abusividade_service.avaliar_abusividade(
            taxa_contrato_am_pct=req.taxa_contrato_am_pct,
            modalidade=req.modalidade,
            data_contrato=req.data_contrato,
            segmento=req.segmento,
            valor_financiado=req.valor_financiado,
            n_parcelas=req.n_parcelas,
            parcela_contratual=req.parcela_contratual,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
