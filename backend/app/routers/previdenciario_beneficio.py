# ── app/routers/previdenciario_beneficio.py ──────────────────────────────────
# Vertical Previdenciário — simulador das 5 regras de transição da EC 103/2019 +
# coeficiente da RMI (art. 26). STATELESS: sem persistência e sem IA.
#
#   GET  /previdenciario/ferramentas/regras-transicao  → consolidação
#   POST /previdenciario/ferramentas/parecer-pdf        → {"download_url": ...}
#   GET  /previdenciario/ferramentas/parecer/{id}/download → FileResponse (PDF)
#
# Auth: require_roles_exact(_EQUIPE) — mesma das demais ferramentas previdenciárias em
# routers/ramos.py. GET simples segue o padrão delas; POST+PDF diverge (com
# hardening) copiando routers/tributario_fiscal.py: rate_limit, UUID no download
# (sem traversal), TTL/LGPD dos PDFs e Field limits no payload.
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.security import require_roles_exact
from app.models.user import User
from app.services.calc.previdenciario_beneficio import simular_aposentadoria

settings = get_settings()
router = APIRouter(prefix="/previdenciario/ferramentas",
                   tags=["Previdenciário / Benefício"])

_EQUIPE = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]

# Retenção LGPD dos PDFs (contêm dados previdenciários do titular).
PDF_TTL_SEGUNDOS = 3600  # 1h
from app.services import visual_law_files as _vlf  # #27: arnês único

# Limites de tamanho no payload de /parecer-pdf (renderizado pelo WeasyPrint —
# caro/síncrono): evitam DoS por strings/listas gigantes.
_TXT = 2000
_TXT_LONGO = 6000


# ── Schemas de resposta (Decimal só interno; JSON sai float) ─────────────────

class RegraTransicaoOut(BaseModel):
    regra_id: str = Field(max_length=64)
    nome: str = Field(max_length=_TXT)
    base_legal: str = Field(max_length=_TXT)
    elegivel: bool
    o_que_falta: list[str] = Field(default_factory=list, max_length=20)
    coeficiente_rmi: Optional[float] = None
    rmi_estimada: Optional[float] = None
    observacoes: list[str] = Field(default_factory=list, max_length=20)


class MelhorRegraOut(BaseModel):
    id: Optional[str] = Field(default=None, max_length=64)
    motivo: str = Field(max_length=_TXT)


class SimulacaoPrevidOut(BaseModel):
    sexo: str = Field(max_length=16)
    idade: float
    tempo_contribuicao: float
    ano: int
    media_informada: bool
    media_salarios_contribuicao: Optional[float] = None
    regras: list[RegraTransicaoOut] = Field(max_length=10)
    regras_elegiveis: list[str] = Field(default_factory=list, max_length=10)
    melhor_regra: MelhorRegraOut
    aviso_hitl: str = Field(max_length=_TXT_LONGO)
    base_legal_geral: str = Field(max_length=_TXT)


# ── Simulação (GET, padrão das ferramentas previdenciárias) ───────────────────

