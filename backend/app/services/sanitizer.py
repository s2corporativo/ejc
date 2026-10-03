# ── app/services/sanitizer.py ────────────────────────────────────────────────
# Sanitização LGPD — remove PII antes de QUALQUER envio ao Groq.
#
# CRÍTICO: o Groq processa dados fora do VPS (EUA). Enviar CPF, CNPJ,
# nome de cliente ou número de processo identificável = violação LGPD.
# Esta camada é OBRIGATÓRIA em todo prompt. Sem exceção.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import re


# ── Cartão: a única regra de PII que regex não expressa sozinha ──────────────
# Um PAN é QUALQUER sequência de 13 a 19 dígitos, agrupada como a bandeira
# quiser. Regex não CONTA dígitos através de separadores, e duas tentativas de
# enumerar formatos deixaram comprimentos de fora: primeiro tudo que não fosse
# 16 dígitos, depois todo PAN AGRUPADO de 13 a 18. Dois achados P1 em SHAs
# consecutivos, pela mesma causa — enumerar formato em vez de contar dígito.
#
# Este objeto expõe a interface de `re.Pattern` que `_PATTERNS` exige (`sub`,
# `search`, `finditer`) para que TODO consumidor da lista — inclusive o
# `ai/pseudonymizer.py`, que a percorre por conta própria — receba a regra certa
# sem precisar saber que ela não é um regex.
#
# O regex abaixo só delimita o CANDIDATO: grupo inicial de 4+ dígitos, grupos
# seguintes de 3+, e um grupo final curto opcional. O piso de 3 dígitos nos
# grupos intermediários é o que impede o candidato de atravessar datas vizinhas
# — "2026-08-22 2027-09-30" são 16 dígitos, e data de audiência não pode virar
# cartão. Quem decide é a contagem.
# `[\s.-]+` (repetido, não único): PAN copiado de PDF/OCR chega com espaço
# duplo — "4111  1111  1111  1111" — e com separador único o candidato nem era
# reconhecido: 16 dígitos seguiam intactos rumo ao provider externo, com a 2ª
# barreira dizendo "sem PII residual". Terceiro achado P1 sobre este ponto, e a
# terceira vez que o furo estava no DELIMITADOR, não na contagem.
#
# `\s` inclui quebra de linha, de propósito: PAN partido em duas linhas por OCR
# é caso real. O custo aceito é over-masking de uma coluna de números de 4
# dígitos cuja soma caia em 13-19. Trade deliberado: over-masking degrada um
# prompt, under-masking vaza cartão para fora do VPS, e a prioridade §71 põe
# LGPD acima de UX.
_CARTAO_TRECHO = re.compile(r'(?<!\d)\d{4,}(?:[\s.-]+\d{3,})*(?:[\s.-]+\d{1,2})?(?!\d)')
_NAO_DIGITO = re.compile(r'\D')


class _MatcherCartao:
    """Contagem de dígitos com cara de `re.Pattern`.

    `permitir_14=False` devolve o empate a favor do CNPJ: 14 dígitos sem
    pontuação é ambíguo (CNPJ e Diners têm o mesmo comprimento) e nada no texto
    os distingue. Na variante EXTERNA isso não aparece — o CNPJ já foi
    mascarado no índice 1, antes desta entrada. Na variante INTERNA CPF/CNPJ
    ficam visíveis de propósito (decisão de 2026-07-04) e o texto nunca sai do
    VPS, então o empate resolve a favor de manter o CNPJ legível.
    """

    __slots__ = ("_permitir_14",)

    def __init__(self, permitir_14: bool = True) -> None:
        self._permitir_14 = permitir_14

    def _e_cartao(self, trecho: str) -> bool:
        n = len(_NAO_DIGITO.sub('', trecho))
        if not 13 <= n <= 19:
            return False
        return not (n == 14 and not self._permitir_14)

    def finditer(self, texto: str):
        return (m for m in _CARTAO_TRECHO.finditer(texto)
                if self._e_cartao(m.group(0)))

    def search(self, texto: str):
        return next(self.finditer(texto), None)

    def sub(self, repl, texto: str) -> str:
        def _troca(m: re.Match) -> str:
            if not self._e_cartao(m.group(0)):
                return m.group(0)          # devolve o texto original intacto
            return repl(m) if callable(repl) else repl
        return _CARTAO_TRECHO.sub(_troca, texto)


