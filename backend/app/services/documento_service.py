"""
documento_service.py — Pipeline unificado de análise inteligente de documentos.

Fluxo:  upload → OCR (ocr_service) → extração estruturada (IA) → análise jurídica
        → enriquecimento RAG (jurisprudência/casos internos) → JSON estruturado.

Reaproveita: ocr_service (PyMuPDF + pytesseract), ai_gateway (LLM com fallback),
buscar_contexto_rag (pgvector). NÃO duplica lógica existente.

REGRAS INVIOLÁVEIS (CLAUDE.md): nunca inventa lei/súmula/jurisprudência/nº de
processo; nunca promete resultado; toda saída é MINUTA — revisão obrigatória do
advogado (OAB).
"""
import json
import logging
import re
from typing import Optional

from app.services import ai_gateway, ocr_service
from app.services.sanitizer import sanitizar_pii

logger = logging.getLogger("ejc.documento_service")

REGRAS = (
    "REGRAS INVIOLÁVEIS: (1) Extraia SOMENTE o que está no documento — se um campo não constar, "
    "use null (não invente CPF, nº de processo, nomes, súmulas ou leis). (2) NUNCA prometa resultado. "
    "(3) Não afirme que algo É ilegal/nulo — diga 'possível nulidade/vício a verificar' e o porquê. "
    "(4) Só cite base legal se tiver certeza; senão escreva 'verificar'."
)

# Esquema-alvo que a IA deve preencher (1 chamada estruturada).
ESQUEMA = """Responda APENAS com um JSON válido nesta forma exata (use null quando não houver dado):
{
 "identificacao_processual": {"numero_processo": null, "vara": null, "tribunal": null, "comarca": null, "classe": null, "assunto": null},
 "partes": {"autor": null, "reu": null, "terceiros": [], "advogados": [], "procuradores": []},
 "dados_pessoais": {"nome": null, "cpf": null, "cnpj": null, "rg": null, "endereco": null, "telefone": null, "email": null},
 "classificacao": {"area": null, "subarea": null, "materia": null, "complexidade": "media"},
 "resumo_executivo": {"fatos": null, "pedidos": null, "situacao_processual": null},
 "diagnostico": {"pontos_fortes": [], "pontos_fracos": [], "riscos": [], "oportunidades": []},
 "brechas_processuais": {"prescricao": null, "decadencia": null, "incompetencia": null, "ilegitimidade": null, "nulidades": [], "falhas_documentais": [], "ausencia_de_provas": null, "teses_defensivas": []},
 "estrategia": {"medidas_cabiveis": [], "recursos": [], "acoes": [], "producao_de_provas": [], "negociacao": []},
 "valor_causa_estimado": null,
 "complexidade_atos": null,
 "campos_v2": {
  "numero_processo": {"valor": null, "trecho_origem": null, "confianca": 0.0},
  "autor": {"valor": null, "trecho_origem": null, "confianca": 0.0},
  "reu": {"valor": null, "trecho_origem": null, "confianca": 0.0},
  "cpf": {"valor": null, "trecho_origem": null, "confianca": 0.0},
  "cnpj": {"valor": null, "trecho_origem": null, "confianca": 0.0},
  "area": {"valor": null, "trecho_origem": null, "confianca": 0.0},
  "valor_causa": {"valor": null, "trecho_origem": null, "confianca": 0.0},
  "data_documento": {"valor": null, "trecho_origem": null, "confianca": 0.0}
 }
}
- "area" deve ser uma de: civil, trabalhista, consumidor, familia, ambiental, criminal, previdenciario, empresarial, tributario.
- "complexidade" deve ser: baixa, media ou alta.
- valores monetários como número (sem R$), ou null.
- Em "campos_v2" (R4 — rastreabilidade da extração): para CADA campo,
  "trecho_origem" = citação LITERAL e CURTA (máx. 15 palavras) copiada do
  documento onde o valor aparece (null se o campo não constar) e
  "confianca" = número entre 0 e 1. NUNCA parafraseie o trecho_origem."""

SYSTEM = (
    "Você é um analista jurídico sênior brasileiro especializado em leitura e triagem de peças "
    "processuais (petições, sentenças, acórdãos, contratos, autos). Extraia dados estruturados e "
    "produza um diagnóstico técnico. " + REGRAS
)

_AVISO = (
    "MINUTA gerada por IA a partir da leitura automática do documento — sujeita a erros de OCR e "
    "interpretação. Revisão obrigatória do advogado responsável (OAB) antes de qualquer uso."
)


