---
name: arquiteto-cuidar-vet-sistema
description: >
  Arquiteta e implementa automações técnicas para a Cuidar Vet (clínica veterinária + e-commerce Nuvemshop). Use SEMPRE que precisar construir integrações técnicas, automações ou sistemas digitais para a Cuidar Vet: integração com API Nuvemshop (estoque, pedidos, preços), sincronização do banco de 7.895 clientes com a loja, automação de pricing (cross-reference com fornecedores), relatórios de faturamento, painel de gestão da clínica, integração do Compêndio Vet com o e-commerce. Diferente de gestor-marketplace-seo-tecnico (que trata de SEO/anúncios): este skill trata de CÓDIGO e INTEGRAÇÃO TÉCNICA. Acionado por: "Nuvemshop API", "integrar Cuidar Vet", "automação e-commerce vet", "sistema clínica vet", "pricing automático", "sincronizar estoque", "relatório Cuidar Vet", "dashboard clínica", "ERP vet", "integração compêndio Nuvemshop", "automatizar Cuidar Vet".
---

# Arquiteto de Sistema — Cuidar Vet (Clínica + E-commerce)

## Contexto

```
EMPRESA: Cuidar Vet — clínica veterinária + e-commerce
PLATAFORMA: Nuvemshop (e-commerce principal)
BANCO CLIENTES: ~7.895 registros únicos (base consolidada)
PRODUTO DIGITAL: Compêndio Vet (banco de medicamentos — 27+ entradas)
STACK RECOMENDADA: Python scripts + Nuvemshop API + SQLite/PostgreSQL
PRINCÍPIO: soluções leves, custo zero ou mínimo, ROI imediato
```

---

## 1. Nuvemshop API — Fundamentos

```python
# nuvemshop/client.py
import httpx
import os
from typing import Optional

# Credenciais em: Painel Nuvemshop → Configurações → API → Criar app
NUVEMSHOP_USER_ID = os.getenv("NUVEMSHOP_USER_ID")
NUVEMSHOP_ACCESS_TOKEN = os.getenv("NUVEMSHOP_ACCESS_TOKEN")
NUVEMSHOP_BASE = f"https://api.nuvemshop.com.br/v1/{NUVEMSHOP_USER_ID}"

HEADERS = {
    "Authentication": f"bearer {NUVEMSHOP_ACCESS_TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "CuidarVet/1.0 (adm@vetmg.com.br)"
}

async def get_products(page: int = 1, per_page: int = 50) -> list[dict]:
    """Lista produtos da loja"""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{NUVEMSHOP_BASE}/products",
            headers=HEADERS,
            params={"page": page, "per_page": per_page}
        )
        r.raise_for_status()
        return r.json()

async def update_product_price(product_id: int, variant_id: int, price: float, compare_price: float = None) -> dict:
    """Atualiza preço de variante do produto"""
    payload = {"price": str(round(price, 2))}
    if compare_price:
        payload["compare_at_price"] = str(round(compare_price, 2))
    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{NUVEMSHOP_BASE}/products/{product_id}/variants/{variant_id}",
            headers=HEADERS, json=payload
        )
        return r.json()

async def update_stock(product_id: int, variant_id: int, quantity: int) -> dict:
    """Atualiza estoque de variante"""
    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{NUVEMSHOP_BASE}/products/{product_id}/variants/{variant_id}",
            headers=HEADERS, json={"stock": quantity}
        )
        return r.json()

async def get_orders(status: str = None, page: int = 1) -> list[dict]:
    """Lista pedidos com filtro opcional de status"""
    params = {"page": page, "per_page": 50}
    if status:
        params["status"] = status  # open, closed, cancelled
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{NUVEMSHOP_BASE}/orders", headers=HEADERS, params=params)
        return r.json()

async def create_customer(data: dict) -> dict:
    """Cria cliente na Nuvemshop"""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{NUVEMSHOP_BASE}/customers", headers=HEADERS, json=data
        )
        return r.json()
```

