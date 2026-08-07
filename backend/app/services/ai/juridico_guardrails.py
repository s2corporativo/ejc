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

# Fonte + vigência/versão da regra citada no aviso (não só a URL): achado de
# review (Codex, PR #703, P0) — um aviso jurídico automático que corrige texto
# do usuário precisa dizer QUAL norma, em QUE REDAÇÃO e DESDE QUANDO, não só
# apontar o artigo. CPC (Lei 13.105/2015) está em vigor desde 18/03/2016 (art.
# 1.045, prazo de vacatio); CDC (Lei 8.078/1990) está em vigor desde
# 11/03/1991 (art. 118) — nenhuma das duas normas mudou de redação nestes
# artigos desde a promulgação até a data deste guardrail.
FONTE_CPC_487_II = (
    "CPC, art. 487, II (Lei 13.105/2015, em vigor desde 18/03/2016, redação "
    "original, sem alteração posterior) "
    "(https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm)"
)
FONTE_CDC_26_27 = (
    "CDC, arts. 26 e 27 (Lei 8.078/1990, em vigor desde 11/03/1991, redação "
    "original, sem alteração posterior) "
    "(https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm)"
)
# CPC, art. 356 — decisão parcial de mérito: quando prescrição/decadência
# resolve só PARTE dos pedidos cumulados, o pronunciamento não é sentença (que
# encerra o processo ou a fase), é decisão interlocutória de mérito parcial.
# Achado de review (Codex, PR #703, P1): afirmar categoricamente "sentença de
# MÉRITO" erra nesse caso — a classificação correta e sempre verdadeira é
# "resolução/decisão de MÉRITO" (sentença OU decisão parcial, a depender de
# extinguir todo o processo ou só parte dos pedidos).
FONTE_CPC_356 = (
    "CPC, art. 356 (Lei 13.105/2015, em vigor desde 18/03/2016) "
    "(https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm)"
)

ALERTA_MERITO_CORRIGIDO = (
    "Guardrail jurídico determinístico corrigiu a qualificação de prescrição/"
    "decadência como extinção SEM resolução de mérito — pelo "
    f"{FONTE_CPC_487_II}, é RESOLUÇÃO DE MÉRITO: sentença, se extinguir todo "
    f"o processo, ou decisão interlocutória de mérito parcial ({FONTE_CPC_356}), "
    "se resolver apenas parte dos pedidos cumulados. Confira o trecho antes "
    "de qualquer uso (HITL)."
)

# Marcador estável usado para detectar se um texto JÁ passou por este
# guardrail (idempotência — achado de review, Codex, PR #703, P1): sem isto,
# reaplicar `aplicar_guardrail_merito` a uma resposta já corrigida encontra as
# próprias palavras-gatilho ("sem resolução de mérito", "art. 485") DENTRO do
# aviso anexado na correção anterior e tenta corrigir o aviso outra vez,
# duplicando-o ou invertendo o próprio texto explicativo.
MARCADOR_CORRECAO_MERITO = (
    "[CORREÇÃO JURÍDICA AUTOMÁTICA — GUARDRAIL DETERMINÍSTICO, Issue #554]"
)

_AVISO_CORRECAO_MERITO = (
    f"\n\n{MARCADOR_CORRECAO_MERITO}\n"
    "Um trecho acima qualificava o reconhecimento de prescrição/decadência "
    "como extinção SEM resolução de mérito (art. 485 do CPC). Isso é um erro: "
    f"pelo {FONTE_CPC_487_II}, prescrição/decadência é RESOLUÇÃO DE MÉRITO — "
    f"sentença, se extinguir todo o processo, ou decisão interlocutória de "
    f"mérito parcial ({FONTE_CPC_356}), se resolver apenas parte dos pedidos "
    "cumulados. Onde o texto dizia \"sem resolução de mérito\", foi corrigido "
    "automaticamente para \"COM resolução de mérito (art. 487, II, do CPC)\". "
    "Revise o texto antes de qualquer uso externo — inclusive para confirmar "
    "se o pronunciamento, no caso concreto, é sentença ou decisão parcial."
)


def ja_corrigido(texto: str | None) -> bool:
    """True se `texto` já contém o marcador deste guardrail — ou seja, já foi
    processado por `aplicar_guardrail_merito` antes. Usado para tornar a
    reaplicação em leitura (GET /ai/logs) idempotente."""
    return bool(texto) and MARCADOR_CORRECAO_MERITO in texto

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

