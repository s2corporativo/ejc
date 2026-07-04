---
name: gerador-habilitacao-automatica
description: >
  Automatiza a compilação do pacote de habilitação para licitações públicas da S2 Estratégia & Negócios Ltda. Use SEMPRE que precisar gerar, organizar ou verificar o pacote de habilitação para um edital específico: lista automática de documentos exigidos vs. documentos disponíveis, identificação de gaps, geração do checklist de habilitação, merge de PDFs em pacote único. Integra com gestor-portais-licitacao (documentos cadastrados) e analista-edital-propostas (documentos exigidos). Cobre: parsing de cláusulas de habilitação, mapeamento edital→documento, verificação de vencimentos, geração de pacote PDF. Acionado por: "pacote de habilitação", "habilitação automática", "documentos habilitação edital", "gerar habilitação", "compilar documentos licitação", "quais documentos faltam", "checklist habilitação", "pacote documental licitação", "habilitação jurídica fiscal técnica econômica".
---

# Gerador de Habilitação Automática — S2 Licitações

## Contexto

```
EMPRESA: S2 Estratégia & Negócios Ltda (+ Verde Limp em licitações de serviços)
BASE LEGAL: Art. 62-70, Lei 14.133/21 (habilitação em 5 categorias)
OBJETIVO: compilar pacote de habilitação automaticamente a partir do edital + cofre documental
```

---

## 1. Categorias de Habilitação (Lei 14.133/21)

```python
# habilitacao/categories.py

HABILITACAO_CATEGORIES = {
    "juridica": {
        "label": "Habilitação Jurídica",
        "base_legal": "Art. 66, Lei 14.133/21",
        "docs": [
            {"key": "contrato_social", "name": "Contrato Social e alterações / Certidão Simplificada JUCEMG", "mandatory": True, "validity_days": 90},
            {"key": "cnpj_cartao", "name": "Cartão CNPJ (dados atualizados)", "mandatory": True, "validity_days": 30},
            {"key": "documentos_socios", "name": "RG e CPF dos sócios", "mandatory": True, "validity_days": None},
        ]
    },
    "fiscal_trabalhista": {
        "label": "Habilitação Fiscal, Social e Trabalhista",
        "base_legal": "Art. 68, Lei 14.133/21",
        "docs": [
            {"key": "cnd_federal", "name": "CND Federal (Receita + PGFN)", "mandatory": True, "validity_days": 180},
            {"key": "cnd_estadual_mg", "name": "CND Estadual — MG", "mandatory": True, "validity_days": 180},
            {"key": "cnd_municipal", "name": "CND Municipal (Betim ou sede licitante)", "mandatory": True, "validity_days": 365},
            {"key": "crf_fgts", "name": "CRF — FGTS (Caixa Econômica)", "mandatory": True, "validity_days": 30},
            {"key": "cndt", "name": "CNDT — Certidão Negativa de Débitos Trabalhistas", "mandatory": True, "validity_days": 180},
        ]
    },
    "qualificacao_tecnica": {
        "label": "Qualificação Técnica",
        "base_legal": "Art. 69, Lei 14.133/21",
        "docs": [
            {"key": "atestado_capacidade_tecnica", "name": "Atestado de Capacidade Técnica (Grupo SADA ou similar)", "mandatory": "conditional", "validity_days": None},
            {"key": "registro_profissional", "name": "Registro profissional (CRM, CREA, OAB, CRBio — conforme objeto)", "mandatory": "conditional", "validity_days": 365},
            {"key": "alvara_funcionamento", "name": "Alvará/Licença de Funcionamento", "mandatory": "conditional", "validity_days": 365},
        ]
    },
    "qualificacao_economica": {
        "label": "Qualificação Econômico-Financeira",
        "base_legal": "Art. 69, §1º, Lei 14.133/21",
        "docs": [
            {"key": "balanco_patrimonial", "name": "Balanço Patrimonial (último exercício)", "mandatory": "conditional", "validity_days": None},
            {"key": "capital_social", "name": "Comprovante de Capital Social mínimo (se exigido)", "mandatory": "conditional", "validity_days": None},
        ]
    }
}
```

---

## 2. Parser de Cláusulas de Habilitação do Edital

