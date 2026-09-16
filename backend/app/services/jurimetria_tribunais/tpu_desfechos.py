"""Desfecho processual a partir dos códigos de movimento da TPU (CNJ/SGT).

FONTE E VERIFICAÇÃO — não editar códigos sem repetir a verificação:
  Sistema de Gestão de Tabelas do CNJ (SGT), web service público
  ``pesquisarItemPublicoWS``/``getArrayFilhosItemPublicoWS``/
  ``getArrayDetalhesItemPublicoWS``, versão da tabela **26/05/2026**,
  consultado em 05/09/2026 via ``app.integrations.cnj_sgt_client``.
  Cada código abaixo foi confirmado item a item (nome e glossário).

O glossário do SGT fixa a semântica que este módulo respeita:
  • 219/220/221 registram a solução "NO JUÍZO ORIGINÁRIO"; em instância
    recursal o SGT manda usar 237/238/239. Por isso a classificação de mérito
    só olha registros de 1º grau, e a de reforma só olha registros de 2º grau.
  • 220 (improcedência) NÃO inclui extinção sem resolução de mérito: "devem
    ser registrados no grupo próprio" — o grupo 456, cujos filhos estão em
    ``SEM_MERITO``.
  • 466 aplica-se "aos casos em que a transação homologada efetivamente põe
    fim à demanda" — é o acordo terminativo.
  • 12451/12453 ("Julgada (im)procedente a impugnação à execução") NÃO são
    desfecho da ação principal e ficam fora de propósito.

O desfecho é um PROXY: depende da disciplina de codificação de cada vara.
Quem consome deve exibir sempre o ``n`` e a data da coleta.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

TPU_VERSAO = "26/05/2026"
TPU_FONTE = (
    "SGT/CNJ — pesquisarItemPublicoWS (tabela de movimentos, Justiça Estadual), "
    f"versão {TPU_VERSAO}, verificada em 05/09/2026"
)

# ── 1º grau: mérito ─────────────────────────────────────────────────────────
PROCEDENCIA = "procedencia"
PROCEDENCIA_PARCIAL = "procedencia_parcial"
IMPROCEDENCIA = "improcedencia"
ACORDO = "acordo"
SEM_MERITO = "sem_resolucao_merito"

MERITO_1GRAU: dict[int, str] = {
    219: PROCEDENCIA,           # Julgado procedente o pedido
    221: PROCEDENCIA_PARCIAL,   # Julgado procedente em parte o pedido
    220: IMPROCEDENCIA,         # Julgado improcedente o pedido
}

# Juizado Especial: julgamento conjunto do pedido e do pedido contraposto.
# A classificação segue o PEDIDO DO AUTOR (primeira metade do nome do item).
JEC_PEDIDO_CONTRAPOSTO: dict[int, str] = {
    11402: PROCEDENCIA,          # Procedência do pedido e procedência em parte do contraposto
    11403: PROCEDENCIA,          # Procedência do pedido e improcedência do contraposto
    11404: PROCEDENCIA_PARCIAL,  # Procedência em parte do pedido e procedência do contraposto
    11405: PROCEDENCIA_PARCIAL,  # Procedência em parte do pedido e procedência em parte do contraposto
    11406: PROCEDENCIA_PARCIAL,  # Procedência em parte do pedido e improcedência do contraposto
    11407: IMPROCEDENCIA,        # Improcedência do pedido e procedência do contraposto
    11408: IMPROCEDENCIA,        # Improcedência do pedido e procedência em parte do contraposto
    11409: IMPROCEDENCIA,        # Improcedência do pedido e improcedência do contraposto
}

ACORDO_1GRAU: dict[int, str] = {
    466: ACORDO,                 # Homologada a Transação (CPC 269, III)
}

# Grupo 456 "Extinção" e seus filhos cíveis ativos/inativos, conforme
# getArrayFilhosItemPublicoWS(456). Os filhos socioeducativos (15250, 15249,
# 15245) ficam fora: não são desfecho cível.
SEM_MERITO_CODIGOS: frozenset[int] = frozenset({
    456,    # Extinção (grupo)
    454,    # Indeferimento da petição inicial
    457,    # Paralisação por negligência das partes
    458,    # Abandono da causa
    459,    # Ausência de pressupostos processuais
    460,    # Perempção, litispendência ou coisa julgada
    461,    # Ausência das condições da ação
    462,    # Convenção de arbitragem
    463,    # Desistência
    464,    # Ação intransmissível
    465,    # Confusão entre autor e réu (situação I)
    11374,  # Devedor não encontrado
    11375,  # Inexistência de bens penhoráveis
    11376,  # Ausência do autor à audiência
    11377,  # Inadmissibilidade do procedimento sumaríssimo
    11378,  # Incompetência territorial
    11379,  # Incompetência em razão da pessoa
    11380,  # Autor falecido e sem habilitação de sucessores
    11381,  # Ausência de citação de sucessores do réu falecido
    12256,  # Continência
    12298,  # Cancelamento de Dívida Ativa
    12325,  # Perda do objeto
    12617,  # Renúncia (situação I)
    14848,  # Ausência de Requerimento Administrativo Prévio
})

DESFECHO_1GRAU: dict[int, str] = {
    **MERITO_1GRAU,
    **JEC_PEDIDO_CONTRAPOSTO,
    **ACORDO_1GRAU,
    **{c: SEM_MERITO for c in SEM_MERITO_CODIGOS},
}

# ── 2º grau: resultado do recurso ───────────────────────────────────────────
PROVIMENTO = "provimento"
PROVIMENTO_PARCIAL = "provimento_parcial"
NAO_PROVIMENTO = "nao_provimento"

RECURSAL_2GRAU: dict[int, str] = {
    237: PROVIMENTO,          # Conhecido o recurso e provido
    238: PROVIMENTO_PARCIAL,  # Conhecido o recurso e provido em parte
    239: NAO_PROVIMENTO,      # Conhecido o recurso e não-provido
    240: PROVIMENTO,          # Conhecimento em Parte e Provimento ou Concessão
    241: PROVIMENTO_PARCIAL,  # Conhecimento em Parte e Provimento em Parte ou Concessão em Parte
    242: NAO_PROVIMENTO,      # Conhecimento em Parte e Não-Provimento ou Denegação
    972: PROVIMENTO,          # Provimento Monocrático (CPC 932, V)
    901: NAO_PROVIMENTO,      # Negação Monocrática de Provimento (CPC 932, IV)
}

# "Reforma" = o tribunal alterou a sentença (provimento total ou parcial).
REFORMA = frozenset({PROVIMENTO, PROVIMENTO_PARCIAL})


def _parse_data(valor: Any) -> datetime | None:
    if not valor:
        return None
    texto = str(valor).strip()
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        try:
            dt = datetime.strptime(texto[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _codigo(mov: dict) -> int | None:
    bruto = mov.get("codigo")
    try:
        return int(bruto)
    except (TypeError, ValueError):
        return None


def _ultimo_em(movimentos: list[dict], tabela: dict[int, str]) -> tuple[str, datetime | None] | None:
    """Último movimento (por dataHora) cujo código está em ``tabela``.

    O ÚLTIMO, não o primeiro: sentença anulada e refeita, embargos acolhidos
    etc. deixam mais de um registro; o vigente é o mais recente.
    """
    candidatos: list[tuple[datetime, str]] = []
    sem_data: list[str] = []
    for mov in movimentos or []:
        cod = _codigo(mov)
        if cod is None or cod not in tabela:
            continue
        dt = _parse_data(mov.get("dataHora"))
        if dt is None:
            sem_data.append(tabela[cod])
        else:
            candidatos.append((dt, tabela[cod]))
    if candidatos:
        dt, rotulo = max(candidatos, key=lambda x: x[0])
        return rotulo, dt
    if sem_data:
        return sem_data[-1], None
    return None


def desfecho_1grau(movimentos: list[dict]) -> tuple[str, datetime | None] | None:
    """(desfecho, data) do juízo originário, ou None se ainda não há desfecho."""
    return _ultimo_em(movimentos, DESFECHO_1GRAU)


def resultado_recursal(movimentos: list[dict]) -> tuple[str, datetime | None] | None:
    """(resultado, data) do julgamento do recurso em 2º grau, ou None."""
    return _ultimo_em(movimentos, RECURSAL_2GRAU)
