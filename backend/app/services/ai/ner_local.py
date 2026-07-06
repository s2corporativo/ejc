# ── app/services/ai/ner_local.py ─────────────────────────────────────────────
# NER LOCAL determinístico (heurística pura, custo ZERO, sem rede/modelo).
#
# CONTEXTO (issue #102): a 2ª barreira do gateway (`validar_sem_pii`) detecta só
# PII ESTRUTURAL (CPF/CNPJ/RG/e-mail/tel/CEP/processo). Nomes próprios só são
# pseudonimizados se estiverem em `entidades` (cadastro do Case). Nomes que
# aparecem SÓ em texto livre/OCR/RAG (vítima, testemunha, terceiro) chegavam EM
# CLARO ao provider externo (EUA). Este módulo REFORÇA a barreira detectando
# NOMES DE PESSOA FÍSICA residuais, com DOIS níveis de confiança:
#
#   • ALTA  — nome precedido de GATILHO de contexto ("vítima X", "testemunha Y",
#             "Sr./Dr./réu/autor/requerente/depoente <Nome>"). É a REDE DE
#             SEGURANÇA: se um nome de alta confiança sobrar EM CLARO após a
#             pseudonimização, o gateway PULA o provider externo (defense-in-depth).
#   • MÉDIA — sequência de 2+ tokens Capitalizados (padrão de nome PT-BR) que NÃO
#             caia na STOPLIST institucional/jurídica. Só PSEUDONIMIZA, nunca
#             bloqueia (preferível a matar a feature).
#
# ⚠️  NÃO SUPER-BLOQUEAR: texto jurídico tem MUITA palavra Capitalizada que não é
# pessoa — tribunais ("Tribunal de Justiça", "STF"/"TJMG"), leis ("Código Civil",
# "Lei"), órgãos ("Ministério Público", "INSS"), cidades/UF, meses, início de
# frase, e a própria identidade do escritório ("De Paula Teixeira Advogados",
# "Dr. Clovis José Soares"). A STOPLIST abaixo exclui esses termos. Falso-positivo
# que vira bloqueio recria o bug original (importação morre): por isso a
# detecção é CONSERVADORA (descarta o candidato se QUALQUER token cair na
# stoplist) e só a ALTA confiança habilita bloqueio.
#
# 100% local: puro regex + conjuntos em memória. Nunca baixa modelo nem faz rede.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import re

# ── Blocos do padrão de nome próprio PT-BR ────────────────────────────────────
# Token de nome: inicial MAIÚSCULA (com acento) seguida de minúsculas. Exige ao
# menos uma minúscula → siglas ALL-CAPS ("STF", "TJMG", "CPF") e marcadores já
# pseudonimizados ("[CLIENTE_1]") NÃO são tokens de nome (degrada seguro).
_TOKEN = r"[A-ZÀ-Ý][a-zà-ÿ]+"
# Conectivos minúsculos comuns em nomes ("da/de/do/dos/das/du", "e", partículas
# estrangeiras). Cobre sobrenomes compostos ("Castro e Silva", "João da Silva").
_CONECTIVO = r"(?:d[aeiou]s?|e|del|van|von|du|la|le)"
# Nome com 1+ tokens (para captura pós-gatilho, onde 1 token já basta: "vítima Ana").
_NOME_1MAIS = rf"{_TOKEN}(?:\s+(?:{_CONECTIVO}\s+)?{_TOKEN})*"
# Nome com 2+ tokens (heurística MÉDIA sem gatilho: exige sequência, não 1 palavra
# capitalizada solta — evita disparar em início de frase e em siglas/termos soltos).
_NOME_2MAIS = rf"{_TOKEN}(?:\s+(?:{_CONECTIVO}\s+)?{_TOKEN})+"

_RE_NOME_MEDIO = re.compile(_NOME_2MAIS)

