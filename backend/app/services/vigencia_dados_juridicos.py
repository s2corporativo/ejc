# ── app/services/vigencia_dados_juridicos.py ─────────────────────────────────
# ALARME DE ENVELHECIMENTO dos dados jurídicos EMBUTIDOS no código.
#
# Achado P2-13 da auditoria de IA (2026-08-18): algumas verdades jurídicas do
# sistema não vivem no banco nem em fonte oficial consultada em tempo real —
# são constantes Python, conferidas à mão numa data e nunca mais. Enquanto o
# direito muda, elas ficam paradas, e o silêncio é o problema: nada no sistema
# avisa que o dado envelheceu.
#
# Duas delas têm efeito jurídico direto:
#   • SUMULA_TETO (verificador_jurisprudencia) — o número da última súmula
#     editada por tribunal. Súmula ACIMA do teto é marcada como provável
#     alucinação. Se o teto envelhece, uma súmula NOVA e verdadeira passa a ser
#     acusada de inexistente — o falso positivo é pior que o falso negativo,
#     porque desacredita o gate inteiro aos olhos do advogado.
#   • DATA_CONFERENCIA (sumulas_ingestion) — a data em que cada verbete do seed
#     foi reconferido contra fonte oficial. Súmula cancelada depois disso
#     continua indexada como jurisprudência vigente.
#
# Este módulo não corrige nem consulta rede: ele apenas TORNA VISÍVEL a idade
# do dado, com o caminho do arquivo a reconferir. É lido pelo painel de saúde
# da IA e pelo próprio verificador (que passa a ressalvar o teto vencido).
from __future__ import annotations

from datetime import date, datetime

# Meio ano: prazo em que os tribunais superiores costumam editar novas súmulas
# e em que uma súmula cancelada já teria repercutido.
LIMITE_DIAS = 180


def _para_data(valor: str | None) -> date | None:
    try:
        return datetime.strptime((valor or "").strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _itens() -> list[dict]:
    """Import tardio: evita ciclo com os módulos que consultam este alarme."""
    from app.services.sumulas_ingestion import DATA_CONFERENCIA
    from app.services.verificador_jurisprudencia import SUMULA_TETO_CONFERIDO_EM

    return [
        {
            "chave": "sumula_teto",
            "descricao": (
                "Número da última súmula editada por tribunal (STF/STF-V/STJ/TST). "
                "Vencido, o gate acusa de alucinação súmula nova e verdadeira."
            ),
            "conferido_em": SUMULA_TETO_CONFERIDO_EM,
            "arquivo": "backend/app/services/verificador_jurisprudencia.py",
        },
        {
            "chave": "sumulas_seed",
            "descricao": (
                "Reconferência dos verbetes do seed de súmulas contra fonte "
                "oficial. Vencida, súmula cancelada segue indexada como vigente."
            ),
            "conferido_em": DATA_CONFERENCIA,
            "arquivo": "backend/app/services/sumulas_ingestion.py",
        },
    ]


def estado(hoje: date | None = None) -> dict:
    """Idade de cada dado jurídico embutido, com alarme quando vencido.

    `hoje` é injetável para o teste não depender do relógio.
    """
    hoje = hoje or date.today()
    itens: list[dict] = []
    alertas: list[str] = []
    for item in _itens():
        conferido = _para_data(item.get("conferido_em"))
        dias = (hoje - conferido).days if conferido else None
        # Data ilegível é tratada como vencida: não saber a idade do dado é
        # exatamente o estado que este alarme existe para eliminar.
        vencido = dias is None or dias > LIMITE_DIAS
        registro = {**item, "dias_desde_conferencia": dias, "vencido": vencido}
        itens.append(registro)
        if vencido:
            alertas.append(
                f"{item['chave']}: conferido em {item.get('conferido_em') or '?'}"
                + (f" ({dias} dias atrás)" if dias is not None else " (data ilegível)")
                + f" — reconferir contra fonte oficial em {item['arquivo']}."
            )
    return {
        "limite_dias": LIMITE_DIAS,
        "avaliado_em": hoje.isoformat(),
        "itens": itens,
        "alertas": alertas,
        "desatualizado": bool(alertas),
    }


def teto_de_sumula_vencido(hoje: date | None = None) -> bool:
    """Só o item do teto — consultado pelo verificador a cada citação."""
    for item in estado(hoje)["itens"]:
        if item["chave"] == "sumula_teto":
            return bool(item["vencido"])
    return False
