---
name: sistema-conciliacao-financeira-s2
description: >
  Arquiteta, constrói e opera o sistema de controle financeiro e conciliação
  bancária de contratos de licitação da S2 Estratégia e Negócios Ltda (CNPJ:
  32.491.468/0001-12). Use SEMPRE que precisar: construir o sistema do zero,
  adicionar módulos, corrigir a lógica de conciliação, importar notas fiscais
  ou extratos, executar o motor de conciliação, gerar relatórios, revisar
  divergências ou fazer qualquer análise financeira dos contratos. Cobre os 10
  módulos do sistema: dashboard, cadastro de contratos/licitações, notas
  fiscais, extrato bancário, motor de conciliação (5 níveis), revisão manual,
  relatórios, controle de lucro, alertas e auditoria. Stack: React + TypeScript
  + Tailwind (frontend) | FastAPI Python (backend) | PostgreSQL (banco). Dados
  fixos da empresa: BB Ag 750-1, CC 126941-0. Acionado por: "sistema
  conciliação S2", "cruzar nota com extrato", "motor de conciliação", "importar
  NF-e", "importar extrato OFX", "conciliar pagamento", "nota sem pagamento",
  "divergência financeira"
---

# Sistema de Conciliação Financeira — S2 Estratégia e Negócios Ltda

## Dados da Empresa

```
RAZÃO SOCIAL: S2 Estratégia e Negócios Ltda
CNPJ:         32.491.468/0001-12
ENDEREÇO:     Rua 1º de Janeiro, 415 — Betim/MG
EMAIL:        adm@vetmg.com.br
BANCO:        Banco do Brasil | Agência: 750-1 | Conta: 126941-0
```

---

## 1. Arquitetura do Sistema

```
FRONTEND:  React + TypeScript + Tailwind CSS
BACKEND:   Python FastAPI
BANCO:     PostgreSQL
ARQUIVOS:  pandas (Excel/CSV) | ofxparse (OFX) | pdfplumber (PDF) | lxml (XML NF-e)
IA:        Apenas como apoio — leitura de históricos bancários e sugestão de conciliação
           NUNCA altera dados sem confirmação humana

PRINCÍPIO FUNDAMENTAL:
  Conciliação baseada em REGRAS OBJETIVAS primeiro (valor, data, CNPJ, número NF, AF, empenho)
  IA como suporte, não como fonte de verdade
  Revisão humana obrigatória para casos prováveis, parciais e divergentes
```

---

## 2. Banco de Dados — Schema Completo

