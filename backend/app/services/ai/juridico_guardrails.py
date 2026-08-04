# ── app/services/ai/juridico_guardrails.py ────────────────────────────────────
# Guardrails jurídicos DETERMINÍSTICOS para as skills `prescricao-decadencia` e
# `simulador-defesa-adversarial` (Issue #554, problemas 1 e 2).
#
# Por que determinístico e não só instrução de prompt: o prompt já orienta o
# modelo a não errar, mas a Issue reproduziu a resposta gerada classificando
# reconhecimento de prescrição/decadência como "extinção sem resolução de
# mérito" mesmo assim. Prompt não é controle — é sugestão. Este módulo aplica
# a regra em código, sobre o TEXTO JÁ GERADO, antes de ele ser devolvido ao
# usuário ou persistido no AILog.
#
# Fontes oficiais (citar sempre a fonte, nunca inventar):
#   - CPC, art. 487, II — prescrição/decadência é SENTENÇA DE MÉRITO:
#     https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm
#   - CDC, arts. 26 e 27 — vício (decadência) x fato do produto/serviço
#     (prescrição) são regimes distintos, com prazos e termos iniciais
#     próprios:
#     https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm
#
# Chamado de dois pontos (defesa em profundidade):
#   1. app/services/ai_skill_service.py — executar_skill/_documento_longo,
#      ANTES do AILog ser gravado (nova execução).
#   2. app/routers/ai.py GET /ai/logs — na LEITURA de respostas já
#      persistidas por execuções anteriores a esta correção. O texto salvo no
#      banco não é reescrito (não há migration de dados no escopo desta
#      Issue); a correção é aplicada só à cópia servida ao cliente.
from __future__ import annotations
import re

# As duas skills reproduzidas na Issue #554. `checar_cumulacao_vicio_fato_cdc`
# e `aplicar_guardrail_merito` também são seguros para qualquer outro texto —
# o padrão só dispara quando prescrição/decadência aparece de fato associada
# à qualificação errada — mas o caller (ai_skill_service) restringe a estas
# duas para não alterar o comportamento de skills fora do escopo da Issue.
NOME_SKILLS_DECADENCIA_PRESCRICAO = {"prescricao-decadencia", "simulador-defesa-adversarial"}

FONTE_CPC_487_II = (
    "CPC, art. 487, II "
    "(https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm)"
)
FONTE_CDC_26_27 = (
    "CDC, arts. 26 e 27 "
    "(https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm)"
)

ALERTA_MERITO_CORRIGIDO = (
    "Guardrail jurídico determinístico corrigiu a qualificação de prescrição/"
    "decadência como extinção SEM resolução de mérito — pelo "
    f"{FONTE_CPC_487_II}, é sentença de MÉRITO. Confira o trecho antes de "
    "qualquer uso (HITL)."
)

_AVISO_CORRECAO_MERITO = (
    "\n\n[CORREÇÃO JURÍDICA AUTOMÁTICA — GUARDRAIL DETERMINÍSTICO, Issue #554]\n"
    "Um trecho acima qualificava o reconhecimento de prescrição/decadência "
    "como extinção SEM resolução de mérito (art. 485 do CPC). Isso é um erro: "
    f"pelo {FONTE_CPC_487_II}, o juiz que pronuncia prescrição ou decadência "
    "profere sentença de MÉRITO — onde o texto dizia \"sem resolução de "
    "mérito\", foi corrigido automaticamente para \"COM resolução de mérito "
    "(art. 487, II, do CPC)\". Revise o texto antes de qualquer uso externo."
)

_PRESCRICAO_DECADENCIA = r"(?:prescri(?:[cç][ãa]o|cional)|decad[êe]ncial?)"
# Janela por CARACTERES (não por frase): usar `[^.\n]` faria o "." de
# abreviações jurídicas comuns ("art.", "II,") dentro da PRÓPRIA correção
# quebrar a janela em substituições encadeadas (clásula corrigida → citação
# de art. 485 na sequência já não seria mais "vista" por estar "depois de um
# ponto"). `.` (sem re.DOTALL) já para em quebra de parágrafo — suficiente
# para não vazar para um parágrafo totalmente diferente.
_JANELA = r".{0,220}?"
# Só o núcleo "sem resolução de mérito" — não exige um verbo específico
# ("extinto"/"extinção"/"extingo"/"julgo extinto"...) antes dele: a IA varia a
# conjugação, e o que importa juridicamente é a QUALIFICAÇÃO (mérito ou não),
# não a forma verbal. Substituir só o núcleo preserva o resto da frase intacto
# e correto em qualquer conjugação.
_CLAUSULA_ERRADA = r"sem\s+resolu[cç][ãa]o\s+d[eo]\s+m[ée]rito"

_RE_CLAUSULA_ANTES = re.compile(
    rf"{_PRESCRICAO_DECADENCIA}{_JANELA}({_CLAUSULA_ERRADA})", re.I,
)
_RE_CLAUSULA_DEPOIS = re.compile(
    rf"({_CLAUSULA_ERRADA}){_JANELA}{_PRESCRICAO_DECADENCIA}", re.I,
)
_RE_ART485_ANTES = re.compile(
    rf"{_PRESCRICAO_DECADENCIA}{_JANELA}(art(?:igo)?\.?\s*485\b)", re.I,
)
_RE_ART485_DEPOIS = re.compile(
    rf"(art(?:igo)?\.?\s*485\b){_JANELA}{_PRESCRICAO_DECADENCIA}", re.I,
)

_SUBSTITUICAO_CLAUSULA = "COM resolução de mérito (art. 487, II, do CPC)"
_SUBSTITUICAO_ART485 = "art. 487, II,"


