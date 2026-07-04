---
name: gerador-relatorios-pdf-dinamicos
description: >
  Gera relatórios PDF dinâmicos a partir de dados de banco para os sistemas EJC, Verde Limp e S2. Use SEMPRE que precisar gerar PDFs automatizados via código: relatório mensal de execução Verde Limp (fotos + OS), extrato de honorários EJC, relatório de casos por cliente, relatório de licitações S2, boleto de cobrança, proposta comercial em PDF. Diferença: relatorio-mensal-executivo gera conteúdo textual no chat; este skill gera arquivos PDF reais via Python (WeasyPrint, ReportLab ou Jinja2+HTML→PDF). Stack: WeasyPrint (HTML→PDF, melhor para layouts) ou ReportLab (PDF puro, mais controle). Acionado por: "gerar PDF", "relatório PDF", "exportar PDF sistema", "relatório mensal PDF vl", "extrato honorários PDF", "PDF automatizado", "WeasyPrint", "ReportLab", "HTML para PDF", "relatório código PDF", "gerar PDF backend".
---

# Gerador de Relatórios PDF — EJC · Verde Limp · S2

## Stack Recomendada

```
WeasyPrint: HTML/CSS → PDF (melhor para layouts complexos, tabelas, imagens)
ReportLab:  Python puro → PDF (melhor para documentos programáticos)
Jinja2:     Template engine para HTML dos relatórios

INSTALAR:
pip install weasyprint jinja2 reportlab --break-system-packages
# WeasyPrint também precisa: apt install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0
```

---

## 1. Template HTML (Verde Limp — Relatório de Execução)

```python
# reports/templates/vl_execucao.html (Jinja2)
VL_EXECUCAO_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 11px; color: #333; margin: 0; padding: 20px; }
  .header { background: #16a34a; color: white; padding: 16px; border-radius: 6px; margin-bottom: 20px; }
  .header h1 { margin: 0; font-size: 18px; }
  .header p { margin: 4px 0 0; font-size: 12px; opacity: 0.9; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; }
  th { background: #f0fdf4; padding: 8px; text-align: left; border-bottom: 2px solid #16a34a; font-size: 11px; }
  td { padding: 6px 8px; border-bottom: 1px solid #e5e7eb; }
  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }
  .kpi-card { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 12px; text-align: center; }
  .kpi-value { font-size: 22px; font-weight: bold; color: #16a34a; }
  .kpi-label { font-size: 10px; color: #6b7280; margin-top: 2px; }
  .footer { margin-top: 24px; padding-top: 12px; border-top: 1px solid #e5e7eb; color: #9ca3af; font-size: 10px; }
  .photo-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; }
  .photo-grid img { width: 100%; height: 120px; object-fit: cover; border-radius: 4px; }
  @page { size: A4; margin: 1.5cm; }
</style>
</head>
<body>
<div class="header">
  <h1>📋 Relatório Mensal de Execução</h1>
  <p>Verde Limp Serviços e Terceirização Ltda | CNPJ: 30.198.776/0001-29</p>
</div>

<table>
  <tr><th colspan="2">INFORMAÇÕES DO CONTRATO</th></tr>
  <tr><td><b>Cliente</b></td><td>{{ cliente }}</td></tr>
  <tr><td><b>Competência</b></td><td>{{ competencia }}</td></tr>
  <tr><td><b>Serviços Contratados</b></td><td>{{ servicos_contratados }}</td></tr>
  <tr><td><b>Área Total</b></td><td>{{ area_m2 }} m²</td></tr>
</table>

<div class="kpi-grid">
  <div class="kpi-card"><div class="kpi-value">{{ total_os }}</div><div class="kpi-label">OS Executadas</div></div>
  <div class="kpi-card"><div class="kpi-value">{{ area_executada }}m²</div><div class="kpi-label">Área Executada</div></div>
  <div class="kpi-card"><div class="kpi-value">{{ horas_trabalhadas }}h</div><div class="kpi-label">Horas Trabalhadas</div></div>
  <div class="kpi-card"><div class="kpi-value">R${{ valor_faturado }}</div><div class="kpi-label">Valor Faturado</div></div>
</div>

<h3>Ordens de Serviço Executadas</h3>
<table>
  <thead>
    <tr><th>OS</th><th>Data</th><th>Serviço</th><th>Área</th><th>Líder</th><th>Status</th></tr>
  </thead>
  <tbody>
    {% for os in ordens_servico %}
    <tr>
      <td>{{ os.os_number }}</td>
      <td>{{ os.service_date }}</td>
      <td>{{ os.service_description[:50] }}</td>
      <td>{{ os.area_executed_m2 or '-' }} m²</td>
      <td>{{ os.leader_name or '-' }}</td>
      <td>✅ {{ os.status }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

{% if fotos %}
<h3>Registro Fotográfico</h3>
<div class="photo-grid">
  {% for foto in fotos %}
  <img src="{{ foto }}" alt="Execução">
  {% endfor %}
</div>
{% endif %}

<div class="footer">
  <p>Relatório gerado em {{ data_geracao }} | Verde Limp Serviços e Terceirização Ltda</p>
  <p>Contato: (31) 99907-4546 | adm@vetmg.com.br</p>
</div>
</body>
</html>
"""
```