def _norm_espacos(s: Optional[str]) -> str:
    """Normaliza espaços/quebras e caixa para comparação fuzzy de trechos."""
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()


def _verificar_origens_v2(campos_v2, texto: str) -> dict:
    """
    Pós-processamento R4: valida que cada trecho_origem REALMENTE ocorre no
    texto extraído (comparação com espaços normalizados). Se não ocorrer,
    rebaixa confianca para 0.3 e marca origem_verificada=false — anti-alucinação.
    """
    if not isinstance(campos_v2, dict):
        return {}
    texto_norm = _norm_espacos(texto)
    saida: dict = {}
    for chave, campo in campos_v2.items():
        if not isinstance(campo, dict):
            campo = {"valor": campo, "trecho_origem": None, "confianca": 0.3}
        try:
            conf = float(campo.get("confianca") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = min(max(conf, 0.0), 1.0)
        trecho = campo.get("trecho_origem")
        trecho_norm = _norm_espacos(str(trecho)) if trecho else ""
        verificada = bool(trecho_norm) and trecho_norm in texto_norm
        if not verificada:
            conf = min(conf, 0.3)
        campo["confianca"] = conf
        campo["origem_verificada"] = verificada
        saida[chave] = campo
    return saida


def _parse_json(txt: str) -> Optional[dict]:
    """Extrai o primeiro objeto JSON da resposta da IA (tolerante a texto ao redor)."""
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        pass
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


async def extrair_e_analisar(
    filepath: str,
    mimetype: Optional[str],
    db=None,
    enriquecer_rag: bool = True,
) -> dict:
    """
    Executa o pipeline completo. Retorna dict estruturado pronto para o frontend
    e para pré-preencher um novo caso.
    """
    # 1) OCR / extração de texto
    texto = ocr_service.extrair_texto(filepath, mimetype)
    if not texto or len(texto.strip()) < 40:
        return {
            "ok": False,
            "erro": "Não foi possível extrair texto legível do documento (OCR vazio). "
                    "Verifique a qualidade do arquivo.",
        }
    texto = texto[:18000]  # teto de contexto
    texto_para_ia, houve_pii = sanitizar_pii(texto)

    # 2) Extração estruturada + diagnóstico (1 chamada de IA)
    # LGPD (Fase 3B): a PII do documento NÃO pode sair para o LLM. O prompt é
    # montado a partir de `texto_para_ia` (já passou por sanitizar_pii), com
    # CPF/CNPJ/nº de processo/e-mail/etc. substituídos por marcadores ([CPF],
    # [PROCESSO], ...). A chamada permanece FIXADA no modelo LOCAL (Ollama),
    # SEM fallback para o Groq (nuvem/EUA): provider_override="ollama" resolve
    # a cadeia só-local e falha fechado se o Ollama estiver indisponível.
    user_msg = f"DOCUMENTO:\n\n{texto_para_ia}\n\n---\n{ESQUEMA}"
    try:
        resp = await ai_gateway.chat(
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": user_msg}],
            task_type="analise_juridica",
            temperature=0.1,
            max_tokens=3200,
            provider_override="ollama",   # LGPD: extração de PII só no modelo local
        )
    except Exception as e:
        logger.warning(f"Falha na IA de extração (modelo local): {e}")
        return {"ok": False, "erro": (
            "IA local (Ollama) indisponível. A extração de documentos roda "
            "apenas no modelo local por conter dados pessoais (LGPD) — não é "
            "enviada a serviço externo. Verifique o Ollama e tente novamente."
        )}

    dados = _parse_json(resp.texto)
    if not dados:
        return {
            "ok": True,
            "parcial": True,
            "texto_extraido": texto_para_ia[:2000],
            "resumo_executivo": {"fatos": resp.texto[:1500]},
            "_aviso": _AVISO,
            "pii_removida": houve_pii,
            # Chave interna (consumida e removida pelo router documento_ia):
            # texto JÁ SANITIZADO para o diagnóstico via núcleo único de IA.
            "_texto_sanitizado": texto_para_ia[:6000],
        }

    # 2.b) R4 — verificação de origem dos campos v2 (anti-alucinação).
    # Retrocompatível: "campos_v2" é chave PARALELA; o formato antigo permanece.
    # LGPD (Fase 3B): a IA só viu `texto_para_ia` (sanitizado), então os
    # trecho_origem que ela cita contêm marcadores ([CPF], [PROCESSO], ...).
    # Verificamos a origem contra o texto sanitizado para preservar a
    # rastreabilidade R4 sem reexpor PII crua.
    dados["campos_v2"] = _verificar_origens_v2(dados.get("campos_v2"), texto_para_ia)

    # 3) Honorários sugeridos (tabela OAB via RAG) + jurisprudência semelhante
    if enriquecer_rag and db is not None:
        try:
            dados["honorarios_sugeridos"] = await _sugerir_honorarios(db, dados)
        except Exception as e:
            logger.warning(f"Honorários RAG falhou: {e}")
        try:
            # LGPD (Fase 3B): a consulta de embeddings do RAG usa APENAS o
            # texto sanitizado — PII crua nunca alimenta o vetor de busca.
            dados["referencias_internas"] = await _buscar_referencias(db, dados, texto_para_ia)
        except Exception as e:
            logger.warning(f"Referências RAG falhou: {e}")

    dados["ok"] = True
    dados["_aviso"] = _AVISO
    dados["_modelo"] = f"{resp.provedor}/{resp.modelo}"
    dados["caracteres_lidos"] = len(texto)
    dados["pii_removida"] = houve_pii
    # Chave interna (consumida e removida pelo router documento_ia): texto JÁ
    # SANITIZADO para o diagnóstico jurídico via núcleo único de IA.
    dados["_texto_sanitizado"] = texto_para_ia[:6000]
    return dados


async def _sugerir_honorarios(db, dados: dict) -> dict:
    """Estima honorários via tabela OAB ingerida no RAG (categoria tabela_honorarios_oab)."""
    from app.services.ai_service import buscar_contexto_rag
    area = (dados.get("classificacao") or {}).get("area") or ""
    materia = (dados.get("classificacao") or {}).get("materia") or ""
    consulta = f"honorários advocatícios {area} {materia} tabela OAB Minas Gerais"
    ctx = await buscar_contexto_rag(db, consulta, limite=6, categorias=["tabela_honorarios_oab"])
    # Filtra placeholders/conteúdo inutilizável (ex.: "lorem ipsum") — senão a IA
    # inventa números de itens. Risco jurídico: nunca citar item que não existe.
    def _util(c):
        t = (c.get("conteudo") or "").lower()
        return len(t.strip()) > 40 and "lorem ipsum" not in t
    ctx_real = [c for c in ctx if _util(c)]
    tabela_ok = len(ctx_real) > 0
    ctx_txt = "\n".join(f"- {(c.get('conteudo') or '')[:500]}" for c in ctx_real)
    valor = dados.get("valor_causa_estimado")
    if tabela_ok:
        sys = (
            "Você sugere honorários com base na TABELA DA OAB/MG fornecida no contexto. "
            "Cite SOMENTE itens que aparecem textualmente no contexto. " + REGRAS
        )
        ctx_bloco = f"CONTEXTO (tabela OAB/MG):\n{ctx_txt}"
        fund_regra = '"fundamento": "<cite o item EXATO que aparece no contexto, ou critério usual se não houver item específico>"'
    else:
        sys = (
            "A tabela oficial da OAB/MG NÃO está disponível na base. Forneça apenas uma "
            "REFERÊNCIA GENÉRICA por percentuais usuais de mercado. É PROIBIDO citar números "
            "de itens/artigos da tabela (você não os tem). " + REGRAS
        )
        ctx_bloco = "CONTEXTO: tabela oficial OAB/MG indisponível na base — NÃO invente itens."
        fund_regra = '"fundamento": "Referência genérica de mercado — tabela oficial OAB/MG deve ser consultada (não disponível na base)"'
    user = (
        f"{ctx_bloco}\n\n"
        f"Área: {area} | Matéria: {materia} | Valor da causa: {valor}\n\n"
        'Responda APENAS JSON: {"minimo": "<valor/regra>", "recomendado": "<valor/faixa>", '
        '"estrategico": "<valor/faixa>", ' + fund_regra + ', '
        '"contrato_sugerido": "<ex: 30% êxito + R$ X entrada>", '
        f'"tabela_oficial_disponivel": {str(tabela_ok).lower()}}}'
    )
    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        task_type="analise_juridica", temperature=0.2, max_tokens=600,
    )
    return _parse_json(resp.texto) or {"_bruto": resp.texto[:500]}