```sql
-- ─── EMPRESA ───────────────────────────────────────────────────────────────
CREATE TABLE empresas (
  id SERIAL PRIMARY KEY,
  razao_social TEXT NOT NULL,
  cnpj TEXT UNIQUE NOT NULL,
  endereco TEXT,
  email TEXT,
  banco TEXT, agencia TEXT, conta TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── ÓRGÃOS PÚBLICOS ────────────────────────────────────────────────────────
CREATE TABLE orgaos_publicos (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  cnpj TEXT UNIQUE,
  municipio TEXT, uf TEXT,
  tipo TEXT,  -- prefeitura, universidade, fundacao, autarquia, federal, estadual
  avg_payment_days INTEGER,  -- média histórica de dias para pagar
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── LICITAÇÕES ─────────────────────────────────────────────────────────────
CREATE TABLE licitacoes (
  id SERIAL PRIMARY KEY,
  orgao_id INTEGER REFERENCES orgaos_publicos(id),
  numero_processo TEXT,
  modalidade TEXT,  -- pregao_eletronico, dispensa, concorrencia, credenciamento
  numero_pregao TEXT,
  objeto TEXT,
  valor_estimado NUMERIC(15,2),
  data_abertura DATE,
  status TEXT DEFAULT 'em_andamento',
  lei_aplicavel TEXT DEFAULT '14133/21',
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── CONTRATOS ──────────────────────────────────────────────────────────────
CREATE TABLE contratos (
  id SERIAL PRIMARY KEY,
  licitacao_id INTEGER REFERENCES licitacoes(id),
  orgao_id INTEGER REFERENCES orgaos_publicos(id),
  numero_contrato TEXT,
  numero_ata TEXT,
  objeto TEXT,
  valor_total NUMERIC(15,2) NOT NULL,
  saldo_contratado NUMERIC(15,2),
  data_inicio DATE,
  data_fim DATE,
  prazo_pagamento_dias INTEGER DEFAULT 30,
  responsavel_interno TEXT,
  status TEXT DEFAULT 'vigente',  -- vigente, encerrado, suspenso
  observacoes TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── EMPENHOS ───────────────────────────────────────────────────────────────
CREATE TABLE empenhos (
  id SERIAL PRIMARY KEY,
  contrato_id INTEGER REFERENCES contratos(id),
  orgao_id INTEGER REFERENCES orgaos_publicos(id),
  numero_empenho TEXT NOT NULL,
  valor NUMERIC(15,2) NOT NULL,
  data_emissao DATE,
  exercicio INTEGER,
  status TEXT DEFAULT 'aberto',  -- aberto, liquidado, pago, anulado
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── AUTORIZAÇÕES DE FORNECIMENTO ───────────────────────────────────────────
CREATE TABLE autorizacoes_fornecimento (
  id SERIAL PRIMARY KEY,
  contrato_id INTEGER REFERENCES contratos(id),
  empenho_id INTEGER REFERENCES empenhos(id),
  numero_af TEXT NOT NULL,
  data_emissao DATE,
  prazo_entrega DATE,
  valor NUMERIC(15,2) NOT NULL,
  status TEXT DEFAULT 'pendente',  -- pendente, faturado, entregue, cancelado
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── NOTAS FISCAIS ──────────────────────────────────────────────────────────
CREATE TABLE notas_fiscais (
  id SERIAL PRIMARY KEY,
  -- Identificação
  numero_nota TEXT NOT NULL,
  serie TEXT,
  chave_acesso TEXT UNIQUE,  -- chave NF-e (44 dígitos)
  -- Emissão
  data_emissao DATE NOT NULL,
  data_competencia DATE,
  -- Tomador
  tomador_cnpj TEXT,
  tomador_nome TEXT,
  orgao_id INTEGER REFERENCES orgaos_publicos(id),
  -- Valores
  valor_bruto NUMERIC(15,2) NOT NULL,
  valor_liquido NUMERIC(15,2),
  valor_impostos NUMERIC(15,2) DEFAULT 0,
  valor_retencoes NUMERIC(15,2) DEFAULT 0,
  descricao_servicos TEXT,
  -- Vínculos
  contrato_id INTEGER REFERENCES contratos(id),
  af_id INTEGER REFERENCES autorizacoes_fornecimento(id),
  empenho_id INTEGER REFERENCES empenhos(id),
  licitacao_id INTEGER REFERENCES licitacoes(id),
  -- Status financeiro
  status TEXT DEFAULT 'nota_emitida',
  -- aguardando_pagamento, conciliada, parcialmente_paga, paga_com_retencao,
  -- divergente, vencida, sem_pagamento, cancelada, a_faturar
  data_prevista_pagamento DATE,
  data_real_pagamento DATE,
  -- Arquivo
  arquivo_path TEXT,
  arquivo_tipo TEXT,  -- xml, pdf, manual
  -- Auditoria
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- ─── ITENS DA NOTA FISCAL ───────────────────────────────────────────────────
CREATE TABLE itens_nota_fiscal (
  id SERIAL PRIMARY KEY,
  nota_id INTEGER REFERENCES notas_fiscais(id) ON DELETE CASCADE,
  descricao TEXT NOT NULL,
  ncm TEXT,
  quantidade NUMERIC(10,4),
  unidade TEXT,
  valor_unitario NUMERIC(15,4),
  valor_total NUMERIC(15,2),
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── EXTRATOS BANCÁRIOS (ARQUIVOS IMPORTADOS) ───────────────────────────────
CREATE TABLE extratos_bancarios (
  id SERIAL PRIMARY KEY,
  banco TEXT DEFAULT 'Banco do Brasil',
  agencia TEXT DEFAULT '750-1',
  conta TEXT DEFAULT '126941-0',
  data_inicio DATE,
  data_fim DATE,
  arquivo_path TEXT,
  arquivo_tipo TEXT,  -- ofx, csv, excel, pdf
  importado_em TIMESTAMP DEFAULT NOW(),
  importado_por TEXT
);

-- ─── TRANSAÇÕES BANCÁRIAS ───────────────────────────────────────────────────
CREATE TABLE transacoes_bancarias (
  id SERIAL PRIMARY KEY,
  extrato_id INTEGER REFERENCES extratos_bancarios(id),
  data_transacao DATE NOT NULL,
  historico TEXT,
  valor NUMERIC(15,2) NOT NULL,
  tipo TEXT NOT NULL,  -- credito, debito
  documento TEXT,  -- número do documento bancário
  identificador TEXT UNIQUE,  -- hash único para dedup
  saldo NUMERIC(15,2),
  status_conciliacao TEXT DEFAULT 'nao_conciliado',
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── CONCILIAÇÕES ───────────────────────────────────────────────────────────
CREATE TABLE conciliacoes (
  id SERIAL PRIMARY KEY,
  nota_id INTEGER REFERENCES notas_fiscais(id),
  transacao_id INTEGER REFERENCES transacoes_bancarias(id),
  -- Resultado
  tipo_conciliacao TEXT NOT NULL,
  -- exata, provavel, com_retencao, parcial, divergente, manual
  score_confianca INTEGER CHECK (score_confianca BETWEEN 0 AND 100),
  justificativa TEXT,
  -- Valores
  valor_nota NUMERIC(15,2),
  valor_transacao NUMERIC(15,2),
  diferenca NUMERIC(15,2),
  valor_retencao_estimada NUMERIC(15,2),
  -- Confirmação
  confirmada_por TEXT,
  confirmada_em TIMESTAMP,
  pendente_revisao BOOLEAN DEFAULT TRUE,
  observacao TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── DIVERGÊNCIAS ───────────────────────────────────────────────────────────
CREATE TABLE divergencias (
  id SERIAL PRIMARY KEY,
  nota_id INTEGER REFERENCES notas_fiscais(id),
  transacao_id INTEGER REFERENCES transacoes_bancarias(id),
  tipo TEXT NOT NULL,
  -- valor_superior, valor_inferior, duplicidade, sem_nota, nf_sem_pagamento, af_sem_nf
  descricao TEXT,
  status TEXT DEFAULT 'aberta',  -- aberta, resolvida, ignorada
  resolvida_por TEXT,
  resolvida_em TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── CUSTOS E MARGENS ───────────────────────────────────────────────────────
CREATE TABLE custos_contrato (
  id SERIAL PRIMARY KEY,
  contrato_id INTEGER REFERENCES contratos(id),
  nota_id INTEGER REFERENCES notas_fiscais(id),
  custo_produto NUMERIC(15,2) DEFAULT 0,
  custo_frete NUMERIC(15,2) DEFAULT 0,
  custo_imposto NUMERIC(15,2) DEFAULT 0,
  custo_comissao NUMERIC(15,2) DEFAULT 0,
  custo_operacional NUMERIC(15,2) DEFAULT 0,
  custo_financeiro NUMERIC(15,2) DEFAULT 0,
  retencoes NUMERIC(15,2) DEFAULT 0,
  margem_bruta NUMERIC(15,2),  -- calculada
  margem_liquida NUMERIC(15,2),  -- calculada
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── LOGS DE AUDITORIA ──────────────────────────────────────────────────────
CREATE TABLE logs_auditoria (
  id SERIAL PRIMARY KEY,
  usuario TEXT,
  acao TEXT NOT NULL,  -- importacao, conciliacao, alteracao_manual, cancelamento
  tabela_afetada TEXT,
  registro_id INTEGER,
  dados_antes JSONB,
  dados_depois JSONB,
  ip TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── ÍNDICES ─────────────────────────────────────────────────────────────────
CREATE INDEX idx_nf_status ON notas_fiscais(status);
CREATE INDEX idx_nf_tomador ON notas_fiscais(tomador_cnpj);
CREATE INDEX idx_nf_data ON notas_fiscais(data_emissao DESC);
CREATE INDEX idx_trans_data ON transacoes_bancarias(data_transacao DESC);
CREATE INDEX idx_trans_valor ON transacoes_bancarias(valor);
CREATE INDEX idx_trans_tipo ON transacoes_bancarias(tipo);
CREATE INDEX idx_conc_nota ON conciliacoes(nota_id);
CREATE INDEX idx_conc_trans ON conciliacoes(transacao_id);
```

