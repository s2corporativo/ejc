#!/usr/bin/env python3
"""Lógica PURA de curadoria da reclassificação de área dos casos históricos.

Sem banco, sem I/O, sem argparse — só decisão, para poder ser testada sem
Postgres. A casca operacional (conexão, transação, relatório, rollback) é
``scripts/reclassificar_areas_casos.py``.

────────────────────────────────────────────────────────────────────────────
O PROBLEMA
────────────────────────────────────────────────────────────────────────────
Até o commit b073d5f o frontend achatava a área do caso: o hub "Bancário"
gravava ``civil``; imobiliário e trânsito idem; ``digital_lgpd`` virava
``empresarial`` e ``administrativo`` virava ``tributario`` — embora os cinco
valores existam no enum ``CaseArea``/``casearea`` desde a migration 083.
Casos NOVOS já nascem certos. Os históricos seguem com a área antiga.

────────────────────────────────────────────────────────────────────────────
POR QUE ISTO É CURADORIA E NÃO UM UPDATE
────────────────────────────────────────────────────────────────────────────
Olhando só ``cases.area`` NÃO existe forma de saber se um caso ``civil`` é
bancário, imobiliário, de trânsito ou civil de verdade. O único sinal por caso
é o registro especializado vinculado (satélite), e ele só existe para DOIS dos
cinco achatamentos:

  hub            satélite            área pré-correção   área canônica
  ─────────────  ──────────────────  ──────────────────  ──────────────
  Bancário       bancario_cases      civil               bancario      ← sinal
  Administrativo admin_cases         tributario          administrativo ← sinal
  Imobiliário    (nenhum)            civil               imobiliario   ← SEM sinal
  Trânsito       (nenhum)            civil               transito      ← SEM sinal
  Digital/LGPD   (nenhum)            empresarial         digital_lgpd  ← SEM sinal

Os hubs de imobiliário, trânsito e digital/LGPD criam CASO SIMPLES
(``endpoint: "/cases/?area=..."`` em ramosConfig.ts) — nenhuma tabela satélite
os distingue de um caso civil/empresarial genuíno. Para esses três, este script
NÃO propõe nada: eles saem como ambíguos/sem sinal, para decisão humana.
O ROPA da LGPD (``lgpd_registros_tratamento``) é por CLIENTE, não por caso, e
portanto também não serve de sinal.

────────────────────────────────────────────────────────────────────────────
DISCRIMINAÇÃO DO SATÉLITE admin_cases
────────────────────────────────────────────────────────────────────────────
``admin_cases`` é reusado por TRÊS hubs (ramosConfig.ts): Administrativo
(area=administrativo), Tributário (area=tributario) e Ambiental
(area=ambiental). Logo "caso tributário com admin_cases" NÃO basta: pode ter
nascido no hub Tributário (e estar certo). O que discrimina é o ``tipo``: os
tipos oferecidos SÓ pelo hub Administrativo provam a origem. Tipos que os hubs
compartilham (``recurso_multa_tributaria``, ``recurso_multa_sanitaria``,
``recurso_autuacao_mte``, ``mandado_seguranca_admin``, ``outro_admin``) são
ambíguos por construção e nunca viram proposta automática.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence


# ── Achatamentos conhecidos ───────────────────────────────────────────────────
# Inverso de `areasLegadas` em frontend/src/pages/ramos/ramosConfig.ts. É o
# ÚNICO mandato deste script: desfazer estes achatamentos. Divergência de área
# fora deste mapa é assunto de outra decisão — aqui é ignorada de propósito.
DE_ACHATAMENTO: dict[str, tuple[str, ...]] = {
    "civil":       ("bancario", "imobiliario", "transito"),
    "tributario":  ("administrativo",),
    "empresarial": ("digital_lgpd",),
}

# Alvos para os quais existe sinal por caso. Os demais alvos do mapa acima
# (imobiliario, transito, digital_lgpd) só podem sair por decisão humana.
ALVOS_COM_SINAL: frozenset[str] = frozenset({"bancario", "administrativo"})

# ── Tipos de admin_cases por hub (ramosConfig.ts, campo `tipo`) ──────────────
TIPOS_HUB_ADMINISTRATIVO: frozenset[str] = frozenset({
    "recurso_multa_transito", "recurso_multa_ambiental",
    "recurso_multa_tributaria", "recurso_multa_sanitaria",
    "recurso_autuacao_mte", "improbidade_administrativa",
    "mandado_seguranca_admin", "servidor_publico", "desapropriacao",
    "indenizacao_estado", "licenca_negada_admin", "contrato_administrativo",
    "outro_admin",
})
TIPOS_HUB_TRIBUTARIO: frozenset[str] = frozenset({
    "recurso_multa_tributaria", "recurso_multa_sanitaria",
    "recurso_autuacao_mte", "mandado_seguranca_admin", "outro_admin",
})
TIPOS_HUB_AMBIENTAL: frozenset[str] = frozenset({
    "recurso_multa_ambiental", "mandado_seguranca_admin", "outro_admin",
})
# Tipos que SÓ o hub Administrativo oferece → provam a origem do satélite.
TIPOS_EXCLUSIVOS_ADMINISTRATIVO: frozenset[str] = frozenset(
    TIPOS_HUB_ADMINISTRATIVO - TIPOS_HUB_TRIBUTARIO - TIPOS_HUB_AMBIENTAL
)

# Satélite → área canônica do hub que o cria (backend/app/models/especializado.py
# + endpoint de cada hub em ramosConfig.ts).
AREA_DO_SATELITE: dict[str, str] = {
    "civel_cases":       "civil",
    "empresarial_cases": "empresarial",
    "penal_cases":       "criminal",
    "trabalhista_cases": "trabalhista",
    "bancario_cases":    "bancario",
}


# ── Níveis de confiança ──────────────────────────────────────────────────────
class Nivel:
    """Ordem de força do sinal. Só ALTA é elegível a ``--aplicar``."""

    ALTA = "alta"            # satélite determina a área sem ambiguidade
    MEDIA = "media"          # sinal existe mas é circunstancial → revisão humana
    AMBIGUA = "ambigua"      # sinais conflitantes ou insuficientes → humano
    SEM_SINAL = "sem_sinal"  # nada distingue: indistinguível por dado
    CONFIRMADO = "confirmado"  # satélite confirma a área atual → não mexer

    ELEGIVEIS_A_APLICAR = frozenset({ALTA})
    #: níveis que valem enumerar caso a caso no relatório (os outros só contam)
    ENUMERAVEIS = (ALTA, MEDIA, AMBIGUA)
    ORDEM = (ALTA, MEDIA, AMBIGUA, SEM_SINAL, CONFIRMADO)


@dataclass(frozen=True)
class CasoBruto:
    """Uma linha do SELECT de candidatos. Sem PII: id, área e sinais.

    ``titulo`` é opcional e só é preenchido com ``--incluir-titulo`` (dado do
    escritório — ver aviso no relatório).
    """

    case_id: str
    area: str
    tem_bancario_esp: bool = False
    tem_civel_esp: bool = False
    tem_empresarial_esp: bool = False
    tem_penal_esp: bool = False
    tem_trabalhista_esp: bool = False
    admin_tipos: tuple[str, ...] = ()
    qtd_analises_bancarias: int = 0
    areas_principais_declaradas: tuple[str, ...] = ()
    titulo: str | None = None


@dataclass(frozen=True)
class Sinal:
    """Evidência achada num caso. ``alvo`` é a área que a evidência aponta."""

    alvo: str
    nivel: str
    regra: str
    evidencia: str


@dataclass(frozen=True)
class Decisao:
    case_id: str
    area_atual: str
    area_nova: str | None
    nivel: str
    regra: str
    evidencia: str
    titulo: str | None = None

    @property
    def elegivel(self) -> bool:
        return self.nivel in Nivel.ELEGIVEIS_A_APLICAR and bool(self.area_nova)


def _sinais(caso: CasoBruto, alvos: Sequence[str]) -> list[Sinal]:
    """Levanta toda a evidência do caso, sem ainda decidir nada."""
    achados: list[Sinal] = []

    # ── Satélite bancário: criado SÓ pelo hub Bancário (POST /bancario).
    # É uma declaração humana feita dentro daquele hub — o sinal mais forte.
    if caso.tem_bancario_esp:
        achados.append(Sinal(
            alvo="bancario", nivel=Nivel.ALTA, regra="satelite_bancario",
            evidencia="bancario_cases vinculado",
        ))

    # ── Satélite administrativo: discriminado pelo tipo (ver docstring).
    if caso.admin_tipos:
        exclusivos = sorted(set(caso.admin_tipos) & TIPOS_EXCLUSIVOS_ADMINISTRATIVO)
        if exclusivos:
            achados.append(Sinal(
                alvo="administrativo", nivel=Nivel.ALTA,
                regra="satelite_admin_tipo_exclusivo",
                evidencia=f"admin_cases tipo={','.join(exclusivos)}",
            ))
        else:
            compartilhados = sorted(set(caso.admin_tipos))
            achados.append(Sinal(
                alvo="administrativo", nivel=Nivel.AMBIGUA,
                regra="satelite_admin_tipo_compartilhado",
                evidencia=(
                    f"admin_cases tipo={','.join(compartilhados)} — tipo também "
                    "oferecido pelo hub Tributário/Ambiental"
                ),
            ))

    # ── Análise de extrato: circunstancial. Um extrato pode ser prova em caso
    # de família, consumidor ou sucessões — não prova que o caso é bancário.
    if caso.qtd_analises_bancarias and not caso.tem_bancario_esp:
        achados.append(Sinal(
            alvo="bancario", nivel=Nivel.MEDIA, regra="analise_extrato",
            evidencia=f"{caso.qtd_analises_bancarias} análise(s) em bank_analyses",
        ))

    # ── caso_areas.principal divergente. Pode ter vindo de curadoria humana
    # (POST /cases/{id}/areas) OU da classificação por IA na materialização de
    # caso (routers/cases.py) — por isso nunca é ALTA. Só consideramos valores
    # dentro do mandato de de-achatamento.
    for area_decl in caso.areas_principais_declaradas:
        if area_decl != caso.area and area_decl in alvos:
            achados.append(Sinal(
                alvo=area_decl, nivel=Nivel.MEDIA, regra="caso_areas_principal",
                evidencia=f"caso_areas.principal={area_decl}",
            ))

    # ── Contraevidência: satélites de outros hubs. O hub Cível grava `civil`
    # hoje e continuará gravando — um civel_cases CONFIRMA `civil`, não é
    # candidato a virar imobiliário mesmo com tipo `imobiliario_locacao`.
    presentes = {
        "civel_cases": caso.tem_civel_esp,
        "empresarial_cases": caso.tem_empresarial_esp,
        "penal_cases": caso.tem_penal_esp,
        "trabalhista_cases": caso.tem_trabalhista_esp,
    }
    for tabela, presente in presentes.items():
        if presente:
            achados.append(Sinal(
                alvo=AREA_DO_SATELITE[tabela], nivel=Nivel.ALTA,
                regra=f"satelite_{tabela}", evidencia=f"{tabela} vinculado",
            ))

    return achados


def classificar_caso(caso: CasoBruto) -> Decisao:
    """Decide o destino de UM caso. Nunca escreve; nunca levanta exceção."""
    alvos = DE_ACHATAMENTO.get(caso.area)
    if not alvos:
        # Área já canônica (ou fora do mapa de achatamento) → nada a fazer.
        # É isto que torna o script idempotente: depois de aplicado, o caso
        # está em `bancario`/`administrativo` e nunca mais é selecionado.
        return Decisao(
            case_id=caso.case_id, area_atual=caso.area, area_nova=None,
            nivel=Nivel.CONFIRMADO, regra="area_fora_do_mapa_de_achatamento",
            evidencia=f"área '{caso.area}' não é uma das áreas achatadas",
            titulo=caso.titulo,
        )

    achados = _sinais(caso, alvos)
    propositivos = [s for s in achados if s.alvo in alvos]
    contra = [s for s in achados if s.alvo not in alvos]

    def _mk(area_nova, nivel, regra, evidencia) -> Decisao:
        return Decisao(
            case_id=caso.case_id, area_atual=caso.area, area_nova=area_nova,
            nivel=nivel, regra=regra, evidencia=evidencia, titulo=caso.titulo,
        )

    if not propositivos:
        if not contra:
            return _mk(
                None, Nivel.SEM_SINAL, "sem_sinal",
                f"nenhum registro especializado — '{caso.area}' pode ser "
                f"legítimo ou qualquer um de {', '.join(alvos)}",
            )
        if all(s.alvo == caso.area for s in contra):
            return _mk(
                None, Nivel.CONFIRMADO, "satelite_confirma_area_atual",
                "; ".join(s.evidencia for s in contra),
            )
        return _mk(
            None, Nivel.AMBIGUA, "sinal_fora_do_mandato",
            "; ".join(f"{s.evidencia} → {s.alvo}" for s in contra),
        )

    alvos_propostos = sorted({s.alvo for s in propositivos})
    if len(alvos_propostos) > 1 or contra:
        partes = [f"{s.evidencia} → {s.alvo}" for s in propositivos + contra]
        return _mk(
            None, Nivel.AMBIGUA, "sinais_conflitantes", "; ".join(partes),
        )

    alvo = alvos_propostos[0]
    niveis = {s.nivel for s in propositivos}
    if Nivel.AMBIGUA in niveis:
        nivel = Nivel.AMBIGUA
    elif Nivel.ALTA in niveis:
        nivel = Nivel.ALTA
    else:
        nivel = Nivel.MEDIA
    fortes = [s for s in propositivos if s.nivel == nivel] or propositivos
    return _mk(
        alvo if nivel != Nivel.AMBIGUA else None,
        nivel,
        fortes[0].regra,
        "; ".join(s.evidencia for s in propositivos),
    )


def classificar(casos: Iterable[CasoBruto]) -> list[Decisao]:
    """Classifica em lote, com ordem determinística (por case_id)."""
    return sorted(
        (classificar_caso(c) for c in casos), key=lambda d: d.case_id
    )


# ── Resumo para o relatório ──────────────────────────────────────────────────
@dataclass
class Resumo:
    total_analisado: int = 0
    por_nivel: dict[str, int] = field(default_factory=dict)
    por_transicao: dict[tuple[str, str], int] = field(default_factory=dict)
    por_regra: dict[str, int] = field(default_factory=dict)
    elegiveis: list[Decisao] = field(default_factory=list)
    revisar: list[Decisao] = field(default_factory=list)

    @property
    def total_elegivel(self) -> int:
        return len(self.elegiveis)


def resumir(decisoes: Sequence[Decisao]) -> Resumo:
    r = Resumo(total_analisado=len(decisoes))
    for d in decisoes:
        r.por_nivel[d.nivel] = r.por_nivel.get(d.nivel, 0) + 1
        r.por_regra[d.regra] = r.por_regra.get(d.regra, 0) + 1
        if d.area_nova:
            chave = (d.area_atual, d.area_nova)
            r.por_transicao[chave] = r.por_transicao.get(chave, 0) + 1
        if d.elegivel:
            r.elegiveis.append(d)
        elif d.nivel in (Nivel.MEDIA, Nivel.AMBIGUA):
            r.revisar.append(d)
    return r


def selecionar_para_aplicar(
    decisoes: Sequence[Decisao], limite: int | None = None
) -> list[Decisao]:
    """Só ALTA com destino definido, em ordem determinística."""
    elegiveis = [d for d in decisoes if d.elegivel]
    return elegiveis[:limite] if limite is not None else elegiveis
