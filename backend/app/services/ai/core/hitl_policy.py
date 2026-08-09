# ── app/services/ai/core/hitl_policy.py ──────────────────────────────────────
# POLÍTICA HITL (Human-In-The-Loop) do Núcleo Único de IA.
#
# Regra OAB/EJC: TODA saída de IA é rascunho. Nenhuma resposta jurídica é
# apresentada como definitiva; o advogado responsável revisa antes de qualquer
# uso. A flag AI_REQUIRE_HITL existe apenas para ambientes de teste — em
# produção permanece True.
from __future__ import annotations

from app.core.config import get_settings

AVISO_HITL = "Rascunho sujeito à revisão humana (HITL obrigatório — OAB)."


def _propagar_alertas_critica(resultado: dict) -> None:
    """Torna falhas/alertas da segunda IA visíveis nas superfícies comuns.

    ``critica_adversarial`` é um metadado efêmero em algumas telas. Se a
    segunda IA ficar indisponível ou seu próprio gate de citações gerar aviso,
    o advogado não pode depender de a UI conhecer esse objeto especial para
    descobrir o risco. Copiamos somente mensagens textuais para ``alertas``,
    que já é persistido/renderizado em todas as superfícies do núcleo.
    """
    critica = resultado.get("critica_adversarial")
    if not isinstance(critica, dict):
        return

    alertas_existentes = resultado.get("alertas")
    alertas = list(alertas_existentes) if isinstance(alertas_existentes, list) else []

    def adicionar(valor) -> None:
        if isinstance(valor, str):
            texto = valor.strip()
            if texto and texto not in alertas:
                alertas.append(texto)

    alertas_critica = critica.get("alertas")
    if isinstance(alertas_critica, list):
        for alerta in alertas_critica:
            adicionar(alerta)

    # Em falha, o aviso é o dado essencial que explica que a segunda revisão
    # não ocorreu e que a conferência manual deve ser reforçada. Em sucesso, o
    # aviso padrão de rascunho seria redundante com AVISO_HITL e não é copiado.
    if critica.get("disponivel") is False:
        adicionar(critica.get("aviso"))

    resultado["alertas"] = alertas


def aplicar(resultado: dict) -> dict:
    """Carimba o resultado padronizado do orchestrator como rascunho HITL.

    Mesmo com AI_REQUIRE_HITL=false (testes), `is_rascunho` permanece True —
    o toggle só controla a exigência de revisão formal, nunca o rótulo de
    rascunho (vedação de resposta jurídica 'final' é inegociável)."""
    _propagar_alertas_critica(resultado)
    requer = bool(get_settings().AI_REQUIRE_HITL)
    resultado["is_rascunho"] = True
    resultado["requer_revisao"] = requer or resultado.get("revisao_obrigatoria", False)
    resultado["status_hitl"] = "gerado"
    resultado["aviso_hitl"] = AVISO_HITL
    return resultado