---

## 2. Gerador Python com WeasyPrint

```python
# reports/pdf_generator.py
from weasyprint import HTML, CSS
from jinja2 import Environment, BaseLoader
from datetime import datetime
import os, base64

def generate_vl_monthly_report(report_data: dict, output_path: str) -> str:
    """Gera PDF do relatório mensal Verde Limp"""
    env = Environment(loader=BaseLoader())
    template = env.from_string(VL_EXECUCAO_TEMPLATE)

    # Converter fotos para base64 (WeasyPrint sem servidor web)
    fotos_b64 = []
    for foto_path in report_data.get("photos", [])[:6]:  # máximo 6 fotos
        if os.path.exists(foto_path):
            with open(foto_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                ext = foto_path.rsplit(".", 1)[-1].lower()
                fotos_b64.append(f"data:image/{ext};base64,{b64}")

    html_content = template.render(
        **report_data,
        fotos=fotos_b64,
        data_geracao=datetime.now().strftime("%d/%m/%Y %H:%M")
    )

    HTML(string=html_content, base_url="/").write_pdf(output_path)
    return output_path


def generate_ejc_honorarios_report(case_data: dict, output_path: str) -> str:
    """Gera extrato de honorários EJC em PDF"""
    HONORARIOS_TEMPLATE = """
    <!DOCTYPE html><html><head><meta charset="UTF-8">
    <style>
      body { font-family: Arial, sans-serif; font-size: 11px; }
      .header { background: #1e40af; color: white; padding: 16px; }
      table { width: 100%; border-collapse: collapse; }
      th { background: #eff6ff; padding: 8px; border: 1px solid #bfdbfe; }
      td { padding: 6px 8px; border: 1px solid #e5e7eb; }
      .total { font-weight: bold; background: #eff6ff; }
      @page { size: A4; margin: 2cm; }
    </style></head>
    <body>
    <div class="header"><h2>Extrato de Honorários</h2>
    <p>{{ escritorio }} | OAB/MG {{ oab }}</p></div>
    <br>
    <p><b>Cliente:</b> {{ cliente }} &nbsp;&nbsp; <b>Caso:</b> {{ numero_caso }}</p>
    <p><b>Área:</b> {{ area }} &nbsp;&nbsp; <b>Gerado em:</b> {{ data }}</p>
    <table>
      <thead><tr><th>Data</th><th>Descrição</th><th>Valor</th><th>Status</th></tr></thead>
      <tbody>
      {% for rec in registros %}
      <tr>
        <td>{{ rec.date }}</td><td>{{ rec.description }}</td>
        <td>R$ {{ "%.2f"|format(rec.value) }}</td><td>{{ rec.status }}</td>
      </tr>
      {% endfor %}
      <tr class="total"><td colspan="2">TOTAL</td>
        <td>R$ {{ "%.2f"|format(total) }}</td><td></td></tr>
      </tbody>
    </table>
    </body></html>
    """
    env = Environment(loader=BaseLoader())
    html = env.from_string(HONORARIOS_TEMPLATE).render(
        **case_data, data=datetime.now().strftime("%d/%m/%Y")
    )
    HTML(string=html).write_pdf(output_path)
    return output_path
```

---

## 3. Endpoint FastAPI para Download de PDF

```python
# routers/reports.py
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
import tempfile, os
from app.auth import get_current_user
from reports.pdf_generator import generate_vl_monthly_report, generate_ejc_honorarios_report

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/verde-limp/monthly/{contract_id}/{year}/{month}")
async def vl_monthly_report(
    contract_id: int, year: int, month: int,
    current_user = Depends(get_current_user)
):
    # Buscar dados do banco
    # data = get_monthly_report_data(contract_id, year, month)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        output_path = f.name
    # generate_vl_monthly_report(data, output_path)
    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=f"VL_Relatorio_{year}_{month:02d}.pdf",
        background=__import__("starlette.background", fromlist=["BackgroundTask"]).BackgroundTask(os.unlink, output_path)
    )
```
