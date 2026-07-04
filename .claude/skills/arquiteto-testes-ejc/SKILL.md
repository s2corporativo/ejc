---
name: arquiteto-testes-ejc
description: >
  Gera suítes de testes automatizados para o EJC (backend pytest + frontend vitest) e configura pipeline CI/CD básico. Use SEMPRE que precisar escrever, organizar ou corrigir testes no EJC: testes unitários de endpoints FastAPI, testes de integração com banco de dados, testes de componentes React, configurar cobertura de código, corrigir testes falhando. A skill auditor-typescript-s2 EXIGE cobertura >70% mas nenhuma skill gera os testes — este skill preenche essa lacuna. Também cobre fixtures pytest, factories de dados de teste, mocking de dependências externas, relatórios de cobertura. Acionado por: "testes EJC", "pytest EJC", "vitest EJC", "cobertura de código", "escreve testes", "testes falhando", "CI testes", "unit test EJC", "integration test", "test suite", "coverage EJC".
---

# Arquiteto de Testes — EJC Backend + Frontend

## Contexto

```
BACKEND: FastAPI Python 3.11+ → pytest + httpx (AsyncClient)
FRONTEND: React TypeScript → vitest + React Testing Library
META: cobertura ≥ 70% (exigida pelo auditor-typescript-s2)
BANCO: PostgreSQL de teste isolado (ou SQLite in-memory para testes unitários)
```

---

## 1. Configuração Backend — pytest

### Instalação

```bash
pip install pytest pytest-asyncio pytest-cov httpx factory-boy faker --break-system-packages
```

### conftest.py — Fixtures Globais

```python
# backend/tests/conftest.py
import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import Base, get_db
import os

# Banco de teste isolado
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_ejc.db")

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

@pytest.fixture(scope="function")
def db(engine):
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()
    yield session
    session.rollback()
    session.close()

@pytest.fixture(scope="function")
def override_get_db(db):
    def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()

@pytest.fixture
async def client(override_get_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def auth_client(client, db):
    """Client autenticado como admin"""
    from app.auth import create_access_token
    from tests.factories import UserFactory
    user = UserFactory(role="admin", db=db)
    token = create_access_token({"sub": str(user.id)})
    client.headers["Authorization"] = f"Bearer {token}"
    yield client

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

### Factories (dados de teste)

```python
# backend/tests/factories.py
import factory
from factory.alchemy import SQLAlchemyModelFactory
from faker import Faker
from app.models.client import Client
from app.models.case import Case
from app.models.deadline import Deadline
from app.models.user import User

fake = Faker("pt_BR")

class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "commit"

    name = factory.LazyAttribute(lambda _: fake.name())
    email = factory.LazyAttribute(lambda _: fake.email())
    role = "advogado"
    is_active = True
    hashed_password = "$2b$12$test_hash"  # senha: test123

class ClientFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Client
        sqlalchemy_session_persistence = "commit"

    name = factory.LazyAttribute(lambda _: fake.name())
    cpf_cnpj = factory.LazyAttribute(lambda _: fake.cpf())
    phone = factory.LazyAttribute(lambda _: fake.phone_number())
    email = factory.LazyAttribute(lambda _: fake.email())
    client_type = "PF"
    status = "ativo"

class CaseFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Case
        sqlalchemy_session_persistence = "commit"

    case_number = factory.Sequence(lambda n: f"0{n:06d}-00.2026.8.13.0000")
    title = factory.LazyAttribute(lambda _: f"Caso - {fake.sentence(3)}")
    area = "Civil"
    status = "em_andamento"
    client = factory.SubFactory(ClientFactory)

class DeadlineFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Deadline
        sqlalchemy_session_persistence = "commit"

    description = factory.LazyAttribute(lambda _: fake.sentence(4))
    deadline_date = factory.LazyAttribute(lambda _: fake.future_date())
    status = "pendente"
    case = factory.SubFactory(CaseFactory)
```

### Testes de Endpoints

```python
# backend/tests/test_clients.py
import pytest
from tests.factories import ClientFactory

@pytest.mark.asyncio
async def test_list_clients_unauthenticated(client):
    response = await client.get("/api/v1/clients")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_list_clients_authenticated(auth_client, db):
    ClientFactory.create_batch(3, db=db)
    response = await auth_client.get("/api/v1/clients")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3
    assert "data" in data
    assert "page" in data

