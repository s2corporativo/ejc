---
name: arquiteto-modulos-ejc
description: >
  Gera novos módulos completos para o EJC (Ecossistema Jurídico Clovis) do zero — backend FastAPI + Pydantic + Alembic migration + React TypeScript + Tailwind. Use SEMPRE que precisar construir funcionalidade nova no EJC, não apenas corrigir: portal do cliente externo, módulo de filas Celery, OCR de documentos, integração com tribunais, notificações automáticas, relatórios gerenciais, ou qualquer nova tela/endpoint. Diferença crítica: arquiteto-ejc REPARA o que existe; este skill CONSTRÓI do zero. Stack obrigatória: FastAPI Python 3.11+, React TypeScript 18+, Tailwind CSS, PostgreSQL, Docker. Padrão arquitetural do EJC deve ser sempre preservado. Acionado por: "cria módulo", "adicionar funcionalidade no EJC", "novo endpoint EJC", "nova tela EJC", "implementar [feature] no EJC", "gerar código para EJC", "módulo portal cliente", "módulo OCR", "módulo Celery".
---

# Arquiteto de Módulos EJC — Geração de Features

## Contexto do Sistema EJC

```
STACK: FastAPI (Python 3.11+) + React TypeScript 18 + Tailwind CSS + PostgreSQL 15 + Docker
PADRÃO: REST API /api/v1/{modulo} | JWT auth | Pydantic validation | Alembic migrations
PERFIS: superadmin, admin, socio, advogado, assistente, financeiro, atendimento
MÓDULOS ATIVOS: auth, clients, leads, cases, deadlines, tasks, documents, legal_docs, fees, financeiro, logs
MÓDULOS FUTUROS: portal_cliente, celery_tasks, ocr_documentos, integracao_tribunal, notificacoes
```

---

## 1. Protocolo de Geração

### Sequência obrigatória para qualquer módulo novo:

```
1. Confirmar nome do módulo e escopo (O QUE o módulo faz)
2. Definir modelo de dados (tabelas, campos, relacionamentos)
3. Gerar migration Alembic
4. Gerar modelo SQLAlchemy
5. Gerar schemas Pydantic (Request/Response)
6. Gerar router FastAPI com todos os endpoints CRUD
7. Gerar componente React (listagem + formulário)
8. Gerar página React com rota
9. Adicionar item ao sidebar
10. Checklist de validação final
```

---

## 2. Templates Padrão

### 2.1 Migration Alembic

```python
"""${message}

Revision ID: ${revision}
Revises: ${down_revision}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '${revision}'
down_revision = '${down_revision}'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        '${table_name}',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        # campos específicos do módulo aqui
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_${table_name}_id'), '${table_name}', ['id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_${table_name}_id'), table_name='${table_name}')
    op.drop_table('${table_name}')
```

### 2.2 Modelo SQLAlchemy

```python
# backend/app/models/${module_name}.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class ${ModelName}(Base):
    __tablename__ = "${table_name}"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Campos específicos
    # Relacionamentos
```

### 2.3 Schemas Pydantic

```python
# backend/app/schemas/${module_name}.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class ${ModelName}Base(BaseModel):
    # campos comuns
    pass

class ${ModelName}Create(${ModelName}Base):
    # campos obrigatórios na criação
    pass

class ${ModelName}Update(BaseModel):
    # todos opcionais para PATCH
    pass

class ${ModelName}Response(${ModelName}Base):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ${ModelName}ListResponse(BaseModel):
    data: List[${ModelName}Response]
    total: int
    page: int
    page_size: int
```

### 2.4 Router FastAPI

