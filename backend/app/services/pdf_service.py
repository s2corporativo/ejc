# ── app/services/pdf_service.py ───────────────────────────────────────────────
# Geração de PDF usando weasyprint (HTML→PDF) + Jinja2.
# Dois usos:
#   1. relatorio_mensal_pdf   — relatório gerencial mensal (scheduler dia 1)
#   2. gerar_caso_pdf         — dossiê resumido de um caso específico
#
# LGPD: PDFs gerados para uso interno do escritório.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import logging
import re
from datetime import date
from typing import Any
from app.core.config import get_settings
from app.services.document_format import (
    juntar_segmentos,
    marca_minuta_ia,
    padronizar_documento_juridico,
    sem_caracteres_problematicos,
)
from app.services import visual_law_theme as vlt

logger = logging.getLogger("ejc.pdf")

_settings = get_settings()

# Logo institucional embutida via tema central (base64, lazy + cache).
_logo_data_uri = vlt.logo_data_uri


_HTML_BASE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  @page {{
    size: A4;
    margin: 2.35cm 1.85cm 2.35cm 2.65cm;
    @bottom-center {{
      content: "De Paula Teixeira Advogados Associados | Pagina " counter(page) " de " counter(pages);
      font-family: "DejaVu Sans", sans-serif;
      font-size: 8pt;
      color: #6b7280;
    }}
  }}
  body {{ font-family: "DejaVu Sans", Arial, sans-serif; font-size: 10.5pt; color: #111827; line-height: 1.58; background: #fff; }}
  .letterhead {{ border-bottom: 3px solid §OURO_CLARO§; padding-bottom: 11px; margin-bottom: 18px; display: table; width: 100%; }}
  .letterhead-logo {{ display: table-cell; width: 190px; vertical-align: middle; }}
  .brand-logo {{ max-width: 178px; max-height: 78px; object-fit: contain; }}
  .brand-logo[src=""] {{ display: none; }}
  .letterhead-text {{ display: table-cell; vertical-align: middle; text-align: right; }}
  .letterhead-nome {{ font-size: 13pt; font-weight: 800; color: §OURO_PROFUNDO§; }}
  .letterhead-sub {{ font-size: 8.4pt; color: #6b7280; margin-top: 3px; }}
  h1 {{ font-size: 15pt; color: #111827; margin: 0 0 10px 0; line-height: 1.24; }}
  h2 {{ font-size: 11.6pt; color: §OURO§; margin: 17px 0 8px 0; padding-left: 8px; border-left: 4px solid §OURO_CLARO§; }}
  h3 {{ font-size: 10.7pt; color: #374151; margin: 13px 0 6px 0; }}
  p {{ margin: 0 0 8px 0; text-align: justify; }}
  ul {{ margin: 4px 0 10px 18px; padding: 0; }}
  li {{ margin-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0 14px 0; page-break-inside: avoid; }}
  th {{ background: §OURO_PROFUNDO§; color: #fff; padding: 7px 8px; text-align: left; font-size: 9.2pt; font-weight: 700; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #e5e7eb; font-size: 9.4pt; vertical-align: top; }}
  tr:nth-child(even) td {{ background: §OURO_PALHA§; }}
  .label {{ font-weight: 700; color: #1f2937; background: §OURO_PALHA§ !important; }}
  .doc-cover {{ border: 1px solid #e5d9ac; border-radius: 10px; padding: 14px 15px 13px 15px; margin-bottom: 16px; background: #fbf8ee; page-break-inside: avoid; }}
  .doc-kicker {{ font-size: 8pt; color: §OURO§; font-weight: 800; text-transform: uppercase; margin-bottom: 4px; }}
  .meta-grid {{ width: 100%; border-collapse: separate; border-spacing: 6px; margin: 10px -6px 0 -6px; }}
  .meta-grid td {{ width: 33.33%; border: 1px solid #e5e7eb; background: #fff; border-radius: 7px; padding: 7px 8px; }}
  .meta-label {{ display: block; font-size: 7.2pt; color: #6b7280; font-weight: 800; text-transform: uppercase; }}
  .meta-value {{ display: block; margin-top: 2px; color: #111827; font-size: 9pt; font-weight: 700; }}
  .doc-body {{ margin-top: 4px; }}
  .doc-section {{ border-top: 1px solid #eef2f7; padding-top: 8px; margin-top: 10px; }}
  .callout, .aviso {{ background: #fffbeb; border: 1px solid #f5d08a; border-left: 4px solid #d97706; padding: 9px 11px; border-radius: 7px; font-size: 9.3pt; color: #78350f; margin: 12px 0; page-break-inside: avoid; }}
  .review-stamp {{ border: 1px solid #e8d9a0; border-left: 4px solid §OURO_CLARO§; background: §OURO_PALHA§; color: §OURO_PROFUNDO§; padding: 9px 11px; border-radius: 7px; font-size: 9pt; margin-top: 16px; page-break-inside: avoid; }}
  .ia-minuta {{ border: 2px solid #dc2626; background: #fef2f2; color: #7f1d1d; padding: 10px 12px; border-radius: 7px; font-size: 9.6pt; font-weight: 800; text-align: center; letter-spacing: .2px; margin-bottom: 14px; page-break-inside: avoid; }}
  .footer-doc {{ margin-top: 24px; font-size: 8.3pt; color: #6b7280; border-top: 1px solid #e5e7eb; padding-top: 8px; }}
</style>
</head>
<body>
<div class="letterhead">
  <div class="letterhead-logo"><img class="brand-logo" src="{logo_data_uri}" alt="De Paula Teixeira" /></div>
  <div class="letterhead-text">
    <div class="letterhead-nome">§ESC_NOME§</div>
    <div class="letterhead-sub">§ESC_SUB1§</div>
    <div class="letterhead-sub">§ESC_SUB2§</div>
  </div>
</div>
{corpo}
<div class="footer-doc">Documento gerado automaticamente pelo sistema EJC em {gerado_em}. Uso profissional - confidencial. Responsabilidade tecnica condicionada a revisao e assinatura do advogado responsavel.</div>
</body>
</html>"""

# Timbre institucional — dados FIXOS do escritório vindos da FONTE ÚNICA
# (settings ESCRITORIO_*). OAB e endereço agora fazem parte do letterhead; CNPJ
# não é mais hardcoded. Valores injetados via §tokens (nunca pelo .format()) e
# HTML-escapados, mesmo sendo config confiável.
def _esc_html(valor: str) -> str:
    import html as _html
    return _html.escape(str(valor or ""))


# Segmentos do timbre: cada um só entra se a setting por trás dele estiver
# preenchida (juntar_segmentos descarta os vazios). Sem isto o rodapé saía com
# "CEP [CEP - preencher em .env]" no documento entregue ao cliente.
_SEP_HTML = " &nbsp;|&nbsp; "
_ESC_NOME = _esc_html(_settings.ESCRITORIO_NOME)
_ESC_SUB1 = juntar_segmentos(
    (
        f"CNPJ {_esc_html(_settings.ESCRITORIO_CNPJ)}" if _settings.ESCRITORIO_CNPJ else "",
        f"OAB/MG {_esc_html(_settings.escritorio_oab())}" if _settings.escritorio_oab() else "",
        _esc_html(_settings.ESCRITORIO_EMAIL),
    ),
    _SEP_HTML,
)
_ESC_SUB2 = juntar_segmentos(
    (
        juntar_segmentos(
            (
                _esc_html(_settings.escritorio_endereco()),
                f"{_esc_html(_settings.ESCRITORIO_CIDADE)}/{_esc_html(_settings.ESCRITORIO_ESTADO)}",
            ),
            " - ",
        ),
        f"CEP {_esc_html(_settings.escritorio_cep())}" if _settings.escritorio_cep() else "",
    ),
    _SEP_HTML,
)

# Paleta dourada vinda do tema central (fonte única de verdade) — os tokens
# §...§ evitam conflito com as chaves duplicadas do .format() no CSS.
_HTML_BASE = (
    _HTML_BASE
    .replace("§OURO_PROFUNDO§", vlt.OURO_PROFUNDO)
    .replace("§OURO_CLARO§", vlt.OURO_CLARO)
    .replace("§OURO_PALHA§", vlt.OURO_PALHA)
    .replace("§OURO§", vlt.OURO)
    .replace("§ESC_NOME§", _ESC_NOME)
    .replace("§ESC_SUB1§", _ESC_SUB1)
    .replace("§ESC_SUB2§", _ESC_SUB2)
)

# Aceita maiúsculas acentuadas ("PETIÇÃO INICIAL", "AÇÃO DE COBRANÇA") — o
# conteúdo armazenado agora preserva acentuação (document_format).
_HEADING_RE = re.compile(r"^(?:[IVXLCDM]+\.|[0-9]+\.|[A-ZÁÂÃÀÄÇÉÊËÍÎÏÓÔÕÖÚÛÜ][A-ZÁÂÃÀÄÇÉÊËÍÎÏÓÔÕÖÚÛÜ0-9ºª§ ,:/().-]{7,})\s*$")
_ALERT_WORDS = ("ATENCAO", "ATENÇÃO", "REVISAO HUMANA", "REVISÃO HUMANA",
                "NAO PROTOCOLAR", "NÃO PROTOCOLAR", "RISCO", "ALERTA")


def _linha_e_titulo(linha: str) -> bool:
    limpa = linha.strip()
    if not limpa or len(limpa) > 140:
        return False
    return bool(_HEADING_RE.match(limpa))


def _linha_e_alerta(linha: str) -> bool:
    alta = linha.upper()
    return any(palavra in alta for palavra in _ALERT_WORDS)


def _art_peca_html(
    titulo: str,
    corpo_html: str,
    *,
    pronto_protocolo: bool,
    codigo_peca: str | None = None,
    versao: int | None = None,
    status: Any = None,
    revisado_em: Any = None,
    minuta_ia: bool = False,
) -> str:
    """Monta o <article> Visual Law da peça: capa + meta-grid + corpo + rodapé.

    Fonte única para os dois caminhos de render (texto puro e HTML pré-montado).
    O meta-grid exibe Controle (código), Versão e Status; o rodapé recebe a
    linha de controle EJC-... — ambos INJETADOS SÓ NO RENDER, nunca no texto da
    IA. Degrada sem quebrar quando falta código (peças antigas).

    minuta_ia=True (peça ai_generated e ainda não human_reviewed) embute a marca
    "MINUTA GERADA POR IA" no topo da 1ª página — a salvaguarda VIAJA com o PDF
    exportado. Peça já revisada sai LIMPA (minuta_ia=False).
    """
    import html as html_lib
    from app.services.peca_numeracao import linha_controle, status_label

    banner_ia = (
        f'<div class="ia-minuta">{html_lib.escape(marca_minuta_ia())}</div>\n'
        if minuta_ia else ""
    )
    titulo_esc = html_lib.escape(titulo or "Documento juridico")
    controle_val = html_lib.escape(
        codigo_peca or ("Pronto para protocolo" if pronto_protocolo else "Minuta revisavel")
    )
    versao_val = html_lib.escape(f"v{int(versao or 1)}.0")
    status_val = html_lib.escape(
        status_label(status) if status is not None
        else ("Peca final validada" if pronto_protocolo else "Rascunho controlado")
    )
    aviso = (
        "Documento aprovado e validado para protocolo. Conferir dados variaveis, anexos e assinatura antes do envio ao tribunal."
        if pronto_protocolo
        else "ATENCAO: Rascunho sujeito a revisao humana obrigatoria por advogado responsavel antes de protocolo, envio ou assinatura."
    )
    rodape = ""
    if codigo_peca:
        linha = html_lib.escape(linha_controle(
            codigo_peca=codigo_peca, titulo=titulo, versao=versao,
            status=status, revisado_em=revisado_em,
        ))
        rodape = f'\n  <div class="footer-doc">{linha}</div>'
    return f"""
<article class=\"visual-law legal-doc\">
  {banner_ia}<div class=\"doc-cover\">
    <div class=\"doc-kicker\">Peca juridica | Padrao Visual Law EJC</div>
    <h1>{titulo_esc}</h1>
    <table class=\"meta-grid\"><tr>
      <td><span class=\"meta-label\">Controle</span><span class=\"meta-value\">{controle_val}</span></td>
      <td><span class=\"meta-label\">Versao</span><span class=\"meta-value\">{versao_val}</span></td>
      <td><span class=\"meta-label\">Status</span><span class=\"meta-value\">{status_val}</span></td>
    </tr></table>
  </div>
  <div class=\"review-stamp\">{aviso}</div>
  <div class=\"doc-body\">{corpo_html}</div>{rodape}
</article>
"""


def _texto_peca_para_html(
    titulo: str,
    conteudo: str,
    pronto_protocolo: bool = False,
    *,
    codigo_peca: str | None = None,
    versao: int | None = None,
    status: Any = None,
    revisado_em: Any = None,
    minuta_ia: bool = False,
) -> str:
    """Converte texto juridico puro em HTML Visual Law sem mudar o teor."""
    import html as html_lib

    linhas = [linha.rstrip() for linha in (conteudo or "").splitlines()]
    blocos: list[str] = []
    itens_lista: list[str] = []

    def fecha_lista() -> None:
        nonlocal itens_lista
        if itens_lista:
            blocos.append("<ul>" + "".join(itens_lista) + "</ul>")
            itens_lista = []

    for linha in linhas:
        limpa = linha.strip()
        if not limpa:
            fecha_lista()
            continue
        if limpa.startswith(("- ", "* ")):
            itens_lista.append(f"<li>{html_lib.escape(limpa[2:].strip())}</li>")
            continue
        fecha_lista()
        esc = html_lib.escape(limpa)
        if _linha_e_alerta(limpa):
            blocos.append(f'<div class="callout">{esc}</div>')
        elif _linha_e_titulo(limpa):
            blocos.append(f'<div class="doc-section"><h2>{esc}</h2></div>')
        elif re.match(r"^[A-Z]\.[ ]+", limpa) or re.match(r"^[0-9]+\.[0-9]+", limpa):
            blocos.append(f"<h3>{esc}</h3>")
        else:
            blocos.append(f"<p>{esc}</p>")

    fecha_lista()
    corpo = "\n".join(blocos)
    return _art_peca_html(
        titulo, corpo,
        pronto_protocolo=pronto_protocolo,
        codigo_peca=codigo_peca, versao=versao, status=status, revisado_em=revisado_em,
        minuta_ia=minuta_ia,
    )


def _html_para_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
        html = sem_caracteres_problematicos(html)
        return HTML(string=html).write_pdf()
    except ImportError:
        raise RuntimeError("weasyprint não instalado. Execute: pip install weasyprint")


# ── Relatório Mensal ──────────────────────────────────────────────────────────

def relatorio_mensal_pdf(mes: int, ano: int, dados: dict[str, Any]) -> bytes:
    """PDF gerencial mensal — chamado pelo scheduler no dia 1 de cada mês."""
    MESES = [
        "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    nome_mes = MESES[mes] if 1 <= mes <= 12 else str(mes)

    novos_casos      = dados.get("novos_casos", 0)
    casos_ativos     = dados.get("casos_ativos", 0)
    casos_encerrados = dados.get("casos_encerrados", 0)
    hon_recebido     = dados.get("honorarios_recebido", 0)
    hon_pendente     = dados.get("honorarios_pendente", 0)
    prazos_vencidos  = dados.get("prazos_vencidos", 0)
    novos_clientes   = dados.get("novos_clientes", 0)

    corpo = f"""
<h1>Relatório Gerencial — {nome_mes}/{ano}</h1>
<p>De Paula Teixeira Sociedade de Advogados</p>

<h2>Casos</h2>
<table>
  <tr><th>Indicador</th><th>Valor</th></tr>
  <tr><td>Novos casos no mês</td><td>{novos_casos}</td></tr>
  <tr><td>Casos ativos (fim do mês)</td><td>{casos_ativos}</td></tr>
  <tr><td>Casos encerrados no mês</td><td>{casos_encerrados}</td></tr>
  <tr><td>Novos clientes</td><td>{novos_clientes}</td></tr>
</table>

<h2>Financeiro</h2>
<table>
  <tr><th>Indicador</th><th>Valor (R$)</th></tr>
  <tr><td>Honorários recebidos</td><td>{hon_recebido:,.2f}</td></tr>
  <tr><td>Honorários em aberto</td><td>{hon_pendente:,.2f}</td></tr>
</table>

<h2>Prazos</h2>
<table>
  <tr><th>Indicador</th><th>Valor</th></tr>
  <tr><td>Prazos vencidos no mês</td><td>{prazos_vencidos}</td></tr>
</table>

<div class="aviso">
  Relatório gerado automaticamente. Valores sujeitos à conferência com os
  lançamentos individuais no sistema.
</div>
"""
    html = _HTML_BASE.format(corpo=corpo, gerado_em=date.today().strftime("%d/%m/%Y"), logo_data_uri=_logo_data_uri())
    return _html_para_pdf(html)


# ── PDF por Caso ──────────────────────────────────────────────────────────────

async def gerar_caso_pdf(db, case_id: str, user_id: str) -> bytes:
    """
    Dossiê PDF resumido de um caso específico.
    Uso: GET /export/casos/{id}.pdf
    """
    from sqlalchemy import select, text
    from app.models.case import Case
    from app.models.client import Client
    from app.models.deadline import Deadline
    from app.models.fee import Fee

    case = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not case:
        raise ValueError(f"Caso {case_id} não encontrado")

    cliente = None
    if case.client_id:
        cliente = (await db.execute(
            select(Client).where(Client.id == case.client_id)
        )).scalar_one_or_none()

    prazos = (await db.execute(
        select(Deadline).where(
            Deadline.case_id == case_id,
            Deadline.status == "pendente",
            Deadline.deleted_at.is_(None),
        ).order_by(Deadline.data_prazo)
    )).scalars().all()

    fees = (await db.execute(
        select(Fee).where(
            Fee.case_id == case_id,
            Fee.status.in_(["pendente", "atrasado"]),
            Fee.deleted_at.is_(None),
        )
    )).scalars().all()

    movs = (await db.execute(text("""
        SELECT descricao, data_evento FROM case_movimentos
        WHERE case_id = :cid
        ORDER BY data_evento DESC NULLS LAST LIMIT 10
    """), {"cid": case_id})).all()

    cliente_nome = "—"
    if cliente:
        cliente_nome = cliente.nome or cliente.razao_social or "—"

    def _dt(d):
        return d.strftime("%d/%m/%Y") if d else "—"

    linhas_prazos = "".join(
        f"<tr><td>{p.titulo}</td><td>{_dt(p.data_prazo)}</td>"
        f"<td>{p.tipo or '—'}</td></tr>"
        for p in prazos
    ) or "<tr><td colspan='3'>Nenhum prazo pendente</td></tr>"

    linhas_fees = "".join(
        f"<tr><td>{f.descricao or '—'}</td>"
        f"<td>R$ {float(f.valor or 0):,.2f}</td>"
        f"<td>{getattr(f.status, 'value', f.status)}</td></tr>"
        for f in fees
    ) or "<tr><td colspan='3'>Nenhum honorário em aberto</td></tr>"

    linhas_movs = "".join(
        f"<tr><td>{_dt(m.data_evento)}</td><td>{(m.descricao or '')[:120]}</td></tr>"
        for m in movs
    ) or "<tr><td colspan='2'>Sem movimentos</td></tr>"

    area_val = getattr(case.area, "value", case.area) if case.area else "—"
    status_val = getattr(case.status, "value", case.status)

    corpo = f"""
<h1>Dossiê do Caso</h1>

<h2>Dados Gerais</h2>
<table>
  <tr><td class="label" width="20%">Nº Interno</td><td width="30%">{case.numero_interno or '—'}</td>
      <td class="label" width="20%">Status</td><td>{status_val}</td></tr>
  <tr><td class="label">Título</td><td colspan="3">{case.titulo or '—'}</td></tr>
  <tr><td class="label">Área</td><td>{area_val}</td>
      <td class="label">Cliente</td><td>{cliente_nome}</td></tr>
  <tr><td class="label">Nº Processo</td><td>{case.numero_processo or '—'}</td>
      <td class="label">Parte Contrária</td><td>{case.parte_contraria or '—'}</td></tr>
</table>

<h2>Prazos Pendentes</h2>
<table>
  <tr><th>Título</th><th>Vencimento</th><th>Tipo</th></tr>
  {linhas_prazos}
</table>

<h2>Honorários em Aberto</h2>
<table>
  <tr><th>Descrição</th><th>Valor</th><th>Status</th></tr>
  {linhas_fees}
</table>

<h2>Últimas Movimentações (10)</h2>
<table>
  <tr><th>Data</th><th>Movimento</th></tr>
  {linhas_movs}
</table>

<div class="aviso">
  Documento de uso interno. Para informações processuais oficiais, consulte
  o sistema judicial competente.
</div>
"""
    html = _HTML_BASE.format(corpo=corpo, gerado_em=date.today().strftime("%d/%m/%Y"), logo_data_uri=_logo_data_uri())
    return _html_para_pdf(html)


async def peca_para_pdf_async(
    titulo: str,
    conteudo: str,
    *,
    pronto_protocolo: bool = False,
    codigo_peca: str | None = None,
    versao: int | None = None,
    status: Any = None,
    revisado_em: Any = None,
    minuta_ia: bool = False,
) -> bytes:
    """Converte uma peca juridica em PDF Visual Law.

    Quando pronto_protocolo=True, o PDF sai como versao final para protocolo.
    Caso contrario, permanece marcado como rascunho controlado.

    codigo_peca/versao/status/revisado_em (do LegalDoc) alimentam o meta-grid e
    a linha de controle do rodape — INJETADOS SO NO RENDER, nunca no texto da
    IA. Ausentes (pecas antigas), o render degrada sem quebrar.

    minuta_ia=True (ai_generated e ainda nao human_reviewed) embute a marca
    "MINUTA GERADA POR IA" no topo — a salvaguarda VIAJA com o PDF baixado.
    """
    import asyncio
    from datetime import date

    titulo = padronizar_documento_juridico(titulo) or "Documento juridico"
    conteudo = padronizar_documento_juridico(conteudo)
    if conteudo.strip().startswith("<"):
        corpo = _art_peca_html(
            titulo, conteudo,
            pronto_protocolo=pronto_protocolo,
            codigo_peca=codigo_peca, versao=versao, status=status, revisado_em=revisado_em,
            minuta_ia=minuta_ia,
        )
    else:
        corpo = _texto_peca_para_html(
            titulo, conteudo, pronto_protocolo=pronto_protocolo,
            codigo_peca=codigo_peca, versao=versao, status=status, revisado_em=revisado_em,
            minuta_ia=minuta_ia,
        )

    html_doc = _HTML_BASE.format(
        corpo=corpo,
        gerado_em=date.today().strftime("%d/%m/%Y"),
        logo_data_uri=_logo_data_uri(),
    )
    return await asyncio.get_event_loop().run_in_executor(None, _html_para_pdf, html_doc)



async def relatorio_mensal_pdf_async(mes: int, ano: int, dados: dict) -> bytes:
    """Versão assíncrona de relatorio_mensal_pdf — delega para executor."""
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(
        None, relatorio_mensal_pdf, mes, ano, dados
    )


async def relatorio_lgpd_pdf_async(dados: dict) -> bytes:
    """Relatório LGPD art.18 — dados pessoais e histórico de acessos do cliente."""
    import asyncio
    import html as _h

    nome    = _h.escape(str(dados.get("nome", "—")))
    email   = _h.escape(str(dados.get("email", "—")))
    cpf     = _h.escape(str(dados.get("cpf", "—")))
    casos   = dados.get("casos", [])
    acessos = dados.get("acessos", [])

    linhas_casos = "".join(
        f"<tr><td>{_h.escape(c.get('numero','—'))}</td>"
        f"<td>{_h.escape(c.get('status','—'))}</td>"
        f"<td>{_h.escape(c.get('area','—'))}</td></tr>"
        for c in casos
    ) or "<tr><td colspan=3>Nenhum caso registrado</td></tr>"

    linhas_acessos = "".join(
        f"<tr><td>{_h.escape(a.get('data','—'))}</td>"
        f"<td>{_h.escape(a.get('acao','—'))}</td>"
        f"<td>{_h.escape(a.get('perfil','—'))}</td></tr>"
        for a in acessos
    ) or "<tr><td colspan=3>Nenhum acesso registrado</td></tr>"

    corpo = f"""
<h1>Relatório de Dados Pessoais — LGPD Art. 18</h1>
<h2>Dados do Titular</h2>
<table>
  <tr><td class="label">Nome</td><td>{nome}</td></tr>
  <tr><td class="label">E-mail</td><td>{email}</td></tr>
  <tr><td class="label">CPF</td><td>{cpf}</td></tr>
</table>
<h2>Casos Vinculados</h2>
<table>
  <tr><th>Nº Processo</th><th>Status</th><th>Área</th></tr>
  {linhas_casos}
</table>
<h2>Histórico de Acessos</h2>
<table>
  <tr><th>Data/Hora</th><th>Ação</th><th>Perfil</th></tr>
  {linhas_acessos}
</table>
<div class="aviso">Relatório emitido em atendimento ao direito de acesso — LGPD, art. 18, II.</div>
"""
    html_doc = _HTML_BASE.format(
        corpo=corpo,
        gerado_em=__import__('datetime').date.today().strftime("%d/%m/%Y"),
        logo_data_uri=_logo_data_uri(),
    )
    return await asyncio.get_event_loop().run_in_executor(None, _html_para_pdf, html_doc)