---

## 3. Motor de Conciliação — 5 Níveis

```python
# conciliacao/engine.py
from dataclasses import dataclass
from typing import Optional
from decimal import Decimal
from datetime import date, timedelta
import re

JANELA_PAGAMENTO_DIAS = 30
TOLERANCIA_RETENCAO_PCT = 0.15  # até 15% de diferença pode ser retenção

@dataclass
class ResultadoConciliacao:
    tipo: str                   # exata, provavel, com_retencao, parcial, divergente
    score: int                  # 0–100
    nota_id: int
    transacao_id: Optional[int]
    valor_nota: Decimal
    valor_recebido: Optional[Decimal]
    diferenca: Optional[Decimal]
    retencao_estimada: Optional[Decimal]
    justificativa: str
    pendente_revisao: bool

def conciliar_nota(nota: dict, transacoes: list[dict]) -> list[ResultadoConciliacao]:
    """
    Executa o motor de conciliação para uma nota fiscal.
    nota: registro da tabela notas_fiscais
    transacoes: créditos bancários candidatos (mesmo período)
    """
    resultados = []
    valor_nota = Decimal(str(nota["valor_bruto"]))
    data_emissao = nota["data_emissao"]
    janela_fim = data_emissao + timedelta(days=JANELA_PAGAMENTO_DIAS)

    # Filtrar apenas créditos dentro da janela
    candidatos = [
        t for t in transacoes
        if t["tipo"] == "credito"
        and data_emissao <= t["data_transacao"] <= janela_fim
    ]

    # ─── NÍVEL 1 — CONCILIAÇÃO EXATA ─────────────────────────────────────────
    for t in candidatos:
        valor_t = Decimal(str(t["valor"]))
        if valor_t == valor_nota:
            score = 70  # base
            justificativas = ["Valor idêntico"]
            historico = (t.get("historico") or "").upper()

            # Boost por correspondência no histórico
            if nota.get("numero_nota") and nota["numero_nota"] in historico:
                score += 20; justificativas.append("Número NF no histórico")
            if nota.get("tomador_cnpj") and nota["tomador_cnpj"].replace(".", "").replace("/", "").replace("-", "") in historico:
                score += 5; justificativas.append("CNPJ no histórico")
            if nota.get("af_id") and str(nota.get("numero_af", "")) in historico:
                score += 5; justificativas.append("Número AF no histórico")
            if nota.get("numero_empenho") and nota["numero_empenho"] in historico:
                score += 5; justificativas.append("Empenho no histórico")

            # Proximidade de data
            dias_diff = abs((t["data_transacao"] - data_emissao).days)
            if dias_diff <= 7:
                score = min(100, score + 5); justificativas.append(f"Crédito em {dias_diff} dias")

            score = min(100, score)
            resultados.append(ResultadoConciliacao(
                tipo="exata",
                score=score,
                nota_id=nota["id"],
                transacao_id=t["id"],
                valor_nota=valor_nota,
                valor_recebido=valor_t,
                diferenca=Decimal("0"),
                retencao_estimada=None,
                justificativa=" | ".join(justificativas),
                pendente_revisao=(score < 95)
            ))

    # ─── NÍVEL 2 — CONCILIAÇÃO PROVÁVEL ──────────────────────────────────────
    if not any(r.tipo == "exata" and r.score >= 90 for r in resultados):
        for t in candidatos:
            valor_t = Decimal(str(t["valor"]))
            if valor_t == valor_nota and not any(r.transacao_id == t["id"] for r in resultados):
                resultados.append(ResultadoConciliacao(
                    tipo="provavel",
                    score=55,
                    nota_id=nota["id"],
                    transacao_id=t["id"],
                    valor_nota=valor_nota,
                    valor_recebido=valor_t,
                    diferenca=Decimal("0"),
                    retencao_estimada=None,
                    justificativa="Valor idêntico mas sem confirmação no histórico",
                    pendente_revisao=True
                ))

    # ─── NÍVEL 3 — CONCILIAÇÃO COM RETENÇÃO ──────────────────────────────────
    if not resultados:
        for t in candidatos:
            valor_t = Decimal(str(t["valor"]))
            diferenca = valor_nota - valor_t
            if Decimal("0") < diferenca <= valor_nota * Decimal(str(TOLERANCIA_RETENCAO_PCT)):
                retencao_pct = float(diferenca / valor_nota) * 100
                retencao_tipo = identificar_retencao(float(diferenca), float(valor_nota))
                resultados.append(ResultadoConciliacao(
                    tipo="com_retencao",
                    score=65,
                    nota_id=nota["id"],
                    transacao_id=t["id"],
                    valor_nota=valor_nota,
                    valor_recebido=valor_t,
                    diferenca=diferenca,
                    retencao_estimada=diferenca,
                    justificativa=f"Diferença de R${diferenca:.2f} ({retencao_pct:.1f}%) — possível {retencao_tipo}",
                    pendente_revisao=True
                ))

    # ─── NÍVEL 4 — PAGAMENTO PARCIAL ─────────────────────────────────────────
    if not resultados:
        creditos_periodo = [t for t in candidatos]
        for janela_dias in [7, 15, 30]:
            candidatos_parcial = [
                t for t in creditos_periodo
                if abs((t["data_transacao"] - data_emissao).days) <= janela_dias
            ]
            soma = sum(Decimal(str(t["valor"])) for t in candidatos_parcial)
            if abs(soma - valor_nota) <= valor_nota * Decimal("0.02"):  # 2% tolerância
                resultados.append(ResultadoConciliacao(
                    tipo="parcial",
                    score=60,
                    nota_id=nota["id"],
                    transacao_id=None,  # múltiplas transações
                    valor_nota=valor_nota,
                    valor_recebido=soma,
                    diferenca=valor_nota - soma,
                    retencao_estimada=None,
                    justificativa=f"{len(candidatos_parcial)} créditos somam R${soma:.2f} em {janela_dias} dias",
                    pendente_revisao=True
                ))
                break

    # ─── NÍVEL 5 — DIVERGÊNCIA / SEM PAGAMENTO ───────────────────────────────
    if not resultados:
        hoje = date.today()
        prazo_vencido = nota.get("data_prevista_pagamento") and nota["data_prevista_pagamento"] < hoje
        resultados.append(ResultadoConciliacao(
            tipo="divergente",
            score=0,
            nota_id=nota["id"],
            transacao_id=None,
            valor_nota=valor_nota,
            valor_recebido=None,
            diferenca=None,
            retencao_estimada=None,
            justificativa="Vencida — pagamento não localizado" if prazo_vencido else "Sem pagamento localizado",
            pendente_revisao=True
        ))

    # Retornar melhor resultado (maior score)
    return sorted(resultados, key=lambda r: r.score, reverse=True)


def identificar_retencao(diferenca: float, valor_nota: float) -> str:
    """Tenta identificar o tipo de retenção pela proporção"""
    pct = diferenca / valor_nota
    retencoes = {
        0.015: "ISS 1,5%", 0.02: "ISS 2%", 0.03: "ISS 3%", 0.05: "ISS 5%",
        0.011: "INSS 11%", 0.08: "IRRF 1,5%", 0.0065: "PIS 0,65%",
        0.03: "COFINS 3%", 0.01: "CSLL 1%",
    }
    for aliq, nome in sorted(retencoes.items(), key=lambda x: abs(x[0] - pct)):
        if abs(pct - aliq) < 0.005:
            return nome
    return f"retenção ({pct*100:.1f}%)"
```

