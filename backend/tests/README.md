# Testes — EJC backend

Suíte mínima criada na Fase 5 (saneamento) para travar as correções de segurança
das Fases 1–3 contra regressão. **Não exige banco** (usa fakes / funções puras).

## Rodar

```bash
cd backend
python -m pytest tests -q
```

(Requer as dependências de teste: `pytest`, `pytest-asyncio` — já em `requirements.txt`.)

## Cobertura

| Arquivo | Protege |
|---|---|
| `test_security.py` | hash bcrypt (seed admin / login) |
| `test_sanitizer.py` | sanitização LGPD (PII fora do RAG/Groq) — Fase 3B |
| `test_ownership.py` | gate de ownership / IDOR (gestão, equipe, anti-lockout, 403/404) — Fase 3A |
| `test_rag_isolation.py` | filtro fail-closed de isolamento do RAG por cliente — Fase 3B |
| `test_smoke.py` | app monta + rotas `/auth/refresh`/`/pecas/gerar` (Fase 1) + cadeia Alembic íntegra (Fase 2) |

> Próximo (Fase 5): testes de integração com Postgres efêmero (pgvector) para
> migrations e queries reais; testes dos cálculos jurídicos (`services/calc`).
