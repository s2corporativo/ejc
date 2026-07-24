"""Motor conversacional e probatório da Sala de Análise Jurídica.

A Sala evolui o Raio-X existente sem criar gateway, RAG ou agente paralelo. A
conversa é livre na interface, mas toda resposta atualiza um estado jurídico
estruturado e auditável. Nenhuma conclusão é promovida a caso oficial sem HITL.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AILog, AIRiscoIA, AIStatusHITL, AITipoUso
from app.models.raio_x import RaioXAnalise
from app.services.ai_gateway import chat as gw_chat
from app.services.ai_service import buscar_contexto_rag
from app.services.sanitizer import sanitizar_pii

logger = logging.getLogger("ejc.sala_analise")

_ALLOWED_STATE_KEYS = (
    "fatos",
    "provas",
    "contradicoes",
    "questoes_juridicas",
    "riscos",
    "documentos_pendentes",
    "proximos_passos",
    "tese_favoravel",
    "tese_adversa",
    "visao_julgador",
    "sintese_atual",
)

_MODE_INSTRUCTIONS = {
    "conversar": "Responda objetivamente à pergunta do advogado e atualize somente o que mudou no estado.",
    "organizar_fatos": "Reconstrua a cronologia e classifique cada fato como comprovado, alegado, inferido, controvertido, ausente ou superado.",
    "detectar_contradicoes": "Compare datas, valores, nomes, locais, versões e documentos. Não trate divergência como erro sem indicar as fontes em conflito.",
    "avaliar_provas": "Avalie pertinência, autenticidade aparente, contemporaneidade, origem, força e lacunas de cada prova. Não transforme indício em prova plena.",
    "simular_defesa": "Atue como advogado da parte contrária e apresente preliminares, teses defensivas, excludentes, impugnações probatórias e riscos de sucumbência.",
    "julgar": "Atue como julgador imparcial: separe admissibilidade, fatos provados, ônus, pontos controvertidos, necessidade de instrução e resultado juridicamente provável.",
    "listar_pendencias": "Liste somente documentos, diligências, perícias, confirmações e decisões humanas ainda necessárias, em ordem de criticidade.",
    "consolidar": "Produza o estado atual completo da análise, eliminando duplicidades e preservando a evolução das premissas superadas.",
}

_SYSTEM_PROMPT = """Você é o núcleo de raciocínio jurídico probatório da Sala de Análise Jurídica do EJC, para uso interno de advogados brasileiros.

REGRAS ABSOLUTAS
1. Trabalhe somente com os fatos, documentos, estado anterior e fontes fornecidos.
2. Diferencie rigorosamente: fato comprovado, alegação, inferência, controvérsia, dado ausente e premissa superada.
3. Não invente lei, súmula, precedente, órgão, data, valor, documento ou conteúdo de prova.
4. Orçamento não é pagamento; reportagem não prova o fato concreto; relato unilateral não é constatação técnica; hipótese não é fato.
5. Apresente tese favorável, tese adversa e visão provável do julgador quando pertinente.
6. Toda fonte jurídica deve ser identificável. Quando a base não sustentar a afirmação, escreva "verificar fonte oficial".
7. Não prometa resultado. Toda saída é rascunho sujeito à revisão humana.
8. Não revele raciocínio interno. Entregue apenas a conclusão estruturada.

