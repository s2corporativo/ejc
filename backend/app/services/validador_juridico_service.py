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


# ── Rubrica auditavel de controle de qualidade FORMAL ─────────────────────────
# NATUREZA: esta rubrica e um CONTROLE DE QUALIDADE FORMAL da peca (presenca de
# secoes obrigatorias, fontes citadas, pedidos, provas, ausencia de marcadores de
# lacuna). NAO e predicao de exito, procedencia ou probabilidade de vitoria.
#
# O score alimenta o GATE de protocolo (legal_docs.VALIDACAO_SCORE_MINIMO >= 75).
# TRAVA DE SEGURANCA INEGOCIAVEL: a rubrica NUNCA pode ser mais permissiva que a
# heuristica historica — so pode MANTER ou BAIXAR o score (mais estrito), jamais
# aumenta-lo. Os 7 criterios PONTUANTES abaixo reproduzem, com pesos rotulados,
# exatamente as deducoes da heuristica original: score = 100 - soma(deducoes),
# identico ao calculo anterior (prova em tests/test_validador_rubrica.py, que
# fixa o invariante score_rubrica <= score_heuristico_legado para toda entrada).
# Os criterios INFORMATIVOS (pontua=False, peso 0) apenas EXPOEM secoes
# obrigatorias ao HITL/UI sem alterar o gate; ativa-los como pontuantes so
# tornaria o gate MAIS estrito e e follow-up deliberado (decisao de produto).

NATUREZA_RUBRICA = (
    "Controle de qualidade FORMAL da peca (secoes obrigatorias, fontes, pedidos, "
    "provas). NAO e predicao de exito, procedencia ou probabilidade de vitoria."
)
RUBRICA_METODO = "rubrica_formal_v1"

_ENDERECAMENTO_RE = re.compile(
    r"\b(excelent[ií]ssim|merit[ií]ssim|mm\.?\s*ju[ií]z|ju[ií]zo\b|\bvara\b|comarca|"
    r"\bforo\b|ju[ií]zado|tribunal\s+de\s+justi|dirigid[ao]\s+ao?)\b",
    re.IGNORECASE,
)
_FATOS_RE = re.compile(
    r"\b(d[oa]s?\s+fatos|d[oa]\s+causa\s+de\s+pedir|s[íi]ntese\s+f[áa]tica|"
    r"breve\s+relat[óo]rio|narrativa\s+f[áa]tica)\b",
    re.IGNORECASE,
)
_VALOR_CAUSA_RE = re.compile(
    r"(valor\s+da\s+causa|d[áa]-se\s+[àa]\s+causa|d[áa]\s+[àa]\s+causa\s+o\s+valor|R\$\s*[\d.]+)",
    re.IGNORECASE,
)


def _criterio(criterio: str, rotulo: str, secao: str, peso: int, atendido: bool,
              deducao: int, observacao: str, *, pontua: bool = True) -> dict:
    """Um item auditavel da rubrica.

    - peso: peso NOMINAL documentado do criterio (constante).
    - deducao: pontos EFETIVAMENTE subtraidos de 100 neste documento (0 se atendido
      ou se o criterio for informativo).
    - pontua: False => criterio informativo, NAO altera o score/gate nesta versao.
    """
    return {
        "criterio": criterio,
        "rotulo": rotulo,
        "secao": secao,
        "peso": peso,
        "atendido": bool(atendido),
        "pontua": pontua,
        "deducao": deducao,
        "observacao": observacao,
    }


