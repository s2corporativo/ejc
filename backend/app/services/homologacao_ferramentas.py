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
    # ── BLOQUEADAS (503 — ver FERRAMENTAS_BLOQUEADAS) ────────────────────────
    "/empresarial/ferramentas/prazos-rj":
        "marcos temporais da recuperação judicial incorretos (Lei 11.101/2005)",
    "/empresarial/ferramentas/juros-mora":
        "regra de juros obsoleta após a Lei 14.905/2024 (nova redação do CC art. 406)",
    "/penal/ferramentas/prazos-processuais":
        "contagem em dias úteis — no processo penal os prazos correm em dias CORRIDOS (CPP art. 798)",
    "/penal/ferramentas/verificar-anpp":
        "requisito de ausência de violência doméstica fixado como True no código, sem checagem real (CPP art. 28-A)",
    # ── COM SELO (respondem, mas o resultado NÃO é homologado) ───────────────
    "/empresarial/ferramentas/verificar-cade":
        "prazo de notificação de 30 dias inexistente — o controle de concentrações é PRÉVIO (Lei 12.529/2011 art. 88)",
    "/civel/ferramentas/prazos-contestacao":
        "prazo universal de 10 dias para contestação no JEC inexistente na Lei 9.099/95",
    "/penal/ferramentas/dosimetria":
        "modelo trifásico excessivamente simplificado — não valida os limites legais de cada fase (CP art. 68)",
    "/penal/ferramentas/prescricao-punitiva":
        "duplicada com prescricao-penal e sem considerar marcos interruptivos (CP art. 117)",
    "/penal/ferramentas/prescricao-penal":
        "duplicada com prescricao-punitiva e sem considerar marcos interruptivos (CP art. 117)",
    "/trabalhista-esp/ferramentas/prazos":
        "prazos contados em dias corridos — a CLT art. 775 determina contagem em dias ÚTEIS",
    "/trabalhista-esp/ferramentas/prescricao-trabalhista":
        "marco quinquenal projetado para frente — a contagem é retroativa da data do ajuizamento (Súm. TST 308)",
    "/transito/ferramentas/prazos-recurso":
        "defesa prévia com 15 dias — o CTB (red. Lei 14.071/2020) exige prazo mínimo de 30 dias — e marcos incorretos",
    "/admin-esp/ferramentas/recurso-multa-transito":
        "marcos temporais incorretos e defesa prévia divergente do CTB (mínimo de 30 dias, red. Lei 14.071/2020)",
    "/transito/ferramentas/pontuacao-cnh":
        "limite de 30 pontos para condutor EAR — o correto é 40 pontos (CTB art. 261, red. Lei 14.071/2020)",
    "/consumidor/ferramentas/devolucao-dobro":
        "critério de má-fé — o STJ exige apenas conduta contrária à boa-fé objetiva (EAREsp 676.608/RS)",
    "/consumidor/ferramentas/prazos-cdc":
        "prescrição genérica de 3 anos para cobrança indevida — o STJ aplica o prazo decenal (EAREsp 738.991/RS)",
    "/previdenciario/ferramentas/prazos":
        "marcos de decadência/prescrição inadequados (Lei 8.213/91 art. 103)",
}

# Subconjunto que fica INDISPONÍVEL (503) até revisão jurídica.
FERRAMENTAS_BLOQUEADAS: frozenset[str] = frozenset({
    "/empresarial/ferramentas/prazos-rj",
    "/empresarial/ferramentas/juros-mora",
    "/penal/ferramentas/prazos-processuais",
    "/penal/ferramentas/verificar-anpp",
})


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
