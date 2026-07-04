---
name: automatizador-google-workspace
description: >
  Automatiza processos dos negócios S2, Cuidar Vet e Verde Limp usando Google Apps Script, Google Sheets API e Google Drive API. Use SEMPRE que precisar criar automações no Google Workspace: dashboards financeiros automáticos em Sheets, templates de propostas em Docs gerados por script, alertas por email automáticos, integração entre planilhas e sistemas, geração de relatórios periódicos, automação de tarefas repetitivas no Google. Cobre: Apps Script (triggers, funções customizadas), Google Sheets API (Python), Google Drive API (gestão de arquivos), Gmail API, automação sem servidor (grátis dentro do Google). Acionado por: "Apps Script", "automatizar Sheets", "Google Sheets API", "dashboard automático planilha", "script Google", "automação Google Workspace", "Google Drive automático", "gerar documento automático", "relatório Sheets automático", "planilha financeira automática", "trigger Google", "Google Forms integração".
---

# Automatizador Google Workspace — S2 · Cuidar Vet · Verde Limp

## Contexto

```
PLATAFORMA: Google Workspace (Gmail, Drive, Sheets, Docs, Forms, Calendar)
LINGUAGEM: JavaScript (Apps Script) ou Python (Google APIs via service account)
CUSTO: gratuito dentro dos limites do Google (Apps Script: 6 min/execução, 90 min/dia)
CASOS DE USO: dashboards, propostas automáticas, alertas, relatórios, integrações
```

---

## 1. Apps Script — Padrões Fundamentais

### Estrutura Base de um Script

```javascript
// ═══════════════════════════════════════════════════
// Arquivo: Code.gs (Google Apps Script)
// ═══════════════════════════════════════════════════

// Constantes de configuração
const CONFIG = {
  SPREADSHEET_ID: PropertiesService.getScriptProperties().getProperty("SPREADSHEET_ID"),
  EMAIL_DESTINO: "adm@vetmg.com.br",
  TIMEZONE: "America/Sao_Paulo"
};

// Configurar triggers programáticos
function setupTriggers() {
  // Remover triggers existentes
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  
  // Dashboard: todo dia às 7h
  ScriptApp.newTrigger("updateDashboard")
    .timeBased().atHour(7).everyDays(1).create();
  
  // Alertas: todo dia útil às 8h
  ScriptApp.newTrigger("checkAlerts")
    .timeBased().atHour(8).everyDays(1).create();
  
  // Relatório mensal: dia 1 às 9h
  ScriptApp.newTrigger("monthlyReport")
    .timeBased().onMonthDay(1).atHour(9).create();
    
  Logger.log("Triggers configurados com sucesso");
}
```

---

## 2. Dashboard Financeiro Consolidado (3 Negócios)

