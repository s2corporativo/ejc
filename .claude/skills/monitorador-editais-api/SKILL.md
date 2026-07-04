---
name: monitorador-editais-api
description: >
  Implementa radar automatizado de editais públicos via PNCP API, ComprasGov e CAGEF/MG para a S2 Estratégia & Negócios Ltda. Use SEMPRE que precisar construir, configurar ou corrigir qualquer componente de monitoramento automático de licitações: scraping de portais, integração com API PNCP, alertas de novos editais, filtros por objeto/órgão/valor, notificações por WhatsApp/email, integração com sistema-s2. Cobre código Python e JavaScript/TypeScript para consumo de APIs públicas de licitação. PNCP tem API pública documentada — nunca raspagem de HTML quando API disponível. Acionado por: "radar automático editais", "monitorar editais", "alerta novo edital", "PNCP API", "ComprasGov API", "scraping licitações", "integração PNCP", "monitoramento automático S2", "radar S2", "alerta licitação".
---

# Monitorador Automático de Editais — API PNCP e ComprasGov

## Contexto

```
EMPRESA: S2 Estratégia & Negócios Ltda
OBJETIVO: radar diário automatizado de editais relevantes
PORTAIS PRIORITÁRIOS: PNCP (API pública) > ComprasGov > CAGEF/MG
SEGMENTOS: veterinários | auditoria ambiental/TCFA | consultoria jurídica | serviços conservação (Verde Limp)
DESTINO: alertas WhatsApp/email + integração sistema-s2
```

---

## 1. PNCP — API Pública Oficial

### Endpoints Relevantes

```
BASE URL: https://pncp.gov.br/api/consulta/v1

# Buscar contratações por data de publicação
GET /contratacoes/publicacao
  Params:
    dataInicial: YYYY-MM-DD
    dataFinal:   YYYY-MM-DD
    pagina:      int (default 1)
    tamanhoPagina: int (default 10, max 50)
    uf:          MG (filtro por estado)
    codigoUnidadeAdministrativa: (opcional, filtrar por UG)

# Detalhes de uma contratação
GET /contratacoes/{anoContratacao}/{sequencialContratacao}

# Itens de uma contratação
GET /contratacoes/{anoContratacao}/{sequencialContratacao}/itens

# Documentos de uma contratação
GET /contratacoes/{anoContratacao}/{sequencialContratacao}/arquivos
```

### Implementação Python — Radar PNCP

```python
# radar_pncp.py
import httpx
import asyncio
import json
from datetime import date, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

PNCP_BASE = "https://pncp.gov.br/api/consulta/v1"

# Palavras-chave por segmento S2
KEYWORDS = {
    "veterinario": ["veterinário", "medicamento veterinário", "animal", "ração", "vacina animal"],
    "ambiental": ["ambiental", "TCFA", "licenciamento", "EIA", "RIMA", "flora", "fauna"],
    "consultoria": ["consultoria jurídica", "assessoria licitação", "consultoria administrativa"],
    "conservacao": ["roçada", "jardinagem", "conservação", "limpeza", "manutenção áreas verdes"],
}

async def fetch_pncp_page(client: httpx.AsyncClient, data_inicial: str, data_final: str, pagina: int = 1) -> dict:
    url = f"{PNCP_BASE}/contratacoes/publicacao"
    params = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "pagina": pagina,
        "tamanhoPagina": 50
    }
    try:
        response = await client.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Erro PNCP página {pagina}: {e}")
        return {}

def matches_keywords(text: str) -> list[str]:
    """Retorna segmentos que coincidem com o objeto"""
    text_lower = text.lower()
    matched = []
    for segment, keywords in KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            matched.append(segment)
    return matched

def is_viable(item: dict) -> bool:
    """Filtros básicos de viabilidade"""
    # Modalidade compatível
    valid_modalities = ["Pregão Eletrônico", "Dispensa Eletrônica", "Credenciamento"]
    modality = item.get("modalidadeNome", "")
    if not any(m in modality for m in valid_modalities):
        return False
    # Prazo mínimo 3 dias úteis (simplificado)
    return True

async def run_radar(days_back: int = 1) -> list[dict]:
    """Executa o radar para os últimos N dias"""
    today = date.today()
    data_inicial = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")
    data_final = today.strftime("%Y-%m-%d")

    results = []
    async with httpx.AsyncClient() as client:
        # Primeira página para saber total
        first_page = await fetch_pncp_page(client, data_inicial, data_final, 1)
        total_pages = first_page.get("totalPaginas", 1)
        items = first_page.get("data", [])

        # Páginas adicionais
        if total_pages > 1:
            tasks = [fetch_pncp_page(client, data_inicial, data_final, p) for p in range(2, total_pages + 1)]
            pages = await asyncio.gather(*tasks)
            for page in pages:
                items.extend(page.get("data", []))

    # Filtrar editais relevantes
    for item in items:
        objeto = item.get("objetoCompra", "")
        matched = matches_keywords(objeto)
        if matched and is_viable(item):
            results.append({
                "pncp_id": item.get("numeroControlePNCP"),
                "orgao": item.get("orgaoEntidade", {}).get("razaoSocial", ""),
                "uf": item.get("unidadeOrgao", {}).get("ufSigla", ""),
                "objeto": objeto,
                "modalidade": item.get("modalidadeNome", ""),
                "valor_estimado": item.get("valorTotalEstimado"),
                "data_publicacao": item.get("dataPublicacaoPncp"),
                "data_abertura": item.get("dataAberturaProposta"),
                "link": f"https://pncp.gov.br/app/editais/{item.get('numeroControlePNCP')}",
                "segmentos": matched
            })
    return results

if __name__ == "__main__":
    editais = asyncio.run(run_radar(days_back=1))
    print(f"Encontrados {len(editais)} editais relevantes")
    for e in editais:
        print(f"[{', '.join(e['segmentos'])}] {e['orgao']} | {e['objeto'][:80]} | {e['link']}")
```

