"""Registro de homologação das ferramentas jurídicas (calculadoras de ramos).

Motivo (auditoria 2026-07-26): o caminho `regra errada → resultado plausível →
documento formal → uso externo` era o risco mais grave do sistema. Qualquer
calculadora podia virar um "Demonstrativo de Cálculo" salvo em Peças sem que
alguém tivesse validado a regra que produziu o número.

Este módulo é o artefato VERSIONADO dessa validação:

- O cálculo NUNCA é bloqueado — a ferramenta continua servindo como apoio, com
  os avisos de MINUTA que já existem.
- A MATERIALIZAÇÃO em documento formal (POST /pecas/demonstrativo) exige status
  `homologada`.
- FAIL-CLOSED: ferramenta ausente deste registro é tratada como NÃO homologada.
  Uma calculadora nova nasce bloqueada para geração de documento.

Promover uma ferramenta a `homologada` é ATO DO ADVOGADO RESPONSÁVEL, não do
desenvolvedor: conferir a regra contra a fonte legal vigente, registrar quem
revisou e quando, e alterar o status aqui — a mudança fica no histórico do git,
auditável, como a auditoria exigiu ("regras jurídicas como artefatos
versionados").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StatusHomologacao = Literal["homologada", "em_revisao", "bloqueada"]


@dataclass(frozen=True)
class Homologacao:
    status: StatusHomologacao
    # Preenchidos no ato da homologação jurídica (nome/OAB e data ISO).
    revisado_por: str | None = None
    revisado_em: str | None = None
    nota: str | None = None


# Chave = path do endpoint da ferramenta (único; o `id` se repete entre ramos).
#
# ESTADO ATUAL: nenhuma ferramenta homologada. As regras P0 apontadas pela
# auditoria foram CORRIGIDAS e cobertas por teste de regressão
# (tests/test_ramos_regras_juridicas_p0.py), mas correção técnica não substitui
# homologação jurídica — quem assina é o advogado responsável pela área.
_REGISTRO: dict[str, Homologacao] = {
    # ── Corrigidas na auditoria P0 de 26/07/2026 (aguardando homologação) ────
    "/civel/ferramentas/prazos-contestacao": Homologacao(
        "em_revisao", nota="Marcos revisados (CPC 335/183; JEC sem prazo em dias)."
    ),
    "/penal/ferramentas/prazos-processuais": Homologacao(
        "em_revisao", nota="Passou a contar dias contínuos da citação (CPP 396/798)."
    ),
    "/trabalhista-esp/ferramentas/prazos": Homologacao(
        "em_revisao", nota="Passou a dias úteis da intimação (CLT 775)."
    ),
    "/transito/ferramentas/prazos-recurso": Homologacao(
        "em_revisao", nota="Marcos próprios por fase (CTB 281/285/288)."
    ),
    "/admin-esp/ferramentas/recurso-multa-transito": Homologacao(
        "em_revisao", nota="Unificada com a ferramenta do ramo Trânsito."
    ),
    "/transito/ferramentas/pontuacao-cnh": Homologacao(
        "em_revisao", nota="EAR corrigido para 40 pontos (CTB 261)."
    ),
    "/empresarial/ferramentas/prazos-rj": Homologacao(
        "em_revisao", nota="Marco = deferimento do processamento (Lei 11.101/05 art. 53)."
    ),
    "/empresarial/ferramentas/verificar-cade": Homologacao(
        "em_revisao", nota="Removido 'prazo de 30 dias'; notificação é prévia."
    ),
    "/empresarial/ferramentas/juros-mora": Homologacao(
        "em_revisao", nota="Sem presunção de 1% a.m. (CC 406, Lei 14.905/2024)."
    ),
    "/consumidor/ferramentas/devolucao-dobro": Homologacao(
        "em_revisao", nota="Dobro não exige má-fé (STJ EAREsp 676.608)."
    ),
    "/consumidor/ferramentas/prazos-cdc": Homologacao(
        "em_revisao", nota="Repetição de indébito passou a decenal (EAREsp 738.991)."
    ),
    "/previdenciario/ferramentas/prazos": Homologacao(
        "em_revisao", nota="Marco próprio por tipo de prazo (Lei 8.213/91 art. 103)."
    ),
    "/previdenciario/ferramentas/tempo-contribuicao": Homologacao(
        "em_revisao", nota="Validação estrita de sexo (fim do startswith)."
    ),
    "/previdenciario/ferramentas/carencia": Homologacao(
        "em_revisao", nota="Carência por categoria do segurado (art. 26 VI)."
    ),
    # ── Pendências jurídicas conhecidas — NÃO promover sem rever a regra ─────
    "/civel/ferramentas/calculo-dano-moral": Homologacao(
        "bloqueada",
        nota="Faixas fixas sem amostra jurimétrica contextual; não há tabelamento legal.",
    ),
    "/civel/ferramentas/alimentos-calcular": Homologacao(
        "bloqueada",
        nota="Percentual não tem parâmetro legal fixo; depende do binômio do caso.",
    ),
}


def status_ferramenta(endpoint: str | None) -> Homologacao:
    """Status da ferramenta. Fail-closed: desconhecida = não homologada."""
    if not endpoint:
        return Homologacao("em_revisao", nota="Ferramenta não identificada na requisição.")
    return _REGISTRO.get(
        endpoint.rstrip("/"),
        Homologacao("em_revisao", nota="Ferramenta ainda não avaliada juridicamente."),
    )


def pode_gerar_documento(endpoint: str | None) -> bool:
    """Só ferramenta homologada materializa documento formal em Peças."""
    return status_ferramenta(endpoint).status == "homologada"


def mapa_status() -> dict[str, str]:
    """Mapa endpoint → status, consumido pela UI para sinalizar cada ferramenta."""
    return {k: v.status for k, v in _REGISTRO.items()}
