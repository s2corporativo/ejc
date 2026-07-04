"""
Pipeline de geração de peças jurídicas em 7 etapas com SSE streaming.
Cada etapa emite um evento SSE com status e resultado parcial.
"""
from __future__ import annotations

import json
import logging
import unicodedata
from collections.abc import AsyncGenerator
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
from app.models.legal_doc import LegalDoc, PecaTipo
from app.services.ai_gateway import chat as gw_chat
from app.services.ai_service import buscar_contexto_rag
from app.services.estilo_service import instrucao_estilo
from app.services.document_format import aviso_rascunho_ia, padronizar_documento_juridico
from app.services.sanitizer import sanitizar_pii

TIPOS_PECA = {
    "auto": "Identificar automaticamente",
    "peticao_inicial": "Petição Inicial",
    "contestacao": "Contestação",
    "recurso_ordinario": "Recurso Ordinário",
    "agravo": "Agravo",
    "agravo_de_instrumento": "Agravo de Instrumento",
    "apelacao": "Apelação",
    "contrarrazoes": "Contrarrazões",
    "replica": "Réplica (Impugnação à Contestação)",
    "memorias": "Memoriais",
    "acordo": "Proposta de Acordo",
    "parecer": "Parecer Jurídico",
    "notificacao": "Notificação Extrajudicial",
    "contrato": "Minuta de Contrato",
    "impugnacao": "Impugnação",
}

TIPOS_PECA_VALIDOS = [k for k in TIPOS_PECA if k != "auto"]

AREAS_DIREITO = [
    "trabalhista", "civil", "previdenciario", "tributario",
    "criminal", "consumidor", "administrativo", "familia",
]

TIPO_PECA_LEGAL_DOC = {
    "peticao_inicial": PecaTipo.peticao_inicial,
    "contestacao": PecaTipo.contestacao,
    "recurso_ordinario": PecaTipo.recurso,
    "agravo": PecaTipo.recurso,
    "agravo_de_instrumento": PecaTipo.recurso,
    "apelacao": PecaTipo.recurso,
    "contrarrazoes": PecaTipo.contrarrazoes,
    "replica": PecaTipo.outro,
    "memorias": PecaTipo.outro,
    "acordo": PecaTipo.contrato,
    "parecer": PecaTipo.parecer,
    "notificacao": PecaTipo.notificacao_extrajudicial,
    "contrato": PecaTipo.contrato,
    "impugnacao": PecaTipo.recurso,
}

TIPOS_PECA_ALIASES = {
    "peticao inicial": "peticao_inicial",
    "peticao": "peticao_inicial",
    "inicial": "peticao_inicial",
    "contestacao": "contestacao",
    "defesa": "contestacao",
    "recurso ordinario": "recurso_ordinario",
    "agravo de instrumento": "agravo_de_instrumento",
    # "agravo" segue aceito como tipo direto (compat frontend), mas na
    # identificação automática resolve para o tipo canônico completo.
    "agravo": "agravo_de_instrumento",
    "apelacao": "apelacao",
    "recurso de apelacao": "apelacao",
    "razoes de apelacao": "apelacao",
    "contrarrazoes": "contrarrazoes",
    "contrarrazoes de apelacao": "contrarrazoes",
    "contrarrazoes de recurso": "contrarrazoes",
    "contra-razoes": "contrarrazoes",
    "replica": "replica",
    "replica a contestacao": "replica",
    "impugnacao a contestacao": "replica",
    "memoriais": "memorias",
    "memorias": "memorias",
    "acordo": "acordo",
    "proposta de acordo": "acordo",
    "parecer": "parecer",
    "parecer juridico": "parecer",
    "notificacao": "notificacao",
    "notificacao extrajudicial": "notificacao",
    "contrato": "contrato",
    "minuta de contrato": "contrato",
    "impugnacao": "impugnacao",
}

