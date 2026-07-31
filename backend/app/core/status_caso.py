"""Fonte única de verdade para status de caso, agregados e visibilidade herdada."""
from __future__ import annotations

from sqlalchemy import Select, or_, select

from app.models.case import Case, CaseArea, CaseStatus
from app.models.legal_doc import LegalDoc, PecaStatus

STATUS_CASO_VALIDOS: tuple[str, ...] = tuple(s.value for s in CaseStatus)
STATUS_ABERTOS: tuple[CaseStatus, ...] = (
    CaseStatus.triagem,
    CaseStatus.ativo,
    CaseStatus.suspenso,
    CaseStatus.acordo,
)
STATUS_FECHADOS: tuple[CaseStatus, ...] = (
    CaseStatus.encerrado,
    CaseStatus.arquivado,
)

# Sentinelas aceitos por clientes legados. Eles nunca chegam ao ENUM nativo.
STATUS_SEM_FILTRO = frozenset({"all", "todos", "*"})
ERRO_STATUS_INVALIDO = (
    "Status de caso inválido: {valor!r}. Valores aceitos: {aceitos}. "
    "Para não filtrar por status, use 'all'/'todos' ou omita o parâmetro."
)


def validar_status_caso(valor: str | None):
    """Normaliza o filtro HTTP e impede valor inválido no ENUM do banco.

    O router legado constrói diretamente ``Case.status == retorno``. Portanto,
    para sentinelas de "todos" retornamos a própria coluna: a expressão gerada
    é ``cases.status = cases.status`` (neutra para coluna NOT NULL), sem tocar no
    enum com um literal inválido. Ausência real do parâmetro continua sendo
    tratada pelo próprio router antes desta função.
    """
    if valor is None:
        return None
    normalizado = valor.strip().lower()
    if normalizado in STATUS_SEM_FILTRO:
        return Case.status
    try:
        return CaseStatus(normalizado)
    except ValueError:
        raise ValueError(
            ERRO_STATUS_INVALIDO.format(
                valor=valor, aceitos=", ".join(STATUS_CASO_VALIDOS)
            )
        ) from None


AREA_CASO_VALIDAS: tuple[str, ...] = tuple(a.value for a in CaseArea)
AREA_SEM_FILTRO = STATUS_SEM_FILTRO
ERRO_AREA_INVALIDA = (
    "Área de caso inválida: {valor!r}. Valores aceitos: {aceitos}. "
    "Para não filtrar por área, use 'all'/'todos' ou omita o parâmetro."
)


def validar_area_caso(valor: str | None):
    """Normaliza área com o mesmo contrato de status."""
    if valor is None:
        return None
    normalizado = valor.strip().lower()
    if normalizado in AREA_SEM_FILTRO:
        return Case.area
    try:
        return CaseArea(normalizado)
    except ValueError:
        raise ValueError(
            ERRO_AREA_INVALIDA.format(
                valor=valor, aceitos=", ".join(AREA_CASO_VALIDAS)
            )
        ) from None


def contar_ativos(por_status: dict[str, int]) -> int:
    """Calcula casos em curso sem incluir encerrados nem arquivados."""
    return sum(por_status.get(s.value, 0) for s in STATUS_ABERTOS)


# Exclusão lógica do pai preserva histórico. Nas superfícies operacionais, os
# dependentes herdam a visibilidade do caso; auditoria/diagnóstico podem acessar
# os registros físicos diretamente.
CASOS_VIVOS = select(Case.id).where(Case.deleted_at.is_(None))
SQL_CASO_VISIVEL = (
    "({col} IS NULL OR EXISTS "
    "(SELECT 1 FROM cases c_v WHERE c_v.id = {col} AND c_v.deleted_at IS NULL))"
)


def filtrar_pecas_visiveis(q: Select) -> Select:
    """Oculta peças de casos excluídos e preserva minutas avulsas."""
    return q.where(
        or_(LegalDoc.case_id.is_(None), LegalDoc.case_id.in_(CASOS_VIVOS))
    )


STATUS_PECA_TERMINAIS: tuple[PecaStatus, ...] = (PecaStatus.protocolada,)


def filtrar_aguardando_revisao(q: Select) -> Select:
    """Conta peças reais de IA ainda não revisadas, inclusive rascunhos."""
    return filtrar_pecas_visiveis(
        q.where(
            LegalDoc.deleted_at.is_(None),
            LegalDoc.ai_generated.is_(True),
            LegalDoc.human_reviewed.is_(False),
            LegalDoc.status.notin_(STATUS_PECA_TERMINAIS),
        )
    )
