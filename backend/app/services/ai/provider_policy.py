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
PROVIDERS_EXTERNOS = {"anthropic", "groq", "maritaca"}

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
        """Delega ao registry — fonte única de habilitação/chave/kill-switch.

        A cópia local desta regra não checava GROQ_ENABLED: o kill-switch do
        Groq só valia depois que `provider_registry_runtime.instalar()` trocava
        este método. Fora do runtime (testes, scripts, worker sem o patch), a
        policy dizia "elegível" para um provedor desligado (auditoria 18/08).
        """
        from app.services.ai.provider_registry import provider_elegivel

        return provider_elegivel(provider)

    @staticmethod
    def _ordem_prioridade() -> list[str]:
        s = get_settings()
        vistos: list[str] = []
        for p in (s.AI_PROVIDER_PRIORITY or "").split(","):
            p = p.strip().lower()
            if p and p not in vistos:
                vistos.append(p)
        # Default sem AI_PROVIDER_PRIORITY: Groq para rotina; Maritaca para
        # leitura/raciocínio jurídico; Ollama como rede local; Claude permanece
        # disponível apenas por requisição explícita quando a política assim exigir.
        return vistos or ["groq", "maritaca", "ollama", "anthropic"]

    def avaliar(
        self,
        texto_completo: str,
        task_type: str,
        *,
        ja_sanitizado: bool = False,
        exige_fonte: bool = False,
        provider_override: str | None = None,
    ) -> PolicyDecision:
        """
        Decide a cadeia de provedores para `task_type` dado o conteúdo.

        Regras:
          1. Cadeia base = AI_PROVIDER_PRIORITY filtrada por elegibilidade.
          2. Destino externo + AI_REQUIRE_SANITIZATION_FOR_EXTERNAL:
             sanitiza e checa residual; PII residual → remove externos.
          3. Cadeia vazia → permitido=False com motivo SEGURO (tipos de PII,
             nunca os valores — o conteúdo jamais é ecoado).
          4. Tarefas complexas priorizam Maritaca; econômicas, Groq/Ollama.
             Claude só entra quando provider_override="anthropic".
        """
        s = get_settings()
        task = (task_type or "").strip().lower()
        motivos: list[str] = []

        elegiveis = [p for p in self._ordem_prioridade() if self._elegivel(p)]
        provider_explicito = (provider_override or "").strip().lower()
        if provider_explicito in PROVIDERS_EXTERNOS | {"ollama"}:
            elegiveis = [provider_explicito] if self._elegivel(provider_explicito) else []
            motivos.append(f"provedor solicitado explicitamente: {provider_explicito}")
        elif getattr(s, "ANTHROPIC_EXPLICIT_ONLY", True):
            elegiveis = [p for p in elegiveis if p != "anthropic"]
            motivos.append("Claude reservado para requisição explícita no EJC")

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
        if task in TAREFAS_COMPLEXAS and "maritaca" in elegiveis:
            # Sabiá/Maritaca é o provider automático de mérito PT-BR —
            # priorizado à frente do Groq, mas
            # NUNCA à frente de provider LOCAL elegível (minimização LGPD: o
            # dado só sai do VPS quando não há opção local).
            locais = [p for p in elegiveis if p not in PROVIDERS_EXTERNOS]
            externos = [p for p in elegiveis
                        if p in PROVIDERS_EXTERNOS and p != "maritaca"]
            elegiveis = locais + ["maritaca"] + externos
            motivos.append("tarefa complexa — Maritaca (Sabiá) priorizada entre externos")
        elif task in TAREFAS_ECONOMICAS:
            econ = [p for p in ("groq", "ollama") if p in elegiveis]
            elegiveis = econ + [p for p in elegiveis if p not in econ]
            motivos.append("tarefa econômica — Groq/Ollama priorizados")

        requer_hitl = bool(s.AI_REQUIRE_HITL)

        if not elegiveis:
            # Mensagem HONESTA conforme a causa da cadeia vazia:
            #  • se externos foram removidos por PII residual, só uma IA LOCAL
            #    resolveria (ou limpar o texto);
            #  • caso contrário, o deploy simplesmente não tem provedor externo
            #    elegível (falta ANTHROPIC_API_KEY / AI_EXTERNAL_PROVIDERS_ALLOWED)
            #    nem Ollama local. Não direcionar só para "habilite o Ollama":
            #    o desenho de produção é IA externa com mascaramento de PII.
            #  • e, desde AUD27-P0-1, a cadeia também fica vazia quando o
            #    kill-switch GLOBAL está desligado — aí nenhuma chave de
            #    provedor resolve, e mandar o operador atrás de
            #    ANTHROPIC_API_KEY o faria perseguir a causa errada.
            removido_por_pii = any("PII residual" in m for m in motivos)
            if not s.AI_ENABLED:
                bloqueio = (
                    "A IA está desligada no sistema (kill-switch AI_ENABLED). "
                    "Nenhum provedor — nem local — responde enquanto ela estiver "
                    "desligada; religue em AI_ENABLED=true para voltar a usar."
                )
            elif removido_por_pii:
                bloqueio = (
                    "Este conteúdo tem dados pessoais que não podem ir a uma IA "
                    "externa. Habilite uma IA local (OLLAMA_ENABLED=true) ou "
                    "remova os dados pessoais do texto e tente novamente."
                )
            else:
                bloqueio = (
                    "Nenhum provedor de IA está configurado. Configure a IA "
                    "externa (defina ANTHROPIC_API_KEY no ambiente e mantenha "
                    "AI_EXTERNAL_PROVIDERS_ALLOWED=true) ou habilite uma IA local "
                    "(OLLAMA_ENABLED=true com um serviço Ollama disponível)."
                )
            return PolicyDecision(
                permitido=False,
                provider_chain=[],
                sanitizar_antes=sanitizar_antes,
                motivo="; ".join(motivos) or "nenhum provedor de IA elegível",
                requer_hitl=requer_hitl,
                requer_fonte=exige_fonte,
                bloqueio_motivo=bloqueio,
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