# ── Presets por rito: instruções específicas injetadas na etapa de redação ──
# Cada perfil orienta estrutura obrigatória, prazo típico e campos que o
# advogado deve preencher/conferir antes de protocolar.
PERFIS_PECA: dict[str, str] = {
    "peticao_inicial": (
        "PERFIL DA PEÇA — PETIÇÃO INICIAL (art. 319 CPC):\n"
        "Atenda a TODOS os requisitos do art. 319 do CPC: I) juízo a que é dirigida; "
        "II) qualificação completa das partes (nomes, prenomes, estado civil, união estável, "
        "profissão, CPF/CNPJ, e-mail, domicílio); III) fatos e fundamentos jurídicos do pedido; "
        "IV) pedido com suas especificações; V) valor da causa; VI) provas que pretende produzir; "
        "VII) opção pela audiência de conciliação/mediação (art. 334). "
        "Verifique também requerimento de justiça gratuita e tutela provisória, se cabíveis.\n"
        "PRAZO TÍPICO: peça inaugural — observar prescrição/decadência da pretensão.\n"
        "CAMPOS A PREENCHER PELO ADVOGADO: [JUÍZO/VARA/COMARCA], [QUALIFICAÇÃO COMPLETA DAS PARTES], "
        "[VALOR DA CAUSA], [ROL DE PROVAS/DOCUMENTOS ANEXOS], [OPÇÃO POR AUDIÊNCIA DE CONCILIAÇÃO]."
    ),
    "contestacao": (
        "PERFIL DA PEÇA — CONTESTAÇÃO (arts. 335-342 CPC):\n"
        "Estruture em: 1) PRELIMINARES do art. 337 do CPC (incompetência, inépcia, perempção, "
        "litispendência, coisa julgada, conexão, incapacidade/irregularidade de representação, "
        "convenção de arbitragem, ausência de legitimidade ou interesse, falta de caução, "
        "incorreção do valor da causa, indevida gratuidade); 2) MÉRITO com IMPUGNAÇÃO ESPECIFICADA "
        "de cada fato alegado na inicial (art. 341 CPC — ônus da impugnação especificada; fato não "
        "impugnado presume-se verdadeiro); 3) eventual reconvenção (art. 343) e provas.\n"
        "PRAZO TÍPICO: 15 dias úteis (art. 335 CPC).\n"
        "CAMPOS A PREENCHER PELO ADVOGADO: [NÚMERO DO PROCESSO], [JUÍZO], [QUALIFICAÇÃO DO RÉU], "
        "[FATOS DA INICIAL A IMPUGNAR PONTO A PONTO], [DOCUMENTOS/PROVAS DA DEFESA]."
    ),
    "replica": (
        "PERFIL DA PEÇA — RÉPLICA / IMPUGNAÇÃO À CONTESTAÇÃO (arts. 350-351 CPC):\n"
        "Impugne a contestação PONTO A PONTO: 1) rebata cada preliminar do art. 337 suscitada; "
        "2) impugne cada fato impeditivo, modificativo ou extintivo alegado pelo réu (art. 350); "
        "3) reafirme os fatos e fundamentos da inicial atingidos pela defesa; 4) manifeste-se sobre "
        "documentos juntados com a contestação (art. 437, §1º); 5) ratifique pedidos e provas.\n"
        "PRAZO TÍPICO: 15 dias úteis (arts. 350-351 CPC), contados da intimação.\n"
        "CAMPOS A PREENCHER PELO ADVOGADO: [NÚMERO DO PROCESSO], [PRELIMINARES ARGUIDAS NA "
        "CONTESTAÇÃO], [FATOS NOVOS/DEFESAS INDIRETAS A REBATER], [DOCUMENTOS DA DEFESA A IMPUGNAR]."
    ),
    "contrarrazoes": (
        "PERFIL DA PEÇA — CONTRARRAZÕES DE RECURSO (art. 1.010, §1º CPC):\n"
        "Responda DIRETAMENTE aos fundamentos do recurso adversário: 1) PRELIMINARMENTE, aponte "
        "óbices de admissibilidade do recurso (intempestividade, deserção, ausência de dialeticidade, "
        "inovação recursal, súmulas impeditivas); 2) NO MÉRITO, rebata cada fundamento recursal na "
        "ordem em que deduzido, defendendo a manutenção da decisão recorrida; 3) requeira o "
        "desprovimento do recurso e a majoração de honorários (art. 85, §11 CPC).\n"
        "PRAZO TÍPICO: 15 dias úteis (art. 1.010, §1º CPC).\n"
        "CAMPOS A PREENCHER PELO ADVOGADO: [NÚMERO DO PROCESSO/RECURSO], [DECISÃO RECORRIDA], "
        "[FUNDAMENTOS DO RECURSO A REBATER UM A UM], [ÓBICES DE ADMISSIBILIDADE IDENTIFICADOS]."
    ),
    "apelacao": (
        "PERFIL DA PEÇA — APELAÇÃO (arts. 1.009-1.014 CPC):\n"
        "Estruture em: 1) PRELIMINARES (nulidades da sentença/processo, cerceamento de defesa, "
        "error in procedendo; questões resolvidas na fase de conhecimento não sujeitas a agravo — "
        "art. 1.009, §1º); 2) MÉRITO (error in judicando: reexame de fatos, provas e teses, com "
        "dialeticidade — impugnação específica dos fundamentos da sentença, art. 1.010, II-III); "
        "3) PREQUESTIONAMENTO explícito dos dispositivos legais e constitucionais violados, para "
        "viabilizar REsp/RE (art. 1.025 CPC); 4) pedido de reforma/anulação e efeito suspensivo "
        "quando cabível (art. 1.012).\n"
        "PRAZO TÍPICO: 15 dias úteis (art. 1.003, §5º CPC).\n"
        "CAMPOS A PREENCHER PELO ADVOGADO: [NÚMERO DO PROCESSO], [SENTENÇA RECORRIDA E SEUS "
        "FUNDAMENTOS], [DISPOSITIVOS A PREQUESTIONAR], [VALOR DO PREPARO/GUIA]."
    ),
    "agravo_de_instrumento": (
        "PERFIL DA PEÇA — AGRAVO DE INSTRUMENTO (arts. 1.015-1.020 CPC):\n"
        "Estruture em: 1) CABIMENTO — demonstre que a decisão interlocutória se enquadra nas "
        "hipóteses do art. 1.015 do CPC (tutelas provisórias, mérito parcial, gratuidade, "
        "distribuição do ônus da prova etc.) ou na taxatividade mitigada (Tema 988/STJ — urgência "
        "decorrente da inutilidade do julgamento diferido); 2) REQUISITOS FORMAIS dos arts. "
        "1.016-1.018: qualificação das partes, exposição do fato e do direito, razões do pedido de "
        "reforma/invalidação, nome e endereço dos advogados, peças obrigatórias (art. 1.017: cópias "
        "da decisão agravada, certidão de intimação e procurações — dispensadas em autos "
        "eletrônicos), comprovante de preparo e comunicação ao juízo de origem (art. 1.018); "
        "3) EFEITO SUSPENSIVO ou tutela antecipada recursal (art. 1.019, I): demonstre probabilidade "
        "de provimento e risco de dano grave ou de difícil reparação.\n"
        "PRAZO TÍPICO: 15 dias úteis (art. 1.003, §5º CPC).\n"
        "CAMPOS A PREENCHER PELO ADVOGADO: [NÚMERO DO PROCESSO DE ORIGEM], [DECISÃO AGRAVADA E "
        "HIPÓTESE DO ART. 1.015], [PEÇAS OBRIGATÓRIAS DO ART. 1.017], [COMPROVANTE DE PREPARO], "
        "[FUNDAMENTOS DO EFEITO SUSPENSIVO]."
    ),
}
# "agravo" (tipo legado mantido por compatibilidade) usa o mesmo perfil.
PERFIS_PECA["agravo"] = PERFIS_PECA["agravo_de_instrumento"]


