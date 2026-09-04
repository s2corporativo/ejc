# ── app/services/ai/core/audit_logger.py ─────────────────────────────────────
# AUDITORIA do Núcleo Único de IA — ponte única para o AILog.
#
# Reusa ai_guard.registrar_ai_log (caminho canônico: erro de gravação PROPAGA —
# IA sem trilha de auditoria deve falhar, não seguir em silêncio). Este módulo
# só traduz o vocabulário do núcleo (TarefaIA/fontes/custo) para o modelo AILog.
# LGPD: somente o prompt SANITIZADO é gravado; nunca segredos, nunca PII.
from __future__ import annotations

from app.models.ai_log import AITipoUso
from app.services.system_prompts import TarefaIA

# TarefaIA (núcleo) → AITipoUso (enum persistido em ai_logs).
_TAREFA_PARA_TIPO_USO: dict[TarefaIA, AITipoUso] = {
    TarefaIA.ANALISE_CASO: AITipoUso.analise_caso,
    TarefaIA.DOSSIE: AITipoUso.analise_caso,
    TarefaIA.TRABALHISTA: AITipoUso.analise_caso,
    TarefaIA.CRIMINAL: AITipoUso.analise_caso,
    TarefaIA.FAMILIA: AITipoUso.analise_caso,
    TarefaIA.ADMINISTRATIVO: AITipoUso.analise_caso,
    TarefaIA.SUCESSOES: AITipoUso.analise_caso,
    TarefaIA.IMOBILIARIO: AITipoUso.analise_caso,
    TarefaIA.AMBIENTAL: AITipoUso.analise_caso,
    TarefaIA.TRIAGEM: AITipoUso.analise_caso,
    TarefaIA.MINUTAS: AITipoUso.redacao_peca,
    TarefaIA.PESQUISA_JURIDICA: AITipoUso.consulta_rag,
    TarefaIA.RAG_QUERY: AITipoUso.consulta_rag,
    TarefaIA.RESUMO: AITipoUso.resumo_documento,
}

# A análise agregada de Clientes usa deliberadamente o DocumentAgent/TarefaIA.RESUMO
# apenas para obter um agente sem `exige_fonte` e, assim, respeitar `usar_rag=False`.
# Isso NÃO transforma a operação em resumo de documento. O marcador abaixo é
# inserido pelo backend em clients.py e não contém PII. Mantemos o override aqui,
# na ponte de auditoria, sem alterar agente, provider, HITL ou retrieval.
_CLIENTE_ANALISE_MARKER = "[INDICADORES AGREGADOS DO CLIENTE]"


def _tipo_uso(tarefa: TarefaIA, prompt_sanitizado: str | None = None) -> AITipoUso:
    if (
        tarefa == TarefaIA.RESUMO
        and prompt_sanitizado
        and _CLIENTE_ANALISE_MARKER in prompt_sanitizado
    ):
        return AITipoUso.outro
    return _TAREFA_PARA_TIPO_USO.get(tarefa, AITipoUso.outro)


def _fontes_str(fontes: list[dict] | None) -> str | None:
    """Serializa a trilha mínima reproduzível dos chunks, sem o conteúdo.

    IDs e ordem permitem reconstruir o contexto no banco; score e versão
    distinguem mudanças de retrieval/documento. Nenhum trecho ou PII é gravado.
    """
    if not fontes:
        return None
    linhas = []
    for rank, f in enumerate(fontes[:20], start=1):
        titulo = (f.get("titulo") or "?")[:150]
        categoria = f.get("categoria") or ""
        partes = [f"rank={rank}", f"chunk={f.get('chunk_id') or '?'}",
                  f"doc={f.get('doc_id') or '?'}"]
        if f.get("versao") is not None:
            partes.append(f"versao={f['versao']}")
        if f.get("score") is not None:
            partes.append(f"score={f['score']}")
        if f.get("rerank_score") is not None:
            partes.append(f"rerank={f['rerank_score']}")
        partes.append(f"titulo={titulo}")
        if categoria:
            partes.append(f"categoria={categoria}")
        linhas.append("|".join(str(p) for p in partes))
    return "; ".join(linhas)[:2000]


async def registrar(
    db,
    *,
    user,
    tarefa: TarefaIA,
    case_id: str | None,
    prompt_sanitizado: str,
    pii_removida: bool,
    resposta: str | None,
    modelo: str,
    fontes: list[dict] | None = None,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    custo_estimado=None,
) -> str | None:
    """
    Grava o AILog da interação. Sem db/user (chamada interna sem sessão) não há
    como auditar → retorna None e o CHAMADOR decide se aceita operar sem log
    (o orchestrator NÃO aceita quando há db+user disponíveis).
    """
    if db is None or user is None:
        return None
    from app.services.ai_guard import registrar_ai_log
    return await registrar_ai_log(
        db,
        user_id=str(user.id),
        tipo_uso=_tipo_uso(tarefa, prompt_sanitizado),
        case_id=case_id,
        prompt_sanitizado=prompt_sanitizado,
        pii_removida=pii_removida,
        resposta=resposta,
        modelo=modelo,
        fontes_rag=_fontes_str(fontes),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        custo_estimado=custo_estimado,
    )