# ── CNPJ: numérico (legado) e ALFANUMÉRICO (IN RFB nº 2.229/2024) ─────────────
# Desde julho/2026 a Receita atribui CNPJ com raiz e ordem ALFANUMÉRICAS
# (letras maiúsculas + dígitos) e DV numérico — ex. oficial "12.ABC.345/01DE-35".
# O regex só-dígitos deixava esse CNPJ passar em claro rumo ao provider
# externo, com a 2ª barreira dizendo "sem PII residual" (mesma entrada).
#
# Regra de decisão sobre o candidato:
#   • só dígitos            → mesmo comportamento de antes (qualquer formatação);
#   • com letra + máscara   → CNPJ ("XX.XXX.XXX/XXXX-DD" é sinal forte);
#   • com letra, sem máscara → só se o DV conferir (evita mascarar código
#     alfanumérico qualquer de 14 posições terminado em 2 dígitos).
# DV: valor do caractere = ASCII − 48; pesos e módulo 11 iguais ao numérico.
_CNPJ_CANDIDATO = re.compile(
    r'\b[0-9A-Z]{2}\.?[0-9A-Z]{3}\.?[0-9A-Z]{3}/?[0-9A-Z]{4}-?\d{2}\b'
)
_CNPJ_MASCARA_COMPLETA = re.compile(
    r'[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-\d{2}'
)
_PESOS_DV_CNPJ = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _dv_cnpj_confere(base14: str) -> bool:
    valores = [ord(c) - 48 for c in base14]
    for n in (12, 13):
        resto = sum(v * p for v, p in zip(valores[:n], _PESOS_DV_CNPJ[13 - n:])) % 11
        if valores[n] != (0 if resto < 2 else 11 - resto):
            return False
    return True


class _MatcherCNPJ:
    """CNPJ numérico ou alfanumérico com cara de `re.Pattern` (`sub`/`search`/
    `finditer`) — mesmo contrato do `_MatcherCartao`, para que TODO consumidor
    de `_PATTERNS` (inclusive o pseudonymizer) receba a regra certa."""

    __slots__ = ()

    @staticmethod
    def _e_cnpj(trecho: str) -> bool:
        compacto = re.sub(r'[./-]', '', trecho)
        if compacto.isdigit():
            return True
        return bool(_CNPJ_MASCARA_COMPLETA.fullmatch(trecho)) or _dv_cnpj_confere(compacto)

    def finditer(self, texto: str):
        return (m for m in _CNPJ_CANDIDATO.finditer(texto) if self._e_cnpj(m.group(0)))

    def search(self, texto: str):
        return next(self.finditer(texto), None)

    def sub(self, repl, texto: str) -> str:
        def _troca(m: re.Match) -> str:
            if not self._e_cnpj(m.group(0)):
                return m.group(0)
            return repl(m) if callable(repl) else repl
        return _CNPJ_CANDIDATO.sub(_troca, texto)


_UFS = (r'(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|'
        r'RO|RR|SC|SP|SE|TO)')


