"""
Router de Auditoria de Licitacoes (consolidacao 28/06/2026).
Correcoes vs pacote v6.0: prefixo /v1 (era /api/v1 -> duplo prefixo); auth JWT;
sem dependencia de DB (auditor stateless).
Montado em /api/v1/licitacao-auditoria (main.py adiciona /api).
"""
import os
import re
import time
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, StringConstraints

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.rate_limit import rate_limit
from app.core.licitacao_auditor import LicitacaoAuditor
from app.models.user import User

settings = get_settings()

router = APIRouter(
    prefix="/v1/licitacao-auditoria",
    tags=["licitacao-auditoria"],
    dependencies=[Depends(get_current_user)],
)

_auditor = LicitacaoAuditor()

# Retenção do PDF (contém dados da licitação/concorrente): varredura best-effort
# remove os mais antigos que o TTL a cada geração (mesmo padrão do tributário).
PDF_TTL_SEGUNDOS = 3600  # 1h
_Str1k = Annotated[str, StringConstraints(max_length=1000)]


@router.post("/analyze-competitor-proposal",
             dependencies=[Depends(rate_limit("licitacao-auditoria", 15))])
async def analyze_competitor_proposal(
    file: UploadFile = File(...),
    com_ia: bool = Query(False, description="Enriquecer com IA (opt-in; texto sanitizado + AILog)"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
) -> Dict[str, Any]:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF sao aceitos.")
    pdf_content = await file.read()
    return await _auditor.analyze_competitor_proposal(
        pdf_content, db=db, user_id=cu.id, com_ia=com_ia,
    )


@router.get("/audit-report-template")
async def get_audit_report_template() -> Dict[str, str]:
    return {"template": await _auditor.get_audit_report_template()}


# ── Relatório de auditoria em PDF (Visual Law) ────────────────────────────────
# Materializa o entregável: os achados computados pelo motor de regras viram um
# relatório dourado que o advogado revisa e entrega. Padrão de segurança
# endurecido, copiado de routers/tributario_fiscal.py.

class AnaliseIn(BaseModel):
    summary: str = Field(default="", max_length=2000)
    potential_flaws: List[_Str1k] = Field(default_factory=list, max_length=200)
    equivalence_issues: List[_Str1k] = Field(default_factory=list, max_length=200)
    aviso: Optional[str] = Field(default=None, max_length=2000)


class ReportIn(BaseModel):
    analise: AnaliseIn
    edital: str = Field(default="", max_length=300)
    concorrente: str = Field(default="", max_length=300)


def _report_dir() -> str:
    out_dir = os.path.join(settings.UPLOAD_DIR, "licitacao_auditoria")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _limpar_pdfs_antigos(out_dir: str) -> None:
    try:
        agora = time.time()
        for nome in os.listdir(out_dir):
            if not nome.endswith(".pdf"):
                continue
            caminho = os.path.join(out_dir, nome)
            try:
                if agora - os.path.getmtime(caminho) > PDF_TTL_SEGUNDOS:
                    os.remove(caminho)
            except OSError:
                continue
    except OSError:
        pass


def _html_report(r: ReportIn) -> str:
    """Monta o HTML do relatório. TODA string vinda do payload passa por esc()."""
    from app.services import visual_law_theme as vlt

    esc = vlt.esc
    a = r.analise
    partes: List[str] = [vlt.render_banner(
        "RELATÓRIO DE AUDITORIA DE PROPOSTA",
        f"Edital: {esc(r.edital or '—')} · Concorrente: {esc(r.concorrente or '—')}",
    )]
    partes.append(
        "<div style='background:" + vlt.OURO_PALHA + ";border-left:4px solid "
        + vlt.OURO + ";padding:12px 16px;margin:14px 0;font-size:10pt;'>"
        f"{esc(a.summary or 'Análise preliminar concluída.')}</div>"
    )

    def _bloco(titulo: str, itens: List[str]) -> None:
        partes.append(f"<h2 style='color:{vlt.OURO};border-bottom:2px solid "
                      f"{vlt.OURO_CLARO};padding-bottom:4px;margin-top:20px;'>"
                      f"{esc(titulo)} ({len(itens)})</h2>")
        if itens:
            partes.append("<ul>" + "".join(
                f"<li style='font-size:10pt;margin-bottom:4px;'>{esc(i)}</li>"
                for i in itens) + "</ul>")
        else:
            partes.append("<p style='font-size:10pt;color:"
                          f"{vlt.TEXTO_SUAVE};'>Nenhum ponto sinalizado.</p>")

    _bloco("Pontos de impugnação potenciais", a.potential_flaws)
    _bloco("Questões de equivalência técnica", a.equivalence_issues)

    partes.append(
        "<div style='background:#fffbe6;border:1px solid #f0ad4e;border-left:"
        f"4px solid {vlt.OURO_CLARO};padding:12px;margin:16px 0;font-size:9.5pt;'>"
        "<strong>ANÁLISE PRELIMINAR — REVISÃO DO ADVOGADO OBRIGATÓRIA (OAB)</strong><br>"
        f"{esc(a.aviso or 'Sinalização automática por regras determinísticas (Lei 14.133/21); não substitui a leitura técnica do edital e da proposta.')}</div>"
    )
    partes.append(
        f"<div style='margin-top:22px;font-size:8.5pt;color:{vlt.RODAPE_COR};"
        "border-top:1px solid #e5e7eb;padding-top:8px;'>Gerado em: "
        f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · "
        "Análise preliminar por regras (sem IA) — Lei 14.133/21</div>"
    )
    rodape = ("De Paula Teixeira Advogados · Auditoria de Proposta de Concorrente "
              "— análise preliminar (revisão obrigatória)")
    return vlt.html_doc("".join(partes), css=vlt.css_fluxo(rodape))


@router.post("/report-pdf",
             dependencies=[Depends(rate_limit("licitacao-auditoria-pdf", 10))])
async def report_pdf(payload: ReportIn) -> Dict[str, str]:
    """Gera o relatório de auditoria em PDF Visual Law a partir dos achados."""
    try:
        from weasyprint import HTML as WP_HTML
    except ImportError as exc:
        raise HTTPException(503, f"Dependencia de PDF nao disponivel: {exc}.")

    html_full = _html_report(payload)
    pdf_bytes = WP_HTML(string=html_full).write_pdf()

    out_dir = _report_dir()
    _limpar_pdfs_antigos(out_dir)
    arquivo_id = str(uuid4())
    path = os.path.join(out_dir, f"auditoria_{arquivo_id}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    return {"download_url": f"/v1/licitacao-auditoria/report/{arquivo_id}/download"}


@router.get("/report/{arquivo_id}/download",
            dependencies=[Depends(rate_limit("licitacao-auditoria-download", 30))])
async def download_report(arquivo_id: str):
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                        arquivo_id):
        raise HTTPException(422, "Identificador de relatorio invalido.")
    path = os.path.join(_report_dir(), f"auditoria_{arquivo_id}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(404, "Relatorio nao encontrado — gere via POST /report-pdf.")
    return FileResponse(path, media_type="application/pdf",
                        filename="auditoria-proposta-concorrente.pdf")