FORMATO DE SAÍDA
Responda exclusivamente com um objeto JSON válido, sem cercas Markdown, com:
{
  "resposta_markdown": "resposta clara ao advogado",
  "estado": {
    "sintese_atual": "síntese consolidada",
    "fatos": [{"texto":"...","classificacao":"comprovado|alegado|inferido|controvertido|ausente|superado","fontes":["documento/página/trecho"],"confianca":"alta|media|baixa"}],
    "provas": [{"texto":"...","forca":"forte|media|fraca|pendente","fontes":["..."]}],
    "contradicoes": [{"texto":"...","fontes":["..."],"impacto":"critico|alto|moderado|baixo"}],
    "questoes_juridicas": [{"texto":"...","status":"resolvida|pendente|controvertida","fonte_juridica":"..."}],
    "riscos": [{"texto":"...","nivel":"critico|alto|moderado|baixo"}],
    "documentos_pendentes": [{"texto":"...","criticidade":"critica|alta|media|baixa"}],
    "proximos_passos": [{"texto":"...","prioridade":"imediata|alta|media|baixa"}],
    "tese_favoravel": ["..."],
    "tese_adversa": ["..."],
    "visao_julgador": "..."
  }
}
Mantenha arrays vazios quando não houver base. Preserve fatos já confirmados no estado anterior, salvo quando nova prova os tornar controvertidos ou superados."""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lista(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _texto_item(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("texto", "fato", "descricao", "titulo", "valor", "evento", "nome"):
            if value.get(key):
                return str(value[key]).strip()
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value or "").strip()


def estado_inicial(analise: RaioXAnalise) -> dict[str, Any]:
    """Converte o relatório documental já existente em estado probatório inicial."""
    report = analise.relatorio or {}
    fatos = []
    for item in _lista(report.get("fatos_provas")):
        texto = _texto_item(item)
        if texto:
            fatos.append({
                "texto": texto,
                "classificacao": "alegado",
                "fontes": _lista(item.get("fontes")) if isinstance(item, dict) else [],
                "confianca": "media" if isinstance(item, dict) and item.get("fontes") else "baixa",
            })
    provas = []
    for item in _lista(report.get("provas")):
        texto = _texto_item(item)
        if texto:
            provas.append({"texto": texto, "forca": "pendente", "fontes": []})
    contradicoes = []
    for item in _lista(report.get("contradicoes")):
        texto = _texto_item(item)
        if texto:
            contradicoes.append({"texto": texto, "fontes": [], "impacto": "moderado"})
    riscos = []
    for item in _lista(report.get("riscos")):
        texto = _texto_item(item)
        if texto:
            riscos.append({"texto": texto, "nivel": "moderado"})
    pendencias = []
    for item in _lista(report.get("documentos_pendentes")):
        texto = _texto_item(item)
        if texto:
            pendencias.append({"texto": texto, "criticidade": "media"})
    passos = []
    for item in _lista(report.get("proximos_passos")):
        texto = _texto_item(item)
        if texto:
            passos.append({"texto": texto, "prioridade": "media"})
    return {
        "versao": 1,
        "atualizado_em": _agora(),
        "revisao_humana_obrigatoria": True,
        "sintese_atual": str(report.get("sintese_executiva") or "Análise preliminar iniciada."),
        "fatos": fatos,
        "provas": provas,
        "contradicoes": contradicoes,
        "questoes_juridicas": [],
        "riscos": riscos,
        "documentos_pendentes": pendencias,
        "proximos_passos": passos,
        "tese_favoravel": _lista(report.get("teses")),
        "tese_adversa": [],
        "visao_julgador": "Ainda não avaliada.",
    }


def serializar_sala(analise: RaioXAnalise) -> dict[str, Any]:
    estado = analise.estado_analise or estado_inicial(analise)
    return {
        "analise_id": analise.id,
        "titulo": analise.titulo,
        "status": analise.status,
        "convertido_case_id": analise.convertido_case_id,
        "conversa": analise.conversa or [],
        "estado_analise": estado,
        "ultima_consolidacao_em": (
            analise.ultima_consolidacao_em.isoformat()
            if analise.ultima_consolidacao_em else None
        ),
        "documentos": [
            {
                "id": doc.id,
                "nome_original": doc.nome_original,
                "tipo_documento": doc.tipo_documento,
                "paginas": doc.paginas,
                "ocr_utilizado": doc.ocr_utilizado,
            }
            for doc in analise.documentos
        ],
        "aviso": "Rascunho interno. Revisão humana obrigatória antes de qualquer uso externo.",
    }


def _nomes_proteger(analise: RaioXAnalise) -> list[str]:
    nomes: list[str] = []
    if analise.potencial_cliente:
        nomes.append(analise.potencial_cliente)
    for item in _lista((analise.relatorio or {}).get("partes")):
        nome = _texto_item(item)
        if 3 <= len(nome) <= 160:
            nomes.append(nome)
    return list(dict.fromkeys(nomes))[:30]


def _formatar_fontes(fontes: list[dict[str, Any]]) -> str:
    if not fontes:
        return "[FONTES JURÍDICAS]\nNenhuma fonte aprovada recuperada. Toda referência normativa deve ser marcada para verificação oficial."
    blocos = ["[FONTES JURÍDICAS APROVADAS]"]
    for idx, fonte in enumerate(fontes, 1):
        blocos.append(
            f"[Fonte {idx}] {fonte.get('titulo') or 'Sem título'} | "
            f"categoria={fonte.get('categoria') or 'não informada'} | "
            f"origem={fonte.get('fonte') or 'base EJC'}\n"
            f"{str(fonte.get('conteudo') or '')[:1200]}"
        )
    return "\n\n".join(blocos)


def _extrair_json(texto: str) -> dict[str, Any] | None:
    bruto = (texto or "").strip()
    bruto = re.sub(r"^```(?:json)?\s*", "", bruto, flags=re.I)
    bruto = re.sub(r"\s*```$", "", bruto)
    try:
        data = json.loads(bruto)
        return data if isinstance(data, dict) else None
    except Exception:
        inicio = bruto.find("{")
        fim = bruto.rfind("}")
        if inicio >= 0 and fim > inicio:
            try:
                data = json.loads(bruto[inicio: fim + 1])
                return data if isinstance(data, dict) else None
            except Exception:
                return None
    return None


def _normalizar_estado(novo: Any, anterior: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(novo, dict):
        novo = {}
    saida: dict[str, Any] = {
        "versao": int(anterior.get("versao") or 1) + 1,
        "atualizado_em": _agora(),
        "revisao_humana_obrigatoria": True,
    }
    for key in _ALLOWED_STATE_KEYS:
        value = novo.get(key, anterior.get(key))
        if key in {"visao_julgador", "sintese_atual"}:
            saida[key] = str(value or "")
        else:
            saida[key] = _lista(value)[:120]
    return saida


def _usage(resp: Any, key: str) -> int | None:
    usage = getattr(resp, "usage", None)
    if usage is not None:
        return getattr(usage, key, None)
    fallback = "input_tokens" if key == "prompt_tokens" else "output_tokens"
    return getattr(resp, fallback, None)


async def processar_mensagem(
    db: AsyncSession,
    analise: RaioXAnalise,
    user_id: str,
    mensagem: str,
    modo: str,
) -> dict[str, Any]:
    estado_anterior = analise.estado_analise or estado_inicial(analise)
    historico = _lista(analise.conversa)[-20:]
    consulta = f"{modo}: {mensagem}".strip()
    fontes = await buscar_contexto_rag(db, consulta, limite=6, scope_client_id=None)

    contexto = {
        "analise": {
            "titulo": analise.titulo,
            "area": analise.area,
            "fase": analise.fase,
            "potencial_cliente": analise.potencial_cliente,
        },
        "relatorio_documental": analise.relatorio or {},
        "estado_anterior": estado_anterior,
        "conversa_recente": [
            {"role": item.get("role"), "content": item.get("content")}
            for item in historico if isinstance(item, dict)
        ],
    }
    prompt = (
        f"MODO SOLICITADO: {modo}\n"
        f"INSTRUÇÃO DO MODO: {_MODE_INSTRUCTIONS.get(modo, _MODE_INSTRUCTIONS['conversar'])}\n\n"
        f"MENSAGEM DO ADVOGADO:\n{mensagem}\n\n"
        f"CONTEXTO ESTRUTURADO DA ANÁLISE:\n"
        f"{json.dumps(contexto, ensure_ascii=False, default=str)[:24000]}\n\n"
        f"{_formatar_fontes(fontes)}"
    )
    prompt_limpo, houve_pii = sanitizar_pii(prompt, _nomes_proteger(analise))

    resp = await gw_chat(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt_limpo},
        ],
        task_type="estrategia",
        temperature=0.1,
        max_tokens=4200,
        nivel_inteligencia="alto",
    )
    texto = getattr(resp, "texto", "") or ""
    parsed = _extrair_json(texto)
    if parsed:
        resposta = str(parsed.get("resposta_markdown") or "Análise atualizada.")
        estado = _normalizar_estado(parsed.get("estado"), estado_anterior)
    else:
        resposta = texto or "Não foi possível estruturar a resposta da IA."
        estado = _normalizar_estado({}, estado_anterior)

    modelo = getattr(resp, "modelo", None) or "nao_informado"
    provedor = getattr(resp, "provedor", None)
    if provedor:
        modelo = f"{provedor}/{modelo}"
    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        case_id=None,
        tipo_uso=AITipoUso.analise_caso,
        modelo=modelo,
        prompt_sanitizado=prompt_limpo[:8000],
        pii_removida=houve_pii,
        resposta=resposta,
        fontes_rag="; ".join(str(item.get("chunk_id")) for item in fontes) or None,
        tokens_input=_usage(resp, "prompt_tokens"),
        tokens_output=_usage(resp, "completion_tokens"),
        risco_ia=AIRiscoIA.medio_risco,
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)

    agora = _agora()
    conversa = _lista(analise.conversa)
    conversa.extend([
        {
            "id": str(uuid4()),
            "role": "user",
            "content": mensagem,
            "modo": modo,
            "created_at": agora,
        },
        {
            "id": str(uuid4()),
            "role": "assistant",
            "content": resposta,
            "modo": modo,
            "created_at": _agora(),
            "ai_log_id": log.id,
            "fontes_usadas": len(fontes),
            "revisao_obrigatoria": True,
        },
    ])
    analise.conversa = conversa[-100:]
    analise.estado_analise = estado
    analise.status = "em_analise" if analise.status == "novo" else analise.status
    if modo == "consolidar":
        analise.ultima_consolidacao_em = datetime.now(timezone.utc)
    await db.flush()
    return {
        "mensagem": analise.conversa[-1],
        "estado_analise": estado,
        "fontes_usadas": len(fontes),
        "ai_log_id": log.id,
        "aviso": "Rascunho de apoio. Revisão por advogado obrigatória.",
    }
