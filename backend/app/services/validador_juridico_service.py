# app/services/validador_juridico_service.py
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
from app.services.ai_gateway import chat
from app.services.ai_service import buscar_contexto_rag
from app.services.sanitizer import sanitizar_pii, validar_sem_pii

AVISO_VALIDACAO = (
    "VALIDACAO JURIDICA AUTOMATICA: relatorio interno de controle. "
    "Nao substitui revisao do advogado responsavel e nao confirma jurisprudencia sem fonte oficial."
)

SYSTEM_PROMPT = """
Voce e um auditor juridico interno do escritorio De Paula Teixeira Advogados Associados.
Sua funcao e validar um rascunho juridico antes de virar peca final.

Regras absolutas:
1. Nao invente lei, sumula, jurisprudencia, acordao, relator, data ou fonte.
2. Se uma citacao nao puder ser confirmada pelo texto ou pelas fontes RAG fornecidas, marque como PENDENTE DE VERIFICACAO.
3. Separe: fonte confirmada, fonte ausente, artigo possivelmente incorreto, tese sem prova, lacuna documental e decisao humana pendente.
4. Nao aprove a peca para protocolo; a conclusao deve ser APTO PARA REVISAO, REVISAR ANTES DE USAR ou BLOQUEAR ATE CORRIGIR.
5. Use linguagem juridica objetiva, sem caracteres decorativos, sem promessa de resultado.
""".strip()

USER_TEMPLATE = """
TIPO DE DOCUMENTO: {tipo_documento}
AREA: {area}
RITO: {rito}
FASE: {fase}

METRICAS AUTOMATICAS:
{metricas}

FONTES RAG RECUPERADAS:
{fontes}

RASCUNHO SANITIZADO:
{rascunho}

DOCUMENTOS/PROVAS INFORMADOS:
{documentos}

TAREFA:
Produza RELATORIO DE VALIDACAO JURIDICA com estas secoes:

1. VEREDITO OPERACIONAL
- Status: APTO PARA REVISAO / REVISAR ANTES DE USAR / BLOQUEAR ATE CORRIGIR
- Score de confianca: 0 a 100
- Motivos objetivos do score

2. FONTES NORMATIVAS
- Artigos e leis citados
- Itens com fonte suficiente
- Itens possivelmente incorretos ou incompletos
- Itens que exigem verificacao oficial

3. JURISPRUDENCIA E SUMULAS
- Citacoes encontradas
- Confirmadas pelas fontes fornecidas, se houver
- Pendentes de verificacao
- Sinais de risco de jurisprudencia inventada ou incompleta

4. PROVA E ONUS PROBATORIO
- Fatos sem prova indicada
- Teses que dependem de documento, testemunha, pericia ou outro suporte
- Lacunas documentais relevantes

5. RITO, PEDIDOS E COERENCIA
- Compatibilidade com rito informado
- Pedidos sem fundamento ou fundamento sem pedido
- Contradicoes internas e excesso argumentativo

6. RISCOS
- Criticos
- Elevados
- Medios
- Baixos

7. CHECKLIST PARA REVISAO HUMANA
- Providencias antes de usar
- Fontes oficiais a consultar
- Documentos a juntar ou conferir
- Decisao que depende do advogado responsavel

Finalize com: REVISAO HUMANA OBRIGATORIA antes de protocolo, envio ao cliente ou uso oficial.
""".strip()

_ARTIGO_RE = re.compile(
    r"\b(?:art\.?|artigo)\s*\d{1,4}(?:[-A-Zº°]*)?(?:\s*,?\s*(?:§|paragrafo)\s*\d+)?(?:\s*(?:do|da|de)\s*(?:CPC|CC|CDC|CLT|CPP|CP|CF|Lei\s*n?[ºo]?\s*\d+[\d./-]*))?",
    re.IGNORECASE,
)
_LEI_RE = re.compile(r"\bLei\s*n?[ºo]?\s*\d{1,5}[\d./-]*", re.IGNORECASE)
_JURIS_RE = re.compile(
    r"\b(?:STF|STJ|TST|TRT\s*\d*|TJ[A-Z]{2}|TJMG|REsp|AREsp|AgInt|AgRg|Apelacao|Apelação|Agravo|HC|MS|Tema\s*\d+|Sumula|Súmula)\b[^\n]{0,180}",
    re.IGNORECASE,
)
_NUM_PROC_RE = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b|\b\d{4,9}[-./]\d{2,4}\b")
_PROVA_RE = re.compile(r"\b(documento|contrato|nota fiscal|comprovante|email|e-mail|print|extrato|laudo|pericia|perícia|testemunha|prova|anexo)\b", re.IGNORECASE)
_PEDIDO_RE = re.compile(r"\b(requer|pede|pedido|condenacao|condenação|procedencia|procedência|improcedencia|improcedência|tutela|liminar)\b", re.IGNORECASE)


@dataclass
class ValidacaoInput:
    rascunho: str
    tipo_documento: str = "peca_juridica"
    area: str | None = None
    rito: str | None = None
    fase: str | None = None
    documentos: list[str] | None = None
    case_id: str | None = None
    nivel_inteligencia: str = "alto"


