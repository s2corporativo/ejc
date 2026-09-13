# ── app/services/ajuizamento/capacidades.py ──────────────────────────────────
# Estados de capacidade e matriz calculada por conector × tribunal/sistema/
# versão/ambiente/credencial/escopo/homologação. Nunca persiste: é derivada
# do perfil cadastrado + settings a cada consulta (fonte única, sem cache
# envelhecido).
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings


class EstadoCapacidade(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    REQUIRES_AUTHORIZATION = "REQUIRES_AUTHORIZATION"


OPERACOES = (
    "validate_target", "list_jurisdictions", "list_competences", "list_classes",
    "list_subjects", "file_new_case", "append_petition", "read_process",
    "read_movements", "read_notices", "download_document", "receive_callback",
    "get_receipt", "sign",
)

# Operações que só podem existir como SUPPORTED com perfil totalmente
# homologado (protocolo real). As demais podem ser CONDITIONAL/leitura.
OPERACOES_ESCRITA = frozenset({"file_new_case", "append_petition", "sign"})


@dataclass(frozen=True)
class ContextoConector:
    """Tudo o que um conector precisa para decidir capacidades — sem segredo."""
    settings: Settings
    perfil: Any | None = None            # JudicialIntegrationProfile | None
    credencial_disponivel: bool = False  # existe referência válida no cofre/MNI
    ambiente: str = "homologacao"

    @property
    def perfil_ativo(self) -> bool:
        return bool(self.perfil is not None and getattr(self.perfil, "ativo", False))

    @property
    def homologado(self) -> bool:
        p = self.perfil
        return bool(
            p is not None and p.ativo and p.authorized and p.homologated_at is not None
            and p.production_endpoint_verified and p.credentials_valid
        )


@dataclass(frozen=True)
class Capacidade:
    operacao: str
    estado: EstadoCapacidade
    motivo: str = ""


@dataclass
class MatrizCapacidades:
    conector: str
    sistema: str
    tribunal: str | None
    ambiente: str
    itens: dict[str, Capacidade] = field(default_factory=dict)
    requisitos_autorizacao: list[str] = field(default_factory=list)

    def estado(self, operacao: str) -> EstadoCapacidade:
        cap = self.itens.get(operacao)
        return cap.estado if cap else EstadoCapacidade.UNSUPPORTED

    def pode(self, operacao: str) -> bool:
        return self.estado(operacao) == EstadoCapacidade.SUPPORTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "conector": self.conector,
            "sistema": self.sistema,
            "tribunal": self.tribunal,
            "ambiente": self.ambiente,
            "operacoes": {
                op: {"estado": c.estado.value, "motivo": c.motivo}
                for op, c in self.itens.items()
            },
            "requisitos_autorizacao": list(self.requisitos_autorizacao),
            "protocolo_real_liberado": self.pode("file_new_case"),
        }


def montar_matriz(
    *, conector: str, sistema: str, ctx: ContextoConector,
    declaradas: dict[str, tuple[EstadoCapacidade, str]],
) -> MatrizCapacidades:
    """Aplica as regras transversais sobre o que o conector declara:

    - operação de ESCRITA só é SUPPORTED com perfil homologado (authorized +
      homologated_at + production_endpoint_verified + credentials_valid) e
      credencial disponível; senão vira REQUIRES_AUTHORIZATION;
    - operação não declarada é UNSUPPORTED;
    - requisitos de autorização são listados para a UI/preflight.
    """
    perfil = ctx.perfil
    tribunal = getattr(perfil, "tribunal_code", None)
    matriz = MatrizCapacidades(conector=conector, sistema=sistema, tribunal=tribunal, ambiente=ctx.ambiente)
    pendentes: list[str] = []
    if perfil is None:
        pendentes.append("perfil de integração do tribunal não cadastrado")
    else:
        if not perfil.ativo:
            pendentes.append("perfil inativo")
        if not perfil.authorized:
            pendentes.append("habilitação institucional não registrada (authorized=false)")
        if perfil.homologated_at is None:
            pendentes.append("homologação com o tribunal não concluída")
        if not perfil.production_endpoint_verified:
            pendentes.append("endpoint de produção não verificado")
        if not perfil.credentials_valid:
            pendentes.append("credencial não validada")
    if not ctx.credencial_disponivel:
        pendentes.append("credencial ausente no cofre/catálogo")

    for op in OPERACOES:
        declarado = declaradas.get(op)
        if declarado is None:
            matriz.itens[op] = Capacidade(op, EstadoCapacidade.UNSUPPORTED, "operação não oferecida por este conector")
            continue
        estado, motivo = declarado
        if op in OPERACOES_ESCRITA and estado == EstadoCapacidade.SUPPORTED and not (ctx.homologado and ctx.credencial_disponivel):
            estado = EstadoCapacidade.REQUIRES_AUTHORIZATION
            motivo = "; ".join(pendentes) or motivo
        matriz.itens[op] = Capacidade(op, estado, motivo)
    if any(c.estado == EstadoCapacidade.REQUIRES_AUTHORIZATION for c in matriz.itens.values()):
        matriz.requisitos_autorizacao = pendentes
    return matriz
