---
name: arquiteto-sistema-s2-dev
description: >
  Desenvolve novas funcionalidades e features para o sistema-s2, plataforma TypeScript full-stack de licitações públicas da S2 Estratégia & Negócios Ltda. Use SEMPRE que precisar construir, implementar ou evoluir o sistema-s2 — não apenas auditá-lo. Diferença crítica: auditor-typescript-s2 AUDITA problemas existentes; este skill CONSTRÓI código novo. Cobre: novos módulos TypeScript, integração com PNCP/ComprasGov, módulo de propostas automatizadas, dashboard de licitações, gestão de contratos, radar de editais. Stack: Node.js TypeScript + PostgreSQL + Express/Fastify. Acionado por: "implementa no sistema-s2", "cria feature no s2", "novo módulo licitação", "desenvolve sistema s2", "adicionar funcionalidade sistema s2", "código novo s2", "evolui sistema s2".
---

# Arquiteto de Desenvolvimento — Sistema S2

## Contexto do Sistema

```
SISTEMA: sistema-s2 (plataforma licitatória S2 Estratégia & Negócios Ltda)
STACK: TypeScript full-stack | Node.js | PostgreSQL | Express ou Fastify
ARQUITETURA: 22 módulos de domínio (db/) + 15 routers especializados
CONFORMIDADE: Lei 14.133/21 | LGPD | auditável pelo TCU
DISTINÇÃO: Este skill CONSTRÓI features; auditor-typescript-s2 AUDITA código existente
```

---

## 1. Protocolo de Desenvolvimento

```
1. Identificar módulo de destino (qual dos 22 módulos de domínio)
2. Definir schema de banco (TypeScript interface + SQL CREATE TABLE)
3. Gerar migration SQL versionada
4. Implementar camada de dados (db/{modulo}.ts)
5. Implementar router REST (routers/{modulo}.ts)
6. Registrar router no app principal
7. Escrever types e interfaces
8. Validação com Zod
9. Checklist de segurança (SQL injection, auth, LGPD)
```

---

## 2. Templates Padrão TypeScript

### 2.1 Interface de Domínio

```typescript
// src/types/${module}.ts
export interface ${Entity} {
  id: number
  createdAt: Date
  updatedAt: Date
  deletedAt?: Date | null
  // campos específicos
}

export interface Create${Entity}Dto {
  // campos obrigatórios
}

export interface Update${Entity}Dto {
  // campos opcionais (Partial)
}

export interface ${Entity}ListResponse {
  data: ${Entity}[]
  total: number
  page: number
  pageSize: number
}
```

### 2.2 Módulo de Dados (db/{modulo}.ts)

```typescript
// src/db/${module}.ts
import { pool } from "./connection"
import { ${Entity}, Create${Entity}Dto, Update${Entity}Dto } from "../types/${module}"

export async function list${Entity}(
  page: number = 1,
  pageSize: number = 20,
  search?: string
): Promise<{ data: ${Entity}[]; total: number }> {
  const offset = (page - 1) * pageSize
  const params: unknown[] = []
  let where = "WHERE deleted_at IS NULL"
  if (search) {
    params.push(`%${search}%`)
    where += ` AND name ILIKE $${params.length}`
  }
  const countResult = await pool.query(`SELECT COUNT(*) FROM ${table} ${where}`, params)
  const total = parseInt(countResult.rows[0].count)
  params.push(pageSize, offset)
  const result = await pool.query(
    `SELECT * FROM ${table} ${where} ORDER BY created_at DESC LIMIT $${params.length - 1} OFFSET $${params.length}`,
    params
  )
  return { data: result.rows, total }
}

export async function create${Entity}(dto: Create${Entity}Dto): Promise<${Entity}> {
  const keys = Object.keys(dto)
  const values = Object.values(dto)
  const placeholders = keys.map((_, i) => `$${i + 1}`).join(", ")
  const result = await pool.query(
    `INSERT INTO ${table} (${keys.join(", ")}) VALUES (${placeholders}) RETURNING *`,
    values
  )
  return result.rows[0]
}

export async function get${Entity}ById(id: number): Promise<${Entity} | null> {
  const result = await pool.query(
    "SELECT * FROM ${table} WHERE id = $1 AND deleted_at IS NULL",
    [id]
  )
  return result.rows[0] ?? null
}

export async function update${Entity}(id: number, dto: Update${Entity}Dto): Promise<${Entity} | null> {
  const entries = Object.entries(dto).filter(([, v]) => v !== undefined)
  if (entries.length === 0) return get${Entity}ById(id)
  const sets = entries.map(([k], i) => `${k} = $${i + 2}`).join(", ")
  const values = [id, ...entries.map(([, v]) => v)]
  const result = await pool.query(
    `UPDATE ${table} SET ${sets}, updated_at = NOW() WHERE id = $1 AND deleted_at IS NULL RETURNING *`,
    values
  )
  return result.rows[0] ?? null
}

export async function softDelete${Entity}(id: number): Promise<boolean> {
  const result = await pool.query(
    "UPDATE ${table} SET deleted_at = NOW() WHERE id = $1 AND deleted_at IS NULL",
    [id]
  )
  return (result.rowCount ?? 0) > 0
}
```