---

## 4. Importadores de Arquivos

### 4.1 Importador OFX (Extrato Banco do Brasil)

```python
# importadores/ofx_importer.py
from ofxparse import OfxParser
import hashlib
from datetime import datetime

def import_ofx(file_path: str, extrato_id: int, db_session) -> dict:
    """Importa extrato OFX e normaliza transações"""
    with open(file_path, "rb") as f:
        ofx = OfxParser.parse(f)

    transacoes_inseridas = 0
    transacoes_duplicadas = 0

    for account in ofx.account:
        for t in account.statement.transactions:
            # Hash único para deduplicação
            hash_key = hashlib.md5(
                f"{t.date.date()}{t.amount}{t.memo}{t.id}".encode()
            ).hexdigest()

            trans = {
                "extrato_id": extrato_id,
                "data_transacao": t.date.date(),
                "historico": t.memo,
                "valor": abs(float(t.amount)),
                "tipo": "credito" if float(t.amount) > 0 else "debito",
                "documento": t.id,
                "identificador": hash_key,
            }

            # INSERT OR IGNORE (dedup por identificador único)
            try:
                db_session.execute(
                    """INSERT INTO transacoes_bancarias
                       (extrato_id, data_transacao, historico, valor, tipo, documento, identificador)
                       VALUES (%(extrato_id)s, %(data_transacao)s, %(historico)s, %(valor)s,
                               %(tipo)s, %(documento)s, %(identificador)s)
                       ON CONFLICT (identificador) DO NOTHING""",
                    trans
                )
                transacoes_inseridas += 1
            except Exception:
                transacoes_duplicadas += 1

    db_session.commit()
    return {"inseridas": transacoes_inseridas, "duplicadas": transacoes_duplicadas}
```