### Integração com Banco (sistema-s2 ou SQLite standalone)

```python
# radar_db.py
import sqlite3
from datetime import datetime

def save_radar_result(db_path: str, edital: dict):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT OR IGNORE INTO editais_radar
        (pncp_id, orgao, uf, objeto, modalidade, valor_estimado, data_publicacao, data_abertura, link, segmentos, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        edital['pncp_id'], edital['orgao'], edital['uf'], edital['objeto'],
        edital['modalidade'], edital['valor_estimado'], edital['data_publicacao'],
        edital['data_abertura'], edital['link'], ','.join(edital['segmentos']),
        'novo', datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

def create_radar_table(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS editais_radar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pncp_id TEXT UNIQUE,
            orgao TEXT,
            uf TEXT,
            objeto TEXT,
            modalidade TEXT,
            valor_estimado REAL,
            data_publicacao TEXT,
            data_abertura TEXT,
            link TEXT,
            segmentos TEXT,
            status TEXT DEFAULT 'novo', -- novo, analisando, participando, descartado
            go_nogo TEXT,
            notes TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
```

---

## 2. ComprasGov — Scraping Alternativo

```python
# comprasgov_scraper.py — usar quando PNCP não cobrir
import httpx
from bs4 import BeautifulSoup

# ComprasGov tem endpoint de consulta pública
COMPRASGOV_SEARCH = "https://www.gov.br/compras/pt-br/sistemas/pesquisa-pregao-eletronico"

def search_comprasgov(keyword: str, uasg: str = None) -> list[dict]:
    """Busca pregões no ComprasGov — fallback quando PNCP não disponível"""
    # Preferir sempre PNCP API — usar ComprasGov apenas para modalidades não cobertas
    params = {"keywords": keyword}
    if uasg:
        params["uasg"] = uasg
    # Implementação via requests/BeautifulSoup ou Selenium se necessário
    return []
```

---

## 3. Agendamento Automático

### Cron Job (Linux/VPS)

```bash
# /etc/cron.d/radar-editais
# Roda todo dia às 7h e 14h
0 7,14 * * * radar_user cd /opt/radar && python radar_pncp.py >> /var/log/radar.log 2>&1
```

### Via n8n (workflow)

```json
{
  "node": "Schedule Trigger",
  "parameters": {
    "rule": {"interval": [{"field": "hours", "hoursInterval": 6}]}
  },
  "next": "HTTP Request (PNCP API)",
  "then": "Filter relevant keywords",
  "then": "Save to DB",
  "then": "Send WhatsApp alert if new editais found"
}
```

---

## 4. Formato de Alerta

```
🔔 RADAR S2 — Novo Edital

📋 Objeto: Aquisição de medicamentos veterinários
🏛️ Órgão: Prefeitura Municipal de Betim/MG
💰 Valor estimado: R$ 85.000,00
📅 Abertura: 28/05/2026 às 10:00
🔗 Link: https://pncp.gov.br/app/editais/...

Segmento: VETERINÁRIO
Status: NOVO — análise pendente

[ANALISAR] [DESCARTAR]
```

---

## 5. Regras de Filtragem GO/NO-GO

```python
def evaluate_go_nogo(edital: dict) -> str:
    """Avaliação automática GO/NO-GO"""
    reasons_nogo = []
    
    # Prazo mínimo (simplificado — data abertura vs hoje)
    from datetime import datetime, date
    if edital.get('data_abertura'):
        try:
            abertura = datetime.fromisoformat(edital['data_abertura']).date()
            days_left = (abertura - date.today()).days
            if days_left < 3:
                reasons_nogo.append(f"Prazo insuficiente: {days_left} dias")
        except:
            pass
    
    # Valor muito baixo
    valor = edital.get('valor_estimado') or 0
    if valor and valor < 5000:
        reasons_nogo.append(f"Valor baixo: R$ {valor:,.2f}")
    
    return "NO-GO" if reasons_nogo else "ANALISAR"
```
