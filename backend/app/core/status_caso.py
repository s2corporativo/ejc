"""Fonte ÚNICA de verdade para status de caso, agregados e visibilidade herdada.

Por que este módulo existe
──────────────────────────
Antes dele havia cinco definições incompatíveis de "caso ativo" espalhadas pelo
backend (dashboard, /cases/stats, dashboard_service, case_health, datajud_sync),
e o Dashboard contava caso `arquivado` como ativo. Contador que discorda de
listagem é falso positivo operacional: o titular vê 9 casos ativos e encontra 8.

Regras de ouro deste módulo:

1. A verdade física é o ENUM `casestatus` do Postgres, refletido em
   `models.case.CaseStatus`. Nada aqui inventa status novo — apenas nomeia
   CONJUNTOS sobre os valores que já existem.
2. `ativo` é um STATUS REAL e persistido. "Ativos" no Dashboard é um AGREGADO
   (tudo que não está encerrado nem arquivado). São conceitos diferentes e o
   código não pode voltar a confundi-los: por isso o agregado se chama
   `STATUS_ABERTOS`, nunca "ativo".
3. Valor de filtro fora do enum NUNCA chega ao banco. A coluna é ENUM nativo:
   `WHERE status = 'all'` estoura InvalidTextRepresentation e vira HTTP 500.
   `validar_status_caso()` transforma isso em 422 com a lista de aceitos.
4. "Todos" é a AUSÊNCIA do filtro. Nenhum valor sentinela (`all`, `todos`, `*`)
   é aceito ou persistido como se fosse status real.

Nota deliberada: `app/core/domain_contracts.py` define um vocabulário paralelo
(`CaseLifecycleStatus`, 11 valores) que NÃO é persistido e mapeia
`acordo -> ENCERRADO`. Adotá-lo aqui mudaria silenciosamente a semântica de
negócio (hoje `acordo` conta como caso ABERTO). Este módulo não o utiliza; a
unificação dos dois vocabulários é decisão de produto, não de refatoração.
"""
from __future__ import annotations

from sqlalchemy import Select, or_, select

from app.models.case import Case, CaseArea, CaseStatus
from app.models.legal_doc import LegalDoc, PecaStatus

# ── Status de caso ───────────────────────────────────────────────────────────

#: Todos os valores aceitos pela coluna `cases.status` (ENUM nativo do PG).
STATUS_CASO_VALIDOS: tuple[str, ...] = tuple(s.value for s in CaseStatus)

#: Caso em curso — o trabalho jurídico ainda acontece.
STATUS_ABERTOS: tuple[CaseStatus, ...] = (
    CaseStatus.triagem,
    CaseStatus.ativo,
    CaseStatus.suspenso,
    CaseStatus.acordo,
)

#: Caso fora da operação. `encerrado` é desfecho; `arquivado` é guarda.
STATUS_FECHADOS: tuple[CaseStatus, ...] = (
    CaseStatus.encerrado,
    CaseStatus.arquivado,
)

#: Mensagem única de erro — o cliente precisa saber o que é aceito.
ERRO_STATUS_INVALIDO = (
    "Status de caso inválido: {valor!r}. Valores aceitos: {aceitos}. "
    "Para não filtrar por status, omita o parâmetro."
)


def validar_status_caso(valor: str | None) -> CaseStatus | None:
    """Converte o filtro recebido no enum, ou explode com erro de domínio.

    `None`/vazio devolve `None` (= sem filtro, "todos"). Qualquer outro valor
    fora do enum levanta `ValueError` — o router traduz em HTTP 422. Isso
    impede que a string crua chegue ao Postgres e vire 500.
    """
    if valor is None or valor == "":
        return None
    try:
        return CaseStatus(valor)
    except ValueError:
        raise ValueError(
            ERRO_STATUS_INVALIDO.format(
                valor=valor, aceitos=", ".join(STATUS_CASO_VALIDOS)
            )
        ) from None


#: `area` é ENUM nativo igual a `status` e sofre EXATAMENTE o mesmo defeito:
#: valor fora do enum vira 500. Validado aqui pelo mesmo caminho.
AREA_CASO_VALIDAS: tuple[str, ...] = tuple(a.value for a in CaseArea)

ERRO_AREA_INVALIDA = (
    "Área de caso inválida: {valor!r}. Valores aceitos: {aceitos}. "
    "Para não filtrar por área, omita o parâmetro."
)


def validar_area_caso(valor: str | None) -> CaseArea | None:
    """Mesmo contrato de `validar_status_caso`, para o filtro de área."""
    if valor is None or valor == "":
        return None
    try:
        return CaseArea(valor)
    except ValueError:
        raise ValueError(
            ERRO_AREA_INVALIDA.format(
                valor=valor, aceitos=", ".join(AREA_CASO_VALIDAS)
            )
        ) from None