# ── Padrões de PII (ordem importa: mais específico primeiro) ─────────────────
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # CPF: 000.000.000-00, 00000000000 ou agrupado por espaço simples
    # (000 000 000 00 — cópia de formulário/OCR escapava da barreira). A forma
    # com espaço exige os TRÊS separadores e não pode estar colada a outro
    # grupo numérico: espaço opcional avulso mordia o miolo de cartão agrupado
    # ("3782 822463 10005" virava "3782 [CPF]", quebrando o matcher de cartão).
    (re.compile(
        r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b'
        r'|(?<!\d )(?<!\d)\d{3} \d{3} \d{3}[ -]\d{2}(?!\d)(?! \d)'
    ), '[CPF]'),
    # CNPJ: numérico (00.000.000/0000-00 ou 14 dígitos) e alfanumérico
    # (IN RFB 2.229/2024) — ver _MatcherCNPJ.
    (_MatcherCNPJ(), '[CNPJ]'),
    # Número de processo CNJ: 0000000-00.0000.0.00.0000
    (re.compile(r'\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b'), '[PROCESSO]'),
    # RG: 00.000.000-0 (padrão MG/SP), também com UF ("MG-12.345.678") e com
    # os rótulos "identidade"/"C.I.". Sem rótulo, só a forma UF + pontuação
    # completa — nº pontuado solto é ambíguo demais para mascarar.
    (re.compile(
        r'\b(?:RG|C\.?I\.?|(?:carteira\s+de\s+)?identidade)[:\s]*(?:n[ºo°]?\.?\s*)?'
        rf'(?:{_UFS}[-\s]?)?\d{{1,2}}\.?\d{{3}}\.?\d{{3}}(?:-?[\dXx])?\b'
        rf'|\b{_UFS}-?\d{{1,2}}\.\d{{3}}\.\d{{3}}(?:-[\dXx])?\b',
        re.I,
    ), 'RG [RG]'),
    # E-mail
    (re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b'), '[EMAIL]'),
    # Cartão de crédito — ANTES do telefone, de propósito.
    # A lista é aplicada em ORDEM e o padrão de telefone morde o miolo de um PAN
    # agrupado ("3782 822463 1000 5" virava "3782 [TELEFONE] 5"): dígitos em
    # claro rumo ao provider externo, ainda por cima rotulados errado. Enquanto o
    # cartão estava depois, cada consumidor teria de reimplementar a ordem — e o
    # `ai/pseudonymizer.py`, que percorre esta lista por conta própria e está no
    # caminho externo, herdaria a falha. Pôr o cartão na posição certa AQUI
    # conserta todos os consumidores de uma vez.
    #
    # O comentário anterior dizia "reordenar não é opção"; era exagero. Os
    # índices são referenciados só dentro deste arquivo (`validar_sem_pii` e
    # `_PATTERNS_INTERNO`, ambos logo abaixo e atualizados junto). O que não pode
    # é reordenar sem atualizá-los.
    (_MatcherCartao(), '[CARTAO]'),
    # Telefone BR: (31) 99999-9999, +55 31 ..., 31999999999
    # `(?<!\d)` impede que o padrão comece NO MEIO de uma sequência maior de
    # dígitos — segunda linha de defesa para o que o cartão (agora acima) já
    # deveria ter consumido.
    (re.compile(r'(?<!\d)(\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b'), '[TELEFONE]'),
    # CEP: 00000-000, 00000000 e a forma pontuada dos Correios 00.000-000.
    (re.compile(r'\b\d{2}\.?\d{3}-?\d{3}\b'), '[CEP]'),
    # PIX chave aleatória (UUID)
    (re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I), '[CHAVE_PIX]'),
    # ── P0-474: padrões adicionais (APPEND-ONLY — índices 0-6 são referenciados
    #    por validar_sem_pii e sanitizar_pii_interno usa [2:]; nunca reordenar) ──
    # Inscrição OAB: "OAB/MG 123.456", "OAB-SP 123456", "OAB nº 12.345"
    (re.compile(r'\bOAB[\s/.-]*(?:[A-Z]{2})?[\s.]*(?:n[ºo°]?\.?\s*)?\d{1,3}\.?\d{2,3}\b', re.I), '[OAB]'),
    # Logradouro: "Rua das Acácias, nº 123" / "Av. Brasil, 500" — exige o tipo
    # de via seguido de nome Capitalizado; número é opcional. Conservador: para
    # na vírgula/quebra para não engolir o resto da frase.
    (re.compile(
        r'\b(?:Rua|Avenida|Av\.|Travessa|Alameda|Pra[çc]a|Rodovia|Estrada)\s+'
        r'(?:d[aeo]s?\s+)?[A-ZÀ-Ý][^,\n;]{2,60}'
        r'(?:,\s*(?:n[ºo°]?\.?\s*)?\d+[-\w]*)?',
    ), '[ENDERECO]'),
    # ── Auditoria do núcleo de IA (03/10/2026): lacunas confirmadas por sonda
    #    empírica. APPEND-ONLY (índices acima seguem referenciados). ──────────
    # Celular SEM DDD: "99999-9999". Exige o 9 inicial + separador: a forma
    # genérica "\d{4}-\d{4}" casaria intervalo de anos ("2024-2025").
    (re.compile(r'(?<![\d.\-/])9\d{4}[-\s]\d{4}(?!\d)'), '[TELEFONE]'),
    # Título de eleitor / PIS-PASEP-NIT-NIS — só com rótulo (12/11 dígitos
    # soltos são ambíguos e o de 11 já cai no CPF).
    (re.compile(
        r'\bt[íi]tulo\s+(?:de\s+)?eleitor(?:al)?[\s:]*(?:n[ºo°]?\.?\s*)?'
        r'\d{4}\s?\d{4}\s?\d{4}\b'
        r'|\b(?:PIS|PASEP|NIT|NIS)(?:/PASEP)?[\s:]*(?:n[ºo°]?\.?\s*)?'
        r'\d{3}\.?\d{5}\.?\d{2}-?\d\b',
        re.I,
    ), '[DOC_ID]'),
    # Dados bancários com rótulo: "agência 1234-5", "conta corrente 12345-6".
    (re.compile(
        r'\b(?:ag[êe]ncia|ag\.)\s*(?:n[ºo°]?\.?\s*|:\s*)?\d{3,5}(?:-[\dXx])?\b'
        r'|\bconta(?:\s+(?:corrente|poupan[çc]a|sal[áa]rio))?\s*'
        r'(?:n[ºo°]?\.?\s*|:\s*)?\d{4,12}(?:-[\dXx])?\b',
        re.I,
    ), '[DADOS_BANCARIOS]'),
    # NIA-08 — placa: padrão Mercosul (ABC1D23) é distintivo o bastante para
    # dispensar rótulo; o antigo (ABC-1234) colide com "ISO-9001", então só
    # com o rótulo "placa".
    (re.compile(
        r'\b[A-Z]{3}\d[A-Z]\d{2}\b'
        r'|\b(?i:placa)\s*(?:n[ºo°]?\.?\s*|:\s*)?[A-Za-z]{3}-?\d{4}\b'
    ), '[PLACA]'),
    # NIA-08 — passaporte (só com rótulo: "FZ123456" solto é código qualquer).
    (re.compile(
        r'\bpassaporte\s*(?:n[ºo°]?\.?\s*|:\s*)?[A-Z]{2}\d{6,7}\b', re.I,
    ), '[DOC_ID]'),
    # NIA-08 — numeração processual anterior ao padrão CNJ (TJMG e similares:
    # 0024.12.345678-9), ainda presente em acervo antigo e em OCR.
    (re.compile(r'\b\d{4}\.\d{2}\.\d{6}-\d\b'), '[PROCESSO]'),
]

