# ── app/routers/tributario_fiscal.py ─────────────────────────────────────────
# Vertical Tributário — leitor de XML fiscal (NF-e) + motor determinístico de
# recuperação de créditos. v1 STATELESS: sem persistência e sem IA.
#
#   POST /tributario/fiscal/analisar-xml      → consolidação das teses
#   POST /tributario/fiscal/relatorio-pdf     → {"download_url": ...}
#   GET  /tributario/fiscal/relatorio/{id}/download → FileResponse (PDF)
#
# Padrões seguidos: upload (MAX_UPLOAD_MB + magic bytes) de routers/documents.py;
# download_url (POST → download_url → blob); Visual Law central
# (services/visual_law_theme.py) como dossie_estrategico.py.
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

import magic  # python-magic — validação por magic bytes (server-side)
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

# Ferramenta de ramo tributário: restrita à equipe jurídica (estagiário+),
# mesmo padrão de previdenciario_beneficio._EQUIPE. cliente_externo já é
# barrado pelo AuthMiddleware — este gate é defesa em profundidade staff-vs-staff.
_EQUIPE = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]

MAX_ARQUIVOS = 50
# Mesmo conjunto aceito para .xml em routers/documents.py (libmagic varia).
MIMES_XML = {"application/xml", "text/xml", "text/plain"}
# Teto agregado do lote (soma de todos os XMLs válidos mantidos em memória):
# além do teto por arquivo (MAX_UPLOAD_MB), limita o total simultâneo para
# não esgotar a RAM do worker com 50 arquivos grandes (hardening DoS).
MAX_LOTE_MB = 120
_CHUNK = 256 * 1024  # 256 KiB — leitura em blocos, sem materializar tudo
# Retenção dos PDFs de diagnóstico (contêm dados fiscais de terceiros — LGPD):
# varredura best-effort remove os mais antigos que este TTL a cada geração.
PDF_TTL_SEGUNDOS = 3600  # 1h

Regime = Literal["simples", "lucro_presumido", "lucro_real"]


# ── Schemas de resposta (Decimal só interno; JSON sai float) ─────────────────

# Limites de tamanho no payload de /relatorio-pdf (entrada do usuário renderizada
# pelo WeasyPrint — caro/síncrono): evitam DoS por strings/listas gigantes.
_TXT = 2000       # texto curto (títulos, fundamentos, alertas)
_TXT_LONGO = 6000  # aviso_hitl


class TeseOut(BaseModel):
    tese_id: str = Field(max_length=64)
    titulo: str = Field(max_length=_TXT)
    base_legal: str = Field(max_length=_TXT)
    fundamento: str = Field(max_length=_TXT)
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
    notas_prescritas: int
    periodo: PeriodoOut
    teses: list[TeseOut] = Field(max_length=20)
    alertas_globais: list[str] = Field(max_length=50)
    aviso_hitl: str = Field(max_length=_TXT_LONGO)
    # teto coerente com MAX_ARQUIVOS (uma nota-resumo por arquivo enviado)
    notas: list[NotaOut] = Field(max_length=MAX_ARQUIVOS)


# ── Análise ───────────────────────────────────────────────────────────────────

@router.post("/analisar-xml", response_model=ConsolidacaoOut,
             dependencies=[Depends(rate_limit("tributario-fiscal-analise", 10))])
