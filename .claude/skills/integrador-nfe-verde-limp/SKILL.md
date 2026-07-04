---
name: integrador-nfe-verde-limp
description: >
  Automatiza emissão e gestão de NFS-e (Nota Fiscal de Serviços Eletrônica) e NF-e para a Verde Limp Serviços e Terceirização Ltda. Use SEMPRE que precisar implementar, configurar ou corrigir faturamento eletrônico da Verde Limp: emissão automática de NFS-e por competência, integração com prefeitura de Betim/MG (ISS), cálculo automático de tributos (ISS, PIS, COFINS, CSLL, IRPJ no regime Simples Nacional), geração de DANF-e, controle de notas emitidas e cancelamentos. Cobre APIs de NFS-e (Focus NFe, SIEG, eNotas) e integração direta com o sistema-gestao-operacional-vl. Acionado por: "nota fiscal verde limp", "NFS-e verde limp", "emitir nota serviço", "NF-e terceirização", "faturamento automático vl", "integrar nota fiscal", "ISS verde limp", "emissão NFS-e Betim", "Focus NFe", "eNotas API".
---

# Integrador NFS-e / NF-e — Verde Limp

## Contexto Fiscal

```
EMPRESA: Verde Limp Serviços e Terceirização Ltda | CNPJ: 30.198.776/0001-29
SEDE: Betim/MG → NFS-e via Prefeitura de Betim (Sistema ISS.NET ou equivalente)
REGIME: Simples Nacional (verificar faixa e alíquota vigente)
TIPO NF: NFS-e (Serviços) — CNAE 8130-3/00 (atividades paisagísticas) e 8121-4/00 (limpeza)
TRIBUTO: ISS (municipal) — retido na fonte quando tomador obrigado a reter
```

---

## 1. Opções de Integração NFS-e

| Provedor | Custo | API | Prefeituras BR | Indicado para |
|----------|-------|-----|----------------|---------------|
| **Focus NFe** | A partir de R$29/mês | REST simples | 4.000+ | MVP Verde Limp |
| **eNotas** | A partir de R$49/mês | REST | 5.000+ | Escala maior |
| **SIEG** | A partir de R$39/mês | REST | 3.500+ | Alternativa |
| **Direta Prefeitura** | Gratuito | Variada | Betim específico | Sem custo |

**Recomendação MVP:** Focus NFe (documentação clara, suporte NFS-e Betim/MG, plano básico suficiente)

---

## 2. Focus NFe — Implementação

```python
# nfe/focus_nfe_client.py
import httpx
import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)

FOCUS_BASE = "https://homologacao.focusnfe.com.br/v2"  # usar api.focusnfe.com.br em produção
FOCUS_TOKEN = os.getenv("FOCUS_NFE_TOKEN")

class FocusNFeClient:
    def __init__(self, sandbox: bool = True):
        self.base = "https://homologacao.focusnfe.com.br/v2" if sandbox else "https://api.focusnfe.com.br/v2"
        self.auth = (FOCUS_TOKEN, "")

    async def emit_nfse(self, ref: str, data: dict) -> dict:
        """Emite NFS-e"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base}/nfse?ref={ref}",
                json=data,
                auth=self.auth,
                timeout=30
            )
            return {"status_code": response.status_code, "data": response.json()}

    async def get_nfse_status(self, ref: str) -> dict:
        """Consulta status da NFS-e"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base}/nfse/{ref}",
                auth=self.auth,
                timeout=15
            )
            return response.json()

    async def cancel_nfse(self, ref: str, reason: str) -> dict:
        """Cancela NFS-e"""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base}/nfse/{ref}",
                json={"justificativa": reason},
                auth=self.auth,
                timeout=15
            )
            return response.json()
```

---

## 3. Payload NFS-e Padrão (Verde Limp)

