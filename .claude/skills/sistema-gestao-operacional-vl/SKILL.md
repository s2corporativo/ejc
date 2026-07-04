---
name: sistema-gestao-operacional-vl
description: >
  Arquiteta e codifica o sistema digital de gestão operacional da Verde Limp Serviços e Terceirização Ltda. Use SEMPRE que precisar construir, implementar ou planejar qualquer componente digital da Verde Limp: sistema de contratos ativos, ordens de serviço (OS) digitais, alocação de equipe, relatórios automáticos, faturamento, dashboard de clientes. Verde Limp não possui nenhuma skill de codificação — este é o skill técnico central. Stack recomendada: FastAPI Python ou Flask + SQLite/PostgreSQL + React simples ou Streamlit para operação mínima. Foco em funcionalidade imediata e baixo custo de manutenção. Acionado por: "sistema verde limp", "digitalizar verde limp", "OS digital vl", "contratos verde limp sistema", "sistema de gestão vl", "app verde limp", "faturamento verde limp", "dashboard clientes vl", "gestão operacional verde limp".
---

# Sistema de Gestão Operacional — Verde Limp

## Contexto da Empresa

```
RAZÃO SOCIAL: Verde Limp Serviços e Terceirização Ltda
CNPJ: 30.198.776/0001-29
PORTE: ME — operação B2B, Betim/MG e Grande BH
SERVIÇOS: roçada, jardinagem corporativa, retroescavadeira, limpeza predial, sinalização, facility
CLIENTE REFERÊNCIA: Grupo SADA
PRINCÍPIO: sistema leve, funcional, baixo custo de manutenção
```

---

## 1. Arquitetura do Sistema (MVP)

### Módulos do Sistema Verde Limp

```
1. CONTRATOS         — clientes, serviços contratados, vigência, valor mensal
2. ORDENS DE SERVIÇO — OS por cliente, equipe alocada, data, status, foto
3. EQUIPE            — funcionários, função, disponibilidade, EPI, NR
4. FATURAMENTO       — base para NF-e, competência, valor, status pagamento
5. DOCUMENTOS        — certidões, PCMSO, PGR, atestados (vencimento, renovação)
6. DASHBOARD         — KPIs: contratos ativos, OS do mês, receita, inadimplência
```

### Stack Recomendada por Porte

```
OPÇÃO A — MÍNIMO VIÁVEL (1 semana):
  Backend:  Python Flask + SQLite
  Frontend: Streamlit (admin interno)
  Deploy:   VPS simples ou localhost

OPÇÃO B — ESCALÁVEL (3 semanas):
  Backend:  FastAPI + PostgreSQL
  Frontend: React + Tailwind
  Deploy:   Docker + VPS
  (reutiliza padrão EJC)
```

---

## 2. Schema de Banco de Dados

```sql
-- CONTRATOS
CREATE TABLE contracts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_name TEXT NOT NULL,
  client_cnpj TEXT,
  client_contact TEXT,
  client_whatsapp TEXT,
  service_type TEXT NOT NULL, -- rocada, jardinagem, facility, limpeza, sinalizacao
  area_m2 REAL,
  monthly_value REAL NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE,
  status TEXT DEFAULT 'ativo', -- ativo, suspenso, encerrado
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ORDENS DE SERVIÇO
CREATE TABLE service_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contract_id INTEGER REFERENCES contracts(id),
  os_number TEXT UNIQUE NOT NULL, -- VL-2026-001
  service_date DATE NOT NULL,
  team_ids TEXT, -- JSON array de IDs da equipe
  leader_name TEXT,
  service_description TEXT NOT NULL,
  area_executed_m2 REAL,
  hours_worked REAL,
  status TEXT DEFAULT 'pendente', -- pendente, em_execucao, concluida, cancelada
  notes TEXT,
  photos_before TEXT, -- JSON array de paths
  photos_after TEXT,  -- JSON array de paths
  client_signature TEXT, -- base64 ou path
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP
);

-- EQUIPE
CREATE TABLE team_members (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  cpf TEXT UNIQUE,
  role TEXT NOT NULL, -- jardineiro, roçador, operador_retro, limpador, sinalizador
  ctps_number TEXT,
  admission_date DATE,
  salary REAL,
  status TEXT DEFAULT 'ativo',
  epis_delivered TEXT, -- JSON: {epi: data_entrega, assinatura: bool}
  nr_trainings TEXT,   -- JSON: {nr: date_completed}
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FATURAMENTO
CREATE TABLE billing (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contract_id INTEGER REFERENCES contracts(id),
  competence TEXT NOT NULL, -- YYYY-MM
  value REAL NOT NULL,
  nfse_number TEXT,
  nfse_date DATE,
  payment_status TEXT DEFAULT 'pendente', -- pendente, faturado, pago, vencido
  payment_date DATE,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DOCUMENTOS OPERACIONAIS
CREATE TABLE operational_docs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_type TEXT NOT NULL, -- PCMSO, PGR, LTCAT, CND_FEDERAL, CND_ESTADUAL, CND_MUNICIPAL, CRF_FGTS, CNDT
  issue_date DATE,
  expiry_date DATE NOT NULL,
  file_path TEXT,
  status TEXT DEFAULT 'vigente', -- vigente, vencendo, vencido
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ALERTAS AUTOMÁTICOS (gerados por job)
CREATE TABLE alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_type TEXT NOT NULL,
  reference_id INTEGER,
  reference_table TEXT,
  message TEXT NOT NULL,
  severity TEXT DEFAULT 'medio', -- critico, alto, medio, baixo
  status TEXT DEFAULT 'ativo',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. Lógica de Negócio Crítica

### Geração Automática de OS
```python
def generate_os_number(db):
    """Gera número sequencial VL-YYYY-NNN"""
    year = datetime.now().year
    last = db.execute(
        "SELECT os_number FROM service_orders WHERE os_number LIKE ? ORDER BY id DESC LIMIT 1",
        (f"VL-{year}-%",)
    ).fetchone()
    if last:
        seq = int(last[0].split("-")[2]) + 1
    else:
        seq = 1
    return f"VL-{year}-{seq:03d}"