async def analisar_xml(
    arquivos: list[UploadFile] = File(..., description="XMLs de NF-e de saída"),
    regime: Regime = Form(...),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """
    Diagnóstico de recuperação de créditos a partir dos XMLs de SAÍDA do
    cliente. Determinístico, sem IA e sem persistência — a resposta é uma
    ESTIMATIVA PRELIMINAR para triagem (HITL obrigatório).
    Fail-soft por arquivo: XML inválido/duplicado vira entrada em
    `notas_com_erro` sem derrubar o lote.
    """
    if len(arquivos) > MAX_ARQUIVOS:
        raise HTTPException(
            status_code=422,
            detail=f"Máximo de {MAX_ARQUIVOS} arquivos por análise "
                   f"(recebidos {len(arquivos)}). Divida o lote e envie em partes.",
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
            erros_previos.append({"arquivo": nome,
                                  "erro": f"Extensão não permitida: {ext or '(sem extensão)'} — apenas .xml."})
            continue
        # Leitura em blocos com corte no teto: aborta o arquivo ao ultrapassar
        # o limite SEM materializar 800 MB na RAM para só então rejeitar.
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
            erros_previos.append({"arquivo": nome,
                                  "erro": f"Arquivo excede {settings.MAX_UPLOAD_MB}MB."})
            continue
        conteudo = b"".join(partes)
        # Teto agregado do lote: barra o esgotamento de RAM por muitos arquivos
        # grandes somados (o restante do lote vira erro, não derruba o app).
        if total_bytes + len(conteudo) > limite_lote:
            erros_previos.append({"arquivo": nome,
                                  "erro": f"Lote excede o total de {MAX_LOTE_MB}MB — "
                                          "envie menos arquivos por vez."})
            continue
        # Magic bytes (server-side), nunca o content_type do cliente —
        # mesmo padrão de routers/documents.py.
        mime_real = magic.from_buffer(conteudo[:2048], mime=True)
        if mime_real not in MIMES_XML:
            erros_previos.append({"arquivo": nome,
                                  "erro": f"Conteúdo do arquivo ({mime_real}) não é XML."})
            continue
        total_bytes += len(conteudo)
        lote.append((nome, conteudo))

    # Rejeições de nível de router (extensão/mime/tamanho) entram no lote como
    # notas com erro — mesmo shape das falhas do parser —, contadas e listadas
    # junto das demais.
    notas = erros_previos + parse_lote(lote)
    resultado = analisar_recuperacao(notas, regime)
    return ConsolidacaoOut.model_validate(resultado)


# ── Relatório PDF (Visual Law) ────────────────────────────────────────────────

# #27: arnês de arquivo (dir + purga TTL + validação UUID) centralizado em
# services/visual_law_files — antes copiado verbatim em cada vertical.
from app.services import visual_law_files as _vlf


def _relatorio_dir() -> str:
    return _vlf.preparar_dir("tributario_fiscal")


def _limpar_pdfs_antigos(out_dir: str) -> None:
    _vlf.purgar_antigos(out_dir)


def _html_relatorio(c: ConsolidacaoOut) -> str:
    """Monta o corpo HTML do diagnóstico. TODO string do payload passa por
    vlt.esc() — o JSON é devolvido pelo frontend (entrada do usuário)."""
    from app.services import visual_law_theme as vlt

    esc = vlt.esc
    regimes_rotulo = {"simples": "Simples Nacional",
                      "lucro_presumido": "Lucro Presumido",
                      "lucro_real": "Lucro Real"}

    def moeda(v: float) -> str:
        inteiro, _, dec = f"{v:,.2f}".partition(".")
        return "R$ " + inteiro.replace(",", ".") + "," + dec

    def data_br(d: Optional[str]) -> str:
        # periodo.inicio/fim chegam como ISO 'YYYY-MM-DD' (ou None).
        if not d:
            return "—"
        try:
            return date.fromisoformat(d).strftime("%d/%m/%Y")
        except ValueError:
            return esc(d)

    partes: list[str] = [vlt.render_banner(
        "DIAGNÓSTICO DE RECUPERAÇÃO DE CRÉDITOS",
        f"Regime: {esc(regimes_rotulo.get(c.regime, c.regime))} · "
        f"{c.notas_analisadas} nota(s) analisada(s)",
    )]

    partes.append(
        "<div style='background:" + vlt.OURO_PALHA + ";border-left:4px solid "
        + vlt.OURO + ";padding:14px 16px;margin:16px 0;'>"
        f"<div style='font-size:10pt;color:{vlt.TEXTO_SUAVE};'>Total estimado "
        "(soma das teses)</div>"
        f"<div style='font-size:20pt;font-weight:bold;color:{vlt.OURO_PROFUNDO};'>"
        f"{moeda(c.total_estimado)}</div>"
        f"<div style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>Período analisado: "
        f"{data_br(c.periodo.inicio)} a {data_br(c.periodo.fim)} · "
        f"{c.notas_prescritas} nota(s) prescrita(s) · "
        f"{c.notas_com_erro} arquivo(s) com erro</div></div>"
    )

    partes.append(
        "<div style='background:#fffbe6;border:1px solid #f0ad4e;border-left:"
        f"4px solid {vlt.OURO_CLARO};padding:12px;margin:12px 0;font-size:9.5pt;'>"
        "<strong>ESTIMATIVA PRELIMINAR — REVISÃO HUMANA OBRIGATÓRIA</strong><br>"
        f"{esc(c.aviso_hitl)}</div>"
    )

    for alerta in c.alertas_globais:
        partes.append(f"<p style='font-size:9.5pt;color:{vlt.TEXTO_SUAVE};'>"
                      f"⚠ {esc(alerta)}</p>")

    for t in c.teses:
        status = ("APLICÁVEL" if t.aplicavel else "INAPLICÁVEL")
        cor = vlt.OURO_PROFUNDO if t.aplicavel else vlt.RODAPE_COR
        partes.append(
            f"<h2 style='color:{vlt.OURO};border-bottom:2px solid "
            f"{vlt.OURO_CLARO};padding-bottom:4px;margin-top:22px;'>"
            f"{esc(t.titulo)}</h2>"
            f"<p><strong style='color:{cor};'>{status}</strong>"
            + (f" · Valor estimado: <strong>{moeda(t.valor_estimado)}</strong>"
               if t.aplicavel else "") + "</p>"
            f"<p style='font-size:10pt;'>{esc(t.fundamento)}</p>"
        )
        if t.motivo_inaplicavel:
            partes.append(f"<p style='font-size:9.5pt;color:{vlt.TEXTO_SUAVE};'>"
                          f"Motivo: {esc(t.motivo_inaplicavel)}</p>")
        if t.base_legal:
            partes.append("<p style='font-size:9pt;'><strong>Base legal:</strong> "
                          + esc(t.base_legal) + "</p>")
        if t.memoria_calculo:
            partes.append("<p style='font-size:9.5pt;margin-bottom:2px;'>"
                          "<strong>Memória de cálculo</strong></p><ul>"
                          + "".join(f"<li style='font-size:9.5pt;'>{esc(p)}</li>"
                                    for p in t.memoria_calculo) + "</ul>")
        for alerta in t.alertas:
            partes.append(f"<p style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>"
                          f"⚠ {esc(alerta)}</p>")

    notas_erro = [n for n in c.notas if n.erro]
    if notas_erro:
        partes.append(f"<h2 style='color:{vlt.OURO};margin-top:22px;'>"
                      "Arquivos não processados</h2><ul>"
                      + "".join(
                          f"<li style='font-size:9pt;'>{esc(n.chave or '(sem chave)')}: "
                          f"{esc(n.erro or '')}</li>" for n in notas_erro)
                      + "</ul>")

    partes.append(
        f"<div style='margin-top:24px;font-size:8.5pt;color:{vlt.RODAPE_COR};"
        "border-top:1px solid #e5e7eb;padding-top:8px;'>Gerado em: "
        f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · "
        "Análise determinística (sem IA) · Nível de confiança: estimativa "
        "preliminar</div>"
    )

    rodape = ("De Paula Teixeira Advogados · Diagnóstico de Recuperação de "
              "Créditos Tributários — estimativa preliminar (HITL)")
    return vlt.html_doc("".join(partes), css=vlt.css_fluxo(rodape))


@router.post("/relatorio-pdf",
             dependencies=[Depends(rate_limit("tributario-fiscal-pdf", 10))])
async def relatorio_pdf(
    consolidacao: ConsolidacaoOut,
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Gera o PDF Visual Law do diagnóstico a partir da consolidação devolvida
    pelo frontend e retorna a URL de download (padrão POST → download_url → blob)."""
    try:
        from weasyprint import HTML as WP_HTML
    except ImportError as exc:
        raise HTTPException(503, f"Dependência de PDF não disponível: {exc}. "
                                 "Instale weasyprint.")

    html_full = _html_relatorio(consolidacao)
    pdf_bytes = WP_HTML(string=html_full).write_pdf()

    out_dir = _relatorio_dir()
    _limpar_pdfs_antigos(out_dir)  # retenção LGPD (TTL) a cada geração
    arquivo_id = str(uuid4())
    path = os.path.join(out_dir, f"diagnostico_{arquivo_id}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    return {"download_url": f"/tributario/fiscal/relatorio/{arquivo_id}/download"}


@router.get("/relatorio/{arquivo_id}/download",
            dependencies=[Depends(rate_limit("tributario-fiscal-download", 30))])
async def download_relatorio(
    arquivo_id: str,
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Download do PDF gerado pelo POST acima. `arquivo_id` é validado como
    UUID (nunca interpolado livre no path — sem traversal)."""
    _vlf.validar_uuid(arquivo_id)
    path = os.path.join(_relatorio_dir(), f"diagnostico_{arquivo_id}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(404, "Relatório não encontrado — gere via POST "
                                 "/tributario/fiscal/relatorio-pdf.")
    return FileResponse(path, media_type="application/pdf",
                        filename="diagnostico_recuperacao_creditos.pdf")
