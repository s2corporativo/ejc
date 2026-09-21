# ── app/routers/tributario_fiscal.py ─────────────────────────────────────────
# Vertical Tributário — leitor de XML fiscal (NF-e) + pré-auditoria determinística.
# Stateless, sem IA e sem persistência do XML.
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

import magic
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.security import require_roles_exact
from app.models.user import User
from app.services.fiscal.nfe_parser import parse_lote
from app.services.fiscal.recuperacao_creditos import analisar_recuperacao

settings = get_settings()
router = APIRouter(prefix="/tributario/fiscal", tags=["Tributário / Fiscal"])

_EQUIPE = [
    "superadmin",
    "admin",
    "socio",
    "advogado",
    "advogado_auxiliar",
    "estagiario",
]

MAX_ARQUIVOS = 50
MIMES_XML = {"application/xml", "text/xml", "text/plain"}
MAX_LOTE_MB = 120
_CHUNK = 256 * 1024
PDF_TTL_SEGUNDOS = 3600

Regime = Literal["simples", "lucro_presumido", "lucro_real"]
_TXT = 2000
_TXT_LONGO = 6000


class TeseOut(BaseModel):
    tese_id: str = Field(max_length=64)
    titulo: str = Field(max_length=_TXT)
    base_legal: str = Field(max_length=_TXT)
    fundamento: str = Field(max_length=_TXT)
    # Contrato legado: representa compatibilidade técnica do radar, não
    # elegibilidade jurídica definitiva.
    aplicavel: bool
    motivo_inaplicavel: Optional[str] = Field(default=None, max_length=_TXT)
    valor_estimado: float
    memoria_calculo: list[str] = Field(max_length=50)
    alertas: list[str] = Field(max_length=50)
    nivel_confianca: str = Field(max_length=64)


class NotaOut(BaseModel):
    chave: str = Field(default="", max_length=64)
    numero: Optional[str] = Field(default=None, max_length=32)
    data_emissao: Optional[str] = Field(default=None, max_length=32)
    emitente_nome: Optional[str] = Field(default=None, max_length=_TXT)
    valor_total: float = 0.0
    icms_destacado: float = 0.0
    erro: Optional[str] = Field(default=None, max_length=_TXT)


class PeriodoOut(BaseModel):
    inicio: Optional[str] = Field(default=None, max_length=32)
    fim: Optional[str] = Field(default=None, max_length=32)


class ConsolidacaoOut(BaseModel):
    regime: str = Field(max_length=32)
    total_estimado: float
    notas_analisadas: int
    notas_com_erro: int
    # Campo legado mantido temporariamente para compatibilidade. O motor P0
    # #1553 não conclui prescrição pela emissão da NF-e e retorna sempre zero.
    notas_prescritas: int
    periodo: PeriodoOut
    teses: list[TeseOut] = Field(max_length=20)
    alertas_globais: list[str] = Field(max_length=50)
    aviso_hitl: str = Field(max_length=_TXT_LONGO)
    notas: list[NotaOut] = Field(max_length=MAX_ARQUIVOS)