# ── Gatilhos de contexto (ALTA confiança) ─────────────────────────────────────
# Palavra que, ANTECEDENDO um nome próprio, sinaliza pessoa física com alta
# probabilidade (partes, sujeitos processuais, tratamentos). Casada
# case-insensitive; o NOME capturado permanece case-sensitive (só Capitalizado).
_GATILHOS = (
    "vítima", "vitima", "testemunha", "depoente", "declarante", "denunciante",
    "denunciado", "denunciada", "réu", "reu", "ré", "acusado", "acusada",
    "indiciado", "indiciada", "investigado", "investigada", "suspeito", "suspeita",
    "querelante", "querelado", "ofendido", "ofendida", "autor", "autora",
    "requerente", "requerido", "requerida", "reclamante", "reclamado", "reclamada",
    "exequente", "executado", "executada", "agravante", "agravado", "apelante",
    "apelado", "impetrante", "impetrado", "embargante", "embargado",
    "falecido", "falecida", "herdeiro", "herdeira", "inventariante", "espólio",
    "genitor", "genitora", "cônjuge", "conjuge", "companheiro", "companheira",
    "esposo", "esposa", "marido", "beneficiário", "beneficiária", "segurado",
    "segurada", "paciente", "menor", "adolescente", "criança", "preso", "presa",
    "vulgo", "sr", "sra", "srta", "dr", "dra", "dom", "dona", "senhor", "senhora",
)
_RE_GATILHO = re.compile(
    rf"\b(?i:{'|'.join(re.escape(g) for g in _GATILHOS)})\.?\s+({_NOME_1MAIS})"
)

# ── STOPLIST institucional / jurídica / geográfica / identidade do escritório ──
# Basta UM token do candidato cair aqui para descartá-lo (conservador). Inclui
# variantes com/sem acento para robustez de OCR. Objetivo: pegar PESSOA FÍSICA,
# nunca entidade jurídica/lugar/mês/termo processual/identidade do controlador.
_STOPLIST: frozenset[str] = frozenset({
    # Instituições / órgãos / poderes
    "tribunal", "tribunais", "justiça", "justica", "supremo", "superior", "federal",
    "estadual", "municipal", "ministério", "ministerio", "público", "publico",
    "ministra", "ministro", "desembargador", "desembargadora", "juiz", "juíza",
    "juiza", "juízo", "juizo", "promotor", "promotora", "promotoria", "procurador",
    "procuradora", "procuradoria", "defensor", "defensora", "defensoria", "vara",
    "varas", "comarca", "foro", "câmara", "camara", "turma", "seção", "secao",
    "sessão", "sessao", "plenário", "plenario", "conselho", "ordem", "advogados",
    "advogado", "advogada", "associados", "escritório", "escritorio", "república",
    "republica", "estado", "união", "uniao", "nação", "nacao", "governo",
    "presidência", "presidencia", "presidente", "congresso", "senado", "assembleia",
    "prefeitura", "prefeito", "secretaria", "secretário", "secretario",
    "departamento", "delegacia", "delegado", "polícia", "policia", "fazenda",
    "receita", "banco", "central", "caixa", "instituto", "fundação", "fundacao",
    "universidade", "faculdade", "escola", "hospital", "empresa", "empresas",
    "companhia", "sociedade", "associação", "associacao", "sindicato", "federação",
    "federacao", "confederação", "cooperativa", "autarquia", "agência", "agencia",
    "cartório", "cartorio", "junta", "corregedoria", "poder", "judiciário",
    "judiciario", "legislativo", "executivo",
    # Documentos / termos jurídicos / peças
    "código", "codigo", "lei", "leis", "decreto", "portaria", "resolução",
    "resolucao", "súmula", "sumula", "acórdão", "acordao", "emenda", "constituição",
    "constituicao", "constitucional", "processo", "processual", "civil", "penal",
    "criminal", "trabalhista", "tributário", "tributario", "administrativo",
    "previdenciário", "previdenciario", "consumidor", "empresarial", "ambiental",
    "família", "familia", "sucessões", "sucessoes", "imobiliário", "imobiliario",
    "ação", "acao", "petição", "peticao", "recurso", "agravo", "apelação",
    "apelacao", "embargos", "mandado", "habeas", "corpus", "liminar", "sentença",
    "sentenca", "despacho", "acórdão", "contrato", "contratos", "artigo", "inciso",
    "parágrafo", "paragrafo", "caput", "cláusula", "clausula", "laudo", "perícia",
    "pericia", "boletim", "inquérito", "inquerito", "autos", "audiência", "audiencia",
    "excelentíssimo", "excelentissimo", "meritíssimo", "meritissimo", "vossa",
    "excelência", "excelencia", "senhoria", "doutor", "doutora", "egrégio",
    "egregio", "colenda",
    # Identidade do escritório (controlador — não é PII de titular; nomes próprios
    # do escritório injetados no system prompt não devem ser pseudonimizados).
    "paula", "teixeira", "clovis", "soares",
    # Lugares / UF (não pessoa)
    "brasil", "brasília", "brasilia", "betim", "contagem", "minas", "gerais",
    "são", "sao", "santo", "santa", "rio", "janeiro", "horizonte", "belo",
    "grosso", "grande", "distrito", "paraná", "parana", "pernambuco", "amazonas",
    "maranhão", "maranhao", "bahia", "ceará", "ceara", "goiás", "goias", "pará",
    "para", "sergipe", "tocantins", "alagoas", "amapá", "amapa", "rondônia",
    "rondonia", "roraima", "piauí", "piaui", "paraíba", "paraiba", "espírito",
    "espirito", "norte", "sul", "oeste", "leste", "nordeste", "sudeste",
    # Meses / dias
    "janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro", "segunda", "terça",
    "terca", "quarta", "quinta", "sexta", "sábado", "sabado", "domingo",
})


