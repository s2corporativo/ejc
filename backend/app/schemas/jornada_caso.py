# ── app/schemas/jornada_caso.py ───────────────────────────────────────────────
# Contrato FIXO da Jornada do Caso (9 etapas do fluxo do escritório).
# O frontend é escrito contra estes nomes — NÃO renomear campos/chaves.
# Literal (e não Enum novo) porque as chaves são um vocabulário do contrato
# HTTP, não um domínio persistido — não existe tabela/coluna correspondente.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChaveEtapa = Literal[
    "cliente", "triagem", "documentos", "inteligencia", "estrategia",
    "producao", "revisao", "protocolo", "gestao",
]

StatusEtapa = Literal["pendente", "em_andamento", "concluida"]

# Ordem canônica das 9 etapas — fonte única usada pelo router e pelos testes.
ORDEM_ETAPAS: tuple[str, ...] = (
    "cliente", "triagem", "documentos", "inteligencia", "estrategia",
    "producao", "revisao", "protocolo", "gestao",
)


class EtapaJornada(BaseModel):
    chave: ChaveEtapa
    titulo: str
    status: StatusEtapa
    resumo: str
    pendencias: list[str] = Field(default_factory=list)
    link_modulo: str


class JornadaCasoOut(BaseModel):
    case_id: str
    titulo: str
    fase: str | None = None
    numero_processo: str | None = None
    cliente_id: str | None = None
    etapas: list[EtapaJornada]
