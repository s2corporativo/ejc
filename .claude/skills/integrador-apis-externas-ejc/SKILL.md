---
name: integrador-apis-externas-ejc
description: >
  Implementa integrações do EJC com APIs externas: tribunais (TJMG, PJe, CNJ), validadores de CPF/CNPJ (ReceitaWS, CNPJ.ws), consulta de processos judiciais, busca de jurisprudência (JusBrasil API), notificações externas, e qualquer outra API pública relevante para escritório de advocacia brasileiro. Use SEMPRE que precisar conectar o EJC a um serviço externo. Cobre: consulta de movimentação processual automática, atualização de dados de processo vinculado ao caso, validação de CNPJ na criação de cliente PJ, busca de CEP (ViaCEP). Todas as integrações seguem padrão: async Python httpx, cache Redis opcional, retry automático, log de erros. Acionado por: "integrar EJC com TJMG", "consulta processo EJC", "busca CPF CNPJ", "integração PJe", "atualizar processo", "consulta CEP", "busca jurisprudência EJC", "API tribunal", "movimentação processo automática".
---

# Integrador de APIs Externas — EJC

## APIs Prioritárias

| API | Finalidade | Custo | URL |
|-----|-----------|-------|-----|
| TJMG Consulta Processual | Movimentações de processos | Gratuito | `sistemas.tjmg.jus.br` |
| CNJ DataJud | Consulta processos todos TJs | Gratuito (token) | `api-publica.datajud.cnj.jus.br` |
| CNPJ.ws | Dados de CNPJ | Gratuito | `publica.cnpj.ws/cnpj/` |
| ReceitaWS | CPF/CNPJ básico | Gratuito limitado | `www.receitaws.com.br/v1/` |
| ViaCEP | Consulta CEP | Gratuito | `viacep.com.br/ws/` |
| JusBrasil | Jurisprudência | Pago / API | `api.jusbrasil.com.br` |

---

## 1. CNJ DataJud — Consulta Processual

```python
# integrations/datajud.py
import httpx
import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)

DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"
# Token: solicitar em https://datajud-wiki.cnj.jus.br/api-publica/acesso
DATAJUD_TOKEN = os.getenv("DATAJUD_API_KEY")

# Mapeamento tribunal → índice Elastic DataJud
TRIBUNAL_INDEX = {
    "TJMG": "tjmg",
    "TJSP": "tjsp",
    "TST": "tst",
    "STJ": "stj",
    "STF": "stf",
    "TRT3": "trt3",  # MG
}

async def search_process(
    process_number: str,
    tribunal_code: str = "TJMG"
) -> Optional[dict]:
    """
    Consulta processo no DataJud CNJ.
    process_number: formato CNJ (NNNNNNN-DD.AAAA.J.TT.OOOO)
    """
    index = TRIBUNAL_INDEX.get(tribunal_code.upper(), tribunal_code.lower())
    url = f"{DATAJUD_BASE}/api_publica_{index}/_search"

    payload = {
        "query": {
            "match": {
                "numeroProcesso": process_number.replace("-", "").replace(".", "")
            }
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"APIKey {DATAJUD_TOKEN}",
                    "Content-Type": "application/json"
                },
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            hits = data.get("hits", {}).get("hits", [])
            return hits[0]["_source"] if hits else None
    except httpx.HTTPError as e:
        logger.error(f"DataJud error for {process_number}: {e}")
        return None

async def get_process_moves(process_number: str, tribunal: str = "TJMG") -> list[dict]:
    """Retorna movimentações do processo ordenadas por data"""
    result = await search_process(process_number, tribunal)
    if not result:
        return []
    moves = result.get("movimentos", [])
    return sorted(moves, key=lambda m: m.get("dataHora", ""), reverse=True)
```

### Endpoint EJC para sincronização