```python
# habilitacao/parser.py
import re
from typing import dict, list

HABILITACAO_KEYWORDS = {
    "cnd_federal": ["receita federal", "pgfn", "certidão federal", "cnd federal"],
    "cnd_estadual_mg": ["certidão estadual", "sefaz", "estado"],
    "cnd_municipal": ["certidão municipal", "prefeitura", "tributos municipais", "iss"],
    "crf_fgts": ["fgts", "crf", "caixa econômica"],
    "cndt": ["cndt", "débitos trabalhistas", "tst"],
    "atestado_capacidade_tecnica": ["atestado", "capacidade técnica", "aptidão", "desempenho"],
    "registro_profissional": ["oab", "crea", "crm", "crbio", "registro profissional", "habilitado"],
    "contrato_social": ["contrato social", "estatuto social", "atos constitutivos", "jucemg"],
    "balanco_patrimonial": ["balanço patrimonial", "demonstrações contábeis"],
}

def parse_habilitacao_from_edital(edital_text: str) -> dict:
    """
    Analisa texto de edital e identifica documentos de habilitação exigidos.
    Retorna dict com documentos identificados e contexto da cláusula.
    """
    text_lower = edital_text.lower()
    required_docs = {}

    for doc_key, keywords in HABILITACAO_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                # Extrair contexto da cláusula (100 chars antes e depois)
                idx = text_lower.find(kw)
                context = edital_text[max(0, idx-100):idx+200]
                required_docs[doc_key] = {
                    "found": True,
                    "keyword_matched": kw,
                    "context": context.strip()
                }
                break

    return required_docs

def generate_habilitacao_checklist(edital_text: str, available_docs: list[str]) -> dict:
    """
    Gera checklist completo comparando documentos exigidos vs. disponíveis.
    available_docs: lista de chaves de documentos disponíveis no cofre
    """
    required = parse_habilitacao_from_edital(edital_text)
    checklist = {"ok": [], "missing": [], "expiring": [], "not_required": []}

    for category, cat_data in HABILITACAO_CATEGORIES.items():
        for doc in cat_data["docs"]:
            key = doc["key"]
            is_required = key in required or doc["mandatory"] is True

            if not is_required:
                checklist["not_required"].append({"key": key, "name": doc["name"]})
                continue

            if key in available_docs:
                checklist["ok"].append({"key": key, "name": doc["name"], "category": category})
            else:
                checklist["missing"].append({
                    "key": key,
                    "name": doc["name"],
                    "category": category,
                    "urgency": "CRÍTICO" if doc["mandatory"] is True else "VERIFICAR"
                })

    return checklist
```

---

## 3. Gerador de PDF do Pacote de Habilitação

```python
# habilitacao/pdf_packager.py
import os
from pypdf import PdfWriter, PdfReader
from typing import list, dict

def merge_habilitacao_pdfs(
    doc_paths: dict[str, str],
    output_path: str,
    company_name: str = "S2 Estratégia & Negócios Ltda",
    edital_ref: str = ""
) -> str:
    """
    Combina PDFs de habilitação em um único arquivo organizado.
    doc_paths: {doc_key: file_path}
    """
    writer = PdfWriter()

    # Ordem padronizada conforme Lei 14.133/21
    order = [
        "contrato_social", "cnpj_cartao", "documentos_socios",
        "cnd_federal", "cnd_estadual_mg", "cnd_municipal", "crf_fgts", "cndt",
        "atestado_capacidade_tecnica", "registro_profissional", "alvara_funcionamento",
        "balanco_patrimonial", "capital_social"
    ]

    for doc_key in order:
        if doc_key in doc_paths and os.path.exists(doc_paths[doc_key]):
            reader = PdfReader(doc_paths[doc_key])
            for page in reader.pages:
                writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)

    return output_path
```

---

## 4. Verificador de Vencimentos

```python
# habilitacao/expiry_checker.py
from datetime import date

EXPIRY_RULES = {
    "cnd_federal": 180,
    "cnd_estadual_mg": 180,
    "cnd_municipal": 365,
    "crf_fgts": 30,
    "cndt": 180,
    "registro_profissional": 365,
    "alvara_funcionamento": 365,
}

def check_document_validity(doc_key: str, issue_date: date, session_date: date) -> dict:
    """Verifica se documento estará válido na data da sessão"""
    validity_days = EXPIRY_RULES.get(doc_key)
    if not validity_days:
        return {"valid": True, "message": "Sem prazo de validade definido"}

    expiry = issue_date + __import__("datetime").timedelta(days=validity_days)
    days_until_session = (session_date - date.today()).days
    days_until_expiry = (expiry - date.today()).days

    if expiry < session_date:
        return {
            "valid": False,
            "message": f"VENCE antes da sessão: {expiry.strftime('%d/%m/%Y')} (sessão: {session_date.strftime('%d/%m/%Y')})",
            "urgency": "CRÍTICO"
        }
    elif days_until_expiry <= 15:
        return {
            "valid": True,
            "message": f"Atenção: vence em {days_until_expiry} dias ({expiry.strftime('%d/%m/%Y')})",
            "urgency": "ALERTA"
        }
    return {"valid": True, "message": f"Válido até {expiry.strftime('%d/%m/%Y')}", "urgency": "OK"}
```

---

## 5. Saída Padrão do Checklist

```
HABILITAÇÃO — Edital: Prefeitura Betim/MG | Pregão Eletrônico 001/2026
Sessão: 28/05/2026 | Gerado em: 21/05/2026

✅ DISPONÍVEIS E VÁLIDOS (5):
  ✅ Contrato Social (Jurídica)
  ✅ CND Federal — válida até 10/08/2026
  ✅ CRF FGTS — válida até 05/06/2026
  ✅ CNDT — válida até 15/09/2026
  ✅ Atestado Grupo SADA (Técnica)

⚠️ ATENÇÃO — VENCENDO (1):
  ⚠️ CND Municipal — vence em 12 dias (02/06/2026) — RENOVAR ANTES DA SESSÃO

❌ FALTANTES — PROVIDENCIAR (2):
  ❌ CND Estadual MG — NÃO LOCALIZADO NO COFRE — solicitar ao contador
  ❌ Alvará de Funcionamento — NÃO LOCALIZADO — emitir na Prefeitura de Betim

RESULTADO: 🔴 NÃO APTO — 2 documentos faltantes críticos
AÇÃO IMEDIATA: solicitar CND Estadual + renovar CND Municipal + emitir Alvará
```