def _uniq(matches: list[str], limite: int = 20) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in matches:
        x = " ".join(m.strip().split())
        k = x.lower()
        if x and k not in seen:
            seen.add(k)
            out.append(x[:260])
        if len(out) >= limite:
            break
    return out


def _calcular_metricas(texto: str, documentos: list[str] | None) -> dict:
    artigos = _uniq(_ARTIGO_RE.findall(texto))
    leis = _uniq(_LEI_RE.findall(texto))
    jurisprudencia = _uniq(_JURIS_RE.findall(texto))
    provas = _uniq(_PROVA_RE.findall(texto))
    pedidos = _uniq(_PEDIDO_RE.findall(texto))
    jur_pendente = [j for j in jurisprudencia if not _NUM_PROC_RE.search(j) and "tema" not in j.lower() and "sum" not in j.lower()]

    score = 100
    if len(texto) < 1500:
        score -= 12
    if not artigos and not leis:
        score -= 22
    if not pedidos:
        score -= 14
    if not provas and not documentos:
        score -= 18
    if jur_pendente:
        score -= min(20, 6 * len(jur_pendente))
    if "verificar fonte" in texto.lower():
        score -= 8
    if "[dado nao informado]" in texto.lower() or "[verificar]" in texto.lower():
        score -= 10
    score = max(0, min(100, score))

    if score >= 78 and not jur_pendente:
        veredito = "APTO PARA REVISAO"
    elif score >= 55:
        veredito = "REVISAR ANTES DE USAR"
    else:
        veredito = "BLOQUEAR ATE CORRIGIR"

    return {
        "score_confianca": score,
        "veredito": veredito,
        "artigos_detectados": artigos,
        "leis_detectadas": leis,
        "jurisprudencia_detectada": jurisprudencia,
        "jurisprudencia_pendente_verificacao": jur_pendente,
        "indicadores_prova": provas,
        "indicadores_pedido": pedidos,
        "tem_documentos_informados": bool(documentos),
        "contagem_caracteres": len(texto),
    }


def _formatar_metricas(m: dict) -> str:
    linhas = [f"- {k}: {v}" for k, v in m.items()]
    return "\n".join(linhas)


def _formatar_fontes(fontes: list[dict]) -> str:
    if not fontes:
        return "[SEM FONTES RAG RECUPERADAS]"
    linhas: list[str] = []
    for i, f in enumerate(fontes, 1):
        linhas.append(
            f"[Fonte {i}] {f.get('titulo')} ({f.get('categoria')}) "
            f"{('- ' + f.get('fonte')) if f.get('fonte') else ''}\n{(f.get('conteudo') or '')[:900]}"
        )
    return "\n\n".join(linhas)


def _formatar_documentos(documentos: list[str] | None) -> str:
    if not documentos:
        return "[NAO INFORMADO]"
    return "\n".join(f"- {d}" for d in documentos if d)


async def validar_rascunho_juridico(payload: ValidacaoInput, db: AsyncSession, user_id: str) -> dict:
    if len((payload.rascunho or "").strip()) < 100:
        raise ValueError("Rascunho muito curto para validacao juridica")

    texto_limpo, houve_pii = sanitizar_pii(payload.rascunho)
    residual = validar_sem_pii(texto_limpo)
    if residual:
        raise ValueError(f"Dados pessoais residuais detectados: {', '.join(residual)}")

    metricas = _calcular_metricas(texto_limpo, payload.documentos)
    consulta = " ".join([
        payload.tipo_documento or "peca juridica",
        payload.area or "",
        payload.rito or "",
        " ".join(metricas.get("artigos_detectados") or [])[:500],
        texto_limpo[:800],
    ])
    fontes = await buscar_contexto_rag(db, consulta, limite=8, modo_or=True)

    user_prompt = USER_TEMPLATE.format(
        tipo_documento=payload.tipo_documento or "peca_juridica",
        area=payload.area or "[NAO INFORMADO]",
        rito=payload.rito or "[NAO INFORMADO]",
        fase=payload.fase or "[NAO INFORMADO]",
        metricas=_formatar_metricas(metricas),
        fontes=_formatar_fontes(fontes),
        rascunho=texto_limpo[:30000],
        documentos=_formatar_documentos(payload.documentos),
    )

    resp = await chat(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        task_type="auditoria_peca",
        temperature=0.05,
        max_tokens=3200,
        nivel_inteligencia=payload.nivel_inteligencia or "alto",
    )

    modelo_log = f"{resp.provedor}/{resp.modelo}"
    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        case_id=payload.case_id,
        tipo_uso=AITipoUso.outro,
        modelo=modelo_log,
        prompt_sanitizado=user_prompt[:8000],
        pii_removida=houve_pii,
        resposta=resp.texto,
        fontes_rag="; ".join(str(f.get("chunk_id")) for f in fontes if f.get("chunk_id")) or None,
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()

    return {
        "ai_log_id": log.id,
        "score_confianca": metricas["score_confianca"],
        "veredito": metricas["veredito"],
        "metricas": metricas,
        "fontes_usadas": len(fontes),
        "pii_removida": houve_pii,
        "modelo": resp.modelo,
        "provedor": resp.provedor,
        "resposta": resp.texto,
        "aviso": AVISO_VALIDACAO,
        "status_hitl": "gerado",
    }