# ── Guardas contra falso-positivo (achado de review, Codex, PR #703, P1) ────
# A janela de proximidade (220 caracteres) casa prescrição/decadência com
# "sem resolução de mérito" mesmo quando: (a) a frase está NEGADA — "não é
# extinção sem resolução de mérito" já afirma o mérito corretamente, e
# substituir só o núcleo da cláusula produziria "não é ... COM resolução de
# mérito", invertendo o sentido; ou (b) a cláusula tem fundamento PRÓPRIO,
# alheio a prescrição/decadência (outra hipótese do art. 485 — ilegitimidade,
# litispendência, coisa julgada etc. — mencionada por coincidência de
# proximidade no mesmo texto). As duas guardas abaixo preferem o FALSO
# NEGATIVO (não corrigir um erro real) ao FALSO POSITIVO (corromper texto já
# correto) — o texto sempre passa por HITL de qualquer forma.
_RE_NEGACAO_PROXIMA = re.compile(r"\bn[ãa]o\b", re.I)
_JANELA_NEGACAO = 35  # caracteres imediatamente antes da cláusula/citação

_RE_OUTRO_FUNDAMENTO_485 = re.compile(
    r"ilegitimidade|il[eé]gitim[oa]|car[êe]ncia\s+de\s+a[cç][ãa]o|"
    r"falta\s+de\s+interesse|aus[êe]ncia\s+de\s+(?:pressuposto|legitimidade|"
    r"interesse)|litispend[êe]ncia|coisa\s+julgada|peremp[cç][ãa]o|"
    r"conven[cç][ãa]o\s+de\s+arbitragem|desist[êe]ncia|"
    r"abandono\s+d[ao]\s+(?:causa|processo)|morte\s+d[ea]\s+parte|"
    r"inde[fs]eri(?:mento)?\s+d[ae]\s+(?:peti[cç][ãa]o\s+)?inicial",
    re.I,
)


def _deve_pular_substituicao(m: re.Match, texto_atual: str) -> bool:
    """True se este match específico NÃO deve ser corrigido: cláusula negada
    (já correta) ou trecho com fundamento próprio alheio a prescrição/
    decadência mencionado só por proximidade."""
    inicio_alvo = m.start(1)
    janela = texto_atual[max(0, inicio_alvo - _JANELA_NEGACAO):inicio_alvo]
    if _RE_NEGACAO_PROXIMA.search(janela):
        return True
    if _RE_OUTRO_FUNDAMENTO_485.search(m.group(0)):
        return True
    return False


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
    menção a prescrição/decadência) exatamente como a IA escreveu. Pula
    matches negados ou com fundamento próprio alheio (`_deve_pular_
    substituicao`) — não corrige o que já está correto ou não tem relação
    real com prescrição/decadência."""
    contagem = 0

    def _rep(m: re.Match) -> str:
        nonlocal contagem
        if _deve_pular_substituicao(m, texto):
            return m.group(0)
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

    Idempotente (achado de review, Codex, PR #703, P1): se `texto` já contém
    o marcador deste guardrail (`ja_corrigido`), retorna sem tocar — evita que
    releituras (GET /ai/logs) encontrem as palavras-gatilho DENTRO do próprio
    aviso anexado numa correção anterior e o reescrevam de novo.

    Retorna (texto_final, foi_corrigido).
    """
    if not texto:
        return texto, False
    if ja_corrigido(texto):
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

# Achado de review (Codex, PR #703, P1): a versão anterior só checava se
# "decadência" e "prescrição" apareciam EM QUALQUER LUGAR do texto — um texto
# que diz "vício e fato do produto; decadência e prescrição aplicam-se
# conjuntamente, sem distinguir prazos" tem as quatro palavras presentes e
# ainda assim é exatamente a cumulação indevida que o guardrail deveria
# capturar. Correção: (1) marcadores textuais explícitos de cumulação
# ("conjuntamente", "sem distinguir/diferenciar", "mesmo prazo/regime") forçam
# alerta mesmo que as quatro palavras apareçam; (2) fora isso, decadência
# precisa estar PAREADA por proximidade a vício (não só presente em algum
# lugar do texto), e prescrição PAREADA a fato do produto/serviço — cada
# regime precisa estar ligado ao instituto correto, não só mencionado.
_JANELA_CDC = r".{0,150}?"