# Variante interna: pula CPF (0) e CNPJ (1), que ficam visíveis de propósito, e
# troca o cartão pela versão que NÃO captura 14 dígitos — senão um CNPJ sem
# pontuação viraria [CARTAO] justamente onde ele deveria continuar legível.
_PATTERNS_INTERNO = (
    _PATTERNS[2:5]
    + [(_MatcherCartao(permitir_14=False), '[CARTAO]')]
    + _PATTERNS[6:]
)

# Datas de nascimento explícitas (contexto "nascido em", "nascimento")
_NASCIMENTO = re.compile(
    r'(nascid[oa]\s+em|data\s+de\s+nascimento[:\s]*)'
    r'\s*\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}',
    re.I,
)


def sanitizar_pii(texto: str, nomes_proteger: list[str] | None = None) -> tuple[str, bool]:
    """
    Remove PII do texto antes do envio ao Groq.

    Args:
      texto: texto livre digitado pelo advogado
      nomes_proteger: lista de nomes próprios (cliente, parte contrária)
                      a substituir por placeholders

    Returns:
      (texto_sanitizado, houve_remocao)
    """
    original = texto
    resultado = texto

    # 1. Padrões estruturados (CPF, CNPJ, etc.)
    #    O cartão entra ENTRE os índices 4 e 5, e a posição é o defeito que ela
    #    corrige: depois de CPF/CNPJ/processo (senão um CNPJ de 14 dígitos sem
    #    pontuação seria contado como PAN) e ANTES de TELEFONE, que num PAN
    #    agrupado morde o miolo ("3782 822463 1000 5" virava
    #    "3782 [TELEFONE] 5") e quebra a sequência antes que o cartão a veja.
    #    Reordenar `_PATTERNS` não é opção: os índices são referenciados.
    for pattern, placeholder in _PATTERNS:
        resultado = pattern.sub(placeholder, resultado)

    # 2. Datas de nascimento contextuais
    resultado = _NASCIMENTO.sub(r'\1 [DATA_NASC]', resultado)

    # 3. Nomes específicos do caso (cliente, parte contrária)
    if nomes_proteger:
        for i, nome in enumerate(nomes_proteger, start=1):
            if nome and len(nome.strip()) >= 4:
                # Substitui nome completo e variações case-insensitive.
                # Usa lookahead/lookbehind de não-palavra em vez de \b para
                # cobrir nomes com pontuação interna (S.A., Ltda., etc.)
                escaped = re.escape(nome.strip())
                resultado = re.sub(
                    rf'(?<!\w){escaped}(?!\w)',
                    f'[PARTE_{i}]',
                    resultado,
                    flags=re.IGNORECASE,
                )

    return resultado, (resultado != original)


