"""
document_classifier.py — Classificação automática de tipo de documento por IA.

Dado um documento já com texto extraído (OCR), a IA sugere UM tipo do catálogo
oficial `document_types_master` (petição, contrato, comprovante, procuração…),
para PRÉ-PREENCHER o campo Document.tipo. A gravação NUNCA é automática: a
resposta é apenas SUGESTÃO — confirmação humana obrigatória (HITL/OAB).

Abordagem NÃO invasiva: service novo e isolado, não altera o fluxo de upload.

Pipeline LGPD OBRIGATÓRIO (mesmo padrão de documento_service.sugerir_tipo):
    ler catálogo → sanitizar_pii(texto) → IA restrita ao enum do catálogo → parse.

Fail-safe: se a IA estiver desabilitada (sem provedores/erro), retorna
`{"tipo_sugerido": None, ...}` SEM levantar exceção — nunca quebra o chamador.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ai_gateway
from app.services.sanitizer import sanitizar_pii  # remoção de PII antes da IA (LGPD)
from app.models.redesign import DocumentTypeMaster

logger = logging.getLogger("ejc.document_classifier")

# Teto de caracteres enviados à IA (o suficiente para classificar cabeçalho/corpo).
_MAX_CHARS = 6000
_MIN_CHARS = 40

_CONFIANCAS = {"alta", "media", "baixa"}


def _parse_json(texto: str) -> dict:
    """Extrai o primeiro objeto JSON da resposta da IA de forma robusta."""
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except Exception:
        pass
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


async def _tipos_validos(db: AsyncSession) -> list[dict]:
    """Lê os tipos ATIVOS do catálogo document_types_master (rótulo + chave)."""
    rows = (await db.execute(
        select(DocumentTypeMaster)
        .where(DocumentTypeMaster.ativo.is_(True))
        .order_by(DocumentTypeMaster.ordem, DocumentTypeMaster.nome)
    )).scalars().all()
    return [
        {"tipo_key": t.tipo_key, "nome": t.nome, "descricao": t.descricao}
        for t in rows
    ]


def _resposta_indisponivel(motivo: str, alternativas: Optional[list] = None) -> dict:
    """Fail-safe padronizado: IA off/erro/catálogo vazio → sugestão nula."""
    return {
        "tipo_sugerido": None,
        "confianca": None,
        "alternativas": alternativas or [],
        "justificativa": motivo,
        "disponivel": False,
    }


async def classificar_documento(db: AsyncSession, texto: str,
                                user_id: str | None = None) -> dict:
    """
    Sugere o tipo de documento a partir do texto extraído (OCR).

    Retorna sempre um dict:
      {
        "tipo_sugerido": "<tipo_key do catálogo> | None",
        "confianca": "alta|media|baixa | None",
        "alternativas": [{"tipo_key": ..., "nome": ...}, ...],
        "justificativa": "<texto>",
        "disponivel": bool,
        "pii_removida": bool,          # presente quando a IA foi acionada
      }

    Fail-safe: qualquer indisponibilidade da IA retorna tipo_sugerido=None
    sem levantar exceção.
    """
    # 0) Texto mínimo para classificar
    texto = (texto or "").strip()
    if len(texto) < _MIN_CHARS:
        return _resposta_indisponivel(
            "Sem texto suficiente para classificar (OCR vazio ou muito curto)."
        )

    # 1) Catálogo oficial — restringe a resposta da IA a estes tipos
    try:
        tipos = await _tipos_validos(db)
    except Exception as e:
        logger.warning("document_types_master indisponível: %s", e)
        return _resposta_indisponivel("Catálogo de tipos indisponível.")
    if not tipos:
        return _resposta_indisponivel(
            "Catálogo de tipos (document_types_master) não populado — rode o seed."
        )
    keys_validas = {t["tipo_key"] for t in tipos}
    catalogo = "\n".join(
        f"- {t['tipo_key']}: {t['nome']}"
        + (f" — {t['descricao']}" if t.get("descricao") else "")
        for t in tipos
    )

    # 2) SANITIZAÇÃO LGPD — remove PII (CPF/CNPJ/nº processo/e-mail/…) ANTES da IA.
    #    Função: app.services.sanitizer.sanitizar_pii (barreira obrigatória).
    texto_limpo, pii_removida = sanitizar_pii(texto[:_MAX_CHARS])

    # 3) Prompt com ENUM restrito ao catálogo (few-shot/enum) — proíbe inventar.
    system = (
        "Você classifica documentos jurídicos, fiscais e administrativos "
        "brasileiros em tipos pré-definidos. Escolha EXATAMENTE UM tipo_key da "
        "lista fornecida — é PROIBIDO inventar tipos fora da lista. Se nenhum se "
        "aplicar com clareza, use 'outro'. Não invente dados do documento."
    )
    user_msg = (
        f"TIPOS DISPONÍVEIS (tipo_key: nome — descrição):\n{catalogo}\n\n"
        f"TEXTO DO DOCUMENTO (sanitizado):\n{texto_limpo}\n\n"
        "Responda APENAS com JSON válido nesta forma exata:\n"
        '{"tipo_sugerido": "<tipo_key da lista>", '
        '"confianca": "alta|media|baixa", '
        '"justificativa": "<1-2 frases objetivas>", '
        '"alternativas": ["<outro tipo_key plausível da lista>", ...]}'
    )

    # 4) IA via gateway (tarefa leve). Fail-safe: erro/IA off → tipo_sugerido=None.
    try:
        resp = await ai_gateway.chat(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user_msg}],
            task_type="chat_rapido",
            temperature=0.1,
            max_tokens=300,
        )
    except Exception as e:
        logger.warning("IA indisponível na classificação de documento: %s", e)
        return _resposta_indisponivel("Serviço de IA indisponível no momento.")

    # I9: AILog quando o chamador informa o usuário (routers/documents.py está
    # em PR aberto — passa a informar quando integrar). Prompt já sanitizado.
    if user_id:
        from app.models.ai_log import AITipoUso
        await ai_gateway.registrar_log_resposta(
            db, user_id=user_id, tipo_uso=AITipoUso.outro, resp=resp,
            prompt_sanitizado="[DOCUMENT_CLASSIFIER]\n" + texto_limpo,
            pii_removida=pii_removida,
        )

    dados = _parse_json(resp.texto) or {}
    tipo = str(dados.get("tipo_sugerido") or "").strip()
    confianca = str(dados.get("confianca") or "").strip().lower()
    justificativa = str(dados.get("justificativa") or resp.texto or "")[:500]

    # 5) Guarda-corpo: só aceita tipos do catálogo (nunca propaga inventado).
    if tipo not in keys_validas:
        if tipo:
            justificativa = (
                f"IA sugeriu '{tipo}', que não existe no catálogo — "
                f"rebaixado para 'outro'. {justificativa}"
            )[:500]
        tipo = "outro" if "outro" in keys_validas else None
        confianca = "baixa"
    if confianca not in _CONFIANCAS:
        confianca = "media"

    # 6) Alternativas: apenas tipos válidos do catálogo, sem repetir o sugerido.
    alternativas: list[dict] = []
    for alt in (dados.get("alternativas") or []):
        alt_key = str(alt).strip()
        if alt_key in keys_validas and alt_key != tipo:
            nome = next((t["nome"] for t in tipos if t["tipo_key"] == alt_key), alt_key)
            alternativas.append({"tipo_key": alt_key, "nome": nome})

    return {
        "tipo_sugerido": tipo,
        "confianca": confianca,
        "alternativas": alternativas,
        "justificativa": justificativa,
        "disponivel": True,
        "pii_removida": pii_removida,
        "modelo": f"{resp.provedor}/{resp.modelo}",
    }
