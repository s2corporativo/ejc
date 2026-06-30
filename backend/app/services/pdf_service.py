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
from datetime import date
from typing import Any
from app.services.document_format import padronizar_documento_juridico, sem_caracteres_problematicos

logger = logging.getLogger("ejc.pdf")

_HTML_BASE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  @page {{
    size: A4;
    margin: 2.5cm 2cm 2.5cm 3cm;
    @bottom-center {{
      content: "De Paula Teixeira Sociedade de Advogados  ·  Pág. " counter(page) " de " counter(pages);
      font-family: "DejaVu Sans", sans-serif;
      font-size: 8pt;
      color: #888;
    }}
  }}
  body {{
    font-family: "DejaVu Sans", sans-serif;
    font-size: 10.5pt;
    color: #1a1a1a;
    line-height: 1.55;
  }}
  .letterhead {{
    border-bottom: 3px solid #1a3a5c;
    padding-bottom: 10px;
    margin-bottom: 18px;
  }}
  .letterhead-nome {{
    font-size: 16pt;
    font-weight: bold;
    color: #1a3a5c;
    letter-spacing: 0.5px;
  }}
  .letterhead-sub {{
    font-size: 9pt;
    color: #555;
    margin-top: 2px;
  }}
  h1 {{
    font-size: 14pt;
    color: #1a3a5c;
    margin-top: 18px;
    margin-bottom: 8px;
    padding-bottom: 4px;
    border-bottom: 1px solid #c8d8e8;
  }}
  h2 {{
    font-size: 11.5pt;
    color: #2a4a6c;
    margin-top: 16px;
    margin-bottom: 6px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0 14px 0;
  }}
  th {{
    background: #1a3a5c;
    color: #fff;
    padding: 6px 8px;
    text-align: left;
    font-size: 9.5pt;
    font-weight: bold;
  }}
  td {{
    padding: 5px 8px;
    border-bottom: 1px solid #dde6ef;
    font-size: 9.5pt;
    vertical-align: top;
  }}
  tr:nth-child(even) td {{
    background: #f5f8fb;
  }}
  .label {{
    font-weight: bold;
    color: #3a5070;
    background: #eef2f7 !important;
  }}
  .aviso {{
    background: #fffbe6;
    border: 1px solid #d4a800;
    border-left: 4px solid #d4a800;
    padding: 10px 12px;
    border-radius: 3px;
    font-size: 9.5pt;
    margin-top: 14px;
  }}
  .footer-doc {{
    margin-top: 24px;
    font-size: 8.5pt;
    color: #888;
    border-top: 1px solid #ddd;
    padding-top: 8px;
  }}
</style>
</head>
<body>
<div class="letterhead">
  <div class="letterhead-nome">De Paula Teixeira Sociedade de Advogados</div>
  <div class="letterhead-sub">
    CNPJ 32.491.468/0001-12 &nbsp;|&nbsp; Betim, MG &nbsp;|&nbsp;
    contato@depaulateixeira.adv.br
  </div>
</div>
{corpo}
<div class="footer-doc">
  Documento gerado automaticamente pelo sistema EJC em {gerado_em}.
  Uso interno — confidencial. Não constitui manifestação jurídica oficial.
</div>
</body>
</html>"""


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
    html = _HTML_BASE.format(corpo=corpo, gerado_em=date.today().strftime("%d/%m/%Y"))
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
    html = _HTML_BASE.format(corpo=corpo, gerado_em=date.today().strftime("%d/%m/%Y"))
    return _html_para_pdf(html)


async def peca_para_pdf_async(titulo: str, conteudo: str) -> bytes:
    """Converte uma peça jurídica (HTML ou texto) em PDF profissional."""
    import asyncio
    import html as html_lib
    from datetime import date

    titulo = padronizar_documento_juridico(titulo)
    conteudo = padronizar_documento_juridico(conteudo)
    if not conteudo.strip().startswith("<"):
        conteudo = "<p>" + html_lib.escape(conteudo).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"

    titulo_esc = html_lib.escape(titulo)
    corpo = f"""
<h1>{titulo_esc}</h1>
{conteudo}
"""
    html_doc = _HTML_BASE.format(
        corpo=corpo,
        gerado_em=date.today().strftime("%d/%m/%Y"),
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
        gerado_em=__import__('datetime').date.today().strftime("%d/%m/%Y")
    )
    return await asyncio.get_event_loop().run_in_executor(None, _html_para_pdf, html_doc)