---

## 2. Cross-Reference de Preços (Automação de Pricing)

```python
# pricing/cross_reference.py
"""
Compara preço de custo (fornecedor) com preço de venda (Nuvemshop)
e sugere/aplica ajustes de margem.
"""
import sqlite3
from typing import list

MARGIN_TARGET = 0.35  # 35% de margem mínima
MARGIN_IDEAL = 0.50   # 50% margem ideal

def calculate_suggested_price(cost: float, margin: float = MARGIN_TARGET) -> float:
    """Preço sugerido dado custo e margem alvo"""
    return round(cost / (1 - margin), 2)

def check_margin(cost: float, sell_price: float) -> dict:
    """Verifica margem atual de um produto"""
    if sell_price <= 0:
        return {"margin": 0, "status": "sem_preco"}
    margin = (sell_price - cost) / sell_price
    return {
        "cost": cost,
        "sell_price": sell_price,
        "margin": round(margin * 100, 1),
        "status": "ok" if margin >= MARGIN_TARGET else "abaixo_meta",
        "suggested_price": calculate_suggested_price(cost, MARGIN_TARGET) if margin < MARGIN_TARGET else None
    }

def generate_pricing_report(db_path: str) -> list[dict]:
    """
    Gera relatório de produtos com margem abaixo da meta.
    Banco deve ter tabela: products (nuvemshop_id, name, cost_price, sell_price)
    """
    conn = sqlite3.connect(db_path)
    products = conn.execute(
        "SELECT nuvemshop_id, name, cost_price, sell_price FROM products WHERE cost_price > 0"
    ).fetchall()
    conn.close()
    
    alerts = []
    for prod in products:
        ns_id, name, cost, sell = prod
        analysis = check_margin(cost, sell)
        if analysis["status"] == "abaixo_meta":
            alerts.append({
                "nuvemshop_id": ns_id,
                "name": name,
                "current_margin": f"{analysis['margin']}%",
                "suggested_price": analysis["suggested_price"],
                "action": f"Aumentar de R${sell:.2f} para R${analysis['suggested_price']:.2f}"
            })
    
    return sorted(alerts, key=lambda x: float(x["current_margin"].replace("%","")))
```

---

## 3. Sincronização de Clientes (Base 7.895 → Nuvemshop)

```python
# sync/customer_sync.py
"""
Sincroniza base de clientes consolidada (7.895 registros) com Nuvemshop.
Estratégia: email como chave única — ignorar duplicatas.
"""
import sqlite3
import asyncio

async def sync_customers_batch(db_path: str, batch_size: int = 20):
    """
    Importa clientes da base local para a Nuvemshop em lotes.
    Respeita rate limit da API: 60 req/min por padrão.
    """
    conn = sqlite3.connect(db_path)
    
    # Buscar clientes não sincronizados com email válido
    customers = conn.execute("""
        SELECT id, nome, email, telefone, cep, cidade, uf
        FROM clientes
        WHERE email IS NOT NULL AND email != ''
        AND sincronizado_nuvemshop = 0
        ORDER BY id
        LIMIT ?
    """, (batch_size,)).fetchall()
    
    results = {"synced": 0, "errors": 0, "skipped": 0}
    
    for customer in customers:
        cid, nome, email, telefone, cep, cidade, uf = customer
        
        payload = {
            "name": nome,
            "email": email,
            "phone": telefone,
            "addresses": [{
                "zipcode": cep,
                "city": cidade,
                "province": uf,
                "country": "BR"
            }] if cep else []
        }
        
        try:
            result = await create_customer(payload)
            if result.get("id"):
                conn.execute(
                    "UPDATE clientes SET sincronizado_nuvemshop=1, nuvemshop_customer_id=? WHERE id=?",
                    (result["id"], cid)
                )
                results["synced"] += 1
            else:
                results["errors"] += 1
        except Exception as e:
            results["errors"] += 1
        
        await asyncio.sleep(1.1)  # Rate limit seguro (54 req/min)
    
    conn.commit()
    conn.close()
    return results
```