_RE_CUMULACAO_EXPLICITA = re.compile(
    r"conjuntamente|em\s+conjunto|simultaneamente"
    r"|sem\s+distin(?:guir|[cç][ãa]o)|sem\s+diferenciar"
    r"|mesmo\s+prazo|mesmo\s+regime|mesma\s+contagem"
    r"|n[ãa]o\s+se\s+distinguem|n[ãa]o\s+se\s+diferenciam",
    re.I,
)
_RE_VICIO_DECADENCIA_PAREADOS = re.compile(
    rf"(?:{_RE_VICIO_CDC.pattern}){_JANELA_CDC}(?:{_RE_DECADENCIA.pattern})"
    rf"|(?:{_RE_DECADENCIA.pattern}){_JANELA_CDC}(?:{_RE_VICIO_CDC.pattern})",
    re.I,
)
_RE_FATO_PRESCRICAO_PAREADOS = re.compile(
    rf"(?:{_RE_FATO_CDC.pattern}){_JANELA_CDC}(?:{_RE_PRESCRICAO.pattern})"
    rf"|(?:{_RE_PRESCRICAO.pattern}){_JANELA_CDC}(?:{_RE_FATO_CDC.pattern})",
    re.I,
)

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
    fato do produto/serviço), o alerta dispara A MENOS que cada instituto
    esteja PAREADO, por proximidade, com sua própria consequência jurídica
    (vício perto de decadência, fato perto de prescrição) — e mesmo assim, um
    marcador explícito de cumulação ("conjuntamente", "sem distinguir"...)
    força o alerta de qualquer forma. Simplesmente nomear as duas palavras em
    qualquer lugar do texto NÃO basta (era o furo anterior). Não altera o
    texto (apenas alerta): a fundamentação de qual pretensão é vício e qual é
    fato do produto depende dos fatos do caso, que só o revisor humano
    confirma.
    """
    if not texto:
        return []
    tem_vicio = bool(_RE_VICIO_CDC.search(texto))
    tem_fato = bool(_RE_FATO_CDC.search(texto))
    if not (tem_vicio and tem_fato):
        return []
    if _RE_CUMULACAO_EXPLICITA.search(texto):
        return [ALERTA_CUMULACAO_CDC]
    vicio_pareado_decadencia = bool(_RE_VICIO_DECADENCIA_PAREADOS.search(texto))
    fato_pareado_prescricao = bool(_RE_FATO_PRESCRICAO_PAREADOS.search(texto))
    if vicio_pareado_decadencia and fato_pareado_prescricao:
        return []
    return [ALERTA_CUMULACAO_CDC]


# Marcador estável do alerta CDC anexado ao texto — mesmo raciocínio de
# `MARCADOR_CORRECAO_MERITO`: permite detectar se o alerta já foi anexado
# (idempotência) e, principalmente, permite persistir o alerta no PRÓPRIO
# texto salvo em `AILog.resposta` (achado de review, Codex, PR #703, P1):
# antes, quando só `checar_cumulacao_vicio_fato_cdc` disparava (sem correção
# de mérito), `texto_corrigido` não mudava — o alerta só existia na resposta
# transiente da API (`resultado["aviso"]`) e sumia ao reler o log.
MARCADOR_ALERTA_CDC = "[ALERTA JURÍDICO AUTOMÁTICO — GUARDRAIL DETERMINÍSTICO, Issue #554]"

_AVISO_CUMULACAO_CDC = f"\n\n{MARCADOR_ALERTA_CDC}\n{ALERTA_CUMULACAO_CDC}"


def anexar_alerta_cdc_ao_texto(texto: str, alertas: list[str]) -> str:
    """Anexa o alerta de cumulação CDC ao TEXTO, no mesmo padrão de
    `aplicar_guardrail_merito` (aviso visível, nunca silencioso) — para que a
    persistência em `AILog.resposta` carregue o alerta, não só a resposta
    transiente da API. Idempotente: não duplica se o marcador já estiver
    presente. Não faz nada se `alertas` estiver vazio (nenhum alerta CDC
    disparou) — preserva o texto exatamente como veio."""
    if not alertas or not texto:
        return texto
    if MARCADOR_ALERTA_CDC in texto:
        return texto
    return texto + _AVISO_CUMULACAO_CDC


def aplicar_guardrails_de_leitura(texto: str) -> tuple[str, bool]:
    """Encadeia os DOIS guardrails na ordem canônica — correção de mérito
    (CPC art. 487, II) e depois alerta de cumulação CDC 26/27 — e devolve
    `(texto, alterou)`.

    Existe para que TODA superfície de leitura de resposta já persistida
    aplique o mesmo conjunto. Antes, `GET /ai/logs` chamava só
    `aplicar_guardrail_merito`: um log legado com cumulação CDC indevida era
    servido sem o alerta que a mesma resposta receberia se fosse gerada hoje
    (achado do review do CodeRabbit no PR #703).

    `alterou` é o gatilho do reset de HITL: se o texto mudou AGORA, na
    leitura, quem revisou antes revisou outra coisa. Ambas as funções são
    idempotentes, então reler um texto já tratado devolve `alterou=False`."""
    corrigido, houve_merito = aplicar_guardrail_merito(texto)
    alertas_cdc = checar_cumulacao_vicio_fato_cdc(corrigido)
    if alertas_cdc:
        com_alerta = anexar_alerta_cdc_ao_texto(corrigido, alertas_cdc)
        if com_alerta != corrigido:
            return com_alerta, True
        corrigido = com_alerta
    return corrigido, houve_merito
