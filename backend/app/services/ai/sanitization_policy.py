# ── app/services/ai/sanitization_policy.py ───────────────────────────────────
# NÍVEIS DE SANITIZAÇÃO DE PII POR TIPO DE TAREFA (Núcleo Único de IA).
#
# Eleva o mascaramento irreversível legado para uma política graduada por
# tarefa, decidindo COMO o conteúdo é tratado antes de um provider EXTERNO
# (Anthropic/Groq — fora do VPS, art. 33/46 LGPD):
#
#   • LOCAL_COMPLETO         (Modo 1) — sigilo reforçado: só Ollama LOCAL; o
#                            conteúdo NUNCA vai a provider externo (nem
#                            pseudonimizado). Sem local elegível → bloqueia.
#   • EXTERNO_PSEUDONIMIZADO (Modo 2+3) — pseudonimiza (marcadores consistentes
#                            e reversíveis) → externo → REIDRATA a resposta
#                            localmente. Seguro para análise/minuta.
#   • EXTRACAO_LOCAL         (Modo 4) — a PII estruturada é extraída LOCALMENTE
#                            (regex/parser) no ponto de importação; ao gateway,
#                            trata-se como ≥ pseudonimizado (nunca vaza PII).
#   • MASCARAMENTO           (legado/fallback) — mascaramento IRREVERSÍVEL via
#                            sanitizer ([CPF], [EMAIL]…). Comportamento atual.
#
# O mapeamento default é REVISÁVEL POR DR. CLOVIS e OVERRIDÁVEL por configuração
# (Settings.AI_SANITIZATION_MODE_MAP — JSON opcional task_type→modo). Sem
# override, vale o default abaixo.
#
# DECISÃO DE PRODUTO (2026-07-06, dono do escritório): a IA deve funcionar
# PLENAMENTE usando PSEUDONIMIZAÇÃO REVERSÍVEL (não mascaramento irreversível,
# não bloqueio). Nenhum PII real sai do VPS — o provider externo recebe apenas
# marcadores consistentes e a resposta é REIDRATADA localmente. O default de
# tarefa não mapeada é EXTERNO_PSEUDONIMIZADO (reversível), não MASCARAMENTO.
#
# ATUALIZAÇÃO (auditoria máxima 2026-07-26, achado AI-019, dono do sistema):
# áreas SENSÍVEIS (penal/criminal, família, saúde, menores, violência) voltam a
# LOCAL_COMPLETO por padrão — pseudonimização protege a identidade direta, mas
# fatos raros e combinações de eventos dessas áreas permitem reidentificação.
# Esses defaults são um PISO não-rebaixável por override (fail-closed sem IA
# local); exceção exige mudança de código revisada, não configuração.
#
# DECISÃO DO TITULAR (18/08, por chat, em resposta à pergunta sobre IA
# indisponível nas 9 áreas de sigilo reforçado): "Fica só a questão de crimes
# sexuais, e com menores. O resto pode ficar normal. Pseudonimizado." — reduz o
# piso LOCAL_COMPLETO a **crimes sexuais e casos envolvendo menores/infância e
# juventude** (o risco de reidentificação por combinação de fatos raros que
# justificou o AI-019 é maior justamente aí: vítima/réu identificável por
# poucos detalhes, e o dano de uma reidentificação errada é o mais grave do
# sistema). Penal/criminal geral, família, saúde, médico e violência
# (inclusive doméstica) voltam ao tratamento "normal" do resto do sistema —
# EXTERNO_PSEUDONIMIZADO, não MASCARAMENTO nem bloqueio: pseudonimiza,
# reidrata a resposta localmente, nunca sai PII real do VPS.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
import logging
import unicodedata
from enum import Enum

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.sanitization_policy")


class ModoSanitizacao(str, Enum):
    LOCAL_COMPLETO = "local_completo"
    EXTERNO_PSEUDONIMIZADO = "externo_pseudonimizado"
    EXTRACAO_LOCAL = "extracao_local"
    MASCARAMENTO = "mascaramento"