async def sugerir_tipo(
    db,
    user_id: str,
    texto: str,
    tipos: list[dict],
    case_id: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> dict:
    """
    Classifica o documento em UM tipo_key do master (R3) — SUGESTÃO apenas.

    Pipeline LGPD obrigatório (mesmo padrão de ai_service):
      sanitizar_pii → IA via ai_gateway (chat_rapido) → AILog (HITL rastreável).
    NUNCA grava o tipo no Document — confirmação humana obrigatória.
    Se a IA devolver tipo fora do master → "outro" com confiança baixa.
    """
    from uuid import uuid4
    from app.services.sanitizer import sanitizar_pii
    from app.models.ai_log import AILog, AITipoUso, AIStatusHITL

    # 1) Sanitização LGPD antes de QUALQUER envio (teto ~6K chars)
    texto_limpo, pii = sanitizar_pii((texto or "")[:6000])

    keys_validas = {t["tipo_key"] for t in tipos}
    catalogo = "\n".join(
        f"- {t['tipo_key']}: {t['nome']}"
        + (f" — {t['descricao']}" if t.get("descricao") else "")
        for t in tipos
    )

    system = (
        "Você classifica documentos jurídicos/administrativos brasileiros em tipos "
        "pré-definidos. Escolha EXATAMENTE UM tipo_key da lista fornecida — é "
        "PROIBIDO inventar tipos fora da lista. Se nenhum se aplicar com clareza, "
        "use 'outro'. " + REGRAS
    )
    user_msg = (
        f"TIPOS DISPONÍVEIS (tipo_key: nome — descrição):\n{catalogo}\n\n"
        f"TEXTO DO DOCUMENTO (sanitizado):\n{texto_limpo}\n\n"
        'Responda APENAS com JSON válido: {"tipo_sugerido": "<tipo_key da lista>", '
        '"confianca": "alta|media|baixa", "justificativa": "<1-2 frases objetivas>"}'
    )

    # 2) IA via gateway (tarefa leve — chat_rapido, com fallback resumo/groq)
    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user_msg}],
        task_type="chat_rapido",
        temperature=0.1,
        max_tokens=300,
    )

    dados = _parse_json(resp.texto) or {}
    tipo = str(dados.get("tipo_sugerido") or "").strip()
    confianca = str(dados.get("confianca") or "").strip().lower()
    justificativa = str(dados.get("justificativa") or resp.texto or "")[:500]

    # 3) Guarda-corpo: tipo fora do master → "outro" (nunca propagar inventado)
    if tipo not in keys_validas:
        if tipo:
            justificativa = (
                f"IA sugeriu '{tipo}', que não existe no catálogo — "
                f"rebaixado para 'outro'. {justificativa}"
            )[:500]
        tipo = "outro"
        confianca = "baixa"
    if confianca not in {"alta", "media", "baixa"}:
        confianca = "media"

    # 4) AILog (LGPD + HITL — toda chamada de IA é registrada)
    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        case_id=case_id,
        tipo_uso=AITipoUso.outro,
        modelo=f"{resp.provedor}/{resp.modelo}",
        prompt_sanitizado=(
            f"[sugerir-tipo doc={doc_id or '-'}] " + user_msg
        )[:8000],
        pii_removida=pii,
        resposta=resp.texto[:4000],
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()

    return {
        "tipo_sugerido": tipo,
        "confianca": confianca,
        "justificativa": justificativa,
        "ai_log_id": log.id,
        "pii_removida": pii,
        "aviso": "⚠️ SUGESTÃO gerada por IA — o tipo NÃO foi gravado no documento; "
                 "confirmação humana obrigatória.",
    }


async def _buscar_referencias(db, dados: dict, texto_para_ia: str) -> list:
    """Busca jurisprudência/precedentes internos semelhantes (RAG semântico).

    LGPD (Fase 3B): `texto_para_ia` já passou por sanitizar_pii. Nenhum caminho
    desta função pode receber texto cru — a consulta de embeddings jamais deve
    conter PII (CPF/CNPJ/nº de processo/e-mail/...).
    """
    from app.services.ai_service import buscar_contexto_rag
    area = (dados.get("classificacao") or {}).get("area") or ""
    fatos = (dados.get("resumo_executivo") or {}).get("fatos") or texto_para_ia[:400]
    consulta = f"{area} {fatos}"[:500]
    ctx = await buscar_contexto_rag(db, consulta, limite=5, modo_or=True)
    return [
        {"titulo": c.get("titulo"), "categoria": c.get("categoria"),
         "fonte": c.get("fonte"), "trecho": (c.get("conteudo") or "")[:280],
         "score": c.get("score")}
        for c in ctx
    ]
