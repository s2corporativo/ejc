# ── app/routers/ambiental_estrategia.py ──────────────────────────────────────
# Vertical Ambiental — Simulador de Estratégia do Auto de Infração.
# Motor DETERMINÍSTICO de decisão (v1 STATELESS: sem persistência, sem IA).
#
#   POST /ambiental/estrategia/simular        → consolidação dos 4 cenários
#   POST /ambiental/estrategia/peca-conversao → {"download_url": ...} (PDF)
#   GET  /ambiental/estrategia/peca/{id}/download → FileResponse (PDF)
#
# Padrões seguidos (COPIADOS de routers/tributario_fiscal.py, hardening recente):
#   - Decimal só interno; JSON de entrada/saída em float;
#   - vlt.esc() em TODA string do payload no HTML (anti-injeção);
#   - download_url + GET com arquivo_id validado como UUID (sem path traversal);
#   - _limpar_pdfs_antigos com TTL de retenção (LGPD);
#   - rate_limit por rota; Field(max_length=...) nas strings/listas de entrada.
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services.ambiental.estrategia_auto import simular_estrategia

settings = get_settings()
router = APIRouter(prefix="/ambiental/estrategia", tags=["Ambiental / Estratégia"])

# Retenção dos PDFs (contêm dados do auto — órgão, número, valores): varredura
# best-effort remove os mais antigos que o TTL a cada geração (LGPD).
PDF_TTL_SEGUNDOS = 3600  # 1h
from app.services import visual_law_files as _vlf  # #27: arnês único

# Limites de tamanho no payload renderizado pelo WeasyPrint (caro/síncrono):
# evitam DoS por strings/listas gigantes.
_TXT = 2000        # texto curto (títulos, base legal, racional)
_TXT_LONGO = 6000  # aviso_hitl


# ── Schema de entrada de /simular ─────────────────────────────────────────────
class SimularIn(BaseModel):
    valor_multa: float = Field(ge=0, description="Valor da multa do auto (R$).")
    data_ciencia: date
    fase: Literal["antes_defesa", "apos_defesa"] = "antes_defesa"
    prob_manutencao_pct: float = Field(
        ge=0, le=100,
        description="Prob. (0-100) de o auto ser mantido — estimativa do advogado.")
    custo_recuperacao_estimado: Optional[float] = Field(default=None, ge=0)
    data_infracao: Optional[date] = None


# ── Schemas de resposta (Decimal só interno; JSON sai float) ──────────────────
class FaixaOut(BaseModel):
    piso: float
    teto: float
    prob_baixa_pct: float
    prob_alta_pct: float


class CenarioOut(BaseModel):
    id: str = Field(max_length=64)
    titulo: str = Field(max_length=_TXT)
    base_legal: str = Field(max_length=_TXT)
    aplicavel: bool
    desembolso_estimado: Optional[float] = None
    memoria_calculo: list[str] = Field(default_factory=list, max_length=50)
    observacoes: list[str] = Field(default_factory=list, max_length=50)
    faixa_sensibilidade: Optional[FaixaOut] = None


class RecomendacaoOut(BaseModel):
    cenario_id: str = Field(max_length=64)
    racional: str = Field(max_length=_TXT)


class ConsolidacaoOut(BaseModel):
    cenarios: list[CenarioOut] = Field(max_length=10)
    recomendacao: RecomendacaoOut
    aviso_hitl: str = Field(max_length=_TXT_LONGO)
    base_legal_geral: str = Field(max_length=_TXT)


@router.post("/simular", response_model=ConsolidacaoOut,
             dependencies=[Depends(rate_limit("ambiental-estrategia", 10))])
