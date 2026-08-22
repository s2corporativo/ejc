"""
verificador_jurisprudencia.py — Verificador RIGOROSO de jurisprudência (anti-alucinação).

Evolução do citation_check (#46): não basta "citar jurisprudência" — o texto
precisa trazer número de processo, tribunal, órgão julgador, data e fonte
verificável. Este módulo:

  1. PARSEIA citações estruturadas:
       • número CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO) com validação do dígito
         verificador (módulo 97 / ISO 7064, Resolução CNJ 65/2008) e
         decodificação de segmento/tribunal/ano;
       • recursos superiores (REsp/AREsp/EREsp/RE/ARE/AgInt/AgRg/EDcl/HC/RHC/
         MS/ADI/ADC/ADPF + número);
       • súmulas STF/STJ/TST (vinculantes ou não) com validação de FAIXA;
       • artigos de lei (mantido do citation_check, conferido no RAG);
       • menções VAGAS ("jurisprudência pacífica", "entendimento consolidado")
         sem referência → citação `generica`.
     E extrai do contexto: tribunal, órgão julgador, relator e data.

  2. CLASSIFICA cada citação:
       • `verificada`  — confirmada em fonte externa/oficial (DataJud p/ nº CNJ
                         quando `consultar_datajud=True`; base RAG oficial p/
                         súmulas e artigos);
       • `identificada`— referência estruturada PLAUSÍVEL (DV válido, súmula em
                         faixa, REsp com número) mas NÃO confirmada externamente;
       • `suspeita`    — formato inválido (DV errado, súmula fora de faixa,
                         tribunal inexistente) → possível alucinação;
       • `generica`    — menção vaga sem qualquer referência verificável.
       • `possivelmente_desatualizada` — localizada na base interna APENAS em
         versão SUPERADA (`KnowledgeDoc.vigente=False`): existe, mas a redação
         ingerida foi substituída. Citar redação revogada em peça é erro
         profissional, e antes disto era indistinguível de "não ingerida".

  3. PONTUA a confiabilidade do texto (0-100):
       score = round(100 * (1.0*verificadas + 0.6*identificadas) / total)
     `suspeita`, `generica` e `possivelmente_desatualizada` pesam 0.
     Texto SEM citações → score = None.

Retorno RETROCOMPATÍVEL com verificar_citacoes (mesmas chaves total/
confirmadas/nao_encontradas/citacoes[{citacao,tipo,encontrada,fonte}]/aviso),
apenas ESTENDIDO com score/avisos/contagem_status e campos extras por citação.
100% local por padrão; consulta externa (DataJud) é opt-in e fail-safe.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata

logger = logging.getLogger("ejc.verificador_juris")

# ── Constantes documentadas ───────────────────────────────────────────────────

# Status possíveis de uma citação (ver docstring do módulo).
STATUS_VERIFICADA = "verificada"
STATUS_IDENTIFICADA = "identificada"
STATUS_SUSPEITA = "suspeita"
STATUS_GENERICA = "generica"
# Localizada na base, mas SÓ em versão superada (KnowledgeDoc.vigente=False).
# Os lookups oficiais filtram vigente=TRUE: sem este estado, citar norma
# revogada/substituída era indistinguível de citar algo nunca ingerido.
STATUS_DESATUALIZADA = "possivelmente_desatualizada"

# Teto plausível de número de súmula por tribunal (última súmula editada
# conhecida; atualizar quando os tribunais editarem novas — número ACIMA do
# teto é forte indício de alucinação):
#   STF: Súmula 736 (última ordinária) · Súmulas Vinculantes: 61
#   STJ: Súmula 676 · TST: Súmula 463
SUMULA_TETO: dict[str, int] = {"STF": 736, "STF-V": 61, "STJ": 676, "TST": 463}
_SUMULA_TETO_DEFAULT = max(SUMULA_TETO.values())  # órgão não informado no texto
# Data da última conferência dos tetos acima contra fonte oficial. Um teto
# vencido acusa de alucinação súmula NOVA e verdadeira (P2-13 da auditoria de
# 18/08) — por isso, vencido o prazo, o aviso passa a ressalvar isso ao revisor
# em vez de afirmar que a súmula "provavelmente não existe".
SUMULA_TETO_CONFERIDO_EM = "2026-07-18"

# Consulta ativa ao DataJud (opt-in): no MÁXIMO 5 números CNJ consultados por
# verificação (evita estourar o rate limit público do CNJ em textos longos) e
# timeout curto por consulta — falha NUNCA vira erro, o status cai para
# `identificada` com aviso.
MAX_CONSULTAS_DATAJUD = 5
DATAJUD_TIMEOUT_S = 8.0

# Janela de contexto (chars) ao redor da citação para extrair tribunal/órgão/
# relator/data e para suprimir menção vaga que JÁ vem acompanhada de referência.
_JANELA_ANTES = 100
_JANELA_DEPOIS = 220

_MAX_TEXTO = 200_000  # guarda defensiva (o endpoint também limita)

# ── Decodificação do número CNJ (Res. CNJ 65/2008) ───────────────────────────

_SEGMENTOS = {
    "1": "STF", "2": "CNJ", "3": "STJ", "4": "Justiça Federal",
    "5": "Justiça do Trabalho", "6": "Justiça Eleitoral",
    "7": "Justiça Militar da União", "8": "Justiça Estadual",
    "9": "Justiça Militar Estadual",
}

# TR (código do tribunal) → UF, para J=6 (TRE) e J=8 (TJ) — ordem alfabética oficial.
_TR_UF = {
    1: "AC", 2: "AL", 3: "AP", 4: "AM", 5: "BA", 6: "CE", 7: "DF", 8: "ES",
    9: "GO", 10: "MA", 11: "MT", 12: "MS", 13: "MG", 14: "PA", 15: "PB",
    16: "PR", 17: "PE", 18: "PI", 19: "RJ", 20: "RN", 21: "RS", 22: "RO",
    23: "RR", 24: "SC", 25: "SE", 26: "SP", 27: "TO",
}

_UFS_VALIDAS = set(_TR_UF.values())


def validar_dv_cnj(numero: str) -> bool:
    """Valida o dígito verificador do número CNJ (módulo 97, ISO 7064).

    Regra da Resolução CNJ 65/2008: reordenando o número como
    NNNNNNN + AAAA + J + TR + OOOO + DD, o resto da divisão por 97 deve ser 1.
    """
    n = re.sub(r"\D", "", numero or "")
    if len(n) != 20:
        return False
    seq, dd, resto = n[:7], n[7:9], n[9:]  # resto = AAAA J TR OOOO
    return int(f"{seq}{resto}{dd}") % 97 == 1


def decodificar_cnj(numero: str) -> dict:
    """Decodifica segmento/tribunal/ano do número CNJ e valida os códigos.

    Retorna {segmento, tribunal, ano, tribunal_valido, motivo}.
    """
    n = re.sub(r"\D", "", numero or "")
    ano, j, tr = n[9:13], n[13], n[14:16]
    tr_i = int(tr)
    segmento = _SEGMENTOS.get(j)
    tribunal: str | None = None
    valido, motivo = True, None
    if not segmento:
        valido, motivo = False, f"segmento de justiça '{j}' inexistente"
    elif j in ("1", "2", "3", "7"):
        # Tribunais únicos (STF/CNJ/STJ/STM) usam TR=00.
        tribunal = {"1": "STF", "2": "CNJ", "3": "STJ", "7": "STM"}[j]
        if tr != "00":
            valido, motivo = False, f"{tribunal} exige código de tribunal 00 (veio {tr})"
    elif j == "4":
        if 1 <= tr_i <= 6:
            tribunal = f"TRF{tr_i}"
        else:
            valido, motivo = False, f"TRF{tr_i} não existe (regiões 1 a 6)"
    elif j == "5":
        if 1 <= tr_i <= 24:
            tribunal = f"TRT{tr_i}"
        else:
            valido, motivo = False, f"TRT{tr_i} não existe (regiões 1 a 24)"
    elif j == "6":
        uf = _TR_UF.get(tr_i)
        if uf:
            tribunal = f"TRE-{uf}"
        else:
            valido, motivo = False, f"código de TRE '{tr}' inexistente"
    elif j == "8":
        uf = _TR_UF.get(tr_i)
        if uf:
            tribunal = f"TJ{uf}"
        else:
            valido, motivo = False, f"código de TJ estadual '{tr}' inexistente"
    elif j == "9":
        if tr_i in (13, 21, 26):  # só MG, RS e SP têm Justiça Militar Estadual
            tribunal = f"TJM{_TR_UF[tr_i]}"
        else:
            valido, motivo = False, f"Justiça Militar Estadual inexistente p/ código {tr}"
    return {"segmento": segmento, "tribunal": tribunal, "ano": ano,
            "tribunal_valido": valido, "motivo": motivo}


def formatar_cnj(numero: str) -> str:
    """20 dígitos → NNNNNNN-DD.AAAA.J.TR.OOOO."""
    n = re.sub(r"\D", "", numero or "")
    return f"{n[:7]}-{n[7:9]}.{n[9:13]}.{n[13]}.{n[14:16]}.{n[16:20]}"


# ── Regexes de extração ───────────────────────────────────────────────────────

# Número CNJ no formato canônico com separadores.
_RE_CNJ = re.compile(r"\b(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})\b")
# 20 dígitos "crus" só quando precedidos de indicação de processo (reduz falso positivo).
_RE_CNJ_CRU = re.compile(
    r"(?:processos?|proc\.?|autos)(?:\s+n[ºo°.]*)?\s*[:.]?\s*(\d{20})\b", re.IGNORECASE)

# Recursos/ações de tribunais superiores. Case-sensitive de propósito
# (siglas curtas como RE/MS/ARE em minúsculas seriam falso positivo).
_RE_RECURSO = re.compile(
    r"\b(AREsp|ARESP|EREsp|ERESP|REsp|RESP|AgInt|AGINT|AgRg|AGRG|EDcl|EDCL|"
    r"RHC|HC|MS|ADPF|ADI|ADC|ARE|RE)\s*(?:n[ºo°.]*\s*)?"
    r"(\d{1,3}(?:\.\d{3})+|\d{1,9})\b(?:\s*/\s*([A-Z]{2}))?")

_CLASSE_STJ = {"RESP", "ARESP", "ERESP"}
_CLASSE_STF = {"RE", "ARE", "ADI", "ADC", "ADPF"}

# Súmula (com captura do "vinculante" e do órgão).
_RE_SUMULA = re.compile(
    r"s[úu]mula(?:\s+(vinculante))?\s+(?:n[ºo°.]*\s*)?(\d{1,4})\s*"
    r"(?:[\-/]?\s*(?:d[oae]\s+)?)?(stf|stj|tst|tjmg)?",
    re.IGNORECASE,
)

# Artigo de lei (mantido do citation_check — conferido no RAG de legislação).
#
# Auditoria de 22/08/2026: o padrão anterior exigia SIGLA e número de até 4
# dígitos sem separador. Medido, isso deixava o gate antialucinação cego para a
# forma mais natural de citar num texto jurídico — 5 de 12 formas testadas
# passavam sem serem sequer extraídas:
#
#     'artigo 927 do Código Civil'   -> []   (e 927 é a cláusula geral de
#                                             responsabilidade civil)
#     'artigo 300 do Código de Processo Civil' -> []
#     'artigo 5º da Constituição Federal'      -> []
#     'art. 1.234 do CPC'            -> []   (separador de milhar)
#     'artigo 42.789 do Código Civil'-> []   (FABRICADO, e passava)
#
# Citação não extraída é citação não verificada: o gate só bloqueia o que
# enxerga. Um gate cego para a forma dominante é um gate desligado na prática,
# e `CLAUDE.md` (regra 4) trata contornar o citation gate como inegociável.
#
# Duas ampliações, ambas medidas contra falso positivo:
#   1. diploma por extenso, normalizado à sigla logo abaixo (`_DIPLOMA_CANONICO`)
#      — sem normalizar, `citation_check._restringir_ao_diploma` não encontra a
#      chave e a citação vira inconfirmável, bloqueando pelo motivo errado;
#   2. número com separador de milhar, capturado DENTRO do grupo do número.
#
# A janela entre número e diploma continua PROIBINDO ponto, de propósito:
# aceitá-lo faria o padrão atravessar fim de frase ("Vendeu o art. 42 ontem. O
# Código Civil regula...") e parear artigo de uma frase com diploma de outra.
# O custo é a forma com abreviação no meio ("art. 5º, inc. II, da CF"), que
# segue não extraída — limitação conhecida, preferida a pareamento errado.
_DIPLOMA_EXTENSO = (
    r"constitui[çc][ãa]o\s+(?:federal"
    r"|da\s+rep[úu]blica(?:\s+federativa(?:\s+do\s+brasil)?)?)"
    r"|c[óo]digo\s+de\s+processo\s+civil"
    r"|c[óo]digo\s+de\s+processo\s+penal"
    r"|c[óo]digo\s+de\s+defesa\s+do\s+consumidor"
    r"|c[óo]digo\s+tribut[áa]rio\s+nacional"
    r"|consolida[çc][ãa]o\s+das\s+leis\s+do\s+trabalho"
    r"|c[óo]digo\s+civil"
    r"|c[óo]digo\s+penal"
)
_RE_ARTIGO = re.compile(
    r"\bart(?:igo)?s?\.?\s*(\d{1,3}(?:\.\d{3})+|\d{1,4})[º°ªa]?(?:[\-,]?[A-Z])?\b"
    r"[^.;\n]{0,45}?\b(" + _DIPLOMA_EXTENSO +
    r"|cf|cpc|cc|clt|cdc|cpp|cp|ctn|lei\s*n?[ºo°.]*\s*[\d.]+\/?\d*)\b",
    re.IGNORECASE,
)

# Diploma por extenso → sigla que `citation_check._SLUG_POR_DIPLOMA` conhece.
# Sem isto o lookup falha e a citação legítima é tratada como não confirmada.
_DIPLOMA_CANONICO = {
    "constituicao federal": "CF",
    "constituicao da republica": "CF",
    "constituicao da republica federativa": "CF",
    "constituicao da republica federativa do brasil": "CF",
    "codigo civil": "CC",
    "codigo penal": "CP",
    "codigo de processo civil": "CPC",
    "codigo de processo penal": "CPP",
    "codigo de defesa do consumidor": "CDC",
    "codigo tributario nacional": "CTN",
    "consolidacao das leis do trabalho": "CLT",
}


def _canonizar_diploma(bruto: str) -> str:
    """Sigla canônica para o diploma citado; devolve o original se não mapear
    (o caso `Lei 8.078/90`, que `_restringir_ao_diploma` resolve por conta)."""
    chave = " ".join(_normalizar(bruto).split())
    return _DIPLOMA_CANONICO.get(chave, bruto.upper())

# Contexto: tribunal, órgão julgador, relator, data.
_RE_TRIBUNAL_CTX = re.compile(
    r"\b(STF|STJ|TST|TSE|STM|TRF\s?-?\s?[1-6]|TRT\s?-?\s?\d{1,2}|TJ[A-Z]{2})\b")
_RE_ORGAO = re.compile(
    r"\b((?:\d{1,2}[ªa]?|Primeira|Segunda|Terceira|Quarta|Quinta|Sexta|S[ée]tima|"
    r"Oitava|Nona|D[ée]cima)\s+(?:Turma|Se[çc][ãa]o|C[âa]mara(?:\s+C[íi]vel|\s+Criminal)?)|"
    r"Corte\s+Especial|Plen[áa]rio|Tribunal\s+Pleno|[ÓO]rg[ãa]o\s+Especial|"
    r"Se[çc][ãa]o\s+Especializada)\b", re.IGNORECASE)
_RE_RELATOR = re.compile(
    r"\b(?:Rel(?:ator[a]?)?\.?\s*[:.]?\s*)?"
    r"(Min(?:istr[oa])?\.?|Des(?:embargador[a]?)?\.?)\s+"
    r"((?:[A-ZÀ-Ý][A-Za-zÀ-ÿ'.\-]+)(?:\s+(?:d[aoe]s?\s+)?[A-ZÀ-Ý][A-Za-zÀ-ÿ'.\-]+){0,4})")
_RE_DATA = re.compile(
    r"\b(\d{1,2}/\d{1,2}/\d{4})\b|"
    r"\b(\d{1,2}[ºo°]?\s+de\s+[a-zç]+\s+de\s+\d{4})\b", re.IGNORECASE)

# Menções vagas a jurisprudência SEM referência verificável.
_RE_GENERICAS = [re.compile(p, re.IGNORECASE) for p in (
    r"jurisprud[êe]ncia\s+(?:pac[íi]fica|dominante|consolidada|majorit[áa]ria|"
    r"remansosa|iterativa|firme|reiterada)",
    r"entendimento\s+(?:pac[íi]fico|consolidado|majorit[áa]rio|firmado|"
    r"sedimentado|dominante)(?:\s+d[oe]s?\s+\w+)?",
    r"os\s+tribunais\s+(?:t[êe]m|v[êe]m)\s+(?:decidido|entendido|decidindo|entendendo)",
    r"(?:[ée]|resta)\s+pac[íi]fic[oa]\s+(?:o\s+entendimento|a\s+jurisprud[êe]ncia)",
    r"segundo\s+a\s+jurisprud[êe]ncia(?:\s+d[oe]s?\s+\w+)?",
    r"conforme\s+(?:reiterada\s+|pac[íi]fica\s+)?jurisprud[êe]ncia",
)]

# ── Avisos (pt-BR) por status ────────────────────────────────────────────────

_AVISO_VERIFICADA = ("Citação confirmada em fonte oficial ({fonte}). Ainda assim, "
                     "leia o inteiro teor antes de usar (responsabilidade do advogado — OAB).")
_AVISO_IDENTIFICADA = ("Referência estruturada plausível, mas NÃO confirmada em fonte "
                       "externa — confirme o inteiro teor no site do tribunal antes de citar.")
_AVISO_SUSPEITA = ("SUSPEITA de alucinação: {motivo}. NÃO utilize esta citação sem "
                   "localizar a fonte oficial.")
_AVISO_GENERICA = ("Menção genérica a jurisprudência sem referência verificável — exija "
                   "número de processo, tribunal, órgão julgador e data, ou remova o trecho.")

_AVISO_GERAL = ("Verificação automática NÃO substitui a conferência humana: toda citação "
                "deve ser confirmada na fonte oficial antes do protocolo "
                "(responsabilidade do advogado — OAB).")


# ── Extração de contexto ─────────────────────────────────────────────────────

def _contexto(texto: str, ini: int, fim: int) -> str:
    return texto[max(0, ini - _JANELA_ANTES):min(len(texto), fim + _JANELA_DEPOIS)]


def _extrair_contexto(janela: str) -> dict:
    """Tribunal/órgão julgador/relator/data mencionados perto da citação."""
    trib = _RE_TRIBUNAL_CTX.search(janela)
    orgao = _RE_ORGAO.search(janela)
    rel = _RE_RELATOR.search(janela)
    data = _RE_DATA.search(janela)
    return {
        "tribunal": re.sub(r"\s|-", "", trib.group(1)) if trib else None,
        "orgao": orgao.group(1).strip() if orgao else None,
        "relator": f"{rel.group(1)} {rel.group(2)}".strip() if rel else None,
        "data": (data.group(1) or data.group(2)) if data else None,
    }


# ── Parser estruturado ───────────────────────────────────────────────────────

def analisar_texto(texto: str) -> list[dict]:
    """Extrai TODAS as citações do texto (sem consultar nada externo).

    Cada item: {tipo, trecho, span, numero, tribunal, orgao, relator, data, ...}
    tipos: processo_cnj | recurso | sumula | artigo | generica
    """
    texto = (texto or "")[:_MAX_TEXTO]
    achados: list[dict] = []
    seen: set = set()
    spans_estruturados: list[tuple[int, int]] = []

    def _add(item: dict, key: tuple, span: tuple[int, int]) -> None:
        if key in seen:
            return
        seen.add(key)
        item["span"] = span
        achados.append(item)
        if item["tipo"] != "generica":
            spans_estruturados.append(span)

    # 1. Números CNJ (formato canônico + 20 dígitos precedidos de "processo").
    for rx, grupo in ((_RE_CNJ, 0), (_RE_CNJ_CRU, 1)):
        for m in rx.finditer(texto):
            bruto = m.group(grupo) if grupo == 0 else m.group(1)
            digitos = re.sub(r"\D", "", bruto)
            ctx = _extrair_contexto(_contexto(texto, m.start(), m.end()))
            dec = decodificar_cnj(digitos)
            _add({
                "tipo": "processo_cnj",
                "trecho": m.group(0)[:120],
                "numero": formatar_cnj(digitos),
                "dv_valido": validar_dv_cnj(digitos),
                "tribunal": dec["tribunal"] or ctx["tribunal"],
                "tribunal_valido": dec["tribunal_valido"],
                "motivo_invalido": dec["motivo"],
                "ano": dec["ano"],
                "orgao": ctx["orgao"], "relator": ctx["relator"], "data": ctx["data"],
            }, ("cnj", digitos), (m.start(), m.end()))

    # 2. Recursos superiores (REsp 1.737.428/SP etc.).
    for m in _RE_RECURSO.finditer(texto):
        classe = m.group(1)
        num = re.sub(r"\D", "", m.group(2))
        ctx = _extrair_contexto(_contexto(texto, m.start(), m.end()))
        cu = classe.upper()
        tribunal = ("STJ" if cu in _CLASSE_STJ else
                    "STF" if cu in _CLASSE_STF else ctx["tribunal"])
        _add({
            "tipo": "recurso",
            "trecho": m.group(0)[:120],
            "classe": classe,
            "numero": m.group(2),
            "numero_int": int(num) if num else 0,
            "uf": m.group(3),
            "tribunal": tribunal,
            "orgao": ctx["orgao"], "relator": ctx["relator"], "data": ctx["data"],
        }, ("recurso", cu, num), (m.start(), m.end()))

    # 3. Súmulas.
    for m in _RE_SUMULA.finditer(texto):
        vinculante = bool(m.group(1))
        num, orgao_t = m.group(2), (m.group(3) or "").upper()
        if vinculante and not orgao_t:
            orgao_t = "STF"
        ctx = _extrair_contexto(_contexto(texto, m.start(), m.end()))
        _add({
            "tipo": "sumula",
            "trecho": m.group(0).strip()[:120],
            "numero": num,
            "vinculante": vinculante,
            "tribunal": orgao_t or ctx["tribunal"],
            "orgao": None, "relator": None, "data": None,
        }, ("sumula", num, orgao_t), (m.start(), m.end()))

    # 4. Artigos de lei (legado citation_check — conferidos no RAG).
    for m in _RE_ARTIGO.finditer(texto):
        # Número sem separador: `_regex_artigo` já limpa não-dígitos no lookup,
        # e normalizar aqui faz "1.234" e "1234" deduplicarem como um só artigo.
        num = m.group(1).replace(".", "")
        dipl = _canonizar_diploma(m.group(2) or "")
        _add({
            "tipo": "artigo",
            "trecho": m.group(0).strip()[:120],
            "numero": num,
            "diploma": dipl,
            "tribunal": None, "orgao": None, "relator": None, "data": None,
        }, ("artigo", num, dipl), (m.start(), m.end()))

    # 5. Menções vagas — só viram citação `generica` se NÃO houver referência
    #    estruturada na vizinhança (janela após a menção).
    for rx in _RE_GENERICAS:
        for m in rx.finditer(texto):
            ini, fim = m.start(), m.end()
            tem_ref_perto = any(
                s_ini < fim + _JANELA_DEPOIS and s_fim > ini - _JANELA_ANTES
                for s_ini, s_fim in spans_estruturados
            )
            if tem_ref_perto:
                continue
            _add({
                "tipo": "generica",
                "trecho": m.group(0).strip()[:120],
                "numero": None,
                "tribunal": _extrair_contexto(m.group(0))["tribunal"],
                "orgao": None, "relator": None, "data": None,
            }, ("generica", _normalizar(m.group(0))), (ini, fim))

    achados.sort(key=lambda a: a["span"][0])
    return achados


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


# ── Consulta ativa ao DataJud (opt-in, fail-safe) ────────────────────────────

async def _confirmar_datajud(numero_fmt: str) -> tuple[dict | None, str]:
    """Consulta o DataJud/CNJ. Retorna (info|None, desfecho).

    desfecho: "confirmado" | "nao_localizado" | "erro". NUNCA propaga exceção.
    """
    try:
        from app.services import datajud_service
        info = await asyncio.wait_for(
            datajud_service.consultar_processo(numero_fmt), timeout=DATAJUD_TIMEOUT_S)
    except Exception as e:  # timeout, rede, HTTP — vira aviso, nunca erro
        from app.services.datajud_service import DataJudDesabilitadoError
        if isinstance(e, DataJudDesabilitadoError):
            # Integração desligada é estado esperado, não indisponibilidade.
            return None, "nao_localizado"
        # Sem número de processo no log (PII/segredo de justiça — mesma regra
        # dos demais logs do DataJud nesta governança).
        logger.warning("DataJud indisponível: %s", type(e).__name__)
        return None, "erro"
    if info:
        return info, "confirmado"
    return None, "nao_localizado"


# ── Classificação + relatório ────────────────────────────────────────────────

async def verificar_jurisprudencia(
    db, texto: str, *, consultar_datajud: bool = False,
) -> dict:
    """Relatório rigoroso de verificação de citações (shape retrocompatível).

    - `db`: sessão async (lookup de súmulas/artigos no RAG oficial).
    - `consultar_datajud`: confirma nº CNJ com DV válido no DataJud
      (máx. MAX_CONSULTAS_DATAJUD por chamada; falha → `identificada`).
    """
    from app.services.citation_check import (
        _artigo_superado,
        _existe_artigo,
        _existe_sumula,
        _sumula_superada,
    )

    def _aviso_superada(info: dict, tipo: str) -> str:
        return (
            f"Localizada na base interna APENAS em versão SUPERADA "
            f"(v{info.get('versao')}): “{str(info.get('titulo') or '')[:120]}”. "
            f"A redação vigente d{tipo} pode ter mudado — confira o texto "
            "atualizado na fonte oficial ANTES de protocolar."
        )

    achados = analisar_texto(texto)
    resultados: list[dict] = []
    consultas_datajud = 0
    datajud_saturado = False

    for c in achados:
        status = STATUS_IDENTIFICADA
        fonte: str | None = None
        aviso: str | None = None
        rotulo = c["trecho"]

        if c["tipo"] == "processo_cnj":
            rotulo = f"Processo {c['numero']}"
            if not c["dv_valido"]:
                status = STATUS_SUSPEITA
                aviso = _AVISO_SUSPEITA.format(
                    motivo="dígito verificador do número CNJ inválido (módulo 97, "
                           "Res. CNJ 65/2008) — o número como escrito não pode existir")
            elif not c["tribunal_valido"]:
                status = STATUS_SUSPEITA
                aviso = _AVISO_SUSPEITA.format(
                    motivo=f"tribunal inexistente no número CNJ ({c['motivo_invalido']})")
            elif consultar_datajud and consultas_datajud < MAX_CONSULTAS_DATAJUD:
                consultas_datajud += 1
                info, desfecho = await _confirmar_datajud(c["numero"])
                if desfecho == "confirmado":
                    status = STATUS_VERIFICADA
                    fonte = "DataJud/CNJ" + (
                        f" — {info.get('classe')}" if info.get("classe") else "")
                    c["orgao"] = c["orgao"] or info.get("orgao")
                    aviso = _AVISO_VERIFICADA.format(fonte="DataJud/CNJ")
                elif desfecho == "nao_localizado":
                    aviso = ("Número CNJ estruturalmente válido, mas NÃO localizado no "
                             "DataJud (cobertura parcial de tribunais ou consulta "
                             "desativada) — confirme no site do tribunal.")
                else:  # erro/timeout da API → nunca derruba a verificação
                    aviso = ("Consulta ao DataJud indisponível no momento — citação "
                             "apenas identificada; confirme manualmente.")
            else:
                if consultar_datajud:
                    datajud_saturado = True
                aviso = _AVISO_IDENTIFICADA

        elif c["tipo"] == "recurso":
            rotulo = f"{c['classe']} {c['numero']}" + (f"/{c['uf']}" if c.get("uf") else "")
            if c["numero_int"] <= 0:
                status = STATUS_SUSPEITA
                aviso = _AVISO_SUSPEITA.format(motivo="número do recurso inválido (zero)")
            else:
                aviso = _AVISO_IDENTIFICADA

        elif c["tipo"] == "sumula":
            rotulo = ("Súmula Vinculante " if c["vinculante"] else "Súmula ") + c["numero"]
            if c["tribunal"]:
                rotulo += f" {c['tribunal']}"
            num_i = int(c["numero"])
            chave_teto = "STF-V" if c["vinculante"] else (c["tribunal"] or "")
            if chave_teto in SUMULA_TETO:
                teto = SUMULA_TETO[chave_teto]
            elif not c["tribunal"]:
                teto = _SUMULA_TETO_DEFAULT  # órgão não informado: teto mais alto
            else:
                teto = None  # tribunal fora da tabela (ex.: TJMG): sem faixa
            if num_i < 1 or (teto and num_i > teto):
                status = STATUS_SUSPEITA
                ref = chave_teto or "tribunais superiores"
                from app.services.vigencia_dados_juridicos import (
                    teto_de_sumula_vencido,
                )
                if num_i >= 1 and teto_de_sumula_vencido():
                    # O teto está desatualizado: a súmula pode ser nova e real.
                    ressalva = (
                        f"acima do teto conhecido de {ref} (1 a {teto}), MAS a "
                        f"tabela de tetos não é reconferida desde "
                        f"{SUMULA_TETO_CONFERIDO_EM} — confirme na fonte oficial "
                        "antes de tratar como inexistente"
                    )
                else:
                    ressalva = (
                        f"Súmula {c['numero']} fora da faixa plausível de {ref} "
                        f"(1 a {teto}) — provavelmente não existe"
                    )
                aviso = _AVISO_SUSPEITA.format(motivo=ressalva)
            else:
                fonte = await _existe_sumula(db, c["numero"],
                                             c["tribunal"] if c["tribunal"] in
                                             ("STF", "STJ", "TST", "TJMG") else "")
                if fonte:
                    status = STATUS_VERIFICADA
                    aviso = _AVISO_VERIFICADA.format(fonte="base oficial interna/RAG")
                else:
                    # Só então procura em versão superada: a súmula pode existir
                    # na base, mas numa redação que foi substituída.
                    superada = await _sumula_superada(
                        db, c["numero"],
                        c["tribunal"] if c["tribunal"] in
                        ("STF", "STJ", "TST", "TJMG") else "",
                    )
                    if superada:
                        status = STATUS_DESATUALIZADA
                        fonte = superada.get("titulo")
                        aviso = _aviso_superada(superada, "a súmula")
                    else:
                        aviso = _AVISO_IDENTIFICADA

        elif c["tipo"] == "artigo":
            rotulo = f"art. {c['numero']} {c['diploma']}".strip()
            # AI-056: o lookup é RESTRITO ao diploma citado — nunca confirma
            # "art. N" contra uma lei diferente da referida no texto.
            fonte = await _existe_artigo(db, c["numero"], c.get("diploma"))
            if fonte:
                status = STATUS_VERIFICADA
                aviso = _AVISO_VERIFICADA.format(fonte="base oficial interna/RAG")
            else:
                # Mesmo recorte por diploma do lookup vigente (AI-056): avisar
                # "superado" com base numa lei diferente da citada seria uma
                # informação errada entregue com ar de certeza.
                superado = await _artigo_superado(db, c["numero"], c.get("diploma"))
                if superado:
                    status = STATUS_DESATUALIZADA
                    fonte = superado.get("titulo")
                    aviso = _aviso_superada(superado, "o dispositivo")
                else:
                    aviso = ("Artigo não localizado na legislação ingerida na base interna — "
                             "confira o texto legal vigente antes de citar.")

        else:  # generica
            status = STATUS_GENERICA
            aviso = _AVISO_GENERICA

        resultados.append({
            # ── chaves LEGADAS (citation_check) — não remover/renomear ──
            "citacao": rotulo,
            "tipo": c["tipo"],
            "encontrada": status == STATUS_VERIFICADA,
            "fonte": fonte,
            # ── chaves NOVAS (verificador rigoroso) ──
            "trecho": c["trecho"],
            "status": status,
            "tribunal": c.get("tribunal"),
            "numero": c.get("numero"),
            "orgao": c.get("orgao"),
            "relator": c.get("relator"),
            "data": c.get("data"),
            "fonte_verificacao": fonte,
            "aviso": aviso,
        })

    return _montar_relatorio(resultados, datajud_saturado)


def _montar_relatorio(resultados: list[dict], datajud_saturado: bool) -> dict:
    contagem = {s: 0 for s in (STATUS_VERIFICADA, STATUS_IDENTIFICADA,
                               STATUS_SUSPEITA, STATUS_GENERICA,
                               STATUS_DESATUALIZADA)}
    for r in resultados:
        contagem[r["status"]] += 1

    total = len(resultados)
    v, i = contagem[STATUS_VERIFICADA], contagem[STATUS_IDENTIFICADA]
    s, g = contagem[STATUS_SUSPEITA], contagem[STATUS_GENERICA]
    d = contagem[STATUS_DESATUALIZADA]

    # Fórmula do score (documentada no docstring do módulo):
    #   score = round(100 * (1.0*verificadas + 0.6*identificadas) / total)
    # suspeitas, genéricas e desatualizadas pesam 0 → puxam o score para baixo.
    # Desatualizada pesa 0 de propósito: a existência na base não redime citar
    # redação superada — é defeito a corrigir, não crédito parcial.
    score = round(100 * (1.0 * v + 0.6 * i) / total) if total else None

    avisos: list[str] = []
    if total == 0:
        avisos.append("Nenhuma citação jurisprudencial detectada no texto.")
    if s:
        avisos.append(f"{s} citação(ões) SUSPEITA(s) de alucinação (formato/faixa "
                      "inválidos) — remova ou substitua por fonte real.")
    if g:
        avisos.append(f"{g} menção(ões) genérica(s) a jurisprudência sem referência "
                      "verificável — exija processo, tribunal, órgão julgador e data.")
    if d:
        avisos.append(f"{d} citação(ões) localizada(s) APENAS em versão SUPERADA na "
                      "base interna — a redação vigente pode ter mudado; confira a "
                      "fonte oficial antes de protocolar.")
    if i:
        avisos.append(f"{i} citação(ões) apenas identificada(s) (não confirmadas em "
                      "fonte externa) — confirme o inteiro teor antes do protocolo.")
    if datajud_saturado:
        avisos.append(f"Limite de {MAX_CONSULTAS_DATAJUD} consultas ao DataJud por "
                      "verificação atingido — números excedentes ficaram como "
                      "'identificada'.")
    avisos.append(_AVISO_GERAL)

    return {
        # ── shape LEGADO (compatível com response_validator/skill_registry/
        #     anexos/peca_service/analise_estrategica/qualidade) ──
        "total": total,
        "confirmadas": v,
        "nao_encontradas": total - v,
        "citacoes": resultados,
        "aviso": _AVISO_GERAL,
        # ── extensões do verificador rigoroso ──
        "score": score,
        "contagem_status": contagem,
        "avisos": avisos,
    }