def _tipo_identificado(texto: str) -> str | None:
    """Extrai e normaliza o tipo de peca sugerido pela etapa 1."""
    candidatos: list[str] = []
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio != -1 and fim != -1 and fim > inicio:
        try:
            dados = json.loads(texto[inicio:fim + 1])
            valor = dados.get("tipo_confirmado") or dados.get("tipo") or dados.get("tipo_peca")
            if isinstance(valor, str):
                candidatos.append(valor)
        except json.JSONDecodeError:
            pass

    candidatos.append(texto[:300])
    for candidato in candidatos:
        normalizado = unicodedata.normalize("NFKD", candidato.strip().lower().replace("_", " "))
        normalizado = "".join(c for c in normalizado if not unicodedata.combining(c))
        if normalizado in TIPOS_PECA_ALIASES:
            return TIPOS_PECA_ALIASES[normalizado]
        # Substring: testa termos mais longos primeiro para que
        # "contrarrazoes de apelacao" não caia em "apelacao", etc.
        for chave in sorted(TIPOS_PECA_VALIDOS, key=len, reverse=True):
            if chave.replace("_", " ") in normalizado:
                return chave
        for alias in sorted(TIPOS_PECA_ALIASES, key=len, reverse=True):
            if alias in normalizado:
                return TIPOS_PECA_ALIASES[alias]
    return None


