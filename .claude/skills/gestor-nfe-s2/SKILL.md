---
name: gestor-nfe-s2
description: >
  Automatiza emissão e gestão de NFS-e para a S2 Estratégia & Negócios Ltda (serviços de consultoria jurídica, licitações e assessoria empresarial). Use SEMPRE que precisar emitir, controlar ou automatizar notas fiscais de serviços da S2: NFS-e de consultoria, honorários, assessoria em licitações, success-fee TCFA, relatórios fiscais. DIFERENÇA do integrador-nfe-verde-limp: aquele trata de serviços de conservação/roçada (Verde Limp, CNAE 8130); este trata de CONSULTORIA JURÍDICA e ASSESSORIA (S2, CNAEs 6911-7, 7020-4, 6920-6). ISS de Betim/MG, regime Simples Nacional. Acionado por: "nota fiscal S2", "NFS-e consultoria", "nota honorários S2", "faturar consultoria", "NFS-e assessoria licitação", "nota fiscal success-fee", "faturamento S2", "NF serviço S2", "emitir nota S2".
---

# Gestor NFS-e — S2 Estratégia & Negócios Ltda

## Contexto Fiscal S2

```
EMPRESA: S2 Estratégia & Negócios Ltda
CNPJ: [verificar — não confirmado nas memórias]
SEDE: Betim/MG → NFS-e via Prefeitura de Betim
REGIME: Simples Nacional (presumido)
SERVIÇOS PRINCIPAIS:
  - Consultoria jurídica (OAB/MG)
  - Assessoria em licitações (Lei 14.133/21)
  - Consultoria ambiental/TCFA (success-fee)
  - Assessoria empresarial
CNAE PRINCIPAL: 6911-7/01 (Serviços advocatícios) ou 7020-4 (Atividades de consultoria em gestão)
ISS BETIM: verificar tabela municipal vigente (~2% a 5% para consultoria)
```

---

## 1. Tipos de Nota Fiscal S2 — Por Serviço

```python
# nfe_s2/service_types.py

S2_SERVICE_TYPES = {
    "consultoria_juridica": {
        "descricao": "Serviços de Consultoria e Assessoria Jurídica",
        "cnae": "6911-7/01",
        "item_lista_lc116": "17.20",  # Planejamento, organização e administração
        "aliquota_iss_betim": 0.02,   # 2% — confirmar tabela municipal vigente
        "nota_fiscal_desc": "Honorários advocatícios e assessoria jurídica"
    },
    "assessoria_licitacao": {
        "descricao": "Assessoria Técnica em Licitações e Contratos Públicos",
        "cnae": "7020-4/00",
        "item_lista_lc116": "17.01",  # Assessoria ou consultoria de qualquer natureza
        "aliquota_iss_betim": 0.02,
        "nota_fiscal_desc": "Assessoria técnica em processos licitatórios — Lei 14.133/21"
    },
    "auditoria_tcfa": {
        "descricao": "Consultoria e Auditoria Ambiental — Regularização TCFA",
        "cnae": "7490-1/04",  # Atividades de consultoria ambiental
        "item_lista_lc116": "17.01",
        "aliquota_iss_betim": 0.02,
        "nota_fiscal_desc": "Serviços de auditoria e regularização TCFA junto ao IBAMA — success-fee"
    },
    "assessoria_empresarial": {
        "descricao": "Assessoria e Consultoria Empresarial",
        "cnae": "7020-4/00",
        "item_lista_lc116": "17.01",
        "aliquota_iss_betim": 0.02,
        "nota_fiscal_desc": "Serviços de assessoria e consultoria empresarial"
    }
}
```

---

## 2. Client Focus NFe para S2

