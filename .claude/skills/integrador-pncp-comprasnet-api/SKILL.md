---
name: integrador-pncp-comprasnet-api
description: >
  Implementa integração direta com as APIs públicas do PNCP (Portal Nacional de Contratações Públicas) e ComprasGov para o sistema-s2 e S2 Estratégia. Use SEMPRE que precisar consumir APIs de licitações públicas: buscar contratações, consultar editais, obter documentos, baixar termos de referência, monitorar abertura de sessões, verificar resultado de disputa. PNCP e ComprasGov possuem APIs REST públicas e documentadas — nunca usar scraping HTML quando API disponível. Cobre também: paginação automática, cache de respostas, tratamento de erros de API, normalização de dados. Acionado por: "PNCP API", "ComprasGov API", "buscar edital API", "consultar licitação API", "integração PNCP sistema-s2", "API pública licitações", "PNCP endpoint", "documentos edital API", "resultado disputa API", "CAGEF API MG".
---

# Integrador PNCP / ComprasGov — APIs Públicas

## Endpoints PNCP Documentados

```
BASE: https://pncp.gov.br/api/consulta/v1

CONTRATAÇÕES:
  GET /contratacoes/publicacao           — busca por data publicação
  GET /contratacoes/{ano}/{seq}          — detalhes de contratação
  GET /contratacoes/{ano}/{seq}/itens    — itens da contratação
  GET /contratacoes/{ano}/{seq}/arquivos — documentos (edital, TR, etc.)

ÓRGÃOS:
  GET /orgaos                            — lista órgãos cadastrados
  GET /orgaos/{cnpj}                     — dados do órgão

ATAS:
  GET /atas/publicacao                   — atas de registro de preço
```

---

## 1. Client PNCP Completo

```python
# integrations/pncp_client.py
import httpx
import asyncio
from datetime import date, timedelta
from typing import Optional, AsyncGenerator
import logging
import json

logger = logging.getLogger(__name__)
PNCP_BASE = "https://pncp.gov.br/api/consulta/v1"
DEFAULT_PAGE_SIZE = 50
MAX_RETRIES = 3

class PNCPClient:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def _get(self, path: str, params: dict = None, retries: int = 0) -> Optional[dict]:
        url = f"{PNCP_BASE}{path}"
        try:
            response = await self._client.get(url, params=params or {})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and retries < MAX_RETRIES:  # Rate limit
                await asyncio.sleep(2 ** retries)
                return await self._get(path, params, retries + 1)
            logger.error(f"PNCP HTTP error {e.response.status_code}: {path}")
            return None
        except httpx.RequestError as e:
            if retries < MAX_RETRIES:
                await asyncio.sleep(1)
                return await self._get(path, params, retries + 1)
            logger.error(f"PNCP request error: {e}")
            return None

    async def search_contratacoes(
        self,
        data_inicial: str,
        data_final: str,
        uf: str = None,
        page_size: int = DEFAULT_PAGE_SIZE
    ) -> AsyncGenerator[dict, None]:
        """Itera todas as páginas de contratações no período"""
        params = {"dataInicial": data_inicial, "dataFinal": data_final, "tamanhoPagina": page_size}
        if uf:
            params["uf"] = uf

        page = 1
        while True:
            params["pagina"] = page
            data = await self._get("/contratacoes/publicacao", params)
            if not data:
                break
            items = data.get("data", [])
            if not items:
                break
            for item in items:
                yield item
            total_pages = data.get("totalPaginas", 1)
            if page >= total_pages:
                break
            page += 1
            await asyncio.sleep(0.2)  # Rate limiting cortesia

    async def get_contratacao_detail(self, ano: int, seq: int) -> Optional[dict]:
        return await self._get(f"/contratacoes/{ano}/{seq}")

    async def get_contratacao_items(self, ano: int, seq: int) -> list[dict]:
        data = await self._get(f"/contratacoes/{ano}/{seq}/itens")
        return data.get("data", []) if data else []

    async def get_contratacao_documents(self, ano: int, seq: int) -> list[dict]:
        data = await self._get(f"/contratacoes/{ano}/{seq}/arquivos")
        return data if isinstance(data, list) else []

    async def download_document(self, url: str, dest_path: str) -> bool:
        try:
            async with self._client.stream("GET", url) as response:
                response.raise_for_status()
                with open(dest_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Document download error: {e}")
            return False

    async def close(self):
        await self._client.aclose()


# Funções utilitárias de alto nível
pncp = PNCPClient()

async def fetch_editais_today(keywords: list[str] = None) -> list[dict]:
    """Busca editais do dia atual com filtro opcional por keyword"""
    today = date.today().strftime("%Y-%m-%d")
    results = []
    async for item in pncp.search_contratacoes(today, today):
        if keywords:
            objeto = item.get("objetoCompra", "").lower()
            if not any(kw.lower() in objeto for kw in keywords):
                continue
        results.append(item)
    return results

def normalize_contratacao(raw: dict) -> dict:
    """Normaliza campos do PNCP para formato interno sistema-s2"""
    return {
        "pncp_id": raw.get("numeroControlePNCP"),
        "ano": raw.get("anoContratacao"),
        "seq": raw.get("sequencialContratacao"),
        "orgao_cnpj": raw.get("orgaoEntidade", {}).get("cnpj"),
        "orgao_nome": raw.get("orgaoEntidade", {}).get("razaoSocial"),
        "uf": raw.get("unidadeOrgao", {}).get("ufSigla"),
        "municipio": raw.get("unidadeOrgao", {}).get("municipioNome"),
        "objeto": raw.get("objetoCompra"),
        "modalidade": raw.get("modalidadeNome"),
        "modo_disputa": raw.get("modoDisputaNome"),
        "valor_estimado": raw.get("valorTotalEstimado"),
        "data_publicacao": raw.get("dataPublicacaoPncp"),
        "data_abertura": raw.get("dataAberturaProposta"),
        "data_encerramento": raw.get("dataEncerramentoProposta"),
        "link_sistema_origem": raw.get("linkSistemaOrigem"),
        "link_pncp": f"https://pncp.gov.br/app/editais/{raw.get('numeroControlePNCP')}",
        "srp": raw.get("srp"),  # Sistema de Registro de Preços
        "lei_aplicavel": "14133/21" if raw.get("anoContratacao", 0) >= 2023 else "verificar"
    }
```

