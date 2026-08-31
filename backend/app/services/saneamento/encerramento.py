# ── app/services/saneamento/encerramento.py ──────────────────────────────────
# Indicativo de encerramento.
#
# REGRA INEGOCIÁVEL: este módulo SINALIZA, nunca decide. Nenhum processo é
# marcado como encerrado sem confirmação de advogado registrada em log de
# auditoria (POST /saneamento/indicativos/{id}/decidir). Encerramento indevido
# destrói o controle de prazo e gera risco disciplinar (Lei 8.906/1994, art.
# 34, IX — infração disciplinar por prejudicar, por locupletação ou
# negligência, causa confiada ao advogado).
#
# Critério composto (todos os fatores precisam concordar):
#
#     candidato = movimento terminativo presente
#                 E ausência de movimento reativador posterior a ele
#                 E ausência de movimento suspensivo vigente
#                 E silêncio superior a N dias desde o último movimento
#
# O parâmetro N é configurável. O padrão sugerido (180 dias) é conservador e
# deve ser calibrado por área — execução fiscal e trabalhista têm dinâmicas
# diferentes.
#
# Quando a classe de um movimento é desconhecida (código ainda não revisado na
# TPU), o módulo REBAIXA a confiança em vez de assumir. Falso negativo é
# barato; falso positivo custa prazo.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Iterable

from .tpu import CatalogoTPU, ClasseMovimento

__all__ = [
    "Confianca",
    "Movimento",
    "Indicativo",
    "avaliar_encerramento",
    "extrair_movimentos",
]

DIAS_SILENCIO_PADRAO = 180


class Confianca(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"
    NENHUMA = "nenhuma"


@dataclass(frozen=True, slots=True)
class Movimento:
    codigo: int | None
    nome: str
    data: datetime


@dataclass(slots=True)
class Indicativo:
    numero: str
    candidato: bool
    confianca: Confianca
    motivos: list[str] = field(default_factory=list)
    ultimo_movimento: Movimento | None = None
    dias_de_silencio: int | None = None
    movimento_terminativo: Movimento | None = None
    exige_revisao_humana: bool = True  # sempre

    def para_dict(self) -> dict[str, Any]:
        return {
            "numero": self.numero,
            "candidato_a_encerramento": self.candidato,
            "confianca": self.confianca.value,
            "motivos": self.motivos,
            "dias_de_silencio": self.dias_de_silencio,
            "ultimo_movimento": (
                {
                    "codigo": self.ultimo_movimento.codigo,
                    "nome": self.ultimo_movimento.nome,
                    "data": self.ultimo_movimento.data.isoformat(),
                }
                if self.ultimo_movimento
                else None
            ),
            "movimento_terminativo": (
                {
                    "codigo": self.movimento_terminativo.codigo,
                    "nome": self.movimento_terminativo.nome,
                    "data": self.movimento_terminativo.data.isoformat(),
                }
                if self.movimento_terminativo
                else None
            ),
            "exige_revisao_humana": True,
        }


def _para_datetime(valor: Any) -> datetime | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day, tzinfo=timezone.utc)
    texto = str(valor).strip()
    if not texto:
        return None
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def extrair_movimentos(doc: dict[str, Any]) -> list[Movimento]:
    """Lê o campo `movimentos` de um documento do DataJud.

    Campos observados na documentação: `codigo`, `nome`, `dataHora`.
    Movimentos sem data utilizável são descartados — não dá para medir
    silêncio contra data ausente.
    """
    saida: list[Movimento] = []
    for m in doc.get("movimentos") or []:
        dt = _para_datetime(m.get("dataHora") or m.get("data_hora") or m.get("data"))
        if dt is None:
            continue
        codigo = m.get("codigo")
        try:
            codigo_int = int(codigo) if codigo is not None else None
        except (TypeError, ValueError):
            codigo_int = None
        saida.append(
            Movimento(codigo=codigo_int, nome=str(m.get("nome") or ""), data=dt)
        )
    saida.sort(key=lambda x: x.data)
    return saida


