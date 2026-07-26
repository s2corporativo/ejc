"""Matriz de homologação das ferramentas das Áreas de Atuação (Onda 1).

Fonte única, em módulo neutro, para evitar acoplamento router→router:
- routers/ramos.py aplica o bloqueio (503) e o selo (homologada=False);
- routers/peca_geracao.py aplica o gate do demonstrativo (422).

As regras jurídicas em si serão corrigidas na Onda 2, ferramenta a ferramenta,
com fonte oficial, vigência e testes; aqui apenas bloqueamos o risco de uso
profissional de resultado errado.
"""
from urllib.parse import unquote

from fastapi import HTTPException

FERRAMENTAS_NAO_HOMOLOGADAS: dict[str, str] = {
    # Onda 2 — Fase A (2026-07): corrigidas e REMOVIDAS da matriz:
    #   /empresarial/ferramentas/prazos-rj · /empresarial/ferramentas/juros-mora
    #   /penal/ferramentas/prazos-processuais · /penal/ferramentas/verificar-anpp
    #   /civel/ferramentas/prazos-contestacao
    #   /penal/ferramentas/prescricao-punitiva · /penal/ferramentas/prescricao-penal
    # Onda 2 — Fase B (2026-07): corrigidas e REMOVIDAS da matriz:
    #   /trabalhista-esp/ferramentas/prazos · /trabalhista-esp/ferramentas/prescricao-trabalhista
    #   /transito/ferramentas/prazos-recurso · /transito/ferramentas/pontuacao-cnh
    #   /admin-esp/ferramentas/recurso-multa-transito (delegada à rota canônica de trânsito)
    # Onda 2 — Fase C (2026-07): corrigidas e REMOVIDAS da matriz:
    #   /consumidor/ferramentas/devolucao-dobro · /consumidor/ferramentas/prazos-cdc
    #   /previdenciario/ferramentas/prazos
    #   /empresarial/ferramentas/verificar-cade (resposta já corrigida na Onda 1 —
    #   controle prévio, sem prazo fictício; considerada juridicamente correta)
    # ── COM SELO (responde, mas o resultado NÃO é homologado) ────────────────
    "/penal/ferramentas/dosimetria":
        "simulador assistido — as frações padrão são referencial jurisprudencial; "
        "conferência e fundamentação pelo advogado são obrigatórias",
}

# Subconjunto que fica INDISPONÍVEL (503) até revisão jurídica.
# Onda 2 — Fase A: as 4 ferramentas bloqueadas na Onda 1 foram corrigidas e
# desbloqueadas; o mecanismo permanece para bloqueios futuros.
FERRAMENTAS_BLOQUEADAS: frozenset[str] = frozenset()


def normalizar_caminho_ferramenta(caminho: str) -> str:
    """Normaliza o caminho declarado antes do lookup na matriz: percent-encoding,
    casing, barras duplicadas, querystring, barra final e prefixo /api."""
    c = unquote(caminho or "").split("?")[0].casefold()
    while "//" in c:
        c = c.replace("//", "/")
    c = c.rstrip("/")
    if c.startswith("/api/"):
        c = c[len("/api"):]
    return c


def motivo_nao_homologada(caminho: str) -> str | None:
    """Motivo da não homologação, ou None se a ferramenta está fora da matriz."""
    return FERRAMENTAS_NAO_HOMOLOGADAS.get(normalizar_caminho_ferramenta(caminho))


def bloquear_nao_homologada(caminho: str) -> None:
    """Indisponibilidade controlada: ferramenta da lista BLOQUEADA responde 503."""
    raise HTTPException(503, detail={
        "codigo": "ferramenta_nao_homologada",
        "motivo": FERRAMENTAS_NAO_HOMOLOGADAS[caminho],
        "mensagem": "Ferramenta temporariamente indisponível — em revisão jurídica",
    })


def selo_homologacao(caminho: str, resposta: dict) -> dict:
    """Anexa o selo homologada=False + aviso quando a ferramenta está na matriz."""
    motivo = FERRAMENTAS_NAO_HOMOLOGADAS.get(caminho)
    if motivo:
        resposta["homologada"] = False
        resposta["aviso_homologacao"] = (
            f"{motivo} — resultado não homologado para uso profissional; "
            "não gere demonstrativo a partir dele"
        )
    return resposta