```python
# nfe/nfse_builder.py
from datetime import date
import os

VERDE_LIMP_DATA = {
    "cnpj_prestador": "30198776000129",
    "razao_social_prestador": "Verde Limp Servicos e Terceirizacao Ltda",
    "inscricao_municipal_prestador": os.getenv("VL_INSCRICAO_MUNICIPAL", ""),
    "codigo_municipio_prestador": "3106200",  # Betim/MG (IBGE)
    "optante_simples_nacional": True,
}

# CNAEs Verde Limp
CNAE_MAP = {
    "rocada": "8130300",       # Atividades paisagísticas
    "jardinagem": "8130300",
    "limpeza": "8121400",      # Limpeza em prédios e em domicílios
    "sinalizacao": "4330499",  # Outros serviços especializados p/ construção
    "retroescavadeira": "4313400",  # Obras de terraplenagem
    "conservacao": "8130300",
    "facility": "8130300",
}

def build_nfse_payload(
    tomador_cnpj: str,
    tomador_razao_social: str,
    tomador_email: str,
    tomador_endereco: dict,
    servico_descricao: str,
    valor_servico: float,
    servico_tipo: str,
    competencia: str,  # YYYY-MM
    os_number: str = ""
) -> dict:
    """Monta payload NFS-e padrão para Verde Limp"""
    ano, mes = competencia.split("-")
    data_competencia = f"{ano}-{mes}-01"
    cnae = CNAE_MAP.get(servico_tipo, "8130300")

    # Alíquota ISS Betim/MG — verificar tabela municipal vigente
    # Simples Nacional: ISS já incluso na alíquota do DAS
    aliquota_iss = 0.02  # 2% para serviços de conservação/limpeza em Betim

    return {
        "prestador": {**VERDE_LIMP_DATA},
        "tomador": {
            "cnpj": tomador_cnpj.replace(".", "").replace("/", "").replace("-", ""),
            "razao_social": tomador_razao_social,
            "email": tomador_email,
            "endereco": tomador_endereco
        },
        "servico": {
            "valor_servico": round(valor_servico, 2),
            "iss_retido": False,  # ajustar conforme contrato
            "valor_iss": round(valor_servico * aliquota_iss, 2),
            "aliquota": aliquota_iss,
            "discriminacao": f"{servico_descricao}\nReferência: {competencia}" + (f" | OS: {os_number}" if os_number else ""),
            "codigo_municipio": "3106200",  # Betim/MG
            "codigo_cnae": cnae,
            "item_lista_servico": "7.10",  # Limpeza e dragagem
        },
        "data_competencia": data_competencia,
        "natureza_operacao": 1  # Tributação no município
    }
```

---

## 4. Job de Faturamento Mensal Automático

```python
# nfe/monthly_billing_job.py
from datetime import datetime, date
import calendar

async def run_monthly_billing(db, year: int, month: int, sandbox: bool = True):
    """
    Job mensal: para cada contrato ativo, emite NFS-e se não emitida.
    Roda no dia 1 de cada mês às 9h.
    """
    focus = FocusNFeClient(sandbox=sandbox)
    competence = f"{year}-{month:02d}"

    # Buscar contratos ativos com faturamento pendente
    contracts = db.execute("""
        SELECT c.*, b.id as billing_id, b.value
        FROM contracts c
        LEFT JOIN billing b ON b.contract_id = c.id AND b.competence = ?
        WHERE c.status = 'ativo' AND (b.nfse_number IS NULL OR b.id IS NULL)
    """, (competence,)).fetchall()

    results = []
    for contract in contracts:
        ref = f"VL-{competence}-{contract['id']:04d}"

        # Criar billing se não existir
        if not contract['billing_id']:
            db.execute(
                "INSERT INTO billing (contract_id, competence, value, payment_status) VALUES (?,?,?,?)",
                (contract['id'], competence, contract['monthly_value'], 'pendente')
            )
            db.commit()

        payload = build_nfse_payload(
            tomador_cnpj=contract['client_cnpj'],
            tomador_razao_social=contract['client_name'],
            tomador_email=contract.get('client_email', ''),
            tomador_endereco={},
            servico_descricao=f"Serviços de {contract['service_type']} — {competence}",
            valor_servico=contract['monthly_value'],
            servico_tipo=contract['service_type'],
            competencia=competence
        )

        result = await focus.emit_nfse(ref, payload)
        if result['status_code'] in [200, 201]:
            nfse_data = result['data']
            db.execute(
                "UPDATE billing SET nfse_number=?, nfse_date=?, payment_status='faturado' WHERE contract_id=? AND competence=?",
                (nfse_data.get('numero_nfse'), date.today().isoformat(), contract['id'], competence)
            )
            db.commit()
            results.append({"contract_id": contract['id'], "status": "emitida", "ref": ref})
        else:
            results.append({"contract_id": contract['id'], "status": "erro", "error": result['data']})

    return results
```

---

## 5. Tabela nfse_logs

```sql
CREATE TABLE IF NOT EXISTS nfse_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    billing_id INTEGER REFERENCES billing(id),
    ref TEXT,
    focus_ref TEXT,
    nfse_number TEXT,
    payload TEXT,  -- JSON
    response TEXT, -- JSON
    status TEXT,   -- emitida, erro, cancelada
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. Variáveis de Ambiente

```env
FOCUS_NFE_TOKEN=SEU_TOKEN_FOCUS
VL_INSCRICAO_MUNICIPAL=NUMERO_IM_BETIM
NFSE_SANDBOX=true  # false em produção
```

---

## 7. Alerta de Compliance Fiscal

- ISS Betim/MG: verificar alíquota vigente no SMALP/Betim antes de emitir
- Simples Nacional: ISS incluso no DAS — NFS-e emitida com iss_retido=False salvo contrato com retenção
- ISSQN retido na fonte: tomador com faturamento > R$ 3,6M/ano geralmente obrigado a reter
- Manter todas as NFS-e emitidas por 5 anos (obrigação fiscal)
- Backup mensal das NFS-e em PDF no cofre documental