def _montar_rubrica(texto: str, documentos: list[str] | None, *, artigos: list[str],
                    leis: list[str], provas: list[str], pedidos: list[str],
                    jur_pendente: list[str]) -> list[dict]:
    """Rubrica formal por secao obrigatoria.

    Os 7 primeiros criterios PONTUAM e reproduzem exatamente as deducoes da
    heuristica historica. Os 3 ultimos sao INFORMATIVOS (pontua=False): cobrem
    secoes obrigatorias ainda sem detector pontuante, sem alterar o gate.
    """
    low = texto.lower()
    curto = len(texto) < 1500
    tem_fund = bool(artigos or leis)
    tem_prova_ou_doc = bool(provas) or bool(documentos)
    tem_verificar_fonte = "verificar fonte" in low
    tem_lacuna = "[dado nao informado]" in low or "[verificar]" in low
    ded_jur = min(20, 6 * len(jur_pendente)) if jur_pendente else 0

    return [
        # ── Criterios PONTUANTES (espelham a heuristica; score identico) ──────
        _criterio(
            "fatos_desenvolvimento", "Narrativa fatica e desenvolvimento minimos", "fatos",
            12, not curto, 12 if curto else 0,
            "Proxy por extensao: peca com menos de 1500 caracteres nao desenvolve os fatos."
            if curto else "Extensao compativel com desenvolvimento minimo dos fatos.",
        ),
        _criterio(
            "fundamentacao_legal_com_fonte", "Fundamentacao legal com artigos/leis citados",
            "fundamentacao_legal", 22, tem_fund, 22 if not tem_fund else 0,
            "Nenhum artigo ou lei citado — fundamentacao normativa ausente."
            if not tem_fund else f"Citados {len(artigos)} artigo(s) e {len(leis)} lei(s).",
        ),
        _criterio(
            "pedidos_explicitos", "Pedidos explicitos", "pedidos",
            14, bool(pedidos), 14 if not pedidos else 0,
            "Nenhum indicador de pedido detectado."
            if not pedidos else f"{len(pedidos)} indicador(es) de pedido detectado(s).",
        ),
        _criterio(
            "provas_ou_documentos", "Indicacao de provas ou documentos", "provas_documentos",
            18, tem_prova_ou_doc, 18 if not tem_prova_ou_doc else 0,
            "Sem indicacao de provas no texto nem documentos informados."
            if not tem_prova_ou_doc else "Provas indicadas no texto e/ou documentos informados.",
        ),
        _criterio(
            "citacoes_sem_pendencia", "Citacoes de jurisprudencia sem pendencia de verificacao",
            "citacoes_validadas", 20, not jur_pendente, ded_jur,
            f"{len(jur_pendente)} citacao(oes) sem numero CNJ/Tema/Sumula — pendente(s) de verificacao oficial."
            if jur_pendente else "Sem citacoes de jurisprudencia pendentes de verificacao.",
        ),
        _criterio(
            "sem_marcador_verificar_fonte", "Ausencia de marcador 'verificar fonte'",
            "marcadores_qualidade", 8, not tem_verificar_fonte, 8 if tem_verificar_fonte else 0,
            "Texto contem marcador 'verificar fonte' — fonte nao confirmada."
            if tem_verificar_fonte else "Sem marcador 'verificar fonte'.",
        ),
        _criterio(
            "sem_marcador_lacuna", "Ausencia de marcadores de lacuna ([verificar]/[dado nao informado])",
            "marcadores_qualidade", 10, not tem_lacuna, 10 if tem_lacuna else 0,
            "Texto contem marcador de lacuna a preencher antes do uso."
            if tem_lacuna else "Sem marcadores de lacuna.",
        ),
        # ── Criterios INFORMATIVOS (pontua=False: nao alteram o gate — follow-up) ─
        _criterio(
            "enderecamento_competencia", "Enderecamento/competencia identificados",
            "enderecamento_competencia", 0, bool(_ENDERECAMENTO_RE.search(texto)), 0,
            "Nao localizado enderecamento/juizo/competencia — conferir cabecalho."
            if not _ENDERECAMENTO_RE.search(texto)
            else "Enderecamento/competencia localizados no texto.",
            pontua=False,
        ),
        _criterio(
            "narrativa_fatica_explicita", "Secao explicita de fatos/causa de pedir", "fatos",
            0, bool(_FATOS_RE.search(texto)), 0,
            "Nao localizada secao explicita 'Dos Fatos'/'Causa de pedir'."
            if not _FATOS_RE.search(texto) else "Secao de fatos/causa de pedir localizada.",
            pontua=False,
        ),
        _criterio(
            "valor_da_causa", "Valor da causa informado (quando aplicavel)", "valor_causa",
            0, bool(_VALOR_CAUSA_RE.search(texto)), 0,
            "Valor da causa nao localizado — obrigatorio quando aplicavel (conferir rito)."
            if not _VALOR_CAUSA_RE.search(texto) else "Valor da causa/pedido economico localizado.",
            pontua=False,
        ),
    ]