```python
# nfe_s2/focus_client_s2.py
import httpx
import os
from datetime import date

FOCUS_BASE = "https://api.focusnfe.com.br/v2"  # produção
# FOCUS_BASE = "https://homologacao.focusnfe.com.br/v2"  # homologação
FOCUS_TOKEN = os.getenv("FOCUS_NFE_TOKEN_S2")

S2_PRESTADOR = {
    "cnpj_prestador": os.getenv("S2_CNPJ", "").replace(".", "").replace("/", "").replace("-", ""),
    "razao_social_prestador": "S2 Estrategia e Negocios Ltda",
    "inscricao_municipal_prestador": os.getenv("S2_INSCRICAO_MUNICIPAL", ""),
    "codigo_municipio_prestador": "3106200",  # Betim/MG (IBGE)
    "optante_simples_nacional": True,
}

def build_nfse_s2(
    tomador_cnpj: str,
    tomador_razao_social: str,
    tomador_email: str,
    valor_servico: float,
    service_type: str,
    descricao_complementar: str = "",
    competencia: str = None,
    ref: str = None
) -> dict:
    """
    Monta payload NFS-e para serviços S2.
    service_type: chave de S2_SERVICE_TYPES
    """
    from nfe_s2.service_types import S2_SERVICE_TYPES
    
    svc = S2_SERVICE_TYPES.get(service_type)
    if not svc:
        raise ValueError(f"service_type inválido: {service_type}")
    
    comp = competencia or date.today().strftime("%Y-%m")
    ano, mes = comp.split("-")
    data_competencia = f"{ano}-{mes}-01"
    
    discriminacao = svc["nota_fiscal_desc"]
    if descricao_complementar:
        discriminacao += f"\n{descricao_complementar}"
    discriminacao += f"\nReferência: {comp}"
    
    return {
        "prestador": {**S2_PRESTADOR},
        "tomador": {
            "cnpj": tomador_cnpj.replace(".", "").replace("/", "").replace("-", ""),
            "razao_social": tomador_razao_social,
            "email": tomador_email,
        },
        "servico": {
            "valor_servico": round(valor_servico, 2),
            "iss_retido": False,
            "valor_iss": round(valor_servico * svc["aliquota_iss_betim"], 2),
            "aliquota": svc["aliquota_iss_betim"],
            "discriminacao": discriminacao,
            "codigo_municipio": "3106200",
            "codigo_cnae": svc["cnae"].replace("-", "").replace("/", ""),
            "item_lista_servico": svc["item_lista_lc116"],
        },
        "data_competencia": data_competencia,
        "natureza_operacao": 1  # Tributação no município
    }

async def emit_nfse_s2(ref: str, payload: dict, sandbox: bool = False) -> dict:
    """Emite NFS-e via Focus NFe"""
    base = "https://homologacao.focusnfe.com.br/v2" if sandbox else FOCUS_BASE
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{base}/nfse?ref={ref}",
            json=payload,
            auth=(FOCUS_TOKEN, ""),
            timeout=30
        )
        return {"status_code": r.status_code, "data": r.json()}
```

---

## 3. Controle de Faturamento S2

```sql
-- Tabela de controle de notas S2
CREATE TABLE IF NOT EXISTS s2_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT UNIQUE NOT NULL,          -- referência interna ex: S2-2026-001
    client_cnpj TEXT NOT NULL,
    client_name TEXT NOT NULL,
    client_email TEXT,
    service_type TEXT NOT NULL,        -- consultoria_juridica, assessoria_licitacao, etc.
    descricao TEXT,
    valor REAL NOT NULL,
    competencia TEXT NOT NULL,         -- YYYY-MM
    nfse_number TEXT,                  -- número da nota emitida
    nfse_date TEXT,
    payment_status TEXT DEFAULT 'pendente',  -- pendente, pago, vencido, cancelado
    payment_date TEXT,
    due_date TEXT,
    focus_status TEXT,                 -- autorizado, cancelado, erro
    focus_response TEXT,               -- JSON da resposta
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_s2_invoices_status ON s2_invoices(payment_status);
CREATE INDEX idx_s2_invoices_comp ON s2_invoices(competencia);
```

