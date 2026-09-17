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
    "/tributario/ferramentas/auto-infracao-prazos":
        "regra do PAF federal corrigida para LC 227/2026, porém ainda em revisão "
        "jurídica integral #1553; não promover resultado a documento profissional",

    "/tributario/ferramentas/prescricao-decadencia":
        "calculadora não modela marcos suficientes e ainda não incorpora integralmente "
        "a LC 236/2026, vigente desde 04/09/2026, inclusive alterações dos arts. "
        "150/151/168/174 do CTN; revisão jurídica P0 #1553 obrigatória",

    "/tributario/ferramentas/parcelamento":
        "simulador mistura PERT/REFIS históricos e parâmetros fixos com transações "
        "tributárias de 2026 que variam por edital, órgão, perfil, natureza do débito "
        "e capacidade de pagamento; confirmar modalidade oficial vigente antes de uso profissional",

    # P0/P1 tributário #1553: o comparativo usa coeficientes históricos fixos do
    # Lucro Presumido e não recebe período de apuração. A LC 224/2025 determinou
    # acréscimo de 10% nos percentuais de presunção sobre a parcela da receita que
    # excede R$ 5 milhões/ano (limite proporcional por período/atividade). Em 2026,
    # a RFB orienta aplicação ao IRPJ desde o 1º trimestre e à CSLL desde o 2º.
    # Além disso, o cenário de consumo deve identificar a transição IBS/CBS de 2026.
    "/tributario/ferramentas/regime-tributario":
        "comparativo usa percentuais fixos de Lucro Presumido e não modela período, "
        "limite ou acréscimo da LC 224/2025 aplicável em 2026 ao IRPJ/CSLL; também "
        "precisa contextualizar a transição IBS/CBS antes de uso profissional",

    "/tributario/ferramentas/reforma-tributaria":
        "simulação geral da reforma ainda usa alíquota indicativa sobre receita bruta "
        "e premissas setoriais sem créditos/redutores/regime específico; atualizar "
        "proveniência para LC 227/2026, atos de 2026 e impactos transversais da LC 236/2026",
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
    """Normaliza o caminho declarado antes do lookup na matriz: espaços,
    percent-encoding, casing, barras duplicadas, querystring, barra final e
    prefixo /api ou /api/v1. É a ÚNICA porta de entrada do lookup — selo,
    bloqueio e gate usam esta função, para que as três semânticas nunca
    divirjam.

    `/api/v1` é o prefixo CANÔNICO (`app/core/api_version_middleware.py`) —
    precisa ser removido ANTES do legado `/api`, senão sobra um `/v1/...`
    que não bate com nenhum caminho da allowlist (Issue #702, achado do
    review Codex)."""
    c = unquote(caminho or "").strip().split("?")[0].strip().casefold()
    while "//" in c:
        c = c.replace("//", "/")
    c = c.rstrip("/")
    if c == "/api/v1" or c.startswith("/api/v1/"):
        c = c[len("/api/v1"):]
    elif c.startswith("/api/"):
        c = c[len("/api"):]
    return c


def motivo_nao_homologada(caminho: str) -> str | None:
    """Motivo da não homologação, ou None se a ferramenta está fora da matriz."""
    return FERRAMENTAS_NAO_HOMOLOGADAS.get(normalizar_caminho_ferramenta(caminho))


def bloquear_nao_homologada(caminho: str) -> None:
    """Indisponibilidade controlada: ferramenta da lista BLOQUEADA responde 503.
    Usa a MESMA normalização do selo e do gate do demonstrativo."""
    motivo = motivo_nao_homologada(caminho)
    if motivo is None:
        raise KeyError(f"Ferramenta fora da matriz de não homologadas: {caminho!r}")
    raise HTTPException(503, detail={
        "codigo": "ferramenta_nao_homologada",
        "motivo": motivo,
        "mensagem": "Ferramenta temporariamente indisponível — em revisão jurídica",
    })


def selo_homologacao(caminho: str, resposta: dict) -> dict:
    """Anexa o selo homologada=False + aviso quando a ferramenta está na matriz.
    Usa a MESMA normalização do gate do demonstrativo (semântica única)."""
    motivo = motivo_nao_homologada(caminho)
    if motivo:
        resposta["homologada"] = False
        resposta["aviso_homologacao"] = (
            f"{motivo} — resultado não homologado para uso profissional; "
            "não gere demonstrativo a partir dele"
        )
    return resposta