def _calcular_metricas(texto: str, documentos: list[str] | None) -> dict:
    artigos = _uniq(_ARTIGO_RE.findall(texto))
    leis = _uniq(_LEI_RE.findall(texto))
    jurisprudencia = _uniq(_JURIS_RE.findall(texto))
    provas = _uniq(_PROVA_RE.findall(texto))
    pedidos = _uniq(_PEDIDO_RE.findall(texto))
    jur_pendente = [j for j in jurisprudencia if not _NUM_PROC_RE.search(j) and "tema" not in j.lower() and "sum" not in j.lower()]

    rubrica = _montar_rubrica(
        texto, documentos, artigos=artigos, leis=leis, provas=provas,
        pedidos=pedidos, jur_pendente=jur_pendente,
    )
    # Score = 100 menos as deducoes dos criterios PONTUANTES. Reproduz, de forma
    # rotulada e auditavel, exatamente a heuristica anterior (invariante <= no teste).
    deducao_total = sum(c["deducao"] for c in rubrica if c["pontua"])
    score = max(0, min(100, 100 - deducao_total))

    if score >= 78 and not jur_pendente:
        veredito = "APTO PARA REVISAO"
    elif score >= 55:
        veredito = "REVISAR ANTES DE USAR"
    else:
        veredito = "BLOQUEAR ATE CORRIGIR"

    return {
        # score_confianca PERMANECE a 1a chave: o gate (legal_docs._parse_score)
        # le o 1o "score_confianca: NN" do prompt formatado. Nao reordenar.
        "score_confianca": score,
        "veredito": veredito,
        "score_base": 100,
        "score_metodo": RUBRICA_METODO,
        "natureza": NATUREZA_RUBRICA,
        "rubrica": rubrica,
        "criterios_reprovados": [c["criterio"] for c in rubrica if c["pontua"] and not c["atendido"]],
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
    """Renderiza as metricas para o prompt do auditor.

    Preserva o contrato do GATE: a 1a linha "score_confianca: NN" e a linha
    "veredito: ..." continuam parseaveis por legal_docs._parse_score/_parse_veredito.
    A rubrica e renderizada em bloco proprio (nao emite outro "score_confianca:").
    """
    linhas: list[str] = []
    for k, v in m.items():
        if k == "rubrica":
            continue
        linhas.append(f"- {k}: {v}")
    rubrica = m.get("rubrica") or []
    if rubrica:
        linhas.append("- rubrica_formal (controle de qualidade FORMAL, nao predicao de exito):")
        for c in rubrica:
            marca = "OK" if c["atendido"] else "FALHA"
            tag = "" if c["pontua"] else " [informativo]"
            linhas.append(
                f"    [{marca}] {c['secao']} :: {c['rotulo']} "
                f"(peso {c['peso']}, deducao {c['deducao']}){tag} — {c['observacao']}"
            )
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


async def validar_rascunho_juridico(
    payload: ValidacaoInput, db: AsyncSession, user_id: str,
    scope_client_id: str | None = None,
) -> dict:
    """scope_client_id (Bloco 5): o CHAMADOR já verifica ownership do
    payload.case_id e deriva o escopo antes de chegar aqui."""
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
    fontes = await buscar_contexto_rag(db, consulta, limite=8, modo_or=True, scope_client_id=scope_client_id)

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