```python
# backend/app/routers/${module_name}.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.auth import get_current_user, require_roles
from app.models.${module_name} import ${ModelName}
from app.schemas.${module_name} import (
    ${ModelName}Create, ${ModelName}Update, ${ModelName}Response, ${ModelName}ListResponse
)
from app.models.audit_log import create_audit_log

router = APIRouter(prefix="/${module_path}", tags=["${module_label}"])

@router.get("/", response_model=${ModelName}ListResponse)
def list_${module_name}(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(${ModelName}).filter(${ModelName}.deleted_at.is_(None))
    if search:
        query = query.filter(${ModelName}.name.ilike(f"%{search}%"))
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"data": items, "total": total, "page": page, "page_size": page_size}

@router.post("/", response_model=${ModelName}Response, status_code=status.HTTP_201_CREATED)
def create_${module_name}(
    payload: ${ModelName}Create,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    item = ${ModelName}(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    create_audit_log(db, current_user.id, "CREATE", "${module_label}", item.id)
    return item

@router.get("/{item_id}", response_model=${ModelName}Response)
def get_${module_name}(
    item_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    item = db.query(${ModelName}).filter(
        ${ModelName}.id == item_id,
        ${ModelName}.deleted_at.is_(None)
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="${ModelName} não encontrado")
    return item

@router.patch("/{item_id}", response_model=${ModelName}Response)
def update_${module_name}(
    item_id: int,
    payload: ${ModelName}Update,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    item = db.query(${ModelName}).filter(
        ${ModelName}.id == item_id,
        ${ModelName}.deleted_at.is_(None)
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="${ModelName} não encontrado")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    create_audit_log(db, current_user.id, "UPDATE", "${module_label}", item.id)
    return item

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_${module_name}(
    item_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_roles(["admin", "socio"]))
):
    item = db.query(${ModelName}).filter(
        ${ModelName}.id == item_id,
        ${ModelName}.deleted_at.is_(None)
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="${ModelName} não encontrado")
    from datetime import datetime, timezone
    item.deleted_at = datetime.now(timezone.utc)
    db.commit()
    create_audit_log(db, current_user.id, "DELETE", "${module_label}", item.id)
```

### 2.5 Componente React (página de listagem)

```tsx
// frontend/src/pages/${ModuleName}Page.tsx
import { useState, useEffect } from "react"
import { Plus, Search } from "lucide-react"
import { api } from "@/lib/api"

interface ${ModelName} {
  id: number
  // campos
  created_at: string
}

export default function ${ModelName}Page() {
  const [items, setItems] = useState<${ModelName}[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    fetchItems()
  }, [search, page])

  const fetchItems = async () => {
    setLoading(true)
    try {
      const res = await api.get("/${module_path}", { params: { search, page, page_size: 20 } })
      setItems(res.data.data)
      setTotal(res.data.total)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-gray-800">${ModuleLabel}</h1>
        <button className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
          <Plus size={16} /> Novo
        </button>
      </div>

      <div className="flex items-center gap-2 mb-4 bg-white border rounded-lg px-3 py-2 w-full max-w-md">
        <Search size={16} className="text-gray-400" />
        <input
          className="flex-1 outline-none text-sm"
          placeholder="Buscar..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {loading ? (
        <div className="text-center py-10 text-gray-400">Carregando...</div>
      ) : (
        <div className="bg-white rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                {/* colunas */}
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id} className="border-b hover:bg-gray-50">
                  {/* células */}
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={99} className="text-center py-8 text-gray-400">Nenhum registro encontrado</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
```

---

## 3. Módulos Candidatos — Especificações

### Portal do Cliente Externo
```
TABELAS: client_portal_users, client_portal_sessions, client_notifications
ENDPOINTS: POST /portal/auth | GET /portal/my-cases | GET /portal/my-documents
REACT: página separada /portal (fora do admin)
SEGURANÇA: token JWT separado, acesso somente leitura, sem dados de outros clientes
```

### Módulo OCR de Documentos
```
DEPENDÊNCIAS: pytesseract, pdf2image, Pillow (requirements.txt)
FLUXO: upload PDF → convert to images → OCR → extract text → store in document.ocr_text
ENDPOINT: POST /documents/{id}/ocr
REACT: botão "Extrair Texto" no card do documento
```

### Integração com Tribunais (TJMG/PJe)
```
DEPENDÊNCIA: httpx, playwright (opcional)
FLUXO: número processo → consulta API pública TJMG → retorna movimentações → vincula ao caso
ENDPOINT: POST /cases/{id}/sync-tribunal | GET /cases/{id}/tribunal-moves
CRON: atualização diária automática (Celery quando disponível)
```

---

## 4. Regras Absolutas

- Nunca quebrar módulo existente ao adicionar novo
- Sempre usar soft delete (deleted_at) — nunca DELETE físico
- Sempre registrar em audit_log após CREATE/UPDATE/DELETE
- Sempre validar permissão por perfil nas rotas sensíveis
- Paginação obrigatória em listagens (page + page_size + total)
- Datas sempre em ISO 8601 UTC no backend
- Frontend nunca faz chamada sem tratamento de erro
- Módulo em desenvolvimento: exibir aviso "Em breve" — nunca tela em branco

---

## 5. Checklist pós-geração

```
[ ] Migration roda sem erro (alembic upgrade head)
[ ] Endpoints respondem no Swagger (/docs)
[ ] CRUD completo testável via Swagger
[ ] Componente React renderiza sem erro de TypeScript
[ ] Rota adicionada ao router principal
[ ] Item adicionado ao sidebar com ícone correto
[ ] Log de auditoria gravando
[ ] Soft delete funcional
[ ] Paginação funcional
[ ] Busca funcional
```