def avaliar_encerramento(
    numero: str,
    movimentos: Iterable[Movimento],
    catalogo: CatalogoTPU,
    *,
    dias_silencio: int = DIAS_SILENCIO_PADRAO,
    referencia: datetime | None = None,
) -> Indicativo:
    """Avalia se o processo é candidato a encerramento.

    Retorna sempre um Indicativo — nunca aplica mudança de estado.
    """
    agora = referencia or datetime.now(timezone.utc)
    movs = sorted(movimentos, key=lambda m: m.data)

    if not movs:
        return Indicativo(
            numero=numero,
            candidato=False,
            confianca=Confianca.NENHUMA,
            motivos=["sem movimentos com data utilizável"],
        )

    ultimo = movs[-1]
    silencio = (agora - ultimo.data).days

    terminativo: Movimento | None = None
    for m in reversed(movs):
        if catalogo.classe_de(m.codigo) is ClasseMovimento.TERMINATIVO:
            terminativo = m
            break

    motivos: list[str] = []

    if terminativo is None:
        motivos.append("nenhum movimento terminativo identificado na TPU")
        return Indicativo(
            numero=numero,
            candidato=False,
            confianca=Confianca.NENHUMA,
            motivos=motivos,
            ultimo_movimento=ultimo,
            dias_de_silencio=silencio,
        )

    posteriores = [m for m in movs if m.data > terminativo.data]

    reativadores = [
        m for m in posteriores
        if catalogo.classe_de(m.codigo) is ClasseMovimento.REATIVADOR
    ]
    if reativadores:
        motivos.append(
            f"movimento reativador posterior ao terminativo: "
            f"{reativadores[-1].codigo} — {reativadores[-1].nome}"
        )
        return Indicativo(
            numero=numero,
            candidato=False,
            confianca=Confianca.NENHUMA,
            motivos=motivos,
            ultimo_movimento=ultimo,
            dias_de_silencio=silencio,
            movimento_terminativo=terminativo,
        )

    suspensivos = [
        m for m in posteriores
        if catalogo.classe_de(m.codigo) is ClasseMovimento.SUSPENSIVO
    ]
    if suspensivos:
        motivos.append(
            f"movimento suspensivo vigente: "
            f"{suspensivos[-1].codigo} — {suspensivos[-1].nome}"
        )
        return Indicativo(
            numero=numero,
            candidato=False,
            confianca=Confianca.NENHUMA,
            motivos=motivos,
            ultimo_movimento=ultimo,
            dias_de_silencio=silencio,
            movimento_terminativo=terminativo,
        )

    if silencio < dias_silencio:
        motivos.append(
            f"silêncio de {silencio} dias, abaixo do limiar de {dias_silencio}"
        )
        return Indicativo(
            numero=numero,
            candidato=False,
            confianca=Confianca.BAIXA,
            motivos=motivos,
            ultimo_movimento=ultimo,
            dias_de_silencio=silencio,
            movimento_terminativo=terminativo,
        )

    motivos.append(
        f"movimento terminativo {terminativo.codigo} — {terminativo.nome} "
        f"em {terminativo.data.date().isoformat()}"
    )
    motivos.append(f"silêncio de {silencio} dias desde o último movimento")

    # Rebaixa a confiança se houver códigos ainda não revisados após o
    # terminativo: podem ser reativadores que o catálogo ainda não conhece.
    nao_classificados = [
        m for m in posteriores
        if catalogo.classe_de(m.codigo) is ClasseMovimento.NAO_CLASSIFICADO
    ]
    if nao_classificados:
        motivos.append(
            f"{len(nao_classificados)} movimento(s) posterior(es) com código TPU "
            "ainda não classificado — confiança rebaixada"
        )
        confianca = Confianca.MEDIA
    else:
        confianca = Confianca.ALTA

    return Indicativo(
        numero=numero,
        candidato=True,
        confianca=confianca,
        motivos=motivos,
        ultimo_movimento=ultimo,
        dias_de_silencio=silencio,
        movimento_terminativo=terminativo,
    )
