# ── app/services/ai/provider_policy.py ───────────────────────────────────────
# POLICY CENTRAL de provedores de IA (Núcleo Único).
#
# Decide, ANTES de qualquer chamada de modelo:
#   • quais provedores são elegíveis (habilitação + chave + soberania de dados);
#   • em que ordem tentar (AI_PROVIDER_PRIORITY + perfil da tarefa);
#   • se o conteúdo precisa/pode ser sanitizado para destino externo (LGPD);
#   • se a chamada é permitida ou bloqueada (PII residual sem provider local).
#
# A policy NÃO chama modelo nenhum — é decisão pura. O despacho continua no
# ai_gateway (que aplica a barreira final de sanitização por conta própria).
from __future__ import annotations
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.services.sanitizer import sanitizar_pii, validar_sem_pii

# Provedores que processam dados FORA do VPS (LGPD: exigem sanitização).
PROVIDERS_EXTERNOS = {"anthropic", "groq"}

# Tarefas complexas (raciocínio jurídico profundo) → priorizam Anthropic
# quando elegível. Aceita tanto nomes de TarefaIA quanto task_types do gateway.
TAREFAS_COMPLEXAS = {
    "analise_caso", "minutas", "dossie", "pesquisa_juridica",
    "estrategia", "analise_juridica", "elaboracao_peca",
}

# Tarefas simples/econômicas → preferem Ollama/Groq (custo ~zero).
TAREFAS_ECONOMICAS = {"resumo", "triagem", "chat_rapido"}


@dataclass
class PolicyDecision:
    permitido: bool
    provider_chain: list[tuple[str, str | None]] = field(default_factory=list)
    sanitizar_antes: bool = False
    motivo: str = ""
    requer_hitl: bool = True
    requer_fonte: bool = False
    bloqueio_motivo: str | None = None


class AIProviderPolicy:
    """Avaliador central de elegibilidade/ordem de provedores de IA."""

    @staticmethod
    def _elegivel(provider: str) -> bool:
        s = get_settings()
        if provider == "ollama":
            return bool(s.OLLAMA_ENABLED)
        if provider == "anthropic":
            return bool(
                s.ANTHROPIC_ENABLED and s.ANTHROPIC_API_KEY
                and s.AI_EXTERNAL_PROVIDERS_ALLOWED
            )
        if provider == "groq":
            return bool(s.GROQ_API_KEY and s.AI_EXTERNAL_PROVIDERS_ALLOWED)
        return False

    @staticmethod
    def _ordem_prioridade() -> list[str]:
        s = get_settings()
        vistos: list[str] = []
        for p in (s.AI_PROVIDER_PRIORITY or "").split(","):
            p = p.strip().lower()
            if p and p not in vistos:
                vistos.append(p)
        return vistos or ["ollama", "anthropic", "groq"]

    def avaliar(
        self,
        texto_completo: str,
        task_type: str,
        *,
        ja_sanitizado: bool = False,
        exige_fonte: bool = False,
    ) -> PolicyDecision:
        """
        Decide a cadeia de provedores para `task_type` dado o conteúdo.

        Regras:
          1. Cadeia base = AI_PROVIDER_PRIORITY filtrada por elegibilidade.
          2. Destino externo + AI_REQUIRE_SANITIZATION_FOR_EXTERNAL:
             sanitiza e checa residual; PII residual → remove externos.
          3. Cadeia vazia → permitido=False com motivo SEGURO (tipos de PII,
             nunca os valores — o conteúdo jamais é ecoado).
          4. Tarefas complexas priorizam Anthropic; econômicas, Ollama/Groq.
        """
        s = get_settings()
        task = (task_type or "").strip().lower()
        motivos: list[str] = []

        elegiveis = [p for p in self._ordem_prioridade() if self._elegivel(p)]

        # ── Barreira LGPD: destino externo exige conteúdo sem PII ────────────
        sanitizar_antes = False
        tem_externo = any(p in PROVIDERS_EXTERNOS for p in elegiveis)
        if tem_externo and s.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL:
            sanitizar_antes = True
            texto_chk = texto_completo or ""
            if not ja_sanitizado:
                texto_chk, _ = sanitizar_pii(texto_chk)
            residual = validar_sem_pii(texto_chk)
            if residual:
                elegiveis = [p for p in elegiveis if p not in PROVIDERS_EXTERNOS]
                motivos.append(
                    "PII residual detectada ("
                    + ", ".join(residual)
                    + ") — provedores externos removidos da cadeia (LGPD)"
                )

        # ── Priorização por perfil da tarefa ─────────────────────────────────
        if task in TAREFAS_COMPLEXAS and "anthropic" in elegiveis:
            elegiveis = ["anthropic"] + [p for p in elegiveis if p != "anthropic"]
            motivos.append("tarefa complexa — Anthropic priorizado")
        elif task in TAREFAS_ECONOMICAS:
            econ = [p for p in elegiveis if p in ("ollama", "groq")]
            elegiveis = econ + [p for p in elegiveis if p not in econ]
            motivos.append("tarefa econômica — Ollama/Groq priorizados")

        requer_hitl = bool(s.AI_REQUIRE_HITL)

        if not elegiveis:
            return PolicyDecision(
                permitido=False,
                provider_chain=[],
                sanitizar_antes=sanitizar_antes,
                motivo="; ".join(motivos) or "nenhum provedor de IA elegível",
                requer_hitl=requer_hitl,
                requer_fonte=exige_fonte,
                bloqueio_motivo=(
                    "Nenhum provedor de IA elegível para este conteúdo. "
                    "Habilite o Ollama local (OLLAMA_ENABLED=true) ou remova "
                    "dados pessoais do texto e tente novamente."
                ),
            )

        # Modelo fica None: o gateway resolve o modelo por tarefa/provedor.
        return PolicyDecision(
            permitido=True,
            provider_chain=[(p, None) for p in elegiveis],
            sanitizar_antes=sanitizar_antes,
            motivo="; ".join(motivos) or "cadeia padrão por prioridade",
            requer_hitl=requer_hitl,
            requer_fonte=exige_fonte,
            bloqueio_motivo=None,
        )
