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
    (re.compile(r'(\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b'), '[TELEFONE]'),
    # CEP: 00000-000
    (re.compile(r'\b\d{5}-?\d{3}\b'), '[CEP]'),
    # Cartão de crédito (16 dígitos com/sem separadores)
    (re.compile(r'\b\d{4}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{4}\b'), '[CARTAO]'),
    # PIX chave aleatória (UUID)
    (re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I), '[CHAVE_PIX]'),
]

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
    for pattern, placeholder in _PATTERNS[2:]:  # pula CPF (0) e CNPJ (1)
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
    return [tipo for tipo in validar_sem_pii(texto) if tipo not in ("CPF", "CNPJ")]


def validar_sem_pii(texto: str) -> list[str]:
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
    }
    for nome, pattern in checks.items():
        if pattern.search(texto):
            encontrados.append(nome)
    return encontrados