async def _emit(event: str, data: dict) -> str:
    """Formata um evento SSE."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def gerar_peca_pipeline(
    db: AsyncSession,
    user_id: str,
    tipo_peca: str,
    area_direito: str,
    descricao_fatos: str,
    pedidos: str,
    nomes_proteger: list[str],
    case_id: str | None,
    instrucoes_adicionais: str | None,
    scope_client_id: str | None = None,
    usar_estilo: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Pipeline SSE de 7 etapas para geração de peça jurídica.
    Yields SSE strings para StreamingResponse.

    scope_client_id (Bloco 5): o CHAMADOR (routers/peca_geracao.py) já verifica
    ownership do case_id e deriva o escopo — esta função não tem acesso ao
    usuário autenticado para checar isso sozinha.
    """

    async def step(num: int, titulo: str, status: str = "iniciando") -> None:
        yield await _emit("step", {"etapa": num, "titulo": titulo, "status": status})

    # Sanitiza entrada (LGPD)
    fatos_limpos, houve_pii_fatos = sanitizar_pii(descricao_fatos, nomes_proteger)
    pedidos_limpos, houve_pii_pedidos = sanitizar_pii(pedidos, nomes_proteger)
    houve_pii = houve_pii_fatos or houve_pii_pedidos
    auto_tipo = tipo_peca == "auto"
    tipo_peca_final = tipo_peca
    nome_peca = "Peca juridica a identificar" if auto_tipo else TIPOS_PECA.get(tipo_peca, tipo_peca)

    yield await _emit("inicio", {
        "pipeline_id": str(uuid4()),
        "tipo_peca": nome_peca,
        "area": area_direito,
        "etapas_total": 7,
        "aviso": aviso_rascunho_ia(),
    })

    # ── ETAPA 1: Identificar tipo de peça ──────────────────────────────────
    yield await _emit("step", {"etapa": 1, "titulo": "Identificando tipo de peça", "status": "em_andamento"})
    instrucao_tipo = (
        "Identifique automaticamente o tipo de peca mais adequado entre: "
        + ", ".join(TIPOS_PECA_VALIDOS)
        if auto_tipo else f"Tipo solicitado: {nome_peca}"
    )

    r1 = await gw_chat(
        messages=[
            {"role": "system", "content": (
                "Você é especialista em direito processual. Analise os fatos e confirme "
                "o tipo de peça mais adequado, identificando o rito processual, "
                "competência e requisitos formais obrigatórios."
            )},
            {"role": "user", "content": (
                f"{instrucao_tipo}\n"
                f"Área: {area_direito}\n"
                f"Fatos: {fatos_limpos[:1500]}\n\n"
                "Confirme o tipo de peça, rito processual, competência e requisitos formais. "
                "Responda em JSON: {\"tipo_confirmado\": ..., \"rito\": ..., \"competencia\": ..., \"requisitos\": [...]}. "
                "Quando estiver em identificacao automatica, tipo_confirmado deve usar uma das chaves permitidas."
            )},
        ],
        task_type="analise_juridica",
        temperature=0.1,
        max_tokens=600,
    )
    if auto_tipo:
        tipo_detectado = _tipo_identificado(r1.texto)
        if tipo_detectado:
            tipo_peca_final = tipo_detectado
            nome_peca = TIPOS_PECA[tipo_detectado]
        else:
            tipo_peca_final = "outro"
            nome_peca = "Peca juridica"
    yield await _emit("step", {
        "etapa": 1,
        "titulo": "Tipo de peça identificado",
        "status": "concluido",
        "tipo_identificado": tipo_peca_final,
        "resultado": r1.texto[:500],
    })

    # ── ETAPA 2: Estruturar enquadramento jurídico ──────────────────────────
    yield await _emit("step", {"etapa": 2, "titulo": "Estruturando enquadramento jurídico", "status": "em_andamento"})

    r2 = await gw_chat(
        messages=[
            {"role": "system", "content": (
                "Você é especialista em direito " + area_direito + ". "
                "Estruture o enquadramento jurídico completo: fundamentos legais, "
                "elementos constitutivos, pressupostos processuais e condições da ação."
            )},
            {"role": "user", "content": (
                f"Peça: {nome_peca}\nFatos: {fatos_limpos[:2000]}\nPedidos: {pedidos_limpos[:500]}\n\n"
                "Liste: 1) artigos de lei aplicáveis, 2) elementos fáticos que preenchem cada requisito, "
                "3) pressupostos processuais atendidos, 4) condições da ação."
            )},
        ],
        task_type="analise_juridica",
        temperature=0.15,
        max_tokens=1000,
    )
    yield await _emit("step", {"etapa": 2, "titulo": "Enquadramento jurídico estruturado", "status": "concluido", "resultado": r2.texto[:500]})

    # ── ETAPA 3: Buscar fundamentos legais (RAG) ───────────────────────────
    yield await _emit("step", {"etapa": 3, "titulo": "Buscando fundamentos legais", "status": "em_andamento"})

    query_rag = f"{area_direito} {tipo_peca_final} {fatos_limpos[:200]}"
    fontes = await buscar_contexto_rag(db, query_rag, limite=6, scope_client_id=scope_client_id)
    rag_txt = ""
    if fontes:
        linhas = [
            f"[Fonte {i+1}] {f['titulo']} ({f['categoria']})\n{f['conteudo'][:600]}"
            for i, f in enumerate(fontes)
        ]
        rag_txt = "\n\n[LEGISLAÇÃO E DOUTRINA ENCONTRADAS]\n" + "\n\n".join(linhas)

    yield await _emit("step", {
        "etapa": 3,
        "titulo": "Fundamentos legais encontrados",
        "status": "concluido",
        "fontes_encontradas": len(fontes),
        "resultado": f"{len(fontes)} fontes no acervo RAG",
    })

    # ── ETAPA 4: Analisar jurisprudência ──────────────────────────────────
    yield await _emit("step", {"etapa": 4, "titulo": "Analisando jurisprudência", "status": "em_andamento"})

    r4 = await gw_chat(
        messages=[
            {"role": "system", "content": (
                "Você é pesquisador de jurisprudência. Baseado EXCLUSIVAMENTE nas fontes RAG "
                "fornecidas, identifique precedentes aplicáveis. "
                "NUNCA invente julgados. Se não houver, diga explicitamente."
            )},
            {"role": "user", "content": (
                f"Fatos: {fatos_limpos[:1000]}\nPedidos: {pedidos_limpos[:300]}\n"
                f"{rag_txt[:3000] if rag_txt else 'Sem fontes RAG disponíveis.'}\n\n"
                "Identifique jurisprudência e doutrina aplicáveis apenas das fontes acima. "
                "Formato: tribunal, número/ementa, aplicabilidade ao caso."
            )},
        ],
        task_type="analise_juridica",
        temperature=0.1,
        max_tokens=1200,
    )
    yield await _emit("step", {"etapa": 4, "titulo": "Jurisprudência analisada", "status": "concluido", "resultado": r4.texto[:500]})

    # ── ETAPA 5: Organizar argumentos ─────────────────────────────────────
    yield await _emit("step", {"etapa": 5, "titulo": "Organizando argumentos", "status": "em_andamento"})

    r5 = await gw_chat(
        messages=[
            {"role": "system", "content": (
                "Você é advogado sênior. Organize os argumentos jurídicos em ordem de força "
                "e impacto: primários (mais sólidos), secundários (subsidiários) e "
                "contingenciais (para casos de rejeição dos anteriores)."
            )},
            {"role": "user", "content": (
                f"Peça: {nome_peca} | Área: {area_direito}\n"
                f"Fatos: {fatos_limpos[:1500]}\n"
                f"Pedidos: {pedidos_limpos[:500]}\n"
                f"Enquadramento jurídico:\n{r2.texto[:1000]}\n"
                f"Jurisprudência:\n{r4.texto[:800]}\n\n"
                "Organize os argumentos em 3 níveis: primários, secundários e contingenciais. "
                "Para cada argumento: fundamento legal + fato que o sustenta + força probatória."
            )},
        ],
        task_type="analise_juridica",
        temperature=0.2,
        max_tokens=1500,
    )
    yield await _emit("step", {"etapa": 5, "titulo": "Argumentos organizados", "status": "concluido", "resultado": r5.texto[:500]})

    # ── ETAPA 6: Apontar riscos ────────────────────────────────────────────
    yield await _emit("step", {"etapa": 6, "titulo": "Identificando riscos processuais", "status": "em_andamento"})

    r6 = await gw_chat(
        messages=[
            {"role": "system", "content": (
                "Você é advogado crítico especializado em gestão de riscos processuais. "
                "Identifique os riscos que o advogado deve conhecer antes de protocolar."
            )},
            {"role": "user", "content": (
                f"Peça: {nome_peca} | Fatos: {fatos_limpos[:1000]}\n"
                f"Argumentos: {r5.texto[:800]}\n\n"
                "Aponte: 1) Riscos de extinção sem julgamento do mérito, "
                "2) Argumentos contrários previsíveis, "
                "3) Provas ausentes que enfraquecem a tese, "
                "4) Prescrição/decadência verificada, "
                "5) Risco de condenação em litigância de má-fé. "
                "Classifique cada risco: ALTO/MÉDIO/BAIXO."
            )},
        ],
        task_type="analise_juridica",
        temperature=0.2,
        max_tokens=1000,
    )
    yield await _emit("step", {"etapa": 6, "titulo": "Riscos identificados", "status": "concluido", "resultado": r6.texto[:500]})

    # ── ETAPA 7: Montar documento completo ────────────────────────────────
    yield await _emit("step", {"etapa": 7, "titulo": "Montando documento completo", "status": "em_andamento"})

    # Busca contexto adicional do caso se disponível para fundamentação real
    contexto_caso = ""
    if case_id:
        from app.models.case import Case
        from sqlalchemy import select
        c_obj = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
        if c_obj:
            contexto_caso = f"\n[CONTEXTO DO CASO]\nTítulo: {c_obj.titulo}\nTese Principal: {c_obj.tese_principal or 'N/A'}\n"

    instrucoes = instrucoes_adicionais or ""
    perfil_peca = PERFIS_PECA.get(tipo_peca_final, "")
    bloco_perfil = f"{perfil_peca}\n\n" if perfil_peca else ""

    # Aprendizado de Estilo (opcional e ortogonal): injeta o estilo de redação
    # do advogado logado APENAS quando a request pediu (usar_estilo) E o advogado
    # tem perfil ativo. Preserva 100% do comportamento atual quando ausente.
    bloco_estilo = ""
    if usar_estilo:
        # Estilo é secundário/opt-in: uma falha transitória ao lê-lo não pode
        # derrubar a geração da peça — degrada para "sem estilo".
        try:
            instr_estilo = await instrucao_estilo(db, user_id)
            if instr_estilo:
                bloco_estilo = "\n\n" + instr_estilo
        except Exception as e:
            logger.warning(f"[peca] estilo do advogado ignorado (falha ao ler): {e}")
    r7 = await gw_chat(
        messages=[
            {"role": "system", "content": (
                f"Você é advogado sênior redator de peças jurídicas em português jurídico brasileiro formal. "
                f"Redija uma {nome_peca} completa, estruturada, fundamentada e persuasiva. "
                "REGRAS INVIOLÁVEIS:\n"
                "1. Baseie-se EXCLUSIVAMENTE nos fatos e jurisprudência fornecidos no RAG.\n"
                "2. Nunca invente números de processos ou links oficiais.\n"
                "3. Toda saída é RASCUNHO — revisão humana obrigatória (OAB).\n"
                "4. Use formatação jurídica padrão (Dos Fatos, Do Direito, Dos Pedidos)."
                f"{bloco_estilo}"
            )},
            {"role": "user", "content": (
                f"TIPO: {nome_peca}\nÁREA: {area_direito}\n\n"
                f"{bloco_perfil}"
                f"FATOS:\n{fatos_limpos}\n\n"
                f"PEDIDOS:\n{pedidos_limpos}\n\n"
                f"{contexto_caso}"
                f"ENQUADRAMENTO JURÍDICO:\n{r2.texto[:1500]}\n\n"
                f"JURISPRUDÊNCIA (RAG):\n{r4.texto[:1000]}\n\n"
                f"ARGUMENTOS ORGANIZADOS:\n{r5.texto[:1500]}\n\n"
                f"RISCOS (para evitar na peça):\n{r6.texto[:800]}\n\n"
                f"{rag_txt[:2000] if rag_txt else ''}\n"
                f"{'INSTRUÇÕES ADICIONAIS: ' + instrucoes if instrucoes else ''}\n\n"
                f"Redija a {nome_peca} completa com todos os elementos formais obrigatórios."
            )},
        ],
        task_type="elaboracao_peca",
        temperature=0.3,
        max_tokens=4000,
    )
    yield await _emit("step", {"etapa": 7, "titulo": "Documento montado", "status": "concluido"})
    documento_final = padronizar_documento_juridico(r7.texto)

    # A3 (auditoria 2026-06-30): verifica as citações (súmulas/artigos) contra a
    # base oficial e anexa o relatório — anti-alucinação (regra absoluta OAB).
    # Fail-safe: falha na verificação não impede a entrega da minuta.
    verificacao_citacoes = None
    try:
        from app.services.citation_check import verificar_citacoes
        verificacao_citacoes = await verificar_citacoes(db, documento_final)
        yield await _emit("step", {
            "etapa": 8, "titulo": "Verificando citações na base oficial",
            "status": "concluido",
            "resultado": (
                f"{verificacao_citacoes['confirmadas']}/{verificacao_citacoes['total']} "
                "citações confirmadas"
                if verificacao_citacoes.get("total") else "sem citações a verificar"
            ),
        })
    except Exception as _e:
        import logging as _lg
        _lg.getLogger(__name__).warning("citation_check falhou: %s", _e)

    # ── Registra no AILog (HITL) ───────────────────────────────────────────
    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        case_id=case_id,
        tipo_uso=AITipoUso.redacao_peca,
        modelo=r7.modelo,
        prompt_sanitizado=fatos_limpos[:4000],
        pii_removida=houve_pii,
        resposta=documento_final,
        fontes_rag="; ".join(f["chunk_id"] for f in fontes) if fontes else None,
        tokens_input=(
            (r1.input_tokens or 0) + (r2.input_tokens or 0) +
            (r4.input_tokens or 0) + (r5.input_tokens or 0) +
            (r6.input_tokens or 0) + (r7.input_tokens or 0)
        ),
        tokens_output=(
            (r1.output_tokens or 0) + (r2.output_tokens or 0) +
            (r4.output_tokens or 0) + (r5.output_tokens or 0) +
            (r6.output_tokens or 0) + (r7.output_tokens or 0)
        ),
        status_hitl=AIStatusHITL.gerado,
    )

    legal_doc = LegalDoc(
        id=str(uuid4()),
        titulo=f"{nome_peca} - rascunho IA",
        tipo_peca=TIPO_PECA_LEGAL_DOC.get(tipo_peca_final, PecaTipo.outro),
        conteudo=documento_final,
        ai_generated=True,
        human_reviewed=False,
        case_id=case_id,
        created_by=user_id,
    )
    db.add(log)
    db.add(legal_doc)
    await db.commit()

    yield await _emit("concluido", {
        "ai_log_id": log.id,
        "legal_doc_id": legal_doc.id,
        "tipo_peca_identificado": tipo_peca_final,
        "documento": documento_final,
        "modelo": r7.modelo,
        "provedor": r7.provedor,
        "fontes_usadas": len(fontes),
        "pii_removida": houve_pii,
        "tokens_totais": (log.tokens_input or 0) + (log.tokens_output or 0),
        "verificacao_citacoes": verificacao_citacoes,
        "aviso": aviso_rascunho_ia(),
    })