def _tokens(nome: str) -> list[str]:
    """Tokens de nome próprio do candidato (ignora conectivos minúsculos)."""
    return re.findall(_TOKEN, nome)


def _institucional(nome: str) -> bool:
    """True se o candidato NÃO é pessoa física: sem tokens, ou QUALQUER token na
    STOPLIST (institucional/jurídico/lugar/mês/identidade do escritório)."""
    toks = _tokens(nome)
    if not toks:
        return True
    return any(t.casefold() in _STOPLIST for t in toks)


def detectar_nomes(texto: str, *, incluir_medio: bool = True) -> list[str]:
    """Retorna nomes de PESSOA FÍSICA detectados em `texto` (para pseudonimizar).

    Une ALTA confiança (gatilho + nome) e, se `incluir_medio`, MÉDIA (sequência
    de 2+ Capitalizados fora da stoplist). Dedup preservando o mais LONGO
    primeiro (substituir nomes longos antes dos curtos evita marcação parcial)."""
    if not texto:
        return []
    achados: dict[str, None] = {}
    for m in _RE_GATILHO.finditer(texto):
        nome = (m.group(1) or "").strip()
        if nome and not _institucional(nome):
            achados[nome] = None
    if incluir_medio:
        for m in _RE_NOME_MEDIO.finditer(texto):
            nome = m.group(0).strip()
            if nome and not _institucional(nome):
                achados[nome] = None
    return sorted(achados, key=len, reverse=True)


def contem_nome_alta_confianca(texto: str) -> bool:
    """True se há nome de ALTA confiança (gatilho de contexto) EM CLARO no texto.

    Usado pela 2ª barreira do gateway como REDE DE SEGURANÇA: após a
    pseudonimização, o gatilho fica seguido de um marcador ("testemunha
    [PESSOA_1]") e isto retorna False — só dispara (→ bloqueio do externo) se um
    nome de alta confiança tiver escapado da pseudonimização (defense-in-depth)."""
    if not texto:
        return False
    for m in _RE_GATILHO.finditer(texto):
        nome = (m.group(1) or "").strip()
        if nome and not _institucional(nome):
            return True
    return False