### 4.2 Importador XML NF-e

```python
# importadores/nfe_xml_importer.py
import xml.etree.ElementTree as ET
from datetime import datetime
import re

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

def parse_nfe_xml(xml_path: str) -> dict:
    """Extrai dados de NF-e (XML padrão SEFAZ)"""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    inf = root.find(".//nfe:infNFe", NS)
    emit = root.find(".//nfe:emit", NS)
    dest = root.find(".//nfe:dest", NS)
    total = root.find(".//nfe:ICMSTot", NS)
    ide = root.find(".//nfe:ide", NS)

    chave = inf.get("Id", "").replace("NFe", "") if inf is not None else ""

    return {
        "chave_acesso": chave,
        "numero_nota": _text(ide, "nNF"),
        "serie": _text(ide, "serie"),
        "data_emissao": datetime.fromisoformat(_text(ide, "dhEmi", "")[:10]).date() if _text(ide, "dhEmi") else None,
        "tomador_cnpj": re.sub(r'\D', '', _text(dest, "CNPJ") or _text(dest, "CPF") or ""),
        "tomador_nome": _text(dest, "xNome"),
        "valor_bruto": float(_text(total, "vNF") or 0),
        "valor_liquido": float(_text(total, "vNF") or 0) - float(_text(total, "vDesc") or 0),
        "valor_impostos": sum(float(_text(total, k) or 0) for k in ["vICMS", "vPIS", "vCOFINS"]),
        "descricao_servicos": "; ".join([
            _text(det, "xProd")
            for det in root.findall(".//nfe:det/nfe:prod", NS)
        ])[:500],
        "arquivo_tipo": "xml",
    }

def _text(element, tag, default=""):
    if element is None: return default
    found = element.find(f"nfe:{tag}", NS)
    return found.text if found is not None else default
```