# ── Mapeamento DEFAULT (revisável por Dr. Clovis) ─────────────────────────────
# Chaves em minúsculo; cobre o vocabulário de TarefaIA (system_prompts/router.py)
# E os task_types do ai_gateway (TASK_ROUTING + aliases), pois `chat()` pode
# receber qualquer um dos dois. Comparação é feita sobre o task_type ORIGINAL
# (antes da normalização por aliases do gateway).
_MODO_DEFAULT_POR_TASK: dict[str, ModoSanitizacao] = {
    # ── SIGILO REFORÇADO → LOCAL_COMPLETO (decisão do titular, 18/08: reduz o
    # piso do AI-019 a crimes sexuais e casos com menores/infância e juventude
    # — ver decisão datada acima). Consequência operacional deliberada
    # (fail-closed): sem Ollama on-prem ativo, a IA dessas DUAS áreas fica
    # INDISPONÍVEL (scripts/subir-ia-local.sh para habilitar IA local). O piso
    # de segurança em modo_para_task impede rebaixar estes defaults por
    # override.
    "crimes_sexuais": ModoSanitizacao.LOCAL_COMPLETO,
    "menores": ModoSanitizacao.LOCAL_COMPLETO,
    "infancia_juventude": ModoSanitizacao.LOCAL_COMPLETO,
    # Penal/criminal geral, família, saúde, médico e violência (achado AI-019
    # original) voltaram ao tratamento normal do resto do sistema por decisão
    # do titular (18/08) — explícitas aqui (em vez de cair no fallback) para
    # que a intenção fique registrada e não dependa do valor de
    # `_MODO_FALLBACK` mudar no futuro.
    "criminal": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "penal": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "familia": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "saude": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "medico": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "violencia": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "violencia_domestica": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    # Modo 2+3 — pseudonimização reversível + reidratação (análise/minuta).
    "analise_caso": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "dossie": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "minutas": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "estrategia": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "pesquisa_juridica": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "trabalhista": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "administrativo": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "sucessoes": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "imobiliario": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "constitucional": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "juizados": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "civel": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "ambiental": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "honorarios": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "audiencia": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "prazos": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    # Vocabulário do gateway (TASK_ROUTING) para tarefas complexas equivalentes.
    "analise_juridica": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "elaboracao_peca": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "analise_contrato": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "auditoria_peca": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "jurimetria": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "critica_adversarial": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    # Modo 4 — extração estruturada local (importação/OCR de documento).
    "intake": ModoSanitizacao.EXTRACAO_LOCAL,
    "importacao_documento": ModoSanitizacao.EXTRACAO_LOCAL,
    "extracao_documento": ModoSanitizacao.EXTRACAO_LOCAL,
    "ocr": ModoSanitizacao.EXTRACAO_LOCAL,
    # Tarefas simples/econômicas — antes MASCARAMENTO irreversível. Migradas
    # para EXTERNO_PSEUDONIMIZADO (2026-07-06) para NÃO degradar a qualidade com
    # marcadores irreversíveis ([CPF]/[EMAIL]): agora usam marcadores reversíveis
    # e a resposta é reidratada localmente. A barreira externa continua idêntica.
    "triagem": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "resumo": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "rag_query": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "chat_rapido": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "chat": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "default": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
}

# Fallback para tarefa desconhecida (2026-07-06): PSEUDONIMIZAÇÃO REVERSÍVEL —
# nunca "sem sanitização". Antes era MASCARAMENTO irreversível; a decisão de
# produto elegeu pseudonimização reversível como piso universal (qualidade sem
# vazar PII: o gateway só envia marcadores ao externo e reidrata a resposta).
_MODO_FALLBACK = ModoSanitizacao.EXTERNO_PSEUDONIMIZADO

# ── Normalização de rótulo (consolidação 2026-07-29) ─────────────────────────
# O `task_type`/`domain` chega de campo livre (`Field(max_length=60)` em
# routers/ai_core.py) e da UI em português. Antes, a resolução era um lookup de
# chave EXATA sobre `.strip().lower()`: "família" (com acento), "Direito de
# Família" e "familia_analysis" NÃO batiam com a chave "familia" e caíam no
# fallback EXTERNO_PSEUDONIMIZADO — ou seja, o conteúdo de uma área de sigilo
# reforçado saía do VPS. A normalização abaixo (acentos, separadores e sufixos
# de rotina) fecha esse bypass por alias/string livre num ÚNICO ponto, de modo
# que todos os chamadores (gateway, orquestrador, agent/loop, ai_cache) herdam a
# mesma regra — sem cópias divergentes espalhadas pelo código.
_SUFIXOS_DE_ROTINA = ("_analysis", "_analise", "_analise_juridica", "_ia", "_agent")


