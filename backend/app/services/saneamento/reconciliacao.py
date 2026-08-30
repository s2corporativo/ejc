# ── app/services/saneamento/reconciliacao.py ─────────────────────────────────
# Reconciliação entre a base interna do EJC e o DataJud.
#
# Produz o painel de divergências. Toda divergência é APONTAMENTO, nunca
# correção automática: o DataJud é fonte de metadados oficial, mas tem
# latência de atualização variável por tribunal e não cobre processo em
# segredo de justiça — sobrescrever a base interna com ele às cegas
# introduziria erro em vez de removê-lo.
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["TipoDivergencia", "Divergencia", "RelatorioReconciliacao", "reconciliar"]


class TipoDivergencia(str, Enum):
    AUSENTE_NO_DATAJUD = "ausente_no_datajud"
    """Está na base interna, não retornou do DataJud. Causas prováveis:
    número errado, segredo de justiça, tribunal fora da cobertura, latência."""

    AUSENTE_NA_BASE = "ausente_na_base"
    """Retornou do DataJud e não existe na base interna."""

    CLASSE_DIVERGENTE = "classe_divergente"
    ORGAO_DIVERGENTE = "orgao_divergente"
    DATA_AJUIZAMENTO_DIVERGENTE = "data_ajuizamento_divergente"
    SIGILO = "sigilo"
    """nivelSigilo > 0 — tratamento restrito, não expor em relatório amplo."""


@dataclass(slots=True)
class Divergencia:
    numero: str
    tipo: TipoDivergencia
    valor_interno: Any = None
    valor_datajud: Any = None
    observacao: str = ""

    def para_dict(self) -> dict[str, Any]:
        return {
            "numero": self.numero,
            "tipo": self.tipo.value,
            "valor_interno": self.valor_interno,
            "valor_datajud": self.valor_datajud,
            "observacao": self.observacao,
        }


@dataclass(slots=True)
class RelatorioReconciliacao:
    divergencias: list[Divergencia] = field(default_factory=list)

    def resumo(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for d in self.divergencias:
            contagem[d.tipo.value] = contagem.get(d.tipo.value, 0) + 1
        return contagem


def _codigo(valor: Any) -> Any:
    if isinstance(valor, dict):
        return valor.get("codigo")
    return valor


def reconciliar(
    interno: dict[str, dict[str, Any]],
    datajud: dict[str, list[dict[str, Any]]],
) -> RelatorioReconciliacao:
    """`interno`: numero_canonico -> registro da base do EJC.
    `datajud`: numero_canonico -> lista de documentos retornados (um por grau).

    Compara apenas campos que o DataJud efetivamente retorna. Nome de parte,
    advogado e teor de peça NÃO existem na API pública e por isso não entram
    na reconciliação.
    """
    rel = RelatorioReconciliacao()

    for numero, reg in interno.items():
        docs = datajud.get(numero)
        if not docs:
            rel.divergencias.append(
                Divergencia(
                    numero=numero,
                    tipo=TipoDivergencia.AUSENTE_NO_DATAJUD,
                    valor_interno=reg.get("classe"),
                    observacao=(
                        "conferir número, segredo de justiça, cobertura do "
                        "tribunal ou latência de atualização"
                    ),
                )
            )
            continue

        # Usa o documento de menor grau como referência de cadastro.
        doc = sorted(docs, key=lambda d: str(d.get("grau") or "zz"))[0]

        if int(doc.get("nivelSigilo") or 0) > 0:
            rel.divergencias.append(
                Divergencia(
                    numero=numero,
                    tipo=TipoDivergencia.SIGILO,
                    valor_datajud=doc.get("nivelSigilo"),
                    observacao="tratamento restrito — não incluir em relatório amplo",
                )
            )
            # Acha de revisão de código: sem este `continue`, as comparações
            # de classe/órgão/data abaixo ainda rodavam para o MESMO
            # documento sob segredo de justiça e geravam outras linhas de
            # Divergencia com `valor_datajud` — o router só filtra
            # tipo==SIGILO, então esses metadados do processo sigiloso
            # vazavam de qualquer forma. Um processo sob segredo de justiça
            # não entra na reconciliação amplamente visível de jeito nenhum.
            continue

        classe_dj = _codigo(doc.get("classe"))
        classe_int = _codigo(reg.get("classe"))
        if classe_int and classe_dj and str(classe_int) != str(classe_dj):
            rel.divergencias.append(
                Divergencia(
                    numero=numero,
                    tipo=TipoDivergencia.CLASSE_DIVERGENTE,
                    valor_interno=classe_int,
                    valor_datajud=classe_dj,
                )
            )

        orgao_dj = _codigo(doc.get("orgaoJulgador"))
        orgao_int = _codigo(reg.get("orgao_julgador"))
        if orgao_int and orgao_dj and str(orgao_int) != str(orgao_dj):
            rel.divergencias.append(
                Divergencia(
                    numero=numero,
                    tipo=TipoDivergencia.ORGAO_DIVERGENTE,
                    valor_interno=orgao_int,
                    valor_datajud=orgao_dj,
                )
            )

        aj_dj = str(doc.get("dataAjuizamento") or "")[:10]
        aj_int = str(reg.get("data_ajuizamento") or "")[:10]
        if aj_int and aj_dj and aj_int != aj_dj:
            rel.divergencias.append(
                Divergencia(
                    numero=numero,
                    tipo=TipoDivergencia.DATA_AJUIZAMENTO_DIVERGENTE,
                    valor_interno=aj_int,
                    valor_datajud=aj_dj,
                )
            )

    for numero in datajud:
        if numero not in interno:
            rel.divergencias.append(
                Divergencia(
                    numero=numero,
                    tipo=TipoDivergencia.AUSENTE_NA_BASE,
                    observacao="processo no tribunal sem cadastro interno",
                )
            )

    return rel