```javascript
// Dashboard que consolida S2 + Cuidar Vet + Verde Limp

function updateDashboard() {
  const ss = SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
  const dash = ss.getSheetByName("📊 Dashboard") || ss.insertSheet("📊 Dashboard");
  
  const hoje = new Date();
  const mes = hoje.getMonth() + 1;
  const ano = hoje.getFullYear();
  
  // Coletar dados de cada aba
  const s2Data = getSheetMetrics(ss, "S2 - Licitações", mes, ano);
  const vetData = getSheetMetrics(ss, "Cuidar Vet - Pedidos", mes, ano);
  const vlData = getSheetMetrics(ss, "Verde Limp - OS", mes, ano);
  
  const totalFaturamento = s2Data.faturamento + vetData.faturamento + vlData.faturamento;
  
  // Limpar e reconstruir dashboard
  dash.clearContents();
  dash.clearFormats();
  
  // Cabeçalho
  const header = dash.getRange("A1:F1");
  header.merge().setValue(`📊 DASHBOARD EXECUTIVO — ${mes.toString().padStart(2,'0')}/${ano}`)
    .setBackground("#1e40af").setFontColor("white").setFontSize(14).setFontWeight("bold");
  
  // KPIs por negócio
  const kpis = [
    ["Negócio", "Faturamento", "Transações", "Ticket Médio", "vs Mês Ant.", "Status"],
    ["S2 Estratégia", s2Data.faturamento, s2Data.count, s2Data.ticket, "", ""],
    ["Cuidar Vet", vetData.faturamento, vetData.count, vetData.ticket, "", ""],
    ["Verde Limp", vlData.faturamento, vlData.count, vlData.ticket, "", ""],
    ["TOTAL", totalFaturamento, s2Data.count + vetData.count + vlData.count, "", "", ""],
  ];
  
  dash.getRange(3, 1, kpis.length, kpis[0].length).setValues(kpis);
  
  // Formatação monetária
  dash.getRange("B4:B7").setNumberFormat("R$ #,##0.00");
  dash.getRange("D4:D7").setNumberFormat("R$ #,##0.00");
  
  // Linha de total em negrito
  dash.getRange("A7:F7").setFontWeight("bold").setBackground("#e5e7eb");
  
  // Timestamp
  dash.getRange("A10").setValue(`Atualizado: ${Utilities.formatDate(hoje, CONFIG.TIMEZONE, "dd/MM/yyyy HH:mm")}`);
  
  Logger.log(`Dashboard atualizado: R$ ${totalFaturamento.toLocaleString('pt-BR', {minimumFractionDigits:2})}`);
}

function getSheetMetrics(ss, sheetName, mes, ano) {
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) return { faturamento: 0, count: 0, ticket: 0 };
  
  const data = sheet.getDataRange().getValues();
  let total = 0, count = 0;
  
  for (let i = 1; i < data.length; i++) {
    if (!data[i][0]) continue;
    const d = new Date(data[i][0]);
    if (d.getMonth() + 1 === mes && d.getFullYear() === ano) {
      total += parseFloat(data[i][3] || 0);
      count++;
    }
  }
  
  return { faturamento: total, count, ticket: count > 0 ? total / count : 0 };
}
```

---

## 3. Gerador Automático de Propostas (Google Docs)

```javascript
// Gera proposta S2 a partir de um formulário ou planilha de leads

function generateProposal(leadData) {
  // Template de proposta no Google Drive (copiar e personalizar)
  const TEMPLATE_ID = PropertiesService.getScriptProperties().getProperty("PROPOSAL_TEMPLATE_ID");
  const FOLDER_ID = PropertiesService.getScriptProperties().getProperty("PROPOSALS_FOLDER_ID");
  
  // Copiar template
  const templateFile = DriveApp.getFileById(TEMPLATE_ID);
  const newFile = templateFile.makeCopy(
    `Proposta S2 — ${leadData.empresa} — ${Utilities.formatDate(new Date(), CONFIG.TIMEZONE, "dd-MM-yyyy")}`,
    DriveApp.getFolderById(FOLDER_ID)
  );
  
  // Abrir como documento e substituir variáveis
  const doc = DocumentApp.openById(newFile.getId());
  const body = doc.getBody();
  
  const substitutions = {
    "{{EMPRESA}}": leadData.empresa,
    "{{CNPJ}}": leadData.cnpj || "",
    "{{CONTATO}}": leadData.contato || "",
    "{{OBJETO}}": leadData.objeto || "",
    "{{VALOR}}": leadData.valor || "",
    "{{DATA}}": Utilities.formatDate(new Date(), CONFIG.TIMEZONE, "dd 'de' MMMM 'de' yyyy"),
    "{{VALIDADE}}": Utilities.formatDate(
      new Date(new Date().getTime() + 15 * 24 * 60 * 60 * 1000),
      CONFIG.TIMEZONE, "dd/MM/yyyy"
    )
  };
  
  for (const [placeholder, value] of Object.entries(substitutions)) {
    body.replaceText(placeholder, value);
  }
  
  doc.saveAndClose();
  
  // Converter para PDF e salvar
  const pdf = newFile.getAs("application/pdf");
  const pdfFile = DriveApp.getFolderById(FOLDER_ID).createFile(pdf);
  pdfFile.setName(`Proposta S2 — ${leadData.empresa}.pdf`);
  
  // Enviar por email
  MailApp.sendEmail({
    to: leadData.email,
    subject: `Proposta S2 — ${leadData.objeto}`,
    body: `Prezado(a) ${leadData.contato},\n\nSegue nossa proposta conforme solicitado.\n\nDr. Clovis J. Soares\nS2 Estratégia & Negócios`,
    attachments: [pdf]
  });
  
  return pdfFile.getUrl();
}
```