def normalizar_rotulo(valor: str | None) -> str:
    """Canoniza um rótulo de tarefa/área: sem acento, minúsculo, separadores
    unificados em `_` e sem sufixos de rotina (`familia_analysis` → `familia`)."""
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    # Remove acentos (Mn) e TAMBÉM caracteres invisíveis de formatação/controle
    # (Cf/Cc): "fam​ilia" com zero-width space, ou soft hyphen no meio da
    # palavra, escapavam do piso por não casarem nenhuma chave.
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
        and unicodedata.category(c) not in ("Cf", "Cc")
    )
    texto = texto.strip().lower()
    for sep in (" ", "-", "/", ".", ":"):
        texto = texto.replace(sep, "_")
    while "__" in texto:
        texto = texto.replace("__", "_")
    texto = texto.strip("_")
    for sufixo in _SUFIXOS_DE_ROTINA:
        if texto.endswith(sufixo) and len(texto) > len(sufixo):
            texto = texto[: -len(sufixo)]
            break
    return texto


# Palavras que, sozinhas, caracterizam área de sigilo reforçado. Derivadas das
# próprias chaves LOCAL_COMPLETO do mapa (inclusive as compostas: de
# "infancia_juventude" saem "infancia" e "juventude"), para cobrir o rótulo que
# a UI produz — "direito_de_familia", "vara_da_infancia_e_juventude",
# "plano_de_saude" — e que um lookup de chave exata jamais alcançaria.
# Só marcam PARA CIMA: o pior caso de um falso positivo é exigir IA local numa
# área que aceitaria externo, nunca o contrário.
# RADICAIS, não palavras inteiras. Casar palavra exata deixava passar as formas
# que o vocabulário jurídico brasileiro produz o tempo todo: "perícia médica"
# (feminino) não casava "medico", "antecedentes criminais" (plural) não casava
# "criminal", "direito familiar" (adjetivo) não casava "familia". O radical cobre
# as três de uma vez. Só marcam PARA CIMA: o pior caso de um falso positivo é
# exigir IA local numa área que aceitaria externo — nunca o contrário.
# NOTA (18/08): esta tabela mapeia radical → CHAVE DE ÁREA canônica, não
# radical → LOCAL_COMPLETO. Quem decide LOCAL_COMPLETO vs EXTERNO_PSEUDONIMIZADO
# é `_MODO_DEFAULT_POR_TASK` (acima) para a chave resolvida — várias das chaves
# aqui (familia, criminal, penal, saude, medico, violencia*) hoje resolvem para
# EXTERNO_PSEUDONIMIZADO. A tabela continua útil para identificar/rotular a
# área mesmo quando ela não é sigilo reforçado.
_RADICAIS_SIGILO_REFORCADO: tuple[tuple[str, str], ...] = (
    ("famili", "familia"),          # familia, familiar, familiares
    ("crimin", "criminal"),         # criminal, criminais, criminalista
    ("penal", "penal"),             # penal, penais
    ("saud", "saude"),              # saude, saudes
    ("medic", "medico"),            # medico, medica, medicas, medicamento
    ("menor", "menores"),           # menor, menores
    ("infan", "infancia_juventude"),   # infancia, infantil, infanto
    ("juven", "infancia_juventude"),   # juventude, juvenil
    # Achado do security-auditor (Issue #1194): "criança"/"adolescente" são
    # vocabulário comum de família/infância e não tinham radical próprio — só
    # eram cobertos incidentalmente quando o texto TAMBÉM continha "infantil"/
    # "menor"/"juvenil".
    ("crianc", "infancia_juventude"),  # crianca, criancas
    ("adolescen", "infancia_juventude"),  # adolescente, adolescencia
    ("violen", "violencia"),        # violencia, violento
    ("domestic", "violencia_domestica"),
    ("divorcio", "familia"),        # divórcio é matéria de família
    ("guarda", "familia"),          # guarda de menor (o token "menor" à parte
                                     # já cobre o caso pelo radical "menor")
    ("alimento", "familia"),        # pensão alimentícia
    ("habeas", "penal"),            # habeas corpus
    # Crimes sexuais (decisão do titular, 18/08) — continuam sigilo reforçado
    # mesmo fora de "criminal"/"penal" geral (agora normais). "sexual" sozinho
    # cobre a maioria das expressões compostas do vocabulário jurídico
    # ("crime sexual", "abuso sexual", "violência sexual", "importunação
    # sexual", "assédio sexual" — o split por "_" isola o token "sexual").
    ("sexual", "crimes_sexuais"),
    ("estupro", "crimes_sexuais"),
    ("pedofil", "crimes_sexuais"),  # pedofilia, pedófilo, pedófila
    # Achado do security-auditor: terminologia legada do CP pré-Lei 12.015/2009
    # ("atentado violento ao pudor") e formas que não contêm o radical "sexual"
    # ou "estupro" isoladamente.
    ("libidinos", "crimes_sexuais"),  # ato libidinoso
    ("pudor", "crimes_sexuais"),      # atentado violento ao pudor (CP pré-2009)
    ("vulneravel", "crimes_sexuais"),  # estupro/ato libidinoso de vulnerável
)