```python
# routers/tribunal.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from integrations.datajud import get_process_moves, search_process
from app.models.case import Case
from app.models.audit_log import create_audit_log

router = APIRouter(prefix="/cases", tags=["tribunal"])

@router.post("/{case_id}/sync-tribunal")
async def sync_case_with_tribunal(
    case_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    case = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    if not case.case_number:
        raise HTTPException(status_code=400, detail="Caso sem número de processo vinculado")

    background_tasks.add_task(_sync_tribunal_bg, case_id, case.case_number, db, current_user.id)
    return {"message": "Sincronização iniciada em background", "case_id": case_id}

async def _sync_tribunal_bg(case_id: int, process_number: str, db: Session, user_id: int):
    moves = await get_process_moves(process_number)
    # Salvar movimentações na tabela tribunal_moves
    for move in moves[:20]:  # últimas 20
        db.execute(
            "INSERT OR IGNORE INTO tribunal_moves (case_id, move_date, description, code) VALUES (?,?,?,?)",
            (case_id, move.get("dataHora"), move.get("nome"), move.get("codigo"))
        )
    db.commit()
    create_audit_log(db, user_id, "SYNC_TRIBUNAL", "cases", case_id)

@router.get("/{case_id}/tribunal-moves")
async def get_tribunal_moves(
    case_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    moves = db.execute(
        "SELECT * FROM tribunal_moves WHERE case_id = ? ORDER BY move_date DESC LIMIT 50",
        (case_id,)
    ).fetchall()
    return {"data": [dict(m) for m in moves], "total": len(moves)}
```

---

## 2. CNPJ.ws — Validação de CNPJ

```python
# integrations/cnpj.py
import httpx
from typing import Optional
import re

async def get_cnpj_data(cnpj: str) -> Optional[dict]:
    """Busca dados da empresa pelo CNPJ (gratuito, sem token)"""
    cnpj_clean = re.sub(r'\D', '', cnpj)
    if len(cnpj_clean) != 14:
        return None
    url = f"https://publica.cnpj.ws/cnpj/{cnpj_clean}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    "razao_social": data.get("razao_social"),
                    "nome_fantasia": data.get("estabelecimento", {}).get("nome_fantasia"),
                    "situacao": data.get("estabelecimento", {}).get("situacao_cadastral", {}).get("descricao"),
                    "atividade_principal": data.get("estabelecimento", {}).get("atividade_principal", {}).get("descricao"),
                    "logradouro": data.get("estabelecimento", {}).get("logradouro"),
                    "municipio": data.get("estabelecimento", {}).get("municipio", {}).get("descricao"),
                    "uf": data.get("estabelecimento", {}).get("estado", {}).get("sigla"),
                    "cep": data.get("estabelecimento", {}).get("cep"),
                    "email": data.get("estabelecimento", {}).get("email"),
                    "telefone": data.get("estabelecimento", {}).get("telefone1"),
                }
    except Exception:
        return None

# Uso no endpoint de criação de cliente PJ
# POST /api/v1/clients → se client_type == "PJ" → auto-preencher com CNPJ.ws
```

---

## 3. ViaCEP — Consulta de CEP

```python
# integrations/cep.py
import httpx
from typing import Optional

async def get_cep_data(cep: str) -> Optional[dict]:
    """Consulta endereço por CEP"""
    cep_clean = cep.replace("-", "").replace(" ", "")
    if len(cep_clean) != 8:
        return None
    url = f"https://viacep.com.br/ws/{cep_clean}/json/"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("erro"):
                    return None
                return {
                    "logradouro": data.get("logradouro"),
                    "bairro": data.get("bairro"),
                    "cidade": data.get("localidade"),
                    "uf": data.get("uf"),
                    "cep": cep_clean
                }
    except Exception:
        return None
```

---

## 4. Endpoint Unificado de Enriquecimento de Dados

```python
# routers/enrich.py — endpoints auxiliares para o frontend
from fastapi import APIRouter
from integrations.cnpj import get_cnpj_data
from integrations.cep import get_cep_data

router = APIRouter(prefix="/enrich", tags=["enrich"])

@router.get("/cnpj/{cnpj}")
async def enrich_cnpj(cnpj: str):
    data = await get_cnpj_data(cnpj)
    if not data:
        return {"error": "CNPJ não encontrado ou inválido"}
    return data

@router.get("/cep/{cep}")
async def enrich_cep(cep: str):
    data = await get_cep_data(cep)
    if not data:
        return {"error": "CEP não encontrado"}
    return data
```

---

## 5. Tabela tribunal_moves (Migration)

```sql
CREATE TABLE IF NOT EXISTS tribunal_moves (
    id INTEGER PRIMARY KEY,
    case_id INTEGER REFERENCES cases(id),
    move_date TEXT,
    description TEXT,
    code TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(case_id, move_date, code)
);
CREATE INDEX idx_tribunal_moves_case ON tribunal_moves(case_id);
```

---

## 6. Regras

- Cache de 1h para consultas CNPJ e CEP (Redis ou dict em memória)
- Retry automático: máximo 2 tentativas com backoff de 1s
- Timeout máximo: 15s por requisição externa
- Nunca bloquear fluxo principal por falha em API externa (usar background_tasks)
- Log de todas as consultas externas em tabela external_api_logs
- Mascarar CPF em logs (nunca logar completo)