@router.get("/regras-transicao", response_model=SimulacaoPrevidOut)
async def regras_transicao(
    idade: float = Query(..., ge=0, le=120, description="Idade atual em anos"),
    tempo_contribuicao_anos: float = Query(..., ge=0, le=80),
    sexo: str = Query("M", pattern="^[MmFf]"),
    ano: int = Query(2026, ge=2019, le=2060),
    media_salarios_contribuicao: Optional[float] = Query(
        None, ge=0, description="Média dos salários de contribuição (CNIS). "
                                "Se omitida, a RMI não é calculada — só o coeficiente."),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Compara as 5 regras de transição da EC 103/2019 e devolve a consolidação
    (elegibilidade, coeficiente da RMI e melhor regra). SIMULAÇÃO — HITL."""
    media = (Decimal(str(media_salarios_contribuicao))
             if media_salarios_contribuicao is not None else None)
    resultado = simular_aposentadoria(
        sexo=sexo,
        idade=Decimal(str(idade)),
        tempo_contribuicao=Decimal(str(tempo_contribuicao_anos)),
        media_salarios=media,
        ano=ano,
    )
    return SimulacaoPrevidOut.model_validate(resultado)


# ── Parecer PDF (Visual Law) ─────────────────────────────────────────────────

def _parecer_dir() -> str:
    out_dir = os.path.join(settings.UPLOAD_DIR, "previdenciario_beneficio")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _limpar_pdfs_antigos(out_dir: str) -> None:
    """Retenção LGPD: varredura best-effort remove PDFs mais antigos que o TTL a
    cada geração — sem estado externo, tolerante a falhas."""
    # #27: purga TTL centralizada em services/visual_law_files (retenção LGPD).
    _vlf.purgar_antigos(out_dir, PDF_TTL_SEGUNDOS)


def _html_parecer(c: SimulacaoPrevidOut) -> str:
    """Monta o corpo HTML da simulação. TODO string do payload passa por
    vlt.esc() — o JSON é devolvido pelo frontend (entrada do usuário)."""
    from app.services import visual_law_theme as vlt

    esc = vlt.esc

    def pct(v: Optional[float]) -> str:
        return "—" if v is None else f"{v * 100:.2f}".rstrip("0").rstrip(".") + "%"

    def moeda(v: Optional[float]) -> str:
        if v is None:
            return "informe a média do CNIS"
        inteiro, _, dec = f"{v:,.2f}".partition(".")
        return "R$ " + inteiro.replace(",", ".") + "," + dec

    partes: list[str] = [vlt.render_banner(
        "SIMULAÇÃO DE APOSENTADORIA (EC 103/2019)",
        f"Sexo: {esc(c.sexo)} · Idade: {c.idade:g} anos · "
        f"Tempo de contribuição: {c.tempo_contribuicao:g} anos · Ano-base: {c.ano}",
    )]

    # Aviso HITL em destaque.
    partes.append(
        "<div style='background:#fffbe6;border:1px solid #f0ad4e;border-left:"
        f"4px solid {vlt.OURO_CLARO};padding:12px;margin:12px 0;font-size:9.5pt;'>"
        "<strong>SIMULAÇÃO DE ELEGIBILIDADE — REVISÃO HUMANA OBRIGATÓRIA</strong>"
        f"<br>{esc(c.aviso_hitl)}</div>"
    )

    # Melhor regra.
    partes.append(
        "<div style='background:" + vlt.OURO_PALHA + ";border-left:4px solid "
        + vlt.OURO + ";padding:14px 16px;margin:16px 0;'>"
        f"<div style='font-size:10pt;color:{vlt.TEXTO_SUAVE};'>Melhor caminho "
        "(entre as regras elegíveis)</div>"
        f"<div style='font-size:14pt;font-weight:bold;color:{vlt.OURO_PROFUNDO};'>"
        f"{esc(c.melhor_regra.id or '—')}</div>"
        f"<div style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>"
        f"{esc(c.melhor_regra.motivo)}</div></div>"
    )

    if not c.media_informada:
        partes.append(f"<p style='font-size:9.5pt;color:{vlt.TEXTO_SUAVE};'>"
                      "⚠ Média dos salários de contribuição NÃO informada — a RMI "
                      "não pôde ser estimada; apresenta-se apenas o coeficiente. A "
                      "média real vem do CNIS (salários desde 07/1994).</p>")

    for r in c.regras:
        status = "ELEGÍVEL" if r.elegivel else "NÃO ELEGÍVEL"
        cor = vlt.OURO_PROFUNDO if r.elegivel else vlt.RODAPE_COR
        partes.append(
            f"<h2 style='color:{vlt.OURO};border-bottom:2px solid "
            f"{vlt.OURO_CLARO};padding-bottom:4px;margin-top:22px;'>"
            f"{esc(r.nome)}</h2>"
            f"<p><strong style='color:{cor};'>{status}</strong> · "
            f"Coeficiente: <strong>{pct(r.coeficiente_rmi)}</strong> · "
            f"RMI estimada: <strong>{moeda(r.rmi_estimada)}</strong></p>"
            f"<p style='font-size:9pt;'><strong>Base legal:</strong> "
            f"{esc(r.base_legal)}</p>"
        )
        if r.o_que_falta:
            partes.append("<p style='font-size:9.5pt;margin-bottom:2px;'>"
                          "<strong>O que falta</strong></p><ul>"
                          + "".join(f"<li style='font-size:9.5pt;'>{esc(x)}</li>"
                                    for x in r.o_que_falta) + "</ul>")
        for o in r.observacoes:
            partes.append(f"<p style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>"
                          f"• {esc(o)}</p>")

    partes.append(
        f"<div style='margin-top:24px;font-size:8.5pt;color:{vlt.RODAPE_COR};"
        "border-top:1px solid #e5e7eb;padding-top:8px;'>Gerado em: "
        f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · "
        "Simulação determinística (sem IA) · "
        f"{esc(c.base_legal_geral)}</div>"
    )

    rodape = ("De Paula Teixeira Advogados · Simulação de Aposentadoria "
              "(EC 103/2019) — elegibilidade preliminar (HITL)")
    return vlt.html_doc("".join(partes), css=vlt.css_fluxo(rodape))


@router.post("/parecer-pdf",
             dependencies=[Depends(rate_limit("previdenciario-parecer-pdf", 10))])
async def parecer_pdf(
    simulacao: SimulacaoPrevidOut,
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Gera o PDF Visual Law da simulação a partir da consolidação devolvida pelo
    frontend e retorna a URL de download (padrão tributario_fiscal)."""
    try:
        from weasyprint import HTML as WP_HTML
    except ImportError as exc:
        raise HTTPException(503, f"Dependência de PDF não disponível: {exc}. "
                                 "Instale weasyprint.")

    html_full = _html_parecer(simulacao)
    pdf_bytes = WP_HTML(string=html_full).write_pdf()

    out_dir = _parecer_dir()
    _limpar_pdfs_antigos(out_dir)  # retenção LGPD (TTL) a cada geração
    arquivo_id = str(uuid4())
    path = os.path.join(out_dir, f"parecer_{arquivo_id}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    # Auditoria §11/S10: binding usuário↔arquivo — capability URL não basta.
    _vlf.registrar_origem(out_dir, arquivo_id, criado_por=cu.id)
    return {"download_url": f"/previdenciario/ferramentas/parecer/{arquivo_id}/download"}


@router.get("/parecer/{arquivo_id}/download",
            dependencies=[Depends(rate_limit("previdenciario-parecer-download", 30))])
async def download_parecer(
    arquivo_id: str,
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Download do PDF gerado pelo POST acima. `arquivo_id` é validado como UUID
    (nunca interpolado livre no path — sem traversal)."""
    # #27: validação anti-traversal (UUID) centralizada.
    _vlf.validar_uuid(arquivo_id)
    path = os.path.join(_parecer_dir(), f"parecer_{arquivo_id}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(404, "Parecer não encontrado — gere via POST "
                                 "/previdenciario/ferramentas/parecer-pdf.")
    # Auditoria §11/S10: só o criador (ou gestão) baixa — fail-closed.
    _vlf.exigir_origem(_parecer_dir(), arquivo_id, cu)
    return FileResponse(path, media_type="application/pdf",
                        filename="simulacao_aposentadoria_ec103.pdf")