@pytest.mark.asyncio
async def test_create_client(auth_client):
    payload = {
        "name": "João da Silva",
        "cpf_cnpj": "123.456.789-00",
        "client_type": "PF",
        "phone": "31999999999",
        "email": "joao@test.com"
    }
    response = await auth_client.post("/api/v1/clients", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "João da Silva"
    assert "id" in data

@pytest.mark.asyncio
async def test_create_client_missing_required_fields(auth_client):
    response = await auth_client.post("/api/v1/clients", json={})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_soft_delete_client(auth_client, db):
    client_obj = ClientFactory(db=db)
    response = await auth_client.delete(f"/api/v1/clients/{client_obj.id}")
    assert response.status_code == 204
    # Verificar soft delete
    response = await auth_client.get(f"/api/v1/clients/{client_obj.id}")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_search_clients(auth_client, db):
    ClientFactory(name="Maria Oliveira", db=db)
    ClientFactory(name="Pedro Santos", db=db)
    response = await auth_client.get("/api/v1/clients?search=Maria")
    assert response.status_code == 200
    data = response.json()
    assert all("Maria" in c["name"] for c in data["data"])
```

```python
# backend/tests/test_deadlines.py
import pytest
from datetime import date, timedelta
from tests.factories import DeadlineFactory, CaseFactory

@pytest.mark.asyncio
async def test_deadline_critical_alert(auth_client, db):
    """Prazos em ≤ 2 dias devem aparecer como críticos"""
    case = CaseFactory(db=db)
    DeadlineFactory(deadline_date=date.today() + timedelta(days=1), case=case, db=db)
    DeadlineFactory(deadline_date=date.today() + timedelta(days=10), case=case, db=db)

    response = await auth_client.get("/api/v1/deadlines?days_ahead=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    # Apenas prazo crítico deve aparecer no filtro
```

---

## 2. Configuração Frontend — Vitest

### Instalação

```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

### vite.config.ts additions

```typescript
/// <reference types="vitest" />
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov", "html"],
      thresholds: { lines: 70, functions: 70, branches: 60 }
    }
  }
})
```

### setup.ts

```typescript
// src/test/setup.ts
import "@testing-library/jest-dom"
import { vi } from "vitest"

// Mock da API
vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  }
}))
```

### Exemplo de Teste de Componente

```typescript
// src/test/ClientList.test.tsx
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { vi, describe, it, expect, beforeEach } from "vitest"
import { api } from "@/lib/api"
import ClientsPage from "@/pages/ClientsPage"

const mockClients = {
  data: [
    { id: 1, name: "João Silva", client_type: "PF", status: "ativo" },
    { id: 2, name: "Empresa XYZ", client_type: "PJ", status: "ativo" }
  ],
  total: 2, page: 1, page_size: 20
}

describe("ClientsPage", () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({ data: mockClients })
  })

  it("renderiza lista de clientes", async () => {
    render(<ClientsPage />)
    await waitFor(() => {
      expect(screen.getByText("João Silva")).toBeInTheDocument()
      expect(screen.getByText("Empresa XYZ")).toBeInTheDocument()
    })
  })

  it("exibe loading durante fetch", () => {
    vi.mocked(api.get).mockImplementation(() => new Promise(() => {}))
    render(<ClientsPage />)
    expect(screen.getByText(/carregando/i)).toBeInTheDocument()
  })

  it("exibe mensagem quando lista vazia", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { ...mockClients, data: [], total: 0 } })
    render(<ClientsPage />)
    await waitFor(() => {
      expect(screen.getByText(/nenhum registro/i)).toBeInTheDocument()
    })
  })
})
```

---

## 3. Scripts de Coverage

```bash
# Backend
cd backend
pytest tests/ --cov=app --cov-report=html --cov-report=term-missing
open htmlcov/index.html

# Frontend
cd frontend
npm run test -- --coverage
open coverage/index.html

# Rodar tudo
pytest tests/ --cov=app --cov-fail-under=70 && npm run test -- --coverage
```

---

## 4. pytest.ini

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    slow: marca testes lentos
    integration: testes com banco real
```

---

## 5. Prioridade de Cobertura por Módulo

```
CRÍTICO (testar primeiro):
  - auth (login, token, refresh, logout)
  - clients (CRUD + busca)
  - cases (CRUD + dossiê)
  - deadlines (CRUD + alertas)
  - audit_log (gravação)

IMPORTANTE:
  - leads (CRUD + conversão)
  - documents (upload + download)
  - fees (cálculo honorários)

SECUNDÁRIO:
  - dashboard (aggregations)
  - reports (geração)
```