---

## 4. Dashboard Financeiro Cuidar Vet (Google Sheets via Apps Script)

```javascript
// Google Apps Script — Dashboard automático Cuidar Vet
// Acessa planilha de pedidos Nuvemshop (exportação) + custos

function buildDashboard() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dash = ss.getSheetByName("Dashboard") || ss.insertSheet("Dashboard");
  const orders = ss.getSheetByName("Pedidos");
  
  if (!orders) return;
  
  // Calcular métricas do mês atual
  const hoje = new Date();
  const mesAtual = hoje.getMonth();
  const anoAtual = hoje.getFullYear();
  
  const data = orders.getDataRange().getValues();
  let faturamento = 0, pedidos = 0, ticketTotal = 0;
  
  for (let i = 1; i < data.length; i++) {
    const dataPedido = new Date(data[i][0]);
    if (dataPedido.getMonth() === mesAtual && dataPedido.getFullYear() === anoAtual) {
      faturamento += parseFloat(data[i][3] || 0);
      pedidos++;
      ticketTotal += parseFloat(data[i][3] || 0);
    }
  }
  
  const ticketMedio = pedidos > 0 ? ticketTotal / pedidos : 0;
  
  // Escrever no dashboard
  dash.clearContents();
  dash.getRange("A1").setValue("📊 DASHBOARD CUIDAR VET — " + Utilities.formatDate(hoje, "America/Sao_Paulo", "MMMM/yyyy").toUpperCase());
  dash.getRange("A3:B3").setValues([["Faturamento Mês", faturamento]]);
  dash.getRange("A4:B4").setValues([["Pedidos Mês", pedidos]]);
  dash.getRange("A5:B5").setValues([["Ticket Médio", ticketMedio]]);
  dash.getRange("A7").setValue("Atualizado em: " + Utilities.formatDate(hoje, "America/Sao_Paulo", "dd/MM/yyyy HH:mm"));
}

// Trigger: executar todo dia às 7h
function createDailyTrigger() {
  ScriptApp.newTrigger("buildDashboard")
    .timeBased().atHour(7).everyDays(1).create();
}
```

---

## 5. Integração Compêndio Vet → Nuvemshop

```python
# integration/compendio_to_nuvemshop.py
"""
Sincroniza dados do Compêndio Vet (informações técnicas) com descrições
dos produtos na Nuvemshop.
"""

async def enrich_product_from_compendio(nuvemshop_product_id: int, med_data: dict):
    """
    Atualiza descrição do produto na Nuvemshop com dados técnicos do Compêndio.
    med_data: registro do banco medicamentos
    """
    description = f"""
<h3>Informações Técnicas</h3>
<ul>
  <li><strong>Princípio Ativo:</strong> {med_data['principio_ativo']}</li>
  <li><strong>Concentração:</strong> {med_data['concentracao']}</li>
  <li><strong>Espécies:</strong> {med_data['especies']}</li>
  <li><strong>Indicações:</strong> {med_data['indicacao']}</li>
  <li><strong>Posologia:</strong> {med_data['posologia']}</li>
</ul>
{"<p><strong>⚠️ Uso sob prescrição veterinária.</strong></p>" if med_data['prescricao_obrigatoria'] else ""}
"""
    async with httpx.AsyncClient() as client:
        await client.put(
            f"{NUVEMSHOP_BASE}/products/{nuvemshop_product_id}",
            headers=HEADERS,
            json={"description": {"pt": description}}
        )
```

---

## 6. Variáveis de Ambiente

```env
NUVEMSHOP_USER_ID=SEU_USER_ID
NUVEMSHOP_ACCESS_TOKEN=SEU_TOKEN
CUIDAR_VET_DB=./cuidar_vet.db
MARGIN_TARGET=0.35
```