# ── Contagem de casos: definições compartilhadas ─────────────────────────────
#
# Dashboard, /cases/stats e qualquer agregação nova DEVEM derivar destas quatro
# definições. Não escreva `total - encerrados` em lugar nenhum.
#
#   total geral     = deleted_at IS NULL                (inclui fechados)
#   total ativo     = deleted_at IS NULL AND status IN STATUS_ABERTOS
#   total arquivado = deleted_at IS NULL AND status = 'arquivado'
#   total excluído  = deleted_at IS NOT NULL            (só lixeira/diagnóstico)
#   listagem padrão = deleted_at IS NULL AND status <> 'arquivado'
#
# `listagem padrão` (o filtro `arquivo=ativos` de /cases/) é INTENCIONALMENTE
# mais larga que `total ativo`: ela mostra encerrados junto dos abertos. Essa
# diferença é conhecida e está registrada como Issue própria — não a mude aqui
# sem decisão de produto, sob pena de sumir casos das telas dos advogados.


def contar_ativos(por_status: dict[str, int]) -> int:
    """`ativos` a partir de um mapa status -> contagem (já sem excluídos)."""
    return sum(por_status.get(s.value, 0) for s in STATUS_ABERTOS)


# ── Visibilidade herdada pelo estado do caso ─────────────────────────────────
#
# ESCOLHA DE ARQUITETURA: herança de visibilidade, NÃO soft-delete em cascata.
#
# A exclusão lógica de um caso grava apenas `cases.deleted_at`; os dependentes
# (peças, documentos, prazos, tarefas) permanecem intactos. Em vez de propagar
# a exclusão — que mutaria registros que ninguém mandou excluir e exigiria
# marcação extra para restaurar exatamente os mesmos —, os dependentes HERDAM a
# visibilidade do pai nas superfícies OPERACIONAIS.
#
# Consequências desejadas:
#   • nenhum dado é alterado; auditoria e cadeia histórica ficam intactas;
#   • restaurar o caso restabelece os dependentes automaticamente e sem erro;
#   • a lixeira não é poluída com dezenas de filhos restauráveis isoladamente;
#   • a regra é reversível no código, sem migration e sem tocar em dados.
#
# NÃO aplique este filtro em trilha de auditoria, lixeira, exportação legal ou
# diagnóstico de integridade: lá o registro PRECISA continuar visível.

#: Subquery dos casos vivos. Uso: `LegalDoc.case_id.in_(CASOS_VIVOS)`.
CASOS_VIVOS = select(Case.id).where(Case.deleted_at.is_(None))

#: Mesmo predicado em SQL bruto, para as agregações que ainda usam `text()`.
#: `{col}` recebe a coluna case_id qualificada (ex.: "ld.case_id").
SQL_CASO_VISIVEL = (
    "({col} IS NULL OR EXISTS "
    "(SELECT 1 FROM cases c_v WHERE c_v.id = {col} AND c_v.deleted_at IS NULL))"
)


def filtrar_pecas_visiveis(q: Select) -> Select:
    """Restringe a query de peças às operacionalmente visíveis.

    Peça sem `case_id` (minuta avulsa) é estado LEGÍTIMO e continua visível —
    não confundir com peça de caso excluído.
    """
    return q.where(
        or_(LegalDoc.case_id.is_(None), LegalDoc.case_id.in_(CASOS_VIVOS))
    )


# ── Fila de revisão humana (HITL) ────────────────────────────────────────────

#: Peça protocolada é terminal: não volta para a fila de revisão.
STATUS_PECA_TERMINAIS: tuple[PecaStatus, ...] = (PecaStatus.protocolada,)


def filtrar_aguardando_revisao(q: Select) -> Select:
    """Peças que ainda precisam de revisão humana.

    Responde à pergunta operacional "quantas peças ativas e não excluídas ainda
    precisam de revisão humana?".

    Critério: peça viva, gerada por IA (o HITL é obrigatório justamente para
    essas), ainda não revisada por humano e não terminal.

    NÃO filtra por `rascunho`: a IA entrega a peça EM rascunho, então excluir
    esse status zerava o indicador — era a causa exata do contador em 0 com 22
    peças pendentes na fila.
    """
    return filtrar_pecas_visiveis(
        q.where(
            LegalDoc.deleted_at.is_(None),
            LegalDoc.ai_generated.is_(True),
            LegalDoc.human_reviewed.is_(False),
            LegalDoc.status.notin_(STATUS_PECA_TERMINAIS),
        )
    )
