# ── app/services/sanitizer.py ────────────────────────────────────────────────
# Sanitização LGPD — remove PII antes de QUALQUER envio ao Groq.
#
# CRÍTICO: o Groq processa dados fora do VPS (EUA). Enviar CPF, CNPJ,
# nome de cliente ou número de processo identificável = violação LGPD.
# Esta camada é OBRIGATÓRIA em todo prompt. Sem exceção.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import re


# ── Padrões de PII (ordem importa: mais específico primeiro) ─────────────────
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # CPF: 000.000.000-00 ou 00000000000
    (re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b'), '[CPF]'),
    # CNPJ: 00.000.000/0000-00 ou 14 dígitos
    (re.compile(r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b'), '[CNPJ]'),
    # Número de processo CNJ: 0000000-00.0000.0.00.0000
    (re.compile(r'\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b'), '[PROCESSO]'),
    # RG: 00.000.000-0 (padrão MG/SP)
    (re.compile(r'\bRG[:\s]*\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx]\b', re.I), 'RG [RG]'),
    # E-mail
    (re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b'), '[EMAIL]'),
    # Telefone BR: (31) 99999-9999, +55 31 ..., 31999999999
    # `(?<!\d)` impede que o padrão comece NO MEIO de uma sequência maior de
    # dígitos. Sem essa guarda, um cartão "4111 1111 1111 1111" casava aqui em
    # "11 1111 1111" (os padrões são aplicados em ordem e TELEFONE vem antes de
    # CARTAO), sobrando "41" e "1111" em claro rumo ao provider externo — e
    # ainda rotulados como telefone. Reordenar a lista não é opção: os índices
    # 0-6 são referenciados por `validar_sem_pii` e `sanitizar_pii_interno` usa
    # `[2:]`.
    (re.compile(r'(?<!\d)(\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b'), '[TELEFONE]'),
    # CEP: 00000-000
    (re.compile(r'\b\d{5}-?\d{3}\b'), '[CEP]'),
    # Cartão de crédito — entrada CONSERVADORA, mantida aqui só para os
    # consumidores genéricos de `_PATTERNS` (pseudonymizer, inventário de
    # placeholders): casa os formatos clássicos e nunca mascara a mais. A regra
    # completa NÃO cabe em regex e vive em `mascarar_cartoes`, logo abaixo —
    # todo caminho real chama aquela função, que é subconjunto-superior desta.
    (re.compile(
        r'(?<!\d)(?:'
        r'\d{13,19}'                                              # sem separadores
        r'|\d{4}[\s.-]\d{4}[\s.-]\d{4}[\s.-]\d{4}(?:[\s.-]\d{3})?'  # 4-4-4-4(-3)
        r'|\d{4}[\s.-]\d{6}[\s.-]\d{4,5}'                         # AmEx 4-6-5, Diners 4-6-4
        r')(?!\d)'
    ), '[CARTAO]'),
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
]

# ── Cartão: a única regra de PII que regex não expressa sozinha ──────────────
# Um PAN é QUALQUER sequência de 13 a 19 dígitos, agrupada como a bandeira
# quiser. Regex não CONTA dígitos através de separadores, e cada tentativa de
# enumerar formatos deixou um comprimento de fora: primeiro tudo que não fosse
# 16 dígitos, depois todo PAN AGRUPADO de 13 a 18 ("4222 2222 2222 2" saía
# intacto, e "3782 822463 1000 5" saía como "3782 [TELEFONE] 5" — mascaramento
# parcial rotulado errado). Dois achados P1 do Codex no PR #1238, em SHAs
# consecutivos, pela mesma causa: enumerar formato em vez de contar dígito.
#
# Aqui o regex só delimita o CANDIDATO (grupo inicial de 4+ dígitos, grupos
# seguintes de 3+, e um grupo final curto opcional) e quem decide é a contagem.
# O piso de 3 dígitos nos grupos intermediários é o que impede o candidato de
# atravessar datas vizinhas: "2026-08-22 2027-09-30" são 16 dígitos, mas os
# grupos de 2 quebram o casamento — data de audiência não pode virar cartão.
_CARTAO_TRECHO = re.compile(r'(?<!\d)\d{4,}(?:[\s.-]\d{3,})*(?:[\s.-]\d{1,2})?(?!\d)')
_NAO_DIGITO = re.compile(r'\D')


# O índice 7 sai dos laços de aplicação: quem manda é `mascarar_cartoes`, que
# roda entre o 4 e o 5. Manter os dois faria a entrada conservadora — que não
# distingue CNPJ de Diners, ambos com 14 dígitos — mascarar como [CARTAO] o
# CNPJ que a variante interna quer deixar legível.
_APOS_CARTAO = _PATTERNS[5:7] + _PATTERNS[8:]


def _e_cartao(trecho: str, permitir_14: bool) -> bool:
    """13 a 19 dígitos. `permitir_14=False` devolve o empate a favor do CNPJ.

    14 dígitos sem pontuação é AMBÍGUO: CNPJ e Diners têm o mesmo comprimento e
    nada no texto os distingue. Na variante externa isso não aparece — o CNPJ
    já foi mascarado no índice 1, antes desta passada. Na variante interna
    CPF/CNPJ ficam visíveis de propósito (decisão de 2026-07-04) e o texto
    nunca sai do VPS, então o empate resolve a favor de manter o CNPJ legível.
    """
    n = len(_NAO_DIGITO.sub('', trecho))
    if not 13 <= n <= 19:
        return False
    return not (n == 14 and not permitir_14)


def mascarar_cartoes(texto: str, marcador='[CARTAO]', *, permitir_14: bool = True) -> str:
    """Mascara todo PAN de 13 a 19 dígitos. `marcador` aceita str ou callable
    recebendo o match (o pseudonymizer precisa gerar marcador reversível)."""
    def _troca(m: re.Match) -> str:
        if not _e_cartao(m.group(0), permitir_14):
            return m.group(0)
        return marcador(m) if callable(marcador) else marcador
    return _CARTAO_TRECHO.sub(_troca, texto)


def tem_cartao(texto: str, *, permitir_14: bool = True) -> bool:
    """Versão de leitura, para a segunda barreira."""
    return any(_e_cartao(m.group(0), permitir_14)
               for m in _CARTAO_TRECHO.finditer(texto))


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
    for pattern, placeholder in _PATTERNS[:5]:
        resultado = pattern.sub(placeholder, resultado)
    resultado = mascarar_cartoes(resultado)
    for pattern, placeholder in _APOS_CARTAO:
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
    for pattern, placeholder in _PATTERNS[2:5]:
        resultado = pattern.sub(placeholder, resultado)
    resultado = mascarar_cartoes(resultado, permitir_14=False)
    for pattern, placeholder in _APOS_CARTAO:
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
        'TELEFONE': _PATTERNS[5][0],
        'CEP': _PATTERNS[6][0],
        # CARTAO (7) e CHAVE_PIX (8) faltavam nesta segunda barreira: um número
        # de cartão ou chave PIX residual passava com "nenhuma PII residual".
        # CARTAO não entra neste dict porque a regra é contagem de dígitos, não
        # formato — ver `tem_cartao`, chamado abaixo.
        'CHAVE_PIX': _PATTERNS[8][0],
        'OAB': _PATTERNS[9][0],
        'ENDERECO': _PATTERNS[10][0],
    }
    for nome, pattern in checks.items():
        if pattern.search(texto):
            encontrados.append(nome)
    if tem_cartao(texto, permitir_14=permitir_14):
        encontrados.append('CARTAO')
    return encontrados
