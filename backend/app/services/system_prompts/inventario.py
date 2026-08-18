# ── app/services/system_prompts/inventario.py ────────────────────────────────
# INVENTÁRIO CANÔNICO DOS PROMPTS do núcleo de IA.
#
# Dívida 5.3 da auditoria de IA (2026-08-15): o sistema tinha dezenas de
# prompts espalhados por módulos, sem lugar único que dissesse quais existem,
# quem os consome e QUAL versão produziu determinada saída. Sem isso, um erro
# jurídico numa peça não é rastreável até a instrução que o causou — e um
# prompt órfão (registrado e não consumido) ou fantasma (consumido e não
# registrado) passa despercebido.
#
# O inventário é DERIVADO, nunca digitado: lê SYSTEM_PROMPTS/PROMPT_EXTRAS e o
# registro de agentes. Uma lista escrita à mão envelheceria como qualquer outra
# constante — o problema que este módulo existe para resolver.
#
# A "versão" é a impressão digital do conteúdo (sha256 truncado). Não é
# semântica: muda quando o texto muda, que é exatamente a pergunta a responder
# ("a peça de ontem saiu deste prompt ou do anterior?").
from __future__ import annotations

import hashlib

_TAM_IMPRESSAO = 12


def impressao(conteudo: str) -> str:
    """Impressão digital estável do texto do prompt."""
    return hashlib.sha256((conteudo or "").encode("utf-8")).hexdigest()[:_TAM_IMPRESSAO]


def versao_do_prompt(chave: str) -> str | None:
    """Impressão da chave registrada; None se a chave não existe."""
    from app.services.system_prompts import SYSTEM_PROMPTS

    conteudo = SYSTEM_PROMPTS.get(chave)
    return impressao(conteudo) if conteudo is not None else None


def _consumidores() -> dict[str, list[str]]:
    """Quem consome cada chave — agentes internos do núcleo + tarefas do router."""
    from app.services.ai.core.agent_registry import AGENT_REGISTRY
    from app.services.system_prompts.router import CONFIGURACOES

    mapa: dict[str, list[str]] = {}
    for agente in AGENT_REGISTRY.values():
        mapa.setdefault(agente.prompt_key, []).append(f"agente:{agente.nome}")
    for tarefa, cfg in CONFIGURACOES.items():
        mapa.setdefault(cfg.prompt_key, []).append(f"tarefa:{tarefa.value}")
    return mapa


def inventario() -> list[dict]:
    """Uma linha por prompt registrado, ordenada pela chave."""
    from app.services.system_prompts import PROMPT_EXTRAS, SYSTEM_PROMPTS

    consumidores = _consumidores()
    linhas = [
        {
            "chave": chave,
            "tipo": "system",
            "versao": impressao(conteudo),
            "tamanho": len(conteudo or ""),
            "consumidores": sorted(consumidores.get(chave, [])),
            # Prompt registrado que ninguém consome é dívida silenciosa: ou o
            # consumidor sumiu, ou a chave nunca foi ligada.
            "orfao": not consumidores.get(chave),
        }
        for chave, conteudo in SYSTEM_PROMPTS.items()
    ]
    linhas += [
        {
            "chave": chave,
            "tipo": "extra",          # bloco aditivo por superfície
            "versao": impressao(conteudo),
            "tamanho": len(conteudo or ""),
            "consumidores": ["params:prompt_extra"],
            "orfao": False,
        }
        for chave, conteudo in PROMPT_EXTRAS.items()
    ]
    return sorted(linhas, key=lambda x: (x["tipo"], x["chave"]))


def chaves_fantasma() -> list[str]:
    """Chaves consumidas por agente/tarefa que NÃO existem em SYSTEM_PROMPTS.

    Uma chave fantasma não quebra nada visivelmente — o núcleo cai no prompt
    `default` e o advogado recebe uma resposta genérica onde deveria haver
    especialização. É o pior tipo de falha: silenciosa e plausível.
    """
    from app.services.system_prompts import SYSTEM_PROMPTS

    return sorted(k for k in _consumidores() if k not in SYSTEM_PROMPTS)


def resumo() -> dict:
    linhas = inventario()
    return {
        "total": len(linhas),
        "orfaos": sorted(x["chave"] for x in linhas if x["orfao"]),
        "fantasmas": chaves_fantasma(),
        "prompts": linhas,
    }