```

### Verificação de Vencimentos (job diário)
```python
def check_document_expiry(db):
    """Roda diariamente — gera alertas de documentos vencendo"""
    today = date.today()
    docs = db.execute("SELECT * FROM operational_docs WHERE status != 'vencido'").fetchall()
    alerts = []
    for doc in docs:
        days_left = (doc['expiry_date'] - today).days
        if days_left < 0:
            db.execute("UPDATE operational_docs SET status='vencido' WHERE id=?", (doc['id'],))
            alerts.append({
                'alert_type': 'DOC_VENCIDO',
                'message': f"DOCUMENTO VENCIDO: {doc['doc_type']} — renovar imediatamente",
                'severity': 'critico'
            })
        elif days_left <= 15:
            alerts.append({
                'alert_type': 'DOC_VENCENDO',
                'message': f"Documento vencendo em {days_left} dias: {doc['doc_type']}",
                'severity': 'alto' if days_left <= 7 else 'medio'
            })
    for alert in alerts:
        db.execute("INSERT INTO alerts (alert_type, message, severity) VALUES (?,?,?)",
                   (alert['alert_type'], alert['message'], alert['severity']))
    db.commit()
```

### Cálculo de Receita Mensal
```python
def monthly_revenue_summary(db, year: int, month: int) -> dict:
    """Consolidação financeira por competência"""
    competence = f"{year}-{month:02d}"
    result = db.execute("""
        SELECT
            COUNT(*) as total_contracts,
            SUM(value) as total_billed,
            SUM(CASE WHEN payment_status = 'pago' THEN value ELSE 0 END) as total_received,
            SUM(CASE WHEN payment_status = 'vencido' THEN value ELSE 0 END) as total_overdue
        FROM billing WHERE competence = ?
    """, (competence,)).fetchone()
    return dict(result)
```

---

## 4. Dashboard KPIs

```python
# KPIs do dashboard principal
def get_dashboard_kpis(db) -> dict:
    return {
        "contratos_ativos": db.execute(
            "SELECT COUNT(*) FROM contracts WHERE status='ativo'"
        ).fetchone()[0],
        "os_mes_atual": db.execute(
            "SELECT COUNT(*) FROM service_orders WHERE strftime('%Y-%m', service_date) = ?",
            (datetime.now().strftime("%Y-%m"),)
        ).fetchone()[0],
        "receita_mes": db.execute(
            "SELECT COALESCE(SUM(value),0) FROM billing WHERE competence = ?",
            (datetime.now().strftime("%Y-%m"),)
        ).fetchone()[0],
        "alertas_criticos": db.execute(
            "SELECT COUNT(*) FROM alerts WHERE severity='critico' AND status='ativo'"
        ).fetchone()[0],
        "docs_vencendo_30d": db.execute(
            "SELECT COUNT(*) FROM operational_docs WHERE expiry_date BETWEEN date('now') AND date('now','+30 days')"
        ).fetchone()[0]
    }
```

---

## 5. Relatório Mensal Automatizado

```python
def generate_monthly_report(db, contract_id: int, year: int, month: int) -> dict:
    """Gera dados para relatório mensal de execução por cliente"""
    competence = f"{year}-{month:02d}"
    contract = db.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
    os_list = db.execute(
        "SELECT * FROM service_orders WHERE contract_id=? AND strftime('%Y-%m', service_date)=?",
        (contract_id, competence)
    ).fetchall()
    billing = db.execute(
        "SELECT * FROM billing WHERE contract_id=? AND competence=?",
        (contract_id, competence)
    ).fetchone()
    return {
        "cliente": contract['client_name'],
        "competencia": competence,
        "servicos_executados": len(os_list),
        "area_total_m2": sum(os['area_executed_m2'] or 0 for os in os_list),
        "horas_trabalhadas": sum(os['hours_worked'] or 0 for os in os_list),
        "valor_faturado": billing['value'] if billing else 0,
        "os_detalhes": [dict(os) for os in os_list]
    }
```

---

## 6. Regras Operacionais

- OS só pode ser concluída com pelo menos 1 foto de execução
- Contrato não pode ser encerrado com OS pendentes
- Faturamento do mês gerado automaticamente no dia 28 de cada mês
- Alerta automático quando certidão vence em ≤ 15 dias
- Margem mínima de 15% por contrato — alerta se abaixo
- Nunca deletar contrato ou OS — apenas marcar status
- Backup automático do banco SQLite a cada 24h (copiar arquivo .db)