def sanitizar_pii_interno(texto: str, nomes_proteger: list[str] | None = None) -> tuple[str, bool]:
    """
    Variante de `sanitizar_pii` para uso 100% interno (nunca sai para provider
    externo): mantém CPF/CNPJ visíveis (decisão de 2026-07-04 — uso interno do
    escritório), mas continua removendo processo/RG/e-mail/telefone/CEP/cartão/
    PIX/nomes protegidos, exatamente como antes. NÃO USAR neste texto para
    montar mensagens que possam ir a Anthropic/Groq — para isso, use sempre
    `sanitizar_pii` (que trata CPF/CNPJ como qualquer outro provider externo).
    """
    original = texto
    resultado = texto
    # Mesma ordem da variante externa, pulando CPF (0) e CNPJ (1). Como o CNPJ
    # NÃO foi mascarado aqui, o cartão roda com `permitir_14=False`.
    for pattern, placeholder in _PATTERNS_INTERNO:
        resultado = pattern.sub(placeholder, resultado)
    resultado = _NASCIMENTO.sub(r'\1 [DATA_NASC]', resultado)
    if nomes_proteger:
        for i, nome in enumerate(nomes_proteger, start=1):
            if nome and len(nome.strip()) >= 4:
                escaped = re.escape(nome.strip())
                resultado = re.sub(
                    rf'(?<!\w){escaped}(?!\w)',
                    f'[PARTE_{i}]',
                    resultado,
                    flags=re.IGNORECASE,
                )
    return resultado, (resultado != original)


def validar_sem_pii_interno(texto: str) -> list[str]:
    """Mesma checagem de `validar_sem_pii`, exceto CPF/CNPJ (uso interno)."""
    # `permitir_14=False`: aqui o CNPJ fica visível de propósito e não pode ser
    # reportado como cartão residual.
    return [tipo for tipo in validar_sem_pii(texto, permitir_14=False)
            if tipo not in ("CPF", "CNPJ")]


def validar_sem_pii(texto: str, *, permitir_14: bool = True) -> list[str]:
    """
    Validação final: verifica se ainda há PII residual.
    Retorna lista de tipos encontrados (vazia = limpo).
    Usado como segunda barreira antes da chamada à API.
    """
    encontrados = []
    # Reusa os MESMOS padrões de sanitizar_pii (índices em _PATTERNS).
    checks = {
        'CPF': _PATTERNS[0][0],
        'CNPJ': _PATTERNS[1][0],
        'PROCESSO': _PATTERNS[2][0],
        'RG': _PATTERNS[3][0],
        'EMAIL': _PATTERNS[4][0],
        # `permitir_14=False` (uso interno) usa o matcher que devolve o empate
        # de 14 dígitos ao CNPJ, que ali fica visível de propósito.
        'CARTAO': _PATTERNS[5][0] if permitir_14 else _MatcherCartao(False),
        'TELEFONE': _PATTERNS[6][0],
        'CEP': _PATTERNS[7][0],
        # CARTAO (5) e CHAVE_PIX (8) faltavam nesta segunda barreira: um número
        # de cartão ou chave PIX residual passava com "nenhuma PII residual".
        'CHAVE_PIX': _PATTERNS[8][0],
        'OAB': _PATTERNS[9][0],
        'ENDERECO': _PATTERNS[10][0],
        'TELEFONE_SEM_DDD': _PATTERNS[11][0],
        'DOCUMENTO': _PATTERNS[12][0],
        'DADOS_BANCARIOS': _PATTERNS[13][0],
        'PLACA': _PATTERNS[14][0],
        'PASSAPORTE': _PATTERNS[15][0],
        'PROCESSO_ANTIGO': _PATTERNS[16][0],
    }
    for nome, pattern in checks.items():
        if pattern.search(texto):
            encontrados.append(nome)
    return encontrados