def _chaves_candidatas(rotulo: str) -> list[str]:
    """Chaves a consultar no mapa, da mais específica para a mais genérica: o
    rótulo canônico inteiro e, depois, a chave de sigilo de cada palavra cujo
    RADICAL indique área sensível (`direito_familiar` → consulta `familia`)."""
    if not rotulo:
        return []
    candidatas = [rotulo]
    for palavra in rotulo.split("_"):
        for radical, chave in _RADICAIS_SIGILO_REFORCADO:
            if palavra.startswith(radical) and chave not in candidatas:
                candidatas.append(chave)
                break
    return candidatas


def _overrides() -> dict[str, ModoSanitizacao]:
    """Lê Settings.AI_SANITIZATION_MODE_MAP (JSON opcional task_type→modo).
    JSON inválido/valor desconhecido é ignorado com log de aviso (fail-safe:
    cai no default), nunca derruba a chamada de IA."""
    raw = (getattr(get_settings(), "AI_SANITIZATION_MODE_MAP", "") or "").strip()
    if not raw:
        return {}
    try:
        bruto = json.loads(raw)
        if not isinstance(bruto, dict):
            raise ValueError("esperado objeto JSON task_type→modo")
    except Exception as e:  # noqa: BLE001 — override malformado nunca quebra IA
        logger.warning("AI_SANITIZATION_MODE_MAP ignorado (inválido): %s", str(e)[:200])
        return {}
    resultado: dict[str, ModoSanitizacao] = {}
    for task, modo in bruto.items():
        try:
            resultado[normalizar_rotulo(task)] = ModoSanitizacao(str(modo).strip().lower())
        except ValueError:
            logger.warning(
                "AI_SANITIZATION_MODE_MAP: modo '%s' desconhecido p/ '%s' — ignorado",
                modo, task,
            )
    return resultado


def reforcar_sigilo(base: ModoSanitizacao,
                    area: ModoSanitizacao | None) -> ModoSanitizacao:
    """Combina o modo da TAREFA (`base`) com o modo derivado da ÁREA do caso
    (`area`), aplicando o PISO de sigilo não-rebaixável: se a área exige
    LOCAL_COMPLETO (sigilo reforçado), o resultado é LOCAL_COMPLETO — o dado nunca
    pode sair do VPS mesmo que a tarefa aceitasse externo (achado S1). Caso
    contrário mantém o modo da tarefa (a área nunca ENFRAQUECE o modo da tarefa).
    """
    if area == ModoSanitizacao.LOCAL_COMPLETO:
        return ModoSanitizacao.LOCAL_COMPLETO
    return base