### 4.3 Importador CSV/Excel

```python
# importadores/csv_importer.py
import pandas as pd
from datetime import datetime

COLUNA_MAP = {
    # Mapeamento de nomes alternativos de colunas
    "data": ["data", "data_transacao", "dt_trans", "data_lancamento"],
    "historico": ["historico", "descricao", "memo", "obs", "historico_lancamento"],
    "valor": ["valor", "value", "vl", "montante"],
    "tipo": ["tipo", "type", "natureza", "dc"],
    "saldo": ["saldo", "balance", "saldo_atual"],
}

def import_extrato_csv(file_path: str, extrato_id: int, db_session) -> dict:
    """Importa extrato CSV/Excel com normalização automática de colunas"""
    if file_path.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path, sep=None, engine="python")

    # Normalizar nomes de colunas
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]

    def find_col(candidates):
        for c in candidates:
            if c in df.columns: return c
        return None

    col_data = find_col(COLUNA_MAP["data"])
    col_hist = find_col(COLUNA_MAP["historico"])
    col_valor = find_col(COLUNA_MAP["valor"])
    col_tipo = find_col(COLUNA_MAP["tipo"])

    if not all([col_data, col_hist, col_valor]):
        raise ValueError(f"Colunas obrigatórias não encontradas. Disponíveis: {list(df.columns)}")

    inseridas = 0
    for _, row in df.iterrows():
        valor_raw = float(str(row[col_valor]).replace(",", ".").replace("R$", "").strip())
        tipo = "credito" if valor_raw > 0 else "debito"
        if col_tipo and str(row[col_tipo]).upper() in ["D", "DEB", "DEBITO"]:
            tipo = "debito"

        import hashlib
        hash_key = hashlib.md5(
            f"{row[col_data]}{abs(valor_raw)}{row[col_hist]}".encode()
        ).hexdigest()

        db_session.execute(
            """INSERT INTO transacoes_bancarias
               (extrato_id, data_transacao, historico, valor, tipo, identificador)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (identificador) DO NOTHING""",
            (row[col_data], abs(valor_raw), str(row[col_hist]), abs(valor_raw), tipo, hash_key)
        )
        inseridas += 1

    db_session.commit()
    return {"inseridas": inseridas}
```

