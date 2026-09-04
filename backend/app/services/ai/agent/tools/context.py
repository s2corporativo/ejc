# ── app/services/ai/agent/tools/context.py ───────────────────────────────────
# Contexto de execução das ferramentas do agente. Carrega a sessão de banco, o
# usuário autenticado (para re-checagem de RBAC/ownership DENTRO de cada tool) e
# o caso/cliente em foco. NUNCA é serializado para o modelo — é o "ambiente"
# local e confiável do handler.
from __future__ import annotations

from dataclasses import dataclass, field
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
    # I5/B4: fontes devolvidas pelas tools de leitura (buscar_precedentes) ao
    # longo do laço — o validador final recebe-as em `fontes=` (antes recebia
    # None e carimbava "SEM BASE VERIFICÁVEL" mesmo com RAG usado) e o AILog
    # grava a trilha (fontes_rag). Dicts no formato de buscar_contexto_rag.
    fontes_rag: list[dict] = field(default_factory=list)

    def registrar_fontes(self, trechos: list[dict] | None) -> None:
        """Acumula fontes sem duplicar (chave doc_id/chunk_id, senão título+fonte)."""
        vistos = {
            (f.get("doc_id"), f.get("chunk_id"), f.get("titulo"), f.get("fonte"))
            for f in self.fontes_rag
        }
        for t in (trechos or []):
            if not isinstance(t, dict):
                continue
            chave = (t.get("doc_id"), t.get("chunk_id"), t.get("titulo"), t.get("fonte"))
            if chave in vistos:
                continue
            vistos.add(chave)
            self.fontes_rag.append(t)