async def simular(payload: SimularIn, cu: User = Depends(get_current_user)):
    """
    Simula os 4 caminhos diante de um auto de infração ambiental e devolve a
    consolidação com a recomendação DETERMINÍSTICA. Estimativa/minuta (HITL):
    só matemática sobre o valor informado + datas/prazos + constantes legais.
    """
    resultado = simular_estrategia(
        valor_multa=Decimal(str(payload.valor_multa)),
        data_ciencia=payload.data_ciencia,
        fase=payload.fase,
        prob_manutencao_pct=Decimal(str(payload.prob_manutencao_pct)),
        custo_recuperacao_estimado=(
            Decimal(str(payload.custo_recuperacao_estimado))
            if payload.custo_recuperacao_estimado is not None else None),
        data_infracao=payload.data_infracao,
    )
    return ConsolidacaoOut.model_validate(resultado)


# ── Peça: Requerimento de Conversão de Multa em Serviços (PDF Visual Law) ──────
class PecaConversaoIn(BaseModel):
    consolidacao: ConsolidacaoOut
    orgao_autuador: str = Field(max_length=_TXT)
    numero_auto: str = Field(max_length=128)


def _peca_dir() -> str:
    out_dir = os.path.join(settings.UPLOAD_DIR, "ambiental_estrategia")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _limpar_pdfs_antigos(out_dir: str) -> None:
    """Retenção LGPD: PDFs carregam dados do auto. Varredura best-effort remove
    os mais antigos que o TTL a cada geração — sem estado externo, tolerante a
    falhas (nunca quebra a resposta)."""
    # #27: purga TTL centralizada em services/visual_law_files (retenção LGPD).
    _vlf.purgar_antigos(out_dir, PDF_TTL_SEGUNDOS)


def _moeda(v: Optional[float]) -> str:
    if v is None:
        return "—"
    inteiro, _, dec = f"{v:,.2f}".partition(".")
    return "R$ " + inteiro.replace(",", ".") + "," + dec


def _html_requerimento(p: PecaConversaoIn) -> str:
    """Monta o HTML do requerimento. TODA string do payload passa por vlt.esc()
    — o JSON vem do frontend (entrada do usuário)."""
    from app.services import visual_law_theme as vlt

    esc = vlt.esc
    c = p.consolidacao
    conv = next((x for x in c.cenarios if x.id == "converter_servicos"), None)

    partes: list[str] = [vlt.render_banner(
        "REQUERIMENTO DE CONVERSÃO DE MULTA EM SERVIÇOS",
        f"Auto de infração nº {esc(p.numero_auto)} · {esc(p.orgao_autuador)}",
    )]

    partes.append(
        f"<p>Ao {esc(p.orgao_autuador)}, no bojo do auto de infração nº "
        f"{esc(p.numero_auto)}, requer-se a CONVERSÃO da multa em serviços de "
        "preservação, melhoria e recuperação da qualidade do meio ambiente, nos "
        "termos dos arts. 139 a 148 do Decreto 6.514/2008 (red. Dec. 9.179/2017).</p>"
    )

    if conv is not None:
        partes.append(
            f"<h2 style='color:{vlt.OURO};'>Parcela objeto da conversão</h2>"
            f"<p><strong>{esc(conv.titulo)}</strong></p>"
            f"<p>Desembolso remanescente em dinheiro (parcela não convertida): "
            f"<strong>{_moeda(conv.desembolso_estimado)}</strong>.</p>"
        )
        if conv.memoria_calculo:
            partes.append("<p style='margin-bottom:2px;'><strong>Memória de "
                          "cálculo</strong></p><ul>"
                          + "".join(f"<li style='font-size:9.5pt;'>{esc(m)}</li>"
                                    for m in conv.memoria_calculo) + "</ul>")
        for obs in conv.observacoes:
            partes.append(f"<p style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>"
                          f"⚠ {esc(obs)}</p>")
        if conv.base_legal:
            partes.append("<p style='font-size:9pt;'><strong>Base legal:</strong> "
                          + esc(conv.base_legal) + "</p>")
    else:
        partes.append("<p style='font-size:9.5pt;'>Cenário de conversão não "
                      "informado na consolidação — anexe a simulação completa.</p>")

    partes.append(
        f"<h2 style='color:{vlt.OURO};'>Do pedido</h2>"
        "<p>Requer-se o deferimento da conversão da parcela cabível da multa em "
        "serviços de recuperação ambiental (arts. 139-148 do Dec. 6.514/2008), "
        "com a apresentação de projeto de recuperação a ser aprovado pelo órgão "
        "ambiental, suspendendo-se a exigibilidade da parcela convertida na forma "
        "do rito administrativo aplicável.</p>"
    )

    partes.append(
        "<div style='background:#fffbe6;border:1px solid #f0ad4e;border-left:"
        f"4px solid {vlt.OURO_CLARO};padding:12px;margin:16px 0;font-size:9.5pt;'>"
        "<strong>MINUTA — REVISÃO HUMANA OBRIGATÓRIA</strong><br>"
        f"{esc(c.aviso_hitl)}</div>"
    )

    partes.append("<p style='font-size:9pt;'><strong>Base legal geral:</strong> "
                  + esc(c.base_legal_geral) + "</p>")

    partes.append(
        f"<div style='margin-top:24px;font-size:8.5pt;color:{vlt.RODAPE_COR};"
        "border-top:1px solid #e5e7eb;padding-top:8px;'>Gerado em: "
        f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · "
        "Minuta determinística (sem IA) · Estimativa preliminar (HITL)</div>"
    )

    rodape = ("De Paula Teixeira Advogados · Requerimento de Conversão de Multa "
              "em Serviços de Recuperação Ambiental — minuta (HITL)")
    return vlt.html_doc("".join(partes), css=vlt.css_fluxo(rodape))