### 2.3 Router REST com Zod

```typescript
// src/routers/${module}.ts
import { Router, Request, Response } from "express"
import { z } from "zod"
import { requireAuth, requireRole } from "../middleware/auth"
import { logAction } from "../db/audit"
import * as db from "../db/${module}"

const router = Router()

const Create${Entity}Schema = z.object({
  // campos com validação Zod
})

const Update${Entity}Schema = Create${Entity}Schema.partial()

router.get("/", requireAuth, async (req: Request, res: Response) => {
  try {
    const page = parseInt(req.query.page as string) || 1
    const pageSize = parseInt(req.query.pageSize as string) || 20
    const search = req.query.search as string | undefined
    const result = await db.list${Entity}(page, pageSize, search)
    res.json({ ...result, page, pageSize })
  } catch (err) {
    res.status(500).json({ error: "Erro interno" })
  }
})

router.post("/", requireAuth, async (req: Request, res: Response) => {
  try {
    const parsed = Create${Entity}Schema.safeParse(req.body)
    if (!parsed.success) return res.status(400).json({ error: parsed.error.flatten() })
    const item = await db.create${Entity}(parsed.data)
    await logAction(req.user!.id, "CREATE", "${table}", item.id)
    res.status(201).json(item)
  } catch (err) {
    res.status(500).json({ error: "Erro interno" })
  }
})

router.get("/:id", requireAuth, async (req: Request, res: Response) => {
  const item = await db.get${Entity}ById(parseInt(req.params.id))
  if (!item) return res.status(404).json({ error: "Não encontrado" })
  res.json(item)
})

router.patch("/:id", requireAuth, async (req: Request, res: Response) => {
  try {
    const parsed = Update${Entity}Schema.safeParse(req.body)
    if (!parsed.success) return res.status(400).json({ error: parsed.error.flatten() })
    const item = await db.update${Entity}(parseInt(req.params.id), parsed.data)
    if (!item) return res.status(404).json({ error: "Não encontrado" })
    await logAction(req.user!.id, "UPDATE", "${table}", item.id)
    res.json(item)
  } catch (err) {
    res.status(500).json({ error: "Erro interno" })
  }
})

router.delete("/:id", requireAuth, requireRole(["admin", "manager"]), async (req: Request, res: Response) => {
  const deleted = await db.softDelete${Entity}(parseInt(req.params.id))
  if (!deleted) return res.status(404).json({ error: "Não encontrado" })
  await logAction(req.user!.id, "DELETE", "${table}", parseInt(req.params.id))
  res.status(204).send()
})

export default router
```

---

## 3. Módulos Prioritários Sistema-S2

### Módulo: Radar de Editais (integração PNCP)
```typescript
// Busca automática na API pública PNCP
// GET https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao
// Filtros: dataInicial, dataFinal, codigoUnidadeAdministrativa, tipoPessoa
// Salva em tabela editais_radar com status: novo, analisando, participando, descartado
```

### Módulo: Gestão de Contratos Ativos
```typescript
// Contratos ganhos: vigência, valor, órgão, objeto, aditivos
// Alertas: vencimento 60 dias antes
// Tabela: contracts (id, edital_id, organ, value, start_date, end_date, status)
```

### Módulo: Habilitação Automática
```typescript
// Vincula documentos de habilitação por categoria
// Alerta vencimentos (certidões, atestados)
// Gera pacote de habilitação por edital (quais docs faltam)
```

### Módulo: Dashboard Gerencial
```typescript
// KPIs: editais monitorados, propostas enviadas, taxa de vitória, faturamento acumulado
// Gráfico: evolução mensal de participações/vitórias
// Tabela: próximas sessões (ordenadas por data)
```

---

## 4. Regras de Desenvolvimento

- Toda query SQL com parâmetros — nunca concatenação de string
- Soft delete obrigatório (deleted_at) — nunca DELETE físico
- Audit log em todo CREATE/UPDATE/DELETE com user_id, ação, tabela, record_id
- Validação Zod obrigatória antes de qualquer insert/update
- Respostas sempre em JSON estruturado: `{data, total, page, pageSize}` para listas
- Dados pessoais (CPF, CNPJ) mascarados em logs
- Nunca hardcodar credenciais — sempre process.env
- Verificar lei aplicável: Lei 14.133/21 (contratos novos) vs 8.666/93 (contratos anteriores)

---

## 5. Checklist pós-desenvolvimento

```
[ ] TypeScript compila sem erro (tsc --noEmit)
[ ] Queries SQL com parâmetros (sem SQL injection)
[ ] Zod validation em todos os endpoints de escrita
[ ] Audit log gravando
[ ] Soft delete funcional
[ ] Rota registrada no app principal
[ ] Dados pessoais não expostos em logs
[ ] .env.example atualizado com novas variáveis
```
