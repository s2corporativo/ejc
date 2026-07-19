# ── app/services/ai/agent/tools/context.py ───────────────────────────────────
# Contexto de execução das ferramentas do agente. Carrega a sessão de banco, o
# usuário autenticado (para re-checagem de RBAC/ownership DENTRO de cada tool) e
# o caso/cliente em foco. NUNCA é serializado para o modelo — é o "ambiente"
# local e confiável do handler.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentContext:
    """Ambiente confiável das ferramentas. `db`/`user` permitem que CADA tool
    re-verifique acesso (verificar_acesso_caso) — nunca confiar só no gate de
    entrada do router. `role` é a string do papel (para filtrar tools visíveis).
    `area` é a ÁREA/ramo do caso (ex.: 'criminal', 'trabalhista') — usada para
    derivar o MODO de sanitização por sigilo do caso nas tools de escrita
    (achado S1: o roteamento por TarefaIA não pode ignorar o sigilo da área)."""
    db: Any            # AsyncSession
    user: Any          # models.user.User
    case_id: str
    client_id: str | None
    role: str
    area: str | None = None