@router.post("/peca-conversao",
             dependencies=[Depends(rate_limit("ambiental-estrategia-pdf", 10))])
async def peca_conversao(payload: PecaConversaoIn,
                         cu: User = Depends(get_current_user)):
    """Gera o PDF Visual Law dourado do 'Requerimento de Conversão de Multa em
    Serviços de Recuperação Ambiental' e retorna a URL de download."""
    try:
        from weasyprint import HTML as WP_HTML
    except ImportError as exc:
        raise HTTPException(503, f"Dependência de PDF não disponível: {exc}. "
                                 "Instale weasyprint.")

    html_full = _html_requerimento(payload)
    pdf_bytes = WP_HTML(string=html_full).write_pdf()

    out_dir = _peca_dir()
    _limpar_pdfs_antigos(out_dir)  # retenção LGPD (TTL) a cada geração
    arquivo_id = str(uuid4())
    path = os.path.join(out_dir, f"requerimento_{arquivo_id}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    # Auditoria §11/S2 (P0): binding usuário↔arquivo — capability URL não basta.
    _vlf.registrar_origem(out_dir, arquivo_id, criado_por=cu.id)
    return {"download_url": f"/ambiental/estrategia/peca/{arquivo_id}/download"}


@router.get("/peca/{arquivo_id}/download",
            dependencies=[Depends(rate_limit("ambiental-estrategia-download", 30))])
async def download_peca(arquivo_id: str, cu: User = Depends(get_current_user)):
    """Download do PDF gerado pelo POST acima. `arquivo_id` é validado como UUID
    (nunca interpolado livre no path — sem traversal)."""
    # #27: validação anti-traversal (UUID) centralizada.
    _vlf.validar_uuid(arquivo_id)
    path = os.path.join(_peca_dir(), f"requerimento_{arquivo_id}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(404, "Peça não encontrada — gere via POST "
                                 "/ambiental/estrategia/peca-conversao.")
    # Auditoria §11/S2 (P0): só o criador (ou gestão) baixa — fail-closed.
    _vlf.exigir_origem(_peca_dir(), arquivo_id, cu)
    return FileResponse(path, media_type="application/pdf",
                        filename="requerimento_conversao_multa.pdf")
