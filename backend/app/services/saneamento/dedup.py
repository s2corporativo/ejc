# ── app/services/saneamento/dedup.py ─────────────────────────────────────────
# Deduplicação de base processual.
#
# Três situações distintas que bases sujas costumam confundir:
#
#   1. DUPLICATA REAL — mesmo número CNJ (20 dígitos, após normalização).
#      Ação: colapsar em um registro, preservando a origem de cada cópia.
#
#   2. MESMO PROCESSO EM GRAUS DIFERENTES — numeração única idêntica, campo
#      `grau` distinto (G1/G2/...). NÃO é duplicata: é o mesmo processo em fase
#      recursal. Ação: relacionar, jamais fundir.
#
#   3. PROCESSOS CONEXOS COM NUMERAÇÃO DISTINTA — execução de sentença,
#      cautelar, embargos, ação conexa. Ação: apenas SUGERIR vínculo, com
#      confirmação humana obrigatória. Nunca fundir automaticamente.
#
# Registro cujo número não passa na validação do dígito verificador é ERRO DE
# DIGITAÇÃO, não duplicata: vai para fila de exceção.
#
# A validação do DV é a ÚNICA implementação canônica do projeto
# (validators_service.validar_cnj, que delega a
# verificador_jurisprudencia.validar_dv_cnj) — não reimplementada aqui, para
# não haver duas versões que possam divergir.
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.services.validators_service import normalizar_cnj, validar_cnj

__all__ = [
    "RegistroProcesso",
    "GrupoDuplicatas",
    "Excecao",
    "ResultadoDedup",
    "deduplicar",
    "sugerir_conexos",
]


@dataclass(slots=True)
class RegistroProcesso:
    """Uma linha da base interna do EJC."""

    id_interno: str
    numero: str
    grau: str | None = None
    cliente_id: str | None = None
    dados: dict[str, Any] = field(default_factory=dict)

    def completude(self) -> int:
        """Quantidade de campos preenchidos. Critério de escolha do sobrevivente."""
        base = sum(
            1 for v in (self.grau, self.cliente_id) if v not in (None, "")
        )
        return base + sum(1 for v in self.dados.values() if v not in (None, "", [], {}))


@dataclass(slots=True)
class GrupoDuplicatas:
    numero_canonico: str
    principal: RegistroProcesso
    absorvidos: list[RegistroProcesso] = field(default_factory=list)

    @property
    def total(self) -> int:
        return 1 + len(self.absorvidos)


@dataclass(slots=True)
class Excecao:
    registro: RegistroProcesso
    motivo: str


@dataclass(slots=True)
class ResultadoDedup:
    duplicatas: list[GrupoDuplicatas] = field(default_factory=list)
    graus_relacionados: dict[str, list[RegistroProcesso]] = field(default_factory=dict)
    unicos: list[RegistroProcesso] = field(default_factory=list)
    excecoes: list[Excecao] = field(default_factory=list)

    def resumo(self) -> dict[str, int]:
        return {
            "grupos_duplicados": len(self.duplicatas),
            "registros_absorviveis": sum(len(g.absorvidos) for g in self.duplicatas),
            "processos_multi_grau": len(self.graus_relacionados),
            "unicos": len(self.unicos),
            "excecoes": len(self.excecoes),
        }


def deduplicar(registros: Iterable[RegistroProcesso]) -> ResultadoDedup:
    """Agrupa por número canônico e separa duplicata real de multi-grau.

    Não altera nada: devolve o plano. A aplicação é decisão de quem revisa
    (POST /saneamento/duplicatas/{id}/aplicar).
    """
    resultado = ResultadoDedup()
    por_numero: dict[str, list[RegistroProcesso]] = defaultdict(list)

    for reg in registros:
        # Validação sobre o valor BRUTO (achado de revisão de código):
        # normalizar antes de validar deixa passar lixo com dígitos válidos
        # embutidos — "abc" + 20 dígitos corretos vira, após normalizar_cnj,
        # exatamente os 20 dígitos certos, e validar_cnj(bruto_já_normalizado)
        # aprova porque a essa altura já é puro dígito. validar_cnj recebe o
        # valor como o usuário digitou (aceita dígitos OU máscara oficial —
        # nunca pontuação arbitrária) e só então normalizamos para a chave
        # canônica de agrupamento.
        if not reg.numero:
            resultado.excecoes.append(Excecao(registro=reg, motivo="número vazio"))
            continue
        if not validar_cnj(reg.numero):
            resultado.excecoes.append(
                Excecao(registro=reg, motivo=f"número CNJ inválido (formato ou dígito verificador): {reg.numero!r}")
            )
            continue
        por_numero[normalizar_cnj(reg.numero)].append(reg)

    for numero, grupo in por_numero.items():
        if len(grupo) == 1:
            resultado.unicos.append(grupo[0])
            continue

        # Grau desconhecido (vazio/None) NÃO é descartado do conjunto: um
        # registro sem grau informado ao lado de um com grau conhecido pode
        # ser, precisamente, o grau que falta descobrir — tratar como
        # duplicata fundível aqui violaria "multi-grau nunca funde" (achado
        # de revisão de código). Só {grau único} OU {"" sozinho, ambos sem
        # informação} colapsa como duplicata real.
        graus = {(r.grau or "").strip() for r in grupo}

        if len(graus) > 1:
            # Mesmo processo, graus distintos (ou grau desconhecido ao lado
            # de um grau conhecido): relacionar, não fundir.
            resultado.graus_relacionados[numero] = list(grupo)
            continue

        # Duplicata real: mantém o registro mais completo; empate resolvido
        # de forma determinística pelo id_interno para reprodutibilidade.
        ordenado = sorted(grupo, key=lambda r: (-r.completude(), r.id_interno))
        resultado.duplicatas.append(
            GrupoDuplicatas(
                numero_canonico=numero,
                principal=ordenado[0],
                absorvidos=ordenado[1:],
            )
        )

    return resultado


def sugerir_conexos(
    registros: Iterable[RegistroProcesso],
    *,
    chave_partes: str = "partes_hash",
) -> list[tuple[RegistroProcesso, RegistroProcesso, str]]:
    """Sugere vínculo entre processos de numeração distinta.

    Heurística conservadora: mesmo órgão julgador E mesma assinatura de
    partes. Devolve pares com o motivo. NUNCA funde — a decisão é humana.

    A assinatura de partes precisa vir da base interna do EJC: o DataJud é
    base de metadados e NÃO retorna nomes de partes.
    """
    pares: list[tuple[RegistroProcesso, RegistroProcesso, str]] = []
    balde: dict[tuple[str, str], list[RegistroProcesso]] = defaultdict(list)

    for reg in registros:
        orgao = str(reg.dados.get("orgao_julgador") or "")
        partes = str(reg.dados.get(chave_partes) or "")
        if not orgao or not partes:
            continue
        balde[(orgao, partes)].append(reg)

    for (orgao, _partes), grupo in balde.items():
        if len(grupo) < 2:
            continue
        for i in range(len(grupo)):
            for j in range(i + 1, len(grupo)):
                a, b = grupo[i], grupo[j]
                if normalizar_cnj(a.numero) == normalizar_cnj(b.numero):
                    continue
                pares.append(
                    (a, b, f"mesmo órgão julgador ({orgao}) e mesmas partes")
                )
    return pares
