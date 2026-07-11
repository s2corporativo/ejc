# ── app/routers/trabalhista_liquidacao.py ───────────────────────────────────
# Vertical Trabalhista — Liquidação de sentença. STATELESS: sem persistência e
# sem IA. Determinístico (Decimal + Selic real do BCB, ADC 58).
#
#   POST /trabalhista/liquidacao/calcular          → consolidação da planilha
#   POST /trabalhista/liquidacao/planilha-pdf       → {"download_url": ...}
#   GET  /trabalhista/liquidacao/planilha/{id}/download → FileResponse (PDF)
#
# Padrões seguidos: hardening de PDF de routers/tributario_fiscal.py
# (esc() em todo payload, UUID validado no download, TTL/LGPD, rate_limit,
# Field(max_length) contra payload gigante) e Visual Law central
# (services/visual_law_theme.py).
from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services.calc.liquidacao_trabalhista import calcular_liquidacao

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/trabalhista/liquidacao", tags=["Trabalhista / Liquidação"])

# Retenção dos PDFs (contêm valores e dados de terceiros — LGPD): varredura
# best-effort remove os mais antigos que este TTL a cada geração.
PDF_TTL_SEGUNDOS = 3600  # 1h
from app.services import visual_law_files as _vlf  # #27: arnês único
MAX_VERBAS = 100

# Limites de tamanho no payload de /planilha-pdf (renderizado pelo WeasyPrint —
# caro/síncrono): evitam DoS por strings/listas gigantes.
_TXT = 2000        # texto curto (rubricas, base legal, alertas)
_TXT_LONGO = 6000  # aviso_hitl / observações


# ── Schemas ───────────────────────────────────────────────────────────────────

Natureza = Literal["salarial", "indenizatoria"]


class VerbaIn(BaseModel):
    rubrica: str = Field(..., min_length=1, max_length=_TXT)
    valor: float = Field(..., gt=0)
    natureza: Natureza


class LiquidacaoIn(BaseModel):
    verbas: list[VerbaIn] = Field(..., min_length=1, max_length=MAX_VERBAS)
    data_ajuizamento: date
    data_calculo: date
    percentual_honorarios: float = Field(0, ge=0, le=100)
    fator_ipcae_pre_ajuizamento: Optional[float] = Field(None, gt=0)
    # Fator IPCA-E pré-ajuizamento OFICIAL (BCB SGS via indices_service):
    # com usar_indice_oficial=true e fator manual ausente, o fator é calculado
    # de data_inicio_correcao → data_ajuizamento. O campo manual acima segue
    # valendo e tem PRECEDÊNCIA quando informado (nunca removido).
    usar_indice_oficial: bool = False
    data_inicio_correcao: Optional[date] = None


class VerbaOut(BaseModel):
    rubrica: str = Field(max_length=_TXT)
    valor: float
    natureza: str = Field(max_length=32)


class EncargoOut(BaseModel):
    aliquota_pct: float
    base: float
    valor: float
    base_legal: str = Field(max_length=_TXT)


class HonorariosOut(BaseModel):
    percentual_pct: float
    base: float
    valor: float
    base_legal: str = Field(max_length=_TXT)


class CorrecaoOut(BaseModel):
    regime: str = Field(max_length=_TXT)
    fator_ipcae_pre_ajuizamento: Optional[float] = None
    principal_pos_ipcae: float
    fator_selic: float
    fonte_selic: str = Field(max_length=_TXT)
    meses_selic: int
    principal_corrigido: float


class TributoOut(BaseModel):
    base_calculo: float
    base_calculo_nominal: Optional[float] = None
    valor: Optional[float] = None
    status: str = Field(max_length=32)
    observacao: str = Field(max_length=_TXT_LONGO)