def detectar_qualificacao_extincao_indevida(texto: str) -> bool:
    """True se o texto qualifica prescrição/decadência como extinção SEM
    resolução de mérito (contraria o CPC, art. 487, II) — seja pela
    expressão "sem resolução de mérito" ou por referência ao art. 485."""
    if not texto:
        return False
    return bool(
        _RE_CLAUSULA_ANTES.search(texto)
        or _RE_CLAUSULA_DEPOIS.search(texto)
        or _RE_ART485_ANTES.search(texto)
        or _RE_ART485_DEPOIS.search(texto)
    )


def _substituir_no_match(texto: str, regex: re.Pattern, alvo_original: str) -> tuple[str, int]:
    """Substitui, dentro do trecho casado por `regex`, apenas o grupo 1
    (a cláusula/citação errada) — preserva o resto da frase (inclusive a
    menção a prescrição/decadência) exatamente como a IA escreveu."""
    contagem = 0

    def _rep(m: re.Match) -> str:
        nonlocal contagem
        contagem += 1
        return m.group(0).replace(m.group(1), alvo_original, 1)

    return regex.sub(_rep, texto), contagem


def aplicar_guardrail_merito(texto: str) -> tuple[str, bool]:
    """Corrige deterministicamente a resposta quando ela classifica
    prescrição/decadência como extinção sem resolução de mérito (CPC, art.
    487, II). Substitui a cláusula/citação errada pontualmente (não reescreve
    a frase inteira, para não distorcer o restante do texto gerado) e sempre
    ANEXA um aviso de correção visível ao revisor humano (HITL) — a correção
    nunca é silenciosa.

    Retorna (texto_final, foi_corrigido).
    """
    if not texto:
        return texto, False
    novo = texto
    total = 0
    novo, n = _substituir_no_match(novo, _RE_CLAUSULA_ANTES, _SUBSTITUICAO_CLAUSULA)
    total += n
    novo, n = _substituir_no_match(novo, _RE_CLAUSULA_DEPOIS, _SUBSTITUICAO_CLAUSULA)
    total += n
    novo, n = _substituir_no_match(novo, _RE_ART485_ANTES, _SUBSTITUICAO_ART485)
    total += n
    novo, n = _substituir_no_match(novo, _RE_ART485_DEPOIS, _SUBSTITUICAO_ART485)
    total += n
    if total == 0:
        return texto, False
    return novo + _AVISO_CORRECAO_MERITO, True


# ── CDC arts. 26 e 27 — vício x fato do produto/serviço (Issue #554, item 2) ──
# Regimes DIFERENTES: vício do produto/serviço (art. 26) decai; fato do
# produto/serviço — defeito que causa dano, "acidente de consumo" (art. 27)
# prescreve. A skill não pode tratar os dois pedidos como uma coisa só.
_RE_VICIO_CDC = re.compile(
    r"v[íi]cio\s+(?:do\s+|de\s+)?(?:produto|servi[cç]o)"
    r"|art(?:igo)?\.?\s*26\b[^.\n]{0,40}CDC|CDC[^.\n]{0,40}art(?:igo)?\.?\s*26\b",
    re.I,
)
_RE_FATO_CDC = re.compile(
    r"fato\s+(?:do\s+|de\s+)?(?:produto|servi[cç]o)"
    r"|defeito\s+que\s+causa(?:m)?\s+dano|acidente\s+de\s+consumo"
    r"|art(?:igo)?\.?\s*27\b[^.\n]{0,40}CDC|CDC[^.\n]{0,40}art(?:igo)?\.?\s*27\b",
    re.I,
)
_RE_DECADENCIA = re.compile(r"decad[êe]ncial?", re.I)
_RE_PRESCRICAO = re.compile(r"prescri(?:[cç][ãa]o|cional)", re.I)

ALERTA_CUMULACAO_CDC = (
    "Possível cumulação automática dos regimes do CDC — vício do produto/"
    f"serviço ({FONTE_CDC_26_27}, art. 26, DECADÊNCIA) e fato do produto/"
    "serviço (mesma fonte, art. 27, PRESCRIÇÃO) — sem fundamentar cada "
    "pretensão separadamente, com prazo, termo inicial e fonte próprios. "
    "Revise antes de qualquer uso (HITL)."
)


def checar_cumulacao_vicio_fato_cdc(texto: str) -> list[str]:
    """Detecta cumulação automática, sem fundamentação separada, dos regimes
    do CDC: vício do produto/serviço (art. 26 — decadência) e fato do
    produto/serviço (art. 27 — prescrição).

    Regra determinística: se a resposta menciona os DOIS institutos (vício E
    fato do produto/serviço) mas não nomeia explicitamente as DUAS
    consequências jurídicas distintas (decadência para um, prescrição para o
    outro), a diferenciação por pretensão não foi fundamentada — retorna
    alerta para revisão humana obrigatória. Não altera o texto (apenas
    alerta): a fundamentação de qual pretensão é vício e qual é fato do
    produto depende dos fatos do caso, que só o revisor humano confirma.
    """
    if not texto:
        return []
    tem_vicio = bool(_RE_VICIO_CDC.search(texto))
    tem_fato = bool(_RE_FATO_CDC.search(texto))
    if not (tem_vicio and tem_fato):
        return []
    tem_decadencia = bool(_RE_DECADENCIA.search(texto))
    tem_prescricao = bool(_RE_PRESCRICAO.search(texto))
    if tem_decadencia and tem_prescricao:
        return []
    return [ALERTA_CUMULACAO_CDC]