@router.post(
    "/analisar-xml",
    response_model=ConsolidacaoOut,
    dependencies=[Depends(rate_limit("tributario-fiscal-analise", 10))],
)
async def analisar_xml(
    arquivos: list[UploadFile] = File(..., description="XMLs de NF-e de saída"),
    regime: Regime = Form(...),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Executa pré-auditoria documental por XML.

    O resultado é triagem matemática/técnica, não parecer, crédito reconhecido,
    conclusão de elegibilidade ou cálculo jurídico de prescrição.
    """
    if len(arquivos) > MAX_ARQUIVOS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Máximo de {MAX_ARQUIVOS} arquivos por análise "
                f"(recebidos {len(arquivos)}). Divida o lote e envie em partes."
            ),
        )
    if not arquivos:
        raise HTTPException(status_code=422, detail="Envie ao menos 1 arquivo XML.")

    lote: list[tuple[str, bytes]] = []
    erros_previos: list[dict] = []
    limite_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    limite_lote = MAX_LOTE_MB * 1024 * 1024
    total_bytes = 0

    for f in arquivos:
        nome = f.filename or "sem_nome.xml"
        ext = os.path.splitext(nome)[1].lower()
        if ext != ".xml":
            erros_previos.append(
                {
                    "arquivo": nome,
                    "erro": (
                        f"Extensão não permitida: {ext or '(sem extensão)'} — apenas .xml."
                    ),
                }
            )
            continue

        partes: list[bytes] = []
        tamanho = 0
        estourou = False
        while True:
            bloco = await f.read(_CHUNK)
            if not bloco:
                break
            tamanho += len(bloco)
            if tamanho > limite_bytes:
                estourou = True
                break
            partes.append(bloco)

        if estourou:
            erros_previos.append(
                {
                    "arquivo": nome,
                    "erro": f"Arquivo excede {settings.MAX_UPLOAD_MB}MB.",
                }
            )
            continue

        conteudo = b"".join(partes)
        if total_bytes + len(conteudo) > limite_lote:
            erros_previos.append(
                {
                    "arquivo": nome,
                    "erro": (
                        f"Lote excede o total de {MAX_LOTE_MB}MB — "
                        "envie menos arquivos por vez."
                    ),
                }
            )
            continue

        mime_real = magic.from_buffer(conteudo[:2048], mime=True)
        if mime_real not in MIMES_XML:
            erros_previos.append(
                {
                    "arquivo": nome,
                    "erro": f"Conteúdo do arquivo ({mime_real}) não é XML.",
                }
            )
            continue

        total_bytes += len(conteudo)
        lote.append((nome, conteudo))

    notas = erros_previos + parse_lote(lote)
    resultado = analisar_recuperacao(notas, regime)
    return ConsolidacaoOut.model_validate(resultado)


# ── PDF Visual Law ────────────────────────────────────────────────────────────
from app.services import visual_law_files as _vlf


def _relatorio_dir() -> str:
    return _vlf.preparar_dir("tributario_fiscal")


def _limpar_pdfs_antigos(out_dir: str) -> None:
    _vlf.purgar_antigos(out_dir)


def _html_relatorio(c: ConsolidacaoOut) -> str:
    """Monta a pré-auditoria em HTML, escapando todo conteúdo do payload."""
    from app.services import visual_law_theme as vlt

    esc = vlt.esc
    regimes_rotulo = {
        "simples": "Simples Nacional",
        "lucro_presumido": "Lucro Presumido",
        "lucro_real": "Lucro Real",
    }

    def moeda(v: float) -> str:
        inteiro, _, dec = f"{v:,.2f}".partition(".")
        return "R$ " + inteiro.replace(",", ".") + "," + dec

    def data_br(d: Optional[str]) -> str:
        if not d:
            return "—"
        try:
            return date.fromisoformat(d).strftime("%d/%m/%Y")
        except ValueError:
            return esc(d)

    partes: list[str] = [
        vlt.render_banner(
            "PRÉ-AUDITORIA TRIBUTÁRIA POR XML",
            f"Regime informado: {esc(regimes_rotulo.get(c.regime, c.regime))} · "
            f"{c.notas_analisadas} nota(s) analisada(s)",
        )
    ]

    partes.append(
        "<div style='background:"
        + vlt.OURO_PALHA
        + ";border-left:4px solid "
        + vlt.OURO
        + ";padding:14px 16px;margin:16px 0;'>"
        f"<div style='font-size:10pt;color:{vlt.TEXTO_SUAVE};'>"
        "Estimativa matemática preliminar (soma dos radares compatíveis)"
        "</div>"
        f"<div style='font-size:20pt;font-weight:bold;color:{vlt.OURO_PROFUNDO};'>"
        f"{moeda(c.total_estimado)}</div>"
        f"<div style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>Período documental: "
        f"{data_br(c.periodo.inicio)} a {data_br(c.periodo.fim)} · "
        "Prescrição: não avaliada · "
        f"{c.notas_com_erro} arquivo(s) com erro</div></div>"
    )

    partes.append(
        "<div style='background:#fffbe6;border:1px solid #f0ad4e;border-left:"
        f"4px solid {vlt.OURO_CLARO};padding:12px;margin:12px 0;font-size:9.5pt;'>"
        "<strong>PRÉ-AUDITORIA — REVISÃO HUMANA OBRIGATÓRIA</strong><br>"
        "Este documento não reconhece crédito, elegibilidade ou prescrição.<br>"
        f"{esc(c.aviso_hitl)}</div>"
    )

    for alerta in c.alertas_globais:
        partes.append(
            f"<p style='font-size:9.5pt;color:{vlt.TEXTO_SUAVE};'>⚠ {esc(alerta)}</p>"
        )

    for t in c.teses:
        status = (
            "SINAL TÉCNICO COMPATÍVEL COM O RADAR"
            if t.aplicavel
            else "RADAR SEM COMPATIBILIDADE TÉCNICA"
        )
        cor = vlt.OURO_PROFUNDO if t.aplicavel else vlt.RODAPE_COR
        estimativa = (
            f" · Estimativa matemática: <strong>{moeda(t.valor_estimado)}</strong>"
            if t.aplicavel
            else ""
        )
        partes.append(
            f"<h2 style='color:{vlt.OURO};border-bottom:2px solid "
            f"{vlt.OURO_CLARO};padding-bottom:4px;margin-top:22px;'>"
            f"{esc(t.titulo)}</h2>"
            f"<p><strong style='color:{cor};'>{status}</strong>{estimativa}</p>"
            f"<p style='font-size:10pt;'>{esc(t.fundamento)}</p>"
        )
        if t.motivo_inaplicavel:
            partes.append(
                f"<p style='font-size:9.5pt;color:{vlt.TEXTO_SUAVE};'>"
                f"Motivo técnico: {esc(t.motivo_inaplicavel)}</p>"
            )
        if t.base_legal:
            partes.append(
                "<p style='font-size:9pt;'><strong>Referências jurídicas para revisão:</strong> "
                + esc(t.base_legal)
                + "</p>"
            )
        if t.memoria_calculo:
            partes.append(
                "<p style='font-size:9.5pt;margin-bottom:2px;'>"
                "<strong>Memória da estimativa</strong></p><ul>"
                + "".join(
                    f"<li style='font-size:9.5pt;'>{esc(p)}</li>"
                    for p in t.memoria_calculo
                )
                + "</ul>"
            )
        for alerta in t.alertas:
            partes.append(
                f"<p style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>⚠ {esc(alerta)}</p>"
            )

    notas_erro = [n for n in c.notas if n.erro]
    if notas_erro:
        partes.append(
            f"<h2 style='color:{vlt.OURO};margin-top:22px;'>Arquivos não processados</h2><ul>"
            + "".join(
                f"<li style='font-size:9pt;'>{esc(n.chave or '(sem chave)')}: "
                f"{esc(n.erro or '')}</li>"
                for n in notas_erro
            )
            + "</ul>"
        )

    partes.append(
        f"<div style='margin-top:24px;font-size:8.5pt;color:{vlt.RODAPE_COR};"
        "border-top:1px solid #e5e7eb;padding-top:8px;'>Gerado em: "
        f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · "
        "Análise determinística (sem IA) · elegibilidade/prescrição não avaliadas"
        "</div>"
    )

    rodape = (
        "De Paula Teixeira Advogados · Pré-auditoria tributária por XML — "
        "estimativa preliminar, revisão humana obrigatória"
    )
    return vlt.html_doc("".join(partes), css=vlt.css_fluxo(rodape))


@router.post(
    "/relatorio-pdf",
    dependencies=[Depends(rate_limit("tributario-fiscal-pdf", 10))],
)
async def relatorio_pdf(
    consolidacao: ConsolidacaoOut,
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Gera PDF da pré-auditoria a partir da consolidação validada."""
    try:
        from weasyprint import HTML as WP_HTML
    except ImportError as exc:
        raise HTTPException(
            503,
            f"Dependência de PDF não disponível: {exc}. Instale weasyprint.",
        )

    html_full = _html_relatorio(consolidacao)
    pdf_bytes = WP_HTML(string=html_full).write_pdf()

    out_dir = _relatorio_dir()
    _limpar_pdfs_antigos(out_dir)
    arquivo_id = str(uuid4())
    path = os.path.join(out_dir, f"pre_auditoria_{arquivo_id}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    # Auditoria §11/S10: binding usuário↔arquivo — capability URL não basta.
    _vlf.registrar_origem(out_dir, arquivo_id, criado_por=cu.id)
    return {"download_url": f"/tributario/fiscal/relatorio/{arquivo_id}/download"}


@router.get(
    "/relatorio/{arquivo_id}/download",
    dependencies=[Depends(rate_limit("tributario-fiscal-download", 30))],
)
async def download_relatorio(
    arquivo_id: str,
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Baixa PDF gerado; `arquivo_id` é validado como UUID."""
    _vlf.validar_uuid(arquivo_id)
    path = os.path.join(_relatorio_dir(), f"pre_auditoria_{arquivo_id}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(
            404,
            "Relatório não encontrado — gere via POST /tributario/fiscal/relatorio-pdf.",
        )
    # Auditoria §11/S10: só o criador (ou gestão) baixa — fail-closed.
    _vlf.exigir_origem(_relatorio_dir(), arquivo_id, cu)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="pre_auditoria_tributaria.pdf",
    )