class LiquidacaoOut(BaseModel):
    data_ajuizamento: str = Field(max_length=32)
    data_calculo: str = Field(max_length=32)
    verbas: list[VerbaOut] = Field(max_length=MAX_VERBAS)
    principal_bruto: float
    base_salarial: float
    base_indenizatoria: float
    fgts: EncargoOut
    multa_fgts: EncargoOut
    correcao: CorrecaoOut
    honorarios: HonorariosOut
    inss: TributoOut
    irrf: TributoOut
    subtotal_credito_trabalhista: float
    total_bruto_com_honorarios: float
    total_liquido_estimado: float
    memoria_calculo: list[str] = Field(max_length=100)
    alertas: list[str] = Field(max_length=100)
    base_legal: list[str] = Field(max_length=50)
    aviso_hitl: str = Field(max_length=_TXT_LONGO)


# ── Cálculo ───────────────────────────────────────────────────────────────────

@router.post("/calcular", response_model=LiquidacaoOut,
             dependencies=[Depends(rate_limit("trabalhista-liquidacao-calcular", 20))])
async def calcular(req: LiquidacaoIn, cu: User = Depends(get_current_user)):
    """Calcula a planilha de liquidação de sentença trabalhista (ADC 58 — Selic
    real do BCB). Determinístico, sem IA e sem persistência. A resposta é
    MINUTA para conferência do contador/advogado (HITL)."""
    fator_ipcae = req.fator_ipcae_pre_ajuizamento
    # Caminho oficial (opt-in): busca o fator IPCA-E no BCB quando não veio
    # fator manual. Fail-soft: BCB fora → segue sem fator (o serviço de
    # liquidação já emite o alerta de IPCA-E não aplicado — nunca estima).
    if fator_ipcae is None and req.usar_indice_oficial and req.data_inicio_correcao:
        if req.data_inicio_correcao >= req.data_ajuizamento:
            raise HTTPException(
                422, "data_inicio_correcao deve ser anterior à data_ajuizamento")
        if settings.INDICES_BCB_ENABLED:
            from app.services import indices_service
            try:
                fc = await indices_service.fator_correcao(
                    "ipca_e", req.data_inicio_correcao, req.data_ajuizamento)
                fator_ipcae = fc["fator"]
            except Exception:
                logger.warning("Liquidação: fator IPCA-E oficial indisponível "
                               "(BCB fora) — seguindo sem correção pré-ajuizamento")
    try:
        resultado = await calcular_liquidacao(
            verbas=[v.model_dump() for v in req.verbas],
            data_ajuizamento=req.data_ajuizamento,
            data_calculo=req.data_calculo,
            percentual_honorarios=req.percentual_honorarios,
            fator_ipcae_pre_ajuizamento=fator_ipcae,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    return LiquidacaoOut.model_validate(resultado)


# ── Planilha PDF (Visual Law) ─────────────────────────────────────────────────

def _pdf_dir() -> str:
    out_dir = os.path.join(settings.UPLOAD_DIR, "trabalhista_liquidacao")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _limpar_pdfs_antigos(out_dir: str) -> None:
    """Retenção LGPD: os PDFs carregam valores e dados de terceiros. Varredura
    best-effort remove os mais antigos que o TTL a cada geração — sem estado
    externo, tolerante a falhas (nunca quebra a resposta)."""
    # #27: purga TTL centralizada em services/visual_law_files (retenção LGPD).
    _vlf.purgar_antigos(out_dir, PDF_TTL_SEGUNDOS)


def _moeda(v: float) -> str:
    inteiro, _, dec = f"{v:,.2f}".partition(".")
    return "R$ " + inteiro.replace(",", ".") + "," + dec


def _data_br(d: Optional[str]) -> str:
    if not d:
        return "—"
    try:
        return date.fromisoformat(d).strftime("%d/%m/%Y")
    except ValueError:
        return d


def _html_planilha(c: LiquidacaoOut) -> str:
    """Monta o corpo HTML da planilha. TODO string do payload passa por
    vlt.esc() — o JSON é devolvido pelo frontend (entrada do usuário)."""
    from app.services import visual_law_theme as vlt

    esc = vlt.esc
    partes: list[str] = [vlt.render_banner(
        "PLANILHA DE LIQUIDAÇÃO DE SENTENÇA",
        f"Ajuizamento {esc(_data_br(c.data_ajuizamento))} · Cálculo até "
        f"{esc(_data_br(c.data_calculo))}",
    )]

    # Destaque do total.
    partes.append(
        "<div style='background:" + vlt.OURO_PALHA + ";border-left:4px solid "
        + vlt.OURO + ";padding:14px 16px;margin:16px 0;'>"
        f"<div style='font-size:10pt;color:{vlt.TEXTO_SUAVE};'>Líquido estimado ao "
        "reclamante (antes de INSS/IRRF a apurar)</div>"
        f"<div style='font-size:20pt;font-weight:bold;color:{vlt.OURO_PROFUNDO};'>"
        f"{_moeda(c.total_liquido_estimado)}</div>"
        f"<div style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>Subtotal do crédito "
        f"{_moeda(c.subtotal_credito_trabalhista)} · Total bruto com honorários "
        f"{_moeda(c.total_bruto_com_honorarios)}</div></div>"
    )

    # Aviso HITL.
    partes.append(
        "<div style='background:#fffbe6;border:1px solid #f0ad4e;border-left:"
        f"4px solid {vlt.OURO_CLARO};padding:12px;margin:12px 0;font-size:9.5pt;'>"
        "<strong>MINUTA — REVISÃO HUMANA OBRIGATÓRIA</strong><br>"
        f"{esc(c.aviso_hitl)}</div>"
    )

    # Verbas deferidas.
    partes.append(f"<h2 style='color:{vlt.OURO};'>Verbas deferidas</h2>"
                  "<table><thead><tr><th>Rubrica</th><th>Natureza</th>"
                  "<th style='text-align:right'>Valor</th></tr></thead><tbody>")
    for v in c.verbas:
        partes.append(
            f"<tr><td>{esc(v.rubrica)}</td><td>{esc(v.natureza)}</td>"
            f"<td style='text-align:right'>{_moeda(v.valor)}</td></tr>")
    partes.append(
        f"<tr><td colspan='2'><strong>Principal bruto</strong></td>"
        f"<td style='text-align:right'><strong>{_moeda(c.principal_bruto)}</strong>"
        "</td></tr></tbody></table>")

    # Consolidação de valores.
    partes.append(f"<h2 style='color:{vlt.OURO};'>Consolidação</h2><table><tbody>")
    linhas = [
        ("Base salarial (FGTS/INSS)", _moeda(c.base_salarial)),
        ("Base indenizatória", _moeda(c.base_indenizatoria)),
        (f"Correção — {esc(c.correcao.regime)}",
         f"fator Selic {c.correcao.fator_selic} · {c.correcao.meses_selic} mês(es) · "
         f"fonte {esc(c.correcao.fonte_selic)}"),
        ("Principal corrigido", _moeda(c.correcao.principal_corrigido)),
        (f"FGTS ({c.fgts.aliquota_pct:.0f}% · {esc(c.fgts.base_legal)})",
         _moeda(c.fgts.valor)),
        (f"Multa FGTS ({c.multa_fgts.aliquota_pct:.0f}% · "
         f"{esc(c.multa_fgts.base_legal)})", _moeda(c.multa_fgts.valor)),
        (f"Honorários sucumbenciais ({c.honorarios.percentual_pct:.2f}% · "
         f"{esc(c.honorarios.base_legal)})", _moeda(c.honorarios.valor)),
        ("INSS", f"base {_moeda(c.inss.base_calculo)} — "
                 f"{esc(c.inss.status.replace('_', ' '))}"),
        ("IRRF", f"base {_moeda(c.irrf.base_calculo)} — "
                 f"{esc(c.irrf.status.replace('_', ' '))}"),
        ("Subtotal do crédito trabalhista",
         _moeda(c.subtotal_credito_trabalhista)),
        ("Total bruto com honorários", _moeda(c.total_bruto_com_honorarios)),
        ("Líquido estimado (antes de INSS/IRRF)",
         _moeda(c.total_liquido_estimado)),
    ]
    for rot, val in linhas:
        partes.append(
            f"<tr><td>{rot}</td><td style='text-align:right'>{val}</td></tr>")
    partes.append("</tbody></table>")

    # Memória de cálculo.
    if c.memoria_calculo:
        partes.append(f"<h2 style='color:{vlt.OURO};'>Memória de cálculo</h2><ul>"
                      + "".join(f"<li style='font-size:9.5pt;'>{esc(p)}</li>"
                                for p in c.memoria_calculo) + "</ul>")

    # Alertas.
    for alerta in c.alertas:
        partes.append(f"<p style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>"
                      f"⚠ {esc(alerta)}</p>")

    # Base legal.
    if c.base_legal:
        partes.append(f"<h2 style='color:{vlt.OURO};'>Base legal</h2><ul>"
                      + "".join(f"<li style='font-size:9pt;'>{esc(b)}</li>"
                                for b in c.base_legal) + "</ul>")

    partes.append(
        f"<div style='margin-top:24px;font-size:8.5pt;color:{vlt.RODAPE_COR};"
        "border-top:1px solid #e5e7eb;padding-top:8px;'>Gerado em: "
        f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · "
        "Cálculo determinístico (sem IA) · Correção pela Selic real do BCB "
        "(ADC 58) · MINUTA sujeita a conferência (HITL)</div>"
    )

    rodape = ("De Paula Teixeira Advogados · Planilha de Liquidação de Sentença "
              "Trabalhista — minuta (HITL)")
    return vlt.html_doc("".join(partes), css=vlt.css_fluxo(rodape))


@router.post("/planilha-pdf",
             dependencies=[Depends(rate_limit("trabalhista-liquidacao-pdf", 10))])
async def planilha_pdf(consolidacao: LiquidacaoOut,
                       cu: User = Depends(get_current_user)):
    """Gera o PDF Visual Law da planilha a partir da consolidação devolvida pelo
    frontend e retorna a URL de download (padrão sala_de_guerra_v3)."""
    try:
        from weasyprint import HTML as WP_HTML
    except ImportError as exc:
        raise HTTPException(503, f"Dependência de PDF não disponível: {exc}. "
                                 "Instale weasyprint.")

    html_full = _html_planilha(consolidacao)
    pdf_bytes = WP_HTML(string=html_full).write_pdf()

    out_dir = _pdf_dir()
    _limpar_pdfs_antigos(out_dir)  # retenção LGPD (TTL) a cada geração
    arquivo_id = str(uuid4())
    path = os.path.join(out_dir, f"liquidacao_{arquivo_id}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    return {"download_url": f"/trabalhista/liquidacao/planilha/{arquivo_id}/download"}


@router.get("/planilha/{arquivo_id}/download",
            dependencies=[Depends(rate_limit("trabalhista-liquidacao-download", 30))])
async def download_planilha(arquivo_id: str,
                            cu: User = Depends(get_current_user)):
    """Download do PDF gerado pelo POST acima. `arquivo_id` é validado como UUID
    (nunca interpolado livre no path — sem traversal)."""
    # #27: validação anti-traversal (UUID) centralizada.
    _vlf.validar_uuid(arquivo_id)
    path = os.path.join(_pdf_dir(), f"liquidacao_{arquivo_id}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(404, "Planilha não encontrada — gere via POST "
                                 "/trabalhista/liquidacao/planilha-pdf.")
    return FileResponse(path, media_type="application/pdf",
                        filename="planilha_liquidacao_sentenca.pdf")