def modo_para_task(task_type: str) -> ModoSanitizacao:
    """Retorna o ModoSanitizacao para `task_type` (default + override de config).

    O override (AI_SANITIZATION_MODE_MAP) tem precedência sobre o default, EXCETO
    pelo PISO DE SEGURANÇA não-rebaixável: se o DEFAULT da tarefa for
    LOCAL_COMPLETO (sigilo reforçado), um override que NÃO seja LOCAL_COMPLETO é
    IGNORADO (com aviso) — o dado não pode ser rebaixado para externo por
    configuração. Reforçar (qualquer tarefa → LOCAL_COMPLETO) é sempre permitido.

    NOTA (decisão do titular, 18/08): só crimes sexuais e menores/infância e
    juventude têm default LOCAL_COMPLETO; pelo piso acima, essas DUAS áreas
    NÃO podem ser rebaixadas para externo via AI_SANITIZATION_MODE_MAP.
    Reforçar (qualquer tarefa → LOCAL_COMPLETO) segue sempre permitido. Tarefa
    não mapeada em nenhum dos dois → `_MODO_FALLBACK` (EXTERNO_PSEUDONIMIZADO,
    reversível e seguro).

    Um rótulo composto pode casar MAIS de uma chave (ex.: "violencia_sexual"
    casa "violencia" — normal — E "crimes_sexuais" — sigilo reforçado, via
    `_chaves_candidatas`). Por isso o default NÃO é "a primeira chave que
    bater": é a mais restritiva entre todas as candidatas que baterem —
    LOCAL_COMPLETO nunca perde para uma chave normal encontrada antes dela na
    string (mesma lógica de "só marcam PARA CIMA" da tabela de radicais)."""
    task = normalizar_rotulo(task_type)
    padrao = _MODO_FALLBACK
    primeira_candidata: ModoSanitizacao | None = None
    for chave in _chaves_candidatas(task):
        modo = _MODO_DEFAULT_POR_TASK.get(chave)
        if modo is None:
            continue
        if primeira_candidata is None:
            primeira_candidata = modo
        if modo == ModoSanitizacao.LOCAL_COMPLETO:
            primeira_candidata = ModoSanitizacao.LOCAL_COMPLETO
            break
    if primeira_candidata is not None:
        padrao = primeira_candidata
    over = _overrides()
    if task in over:
        escolhido = over[task]
        # Piso: LOCAL_COMPLETO por default nunca é rebaixado por override.
        if padrao == ModoSanitizacao.LOCAL_COMPLETO and escolhido != ModoSanitizacao.LOCAL_COMPLETO:
            logger.warning(
                "AI_SANITIZATION_MODE_MAP: override '%s' para '%s' IGNORADO — "
                "tarefa de sigilo reforçado (LOCAL_COMPLETO) não pode ser rebaixada "
                "para provider externo (piso de segurança LGPD).",
                escolhido.value, task,
            )
            return ModoSanitizacao.LOCAL_COMPLETO
        return escolhido
    return padrao


def areas_que_exigem_ia_local() -> list[str]:
    """Rótulos cujo modo default é LOCAL_COMPLETO — só a IA local pode atendê-los.

    Sem provedor local elegível, a IA dessas áreas fica INDISPONÍVEL: é
    fail-closed deliberado (o dado sensível não sai do VPS). O problema não é a
    regra, é ela ser invisível — hoje só se descobre quando um advogado tenta
    usar a IA num caso de família e recebe um erro. Ver ia_saude.
    """
    return sorted(
        chave for chave, modo in _MODO_DEFAULT_POR_TASK.items()
        if modo == ModoSanitizacao.LOCAL_COMPLETO
    )


def rotulo_de_sigilo_reforcado(*rotulos: str | None) -> str | None:
    """Primeiro rótulo, na ordem dada, que exige LOCAL_COMPLETO — já CANONIZADO.

    Ponto único da regra "qual rótulo o gateway precisa receber para que o piso
    de sigilo sobreviva às transformações do orquestrador". O orquestrador mapeia
    `TarefaIA.FAMILIA` → "estrategia" antes do gateway, e é o gateway que resolve
    o modo de sanitização pelo `task_type`; sem devolver aqui o rótulo da área, o
    piso se perde no meio da cadeia (achado AI-019).

    Devolve a CHAVE CANÔNICA do mapa (ex.: "familia" para "Direito de Família"),
    não o texto cru recebido — assim o gateway reencontra a mesma política. `None`
    quando nenhum rótulo é de área sensível.

    Não captura exceções de propósito: se a política de sigilo não puder ser
    avaliada, a chamada de IA deve falhar, e não seguir com o rótulo rebaixado.
    """
    for bruto in rotulos:
        canonico = normalizar_rotulo(bruto)
        if not canonico or modo_para_task(canonico) != ModoSanitizacao.LOCAL_COMPLETO:
            continue
        # Devolve a chave do MAPA, não o rótulo composto: de "direito_de_familia"
        # sai "familia", que é o que o gateway sabe rotear.
        for chave in _chaves_candidatas(canonico):
            if chave in _MODO_DEFAULT_POR_TASK:
                return chave
        return canonico
    return None