---

## 4. Relatório Financeiro S2 por Competência

```python
# nfe_s2/financial_report.py
import sqlite3
from datetime import datetime

def monthly_revenue_s2(db_path: str, year: int, month: int) -> dict:
    competence = f"{year}-{month:02d}"
    conn = sqlite3.connect(db_path)
    
    summary = conn.execute("""
        SELECT
            service_type,
            COUNT(*) as count,
            SUM(valor) as total,
            SUM(CASE WHEN payment_status='pago' THEN valor ELSE 0 END) as received,
            SUM(CASE WHEN payment_status='pendente' THEN valor ELSE 0 END) as pending,
            SUM(CASE WHEN payment_status='vencido' THEN valor ELSE 0 END) as overdue
        FROM s2_invoices
        WHERE competencia = ?
        GROUP BY service_type
    """, (competence,)).fetchall()
    
    totals = conn.execute("""
        SELECT SUM(valor), SUM(CASE WHEN payment_status='pago' THEN valor ELSE 0 END)
        FROM s2_invoices WHERE competencia = ?
    """, (competence,)).fetchone()
    
    conn.close()
    
    return {
        "competencia": competence,
        "faturamento_total": totals[0] or 0,
        "recebido": totals[1] or 0,
        "por_servico": [dict(zip(
            ["servico", "qtd", "total", "recebido", "pendente", "vencido"], row
        )) for row in summary]
    }
```

---

## 5. Regras Fiscais Específicas S2

```
OAB × CNPJ — ATENÇÃO:
  → Serviços advocatícios: SOMENTE advogado (OAB) pode prestar
  → Nota fiscal de honorários advocatícios: verificar se deve sair na PJ (S2) ou na pessoa física do advogado
  → Provimento OAB 94/2000 e Resolução CFOA 02/2015: honorários podem ser cobrados por sociedade de advogados
  → S2 não é sociedade de advogados (CNPJ diferente) — honorários advocatícios devem sair na PJ apenas se contrato firmado pela PJ

SUCCESS-FEE TCFA:
  → Nota somente após conclusão da regularização (fato gerador = prestação do serviço)
  → Discriminação deve mencionar: "Serviços de consultoria ambiental — êxito"
  → Retenção na fonte: verificar se tomador é obrigado a reter ISS

SIMPLES NACIONAL:
  → ISS já incluso no DAS — não recolher ISS em guia separada
  → Exceção: ISS retido na fonte pelo tomador (se obrigado) — nesse caso NÃO recolhe no DAS
  → Alíquota efetiva do DAS varia por faixa de faturamento

OBRIGAÇÕES ACESSÓRIAS BETIM:
  → NFS-e emitida via sistema da Prefeitura de Betim (verificar qual sistema: ISS.NET, nota betim, etc.)
  → RAIS, DIRF e obrigações acessórias — manter em dia
  → Livro fiscal digital: manter arquivo NFS-e por 5 anos
```

---

## 6. Variáveis de Ambiente S2

```env
FOCUS_NFE_TOKEN_S2=SEU_TOKEN_FOCUS_S2
S2_CNPJ=XX.XXX.XXX/0001-XX
S2_INSCRICAO_MUNICIPAL=NUMERO_IM_BETIM
S2_DB=./s2_financeiro.db
NFSE_SANDBOX_S2=false
```

---

## 7. Checklist Antes de Emitir NFS-e S2

```
[ ] Contrato assinado com o cliente (ou proposta aceita)
[ ] Serviço efetivamente prestado (fato gerador ocorreu)
[ ] CNPJ do tomador validado
[ ] Valor e competência corretos
[ ] Discriminação clara (evitar "outros serviços")
[ ] ISS retido ou não — verificar obrigação do tomador
[ ] Nota de honorários advocatícios: verificar se sai na S2 ou no CPF do advogado
[ ] Backup da NFS-e emitida em PDF no Google Drive S2
```
