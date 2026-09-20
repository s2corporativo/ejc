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
MSG_SIGILO_BLOQUEADO = (
    "Este caso exige processamento por IA local por motivo de sigilo, mas a "
    "IA local necessária não está disponível. Procure o administrador do sistema."
)
MSG_TRANSCRICAO_NAO_ATIVADA = (
    "A transcrição por IA não está ativada nesta instalação. "
    "Procure o administrador."
)

class SafeAIError(RuntimeError):
    """Erro de IA com metadados explicitamente seguros para log/telemetria.

    A mensagem interna passada ao construtor também deve ser sanitizada. Campos
    estruturados evitam que camadas superiores tenham de inspecionar `str(e)`
    de SDKs, que pode conter request body/PII.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "technical",
        technical_type: str | None = None,
        status_code: int | None = None,
        public_message: str | None = None,
    ):
        super().__init__(message)
        self.ai_error_code = (code or "technical")[:80]
        self.technical_type = (technical_type or type(self).__name__)[:100]
        self.status_code = status_code
        self.public_message = public_message


def descricao_tecnica_segura(erro) -> str:
    """Descrição para logs sem ler mensagem arbitrária de exceção."""
    if not isinstance(erro, BaseException):
        return "erro"
    tipo = getattr(erro, "technical_type", None) or type(erro).__name__
    status = getattr(erro, "status_code", None) or getattr(
        getattr(erro, "response", None), "status_code", None
    )
    codigo = getattr(erro, "ai_error_code", None)
    partes = [str(tipo)[:100]]
    if status:
        partes.append(f"HTTP {status}")
    if codigo:
        partes.append(f"codigo={str(codigo)[:80]}")
    return " | ".join(partes)


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
    r"provedor|provider|task=|\.env|api[_ ]?key|ollama|groq|anthropic|maritaca"
    r"|errno|timeout|timed?\s?out|connection|refused|unreachable|http\s?\d{3}"
    r"|traceback|exception|falha na ia|ia indisponível|desabilitad|configur"
    r"|indispon[ií]vel|localhost|127\.0\.0\.1|:\d{4,5}\b",
    re.I,
)


def mensagem_ia_para_usuario(erro, padrao: str = MSG_IA_INDISPONIVEL) -> str:
    """Converte erro de IA em mensagem leiga sem ecoar exceção arbitrária.

    Strings explícitas continuam aceitas para regras de negócio legadas.
    Exceções só podem fornecer mensagem pública por `SafeAIError`; qualquer
    outra exceção cai no padrão, porque `str(e)` pode conter PII.
    """
    if isinstance(erro, SafeAIError):
        if erro.public_message:
            return erro.public_message[:300]
        if erro.ai_error_code in {"pii_blocked", "lgpd_blocked"}:
            return MSG_PII_BLOQUEADA
        if erro.ai_error_code == "sigilo_blocked":
            return MSG_SIGILO_BLOQUEADO
        if erro.ai_error_code == "transcription_disabled":
            return MSG_TRANSCRICAO_NAO_ATIVADA
        return padrao

    if isinstance(erro, BaseException):
        return padrao

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
        "[IA] %s falhou: %s",
        contexto or "chamada de IA",
        descricao_tecnica_segura(erro),
    )
    return HTTPException(status_code=status_code,
                         detail=mensagem_ia_para_usuario(erro, padrao))
