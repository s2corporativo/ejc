# ── app/core/ai_errors.py ─────────────────────────────────────────────────────
# Tradução de erros de IA para o usuário leigo (P0 — relatório de usabilidade
# 2026-07-18, §10 item 2): nenhum texto com .env/provider/chave/task= chega à
# UI. O DETALHE TÉCNICO vai para logger.error (trilha interna/observabilidade);
# o `detail` da HTTPException vira mensagem leiga em português.
#
# Uso (camada de borda — routers, onde a exceção vira resposta HTTP):
#   except RuntimeError as e:
#       raise http_erro_ia(e, contexto="sugerir-teses")
# ou, para campos degradados em payload 200:
#   aviso = mensagem_ia_para_usuario(e)
from __future__ import annotations

import logging
import re

from fastapi import HTTPException

logger = logging.getLogger("ejc.ai.erros")

# ── Mensagens leigas (contrato com o frontend — não alterar sem combinar) ─────
MSG_IA_INDISPONIVEL = (
    "A inteligência artificial não está disponível no momento. "
    "Tente novamente em instantes ou procure o administrador do sistema."
)
MSG_IA_NAO_ATIVADA = (
    "A inteligência artificial ainda não foi ativada nesta instalação. "
    "Procure o administrador do sistema."
)
# Variante usada no payload degradado da análise completa do caso (§3.1).
MSG_IA_NAO_ATIVADA_CURTA = (
    "A inteligência artificial ainda não foi ativada nesta instalação. "
    "Procure o administrador."
)
MSG_PII_BLOQUEADA = (
    "Este conteúdo contém dados pessoais e não pôde ser enviado à IA externa. "
    "Remova dados pessoais do texto ou procure o administrador."
)
MSG_TRANSCRICAO_NAO_ATIVADA = (
    "A transcrição por IA não está ativada nesta instalação. "
    "Procure o administrador."
)

# ── Classificação do erro técnico ─────────────────────────────────────────────
# Bloqueio LGPD/PII (ai_gateway: "Conteúdo com dados pessoais…", "PII residual…",
# _MSG_BLOQUEIO_LOCAL_COMPLETO "…sigilo reforçado…").
_RE_PII = re.compile(
    r"dados pessoais|pii\s+residual|pseudonimiz|sigilo reforçado|lgpd", re.I
)
# Transcrição desligada/incompleta (ai_gateway.transcrever_audio: GROQ_API_KEY,
# AUDIO_TRANSCRIPTION_ENABLED, ZDR, DPA).
_RE_TRANSCRICAO = re.compile(
    r"transcri[çc][aã]o|zero data retention|audio_transcription|groq_zdr|dpa/", re.I
)
# Qualquer traço de infraestrutura/configuração que um advogado leigo não
# decodifica: providers, chaves, envs, erros de rede, task=, "Falha na IA".
_RE_TECNICO = re.compile(
    r"provedor|provider|task=|\.env|api[_ ]?key|groq|anthropic|maritaca"
    r"|errno|timeout|timed?\s?out|connection|refused|unreachable|http\s?\d{3}"
    r"|traceback|exception|falha na ia|ia indisponível|desabilitad|configur"
    r"|indispon[ií]vel|localhost|127\.0\.0\.1|:\d{4,5}\b",
    re.I,
)


def mensagem_ia_para_usuario(erro, padrao: str = MSG_IA_INDISPONIVEL) -> str:
    """Converte um erro (exceção ou string) de IA em mensagem leiga PT-BR.

    - Bloqueio de PII → MSG_PII_BLOQUEADA
    - Transcrição não ativada → MSG_TRANSCRICAO_NAO_ATIVADA
    - Qualquer texto técnico (provider/chave/.env/rede/task=) ou vazio → `padrao`
    - Mensagem já legível de regra de negócio (ex.: "Texto insuficiente…") passa
      intacta — a tradução nunca esconde orientação útil ao usuário.
    """
    txt = str(erro or "").strip()
    if _RE_PII.search(txt):
        return MSG_PII_BLOQUEADA
    if _RE_TRANSCRICAO.search(txt):
        return MSG_TRANSCRICAO_NAO_ATIVADA
    if not txt or _RE_TECNICO.search(txt):
        return padrao
    return txt[:300]


def http_erro_ia(
    erro,
    status_code: int = 503,
    contexto: str = "",
    padrao: str = MSG_IA_INDISPONIVEL,
) -> HTTPException:
    """Camada de borda: loga o DETALHE TÉCNICO (interno) e devolve HTTPException
    com `detail` leigo. Usar `raise http_erro_ia(e, ...)` nos routers de IA."""
    logger.error(
        "[IA] %s falhou: %s: %s",
        contexto or "chamada de IA",
        type(erro).__name__ if isinstance(erro, BaseException) else "erro",
        str(erro)[:500],
    )
    return HTTPException(status_code=status_code,
                         detail=mensagem_ia_para_usuario(erro, padrao))