---

## 5. Status das Notas Fiscais

```python
STATUS_NOTAS = {
    "a_faturar":              "AF/empenho emitido, NF ainda não gerada",
    "nota_emitida":           "NF emitida, aguardando envio ao órgão",
    "aguardando_pagamento":   "NF enviada, dentro do prazo contratual",
    "conciliada":             "Pagamento localizado e confirmado",
    "parcialmente_paga":      "Pagamentos parciais identificados",
    "paga_com_retencao":      "Pago com retenção tributária (ISS, IR, etc.)",
    "divergente":             "Valor recebido não corresponde à NF",
    "vencida":                "Prazo de pagamento vencido sem pagamento",
    "sem_pagamento":          "Nenhum pagamento localizado no extrato",
    "pagamento_sem_nf":       "Crédito bancário sem NF correspondente",
    "cancelada":              "NF cancelada"
}
```

---

## 6. Endpoints FastAPI — Estrutura

```python
# backend/app/main.py (routers registrados)
from fastapi import FastAPI
from routers import (
    contratos, notas_fiscais, extratos,
    conciliacao, relatorios, dashboard, alertas
)

app = FastAPI(title="S2 Financial — Conciliação Licitações")

app.include_router(contratos.router,      prefix="/api/contratos",     tags=["Contratos"])
app.include_router(notas_fiscais.router,  prefix="/api/notas",         tags=["Notas Fiscais"])
app.include_router(extratos.router,       prefix="/api/extratos",      tags=["Extratos"])
app.include_router(conciliacao.router,    prefix="/api/conciliacao",   tags=["Conciliação"])
app.include_router(relatorios.router,     prefix="/api/relatorios",    tags=["Relatórios"])
app.include_router(dashboard.router,      prefix="/api/dashboard",     tags=["Dashboard"])

# Endpoints críticos:
# POST /api/extratos/import-ofx          → importar OFX
# POST /api/extratos/import-csv          → importar CSV/Excel
# POST /api/notas/import-xml             → importar XML NF-e
# POST /api/notas/import-lote            → importar planilha de notas
# POST /api/conciliacao/executar/{nota_id} → executar motor para uma nota
# POST /api/conciliacao/executar-lote    → executar motor para todas pendentes
# POST /api/conciliacao/confirmar/{id}   → confirmar conciliação manualmente
# GET  /api/dashboard/resumo            → KPIs consolidados
# GET  /api/relatorios/pendentes        → notas sem pagamento
# GET  /api/relatorios/divergencias     → todas divergências abertas
```

---

## 7. Dashboard — KPIs Calculados

```python
# routers/dashboard.py
async def get_dashboard_summary(db):
    return {
        "total_faturado": await db.scalar("SELECT SUM(valor_bruto) FROM notas_fiscais WHERE status != 'cancelada'"),
        "total_recebido": await db.scalar("SELECT SUM(valor_bruto) FROM notas_fiscais WHERE status = 'conciliada'"),
        "total_pendente": await db.scalar("SELECT SUM(valor_bruto) FROM notas_fiscais WHERE status IN ('aguardando_pagamento','nota_emitida')"),
        "total_vencido":  await db.scalar("SELECT SUM(valor_bruto) FROM notas_fiscais WHERE status = 'vencida'"),
        "total_divergente": await db.scalar("SELECT SUM(valor_bruto) FROM notas_fiscais WHERE status = 'divergente'"),
        "notas_sem_pagamento": await db.scalar("SELECT COUNT(*) FROM notas_fiscais WHERE status = 'sem_pagamento'"),
        "pagamentos_nao_identificados": await db.scalar("SELECT COUNT(*) FROM transacoes_bancarias WHERE tipo='credito' AND status_conciliacao='nao_conciliado'"),
        "por_orgao": await db.fetch("SELECT o.nome, SUM(n.valor_bruto) as total, COUNT(*) as notas FROM notas_fiscais n JOIN orgaos_publicos o ON n.orgao_id = o.id GROUP BY o.nome ORDER BY total DESC"),
        "por_contrato": await db.fetch("SELECT c.numero_contrato, SUM(n.valor_bruto), SUM(n.valor_liquido) FROM notas_fiscais n JOIN contratos c ON n.contrato_id = c.id GROUP BY c.numero_contrato"),
    }
```