---

## 4. Sistema de Alertas Automáticos

```javascript
// Verifica planilhas de prazos e envia alertas por email/WhatsApp

function checkAlerts() {
  const ss = SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
  const alertsSheet = ss.getSheetByName("⚠️ Prazos e Certidões");
  if (!alertsSheet) return;
  
  const data = alertsSheet.getDataRange().getValues();
  const hoje = new Date();
  const alertas = [];
  
  for (let i = 1; i < data.length; i++) {
    if (!data[i][0] || !data[i][2]) continue;
    const vencimento = new Date(data[i][2]);
    const diasRestantes = Math.ceil((vencimento - hoje) / (1000 * 60 * 60 * 24));
    const documento = data[i][0];
    const sistema = data[i][1];
    
    if (diasRestantes <= 0) {
      alertas.push(`🔴 VENCIDO: ${documento} (${sistema}) — venceu em ${Utilities.formatDate(vencimento, CONFIG.TIMEZONE, "dd/MM/yyyy")}`);
      alertsSheet.getRange(i + 1, 4).setValue("VENCIDO").setBackground("#fca5a5");
    } else if (diasRestantes <= 7) {
      alertas.push(`🟠 URGENTE: ${documento} (${sistema}) — vence em ${diasRestantes} dias`);
      alertsSheet.getRange(i + 1, 4).setValue(`${diasRestantes}d`).setBackground("#fed7aa");
    } else if (diasRestantes <= 15) {
      alertas.push(`🟡 ATENÇÃO: ${documento} (${sistema}) — vence em ${diasRestantes} dias`);
      alertsSheet.getRange(i + 1, 4).setValue(`${diasRestantes}d`).setBackground("#fef08a");
    }
  }
  
  if (alertas.length > 0) {
    const emailBody = `Alertas automáticos do ecossistema S2/VL/CV:\n\n${alertas.join('\n')}\n\nVerifique a planilha: ${SpreadsheetApp.getActiveSpreadsheet().getUrl()}`;
    MailApp.sendEmail(CONFIG.EMAIL_DESTINO, `⚠️ ${alertas.length} Alertas — Prazos e Certidões`, emailBody);
    Logger.log(`${alertas.length} alertas enviados`);
  }
}
```

---

## 5. Python — Google Sheets API (para integração com sistemas externos)

```python
# google_workspace/sheets_client.py
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import json

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_sheets_service(credentials_json: str):
    """credentials_json: conteúdo do arquivo JSON da service account"""
    creds_data = json.loads(credentials_json)
    creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)

def append_row(service, spreadsheet_id: str, sheet_name: str, values: list):
    """Adiciona linha no final da planilha"""
    body = {"values": [values]}
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:Z",
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()

def read_sheet(service, spreadsheet_id: str, range_notation: str) -> list:
    """Lê intervalo da planilha"""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_notation
    ).execute()
    return result.get("values", [])

# Uso: gravar novo edital S2 na planilha de monitoramento
# append_row(svc, SHEET_ID, "Radar Editais", [pncp_id, orgao, objeto, valor, data, link])
```

---

## 6. Propriedades do Script (gerenciar credenciais)

```javascript
// Executar UMA VEZ para configurar propriedades seguras
function setupProperties() {
  const props = PropertiesService.getScriptProperties();
  props.setProperties({
    "SPREADSHEET_ID": "ID_DA_PLANILHA_PRINCIPAL",
    "PROPOSAL_TEMPLATE_ID": "ID_DO_TEMPLATE_PROPOSTA",
    "PROPOSALS_FOLDER_ID": "ID_DA_PASTA_PROPOSTAS",
    "EJC_API_TOKEN": "TOKEN_EJC",
  });
  Logger.log("Propriedades configuradas");
}
```

---

## 7. Limites Apps Script (Free)

```
Execuções por dia:       Ilimitado (usuário pessoal)
Tempo max por execução:  6 minutos
Tempo total por dia:     90 minutos
Emails por dia:          100 destinatários
Triggers simultâneos:    20 por projeto
URL Fetch por dia:       20.000 chamadas
```
