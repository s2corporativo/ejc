# ── app/services/tese_caso_matcher.py ────────────────────────────────────────
# Varredura reversa TESE → CASO (frente 2 de docs/estrategia/EVOLUCAO_ESTRATEGICA_EJC.md).
#
# O Banco de Teses só sabia responder no sentido caso → teses
# (`teses_do_caso`, `sugerir_teses_ia`, `motor_teses`). Faltava o inverso, que é
# o que converte catálogo em ferramenta de trabalho: dada UMA tese, em quais
# processos do escritório ela pode caber.
#
# INVARIANTES deste módulo:
#   • 100% DETERMINÍSTICO — nenhuma chamada de IA. A varredura é navegação, não
#     produção de conteúdo jurídico: não há alucinação a conter, não há PII
#     saindo para provedor externo e não há HITL a exigir. Mesma escolha de
#     `matriz_provas.py` e `evento_processual.py`.
#   • FUNÇÕES PURAS — sem rede, sem banco, sem estado. Quem consulta e aplica o
#     gate de visibilidade é o router.
#   • NUNCA VINCULA — a saída é lista de CANDIDATOS. Criar o vínculo continua
#     sendo ato humano explícito (`POST /teses/{id}/casos`).
#   • EXPLICÁVEL — todo candidato devolve os termos que casaram. Um score sem
#     justificativa é inútil para o advogado decidir, e pior: convida a
#     confiar sem conferir.
from __future__ import annotations

import re
import unicodedata

# ── Score determinístico — pesos FIXOS e documentados ────────────────────────
#   +15 por termo distinto da tese encontrado no texto do caso (máx. 4 → +60)
#   +40 quando a área da tese é a mesma do caso
#   score = min(100, soma)
#
# Casar a ÁREA sozinha NÃO gera candidato: toda tese cível casaria com todo
# caso cível, e a lista viraria ruído. Pelo menos um termo é obrigatório — a
# área é reforço, não gatilho.
PESO_POR_TERMO = 15
MAX_TERMOS_PONTUADOS = 4
PESO_AREA = 40

# Piso de relevância padrão. Com ele: 1 termo isolado (15) fica de fora;
# 2 termos (30) entram; 1 termo + área (55) entram com folga.
PISO_RELEVANCIA_PADRAO = 25

# Teto de casos varridos numa chamada — a varredura é O(casos × termos) em
# memória, e sem teto uma base grande viraria resposta lenta e enorme.
MAX_CASOS_VARRIDOS = 2_000

# Termos com menos que isto são ruído ("dano", "ação" ainda passam; "de", "do"
# não). Vale junto com a stoplist.
MIN_TAMANHO_TERMO = 4

# Palavras que aparecem em quase toda tese e em quase todo caso: casá-las não
# informa nada. Lista curta e jurídica de propósito — stoplist grande demais
# começa a descartar termo útil.
_STOPWORDS = {
    "acao", "acoes", "artigo", "artigos", "autor", "autora", "banco", "caso",
    "cliente", "codigo", "contra", "direito", "efeito", "empresa", "entre",
    "fato", "fatos", "juiz", "juridica", "juridico", "lei", "logo", "mesmo",
    "para", "parte", "partes", "pedido", "pedidos", "pela", "pelo", "pessoa",
    "pode", "processo", "processual", "quando", "reclamada", "reclamante",
    "requerida", "requerente", "reu", "sobre", "sendo", "tema", "tese",
    "teses", "tribunal", "valor",
}


def normalizar(texto: object) -> str:
    """Minúsculas, sem acento, só alfanumérico — casamento tolerante a grafia.

    Mesma abordagem de `matriz_provas._normalizar`: 'Purgação da Mora' e
    'purgacao da mora' precisam casar.
    """
    bruto = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = "".join(c for c in bruto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", sem_acento)).strip().lower()


def extrair_termos(*campos: object) -> list[str]:
    """Termos distintos e significativos de uma tese, em ordem estável.

    Ordem estável importa: dois casos com o mesmo score precisam listar os
    termos casados na mesma ordem, senão a saída muda entre chamadas iguais e
    fica impossível conferir.
    """
    vistos: list[str] = []
    for campo in campos:
        for palavra in normalizar(campo).split():
            if len(palavra) < MIN_TAMANHO_TERMO:
                continue
            if palavra in _STOPWORDS:
                continue
            if palavra.isdigit():
                continue
            if palavra not in vistos:
                vistos.append(palavra)
    return vistos


def pontuar_caso(
    termos_tese: list[str],
    texto_caso: str,
    *,
    area_tese: object = None,
    area_caso: object = None,
) -> tuple[int, list[str], bool]:
    """Pontua UM caso contra os termos de uma tese.

    Devolve `(score, termos_casados, area_coincide)`. `score` é 0 quando
    nenhum termo casa — e nesse caso o chamador descarta o candidato, ainda
    que a área bata.
    """
    alvo = normalizar(texto_caso)
    casados = [t for t in termos_tese if t in alvo]

    area_coincide = False
    a_tese, a_caso = normalizar(area_tese), normalizar(area_caso)
    if a_tese and a_caso and a_tese == a_caso:
        area_coincide = True

    if not casados:
        return 0, [], area_coincide

    score = PESO_POR_TERMO * min(len(casados), MAX_TERMOS_PONTUADOS)
    if area_coincide:
        score += PESO_AREA
    return min(100, score), casados, area_coincide


def ranquear_candidatos(
    termos_tese: list[str],
    casos: list[dict],
    *,
    area_tese: object = None,
    piso: int = PISO_RELEVANCIA_PADRAO,
    limite: int = 20,
) -> list[dict]:
    """Ordena os casos por aderência à tese.

    `casos` são dicts com pelo menos `id`; os campos textuais considerados são
    `titulo` e `descricao_fatos`, e `area` entra na comparação de área.

    Empate é desempatado pelo `id` — sem isso a ordem depende da ordem de
    chegada do SELECT e a mesma consulta devolve listas diferentes.
    """
    if not termos_tese:
        return []

    fora: list[dict] = []
    for caso in casos:
        texto = f"{caso.get('titulo') or ''} {caso.get('descricao_fatos') or ''}"
        score, casados, area_coincide = pontuar_caso(
            termos_tese, texto, area_tese=area_tese, area_caso=caso.get("area"),
        )
        if score < piso:
            continue
        fora.append({
            "case_id": caso.get("id"),
            "numero_interno": caso.get("numero_interno"),
            "titulo": caso.get("titulo"),
            "area": caso.get("area"),
            "status": caso.get("status"),
            "score": score,
            "termos_casados": casados,
            "area_coincide": area_coincide,
        })

    fora.sort(key=lambda c: (-c["score"], str(c.get("case_id") or "")))
    return fora[:limite]