---

## 2. Endpoint sistema-s2 para sincronização

```typescript
// src/routers/pncp.ts
import { Router } from "express"
import { requireAuth } from "../middleware/auth"

const router = Router()

router.post("/sync-today", requireAuth, async (req, res) => {
  try {
    // Chama script Python via child_process ou via API interna
    const { exec } = require("child_process")
    exec("python3 scripts/radar_pncp.py --days=1", (error, stdout) => {
      if (error) return res.status(500).json({ error: error.message })
      const result = JSON.parse(stdout)
      res.json({ synced: result.count, editais: result.items })
    })
  } catch (err) {
    res.status(500).json({ error: "Sync failed" })
  }
})

router.get("/editais", requireAuth, async (req, res) => {
  const { page = 1, pageSize = 20, status, search } = req.query
  // Query local da tabela editais_radar já populada pelo radar
  const { pool } = require("../db/connection")
  let where = "WHERE 1=1"
  const params: unknown[] = []
  if (status) { params.push(status); where += ` AND status = $${params.length}` }
  if (search) { params.push(`%${search}%`); where += ` AND objeto ILIKE $${params.length}` }
  const count = await pool.query(`SELECT COUNT(*) FROM editais_radar ${where}`, params)
  const offset = (Number(page) - 1) * Number(pageSize)
  params.push(Number(pageSize), offset)
  const rows = await pool.query(
    `SELECT * FROM editais_radar ${where} ORDER BY data_publicacao DESC LIMIT $${params.length-1} OFFSET $${params.length}`,
    params
  )
  res.json({ data: rows.rows, total: parseInt(count.rows[0].count), page: Number(page), pageSize: Number(pageSize) })
})

export default router
```

---

## 3. Schema editais_radar

```sql
CREATE TABLE IF NOT EXISTS editais_radar (
  id SERIAL PRIMARY KEY,
  pncp_id TEXT UNIQUE NOT NULL,
  ano INTEGER,
  seq INTEGER,
  orgao_cnpj TEXT,
  orgao_nome TEXT,
  uf TEXT,
  municipio TEXT,
  objeto TEXT,
  modalidade TEXT,
  modo_disputa TEXT,
  valor_estimado NUMERIC(15,2),
  data_publicacao DATE,
  data_abertura TIMESTAMP,
  data_encerramento TIMESTAMP,
  link_pncp TEXT,
  link_sistema_origem TEXT,
  srp BOOLEAN,
  lei_aplicavel TEXT,
  segmentos TEXT[],              -- {veterinario, ambiental, consultoria}
  status TEXT DEFAULT 'novo',   -- novo, analisando, participando, descartado, ganho, perdido
  go_nogo TEXT,
  viabilidade_score INTEGER,    -- 0-100
  notes TEXT,
  assigned_to INTEGER,          -- user_id responsável
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_editais_status ON editais_radar(status);
CREATE INDEX idx_editais_data ON editais_radar(data_publicacao DESC);
CREATE INDEX idx_editais_uf ON editais_radar(uf);
```