---

## 8. Alertas Automáticos

```python
ALERTAS = [
    {"tipo": "nf_vencida",         "query": "status='aguardando_pagamento' AND data_prevista_pagamento < CURRENT_DATE"},
    {"tipo": "af_sem_nota",        "query": "af: status='pendente' AND data_emissao < CURRENT_DATE - 7"},
    {"tipo": "contrato_vencendo",  "query": "data_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + 30"},
    {"tipo": "saldo_baixo",        "query": "saldo_contratado < valor_total * 0.1"},
    {"tipo": "pagamento_duplicado","query": "GROUP BY nota_id HAVING COUNT(*) > 1 AND tipo='exata'"},
    {"tipo": "credito_sem_nf",     "query": "tipo='credito' AND status_conciliacao='nao_conciliado' AND data_transacao < CURRENT_DATE - 5"},
]
```

---

## 9. Regra de Cruzamento (Operação Padrão)

```
Para cada nota fiscal:
  1. Buscar créditos no extrato com o mesmo valor ± janela 30 dias
  2. Se valor idêntico: verificar histórico (CNPJ, NF, AF, empenho, contrato)
     → Score ≥ 95: CONCILIADA automaticamente
     → Score 70-94: PROVÁVEL — exige confirmação humana
  3. Se valor menor: calcular diferença → verificar se é retenção tributária conhecida
     → Diferença ≤ 15% e plausível: PAGA COM RETENÇÃO — exige confirmação
  4. Se múltiplos créditos menores somam o valor: PARCIALMENTE PAGA — exige confirmação
  5. Se nenhum pagamento encontrado:
     → Prazo vencido: VENCIDA
     → Dentro do prazo: SEM PAGAMENTO LOCALIZADO
  6. Crédito sem NF: PAGAMENTO NÃO IDENTIFICADO — exige investigação
  7. NUNCA dar baixa automática em casos prováveis, parciais ou divergentes
  8. Log de auditoria em toda ação (automática ou manual)
```

---

## 10. Fases de Implementação

```
FASE 1 — MVP CONCILIAÇÃO SIMPLES (2 semanas):
  ✅ Banco de dados completo
  ✅ Importador OFX + CSV + XML NF-e
  ✅ Motor de conciliação (5 níveis)
  ✅ Dashboard básico (KPIs)
  ✅ Tela de revisão manual

FASE 2 — CONTRATOS E VÍNCULOS (1 semana):
  ✅ Cadastro de contratos, AFs, empenhos
  ✅ Vínculo nota ↔ AF ↔ contrato ↔ órgão
  ✅ Saldo contratual

FASE 3 — RELATÓRIOS GERENCIAIS (1 semana):
  ✅ Notas pagas / pendentes / vencidas
  ✅ Fluxo de caixa por contrato
  ✅ Lucro/prejuízo por contrato
  ✅ Divergências em aberto
  ✅ Exportação Excel/PDF

FASE 4 — IA E AUTOMAÇÕES (quando o volume justificar):
  ✅ Leitura inteligente de históricos bancários
  ✅ Sugestão de vínculo órgão público por nome similar
  ✅ Classificação automática de lançamentos
  ✅ Alertas preditivos
```

---

## 11. Variáveis de Ambiente

```env
DATABASE_URL=postgresql://s2user:SENHA@localhost:5432/s2_financeiro
SECRET_KEY=CHAVE_JWT_32_CHARS
S2_CNPJ=32491468000112
S2_BANCO=Banco do Brasil
S2_AGENCIA=750-1
S2_CONTA=126941-0
JANELA_PAGAMENTO_DIAS=30
SCORE_MINIMO_AUTO_CONCILIACAO=95
```
