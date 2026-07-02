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
 "complexidade_atos": null
}
- "area" deve ser uma de: civil, trabalhista, consumidor, familia, ambiental, criminal, previdenciario, empresarial, tributario.
- "complexidade" deve ser: baixa, media ou alta.
- valores monetários como número (sem R$), ou null."""

SYSTEM = (
    "Você é um analista jurídico sênior brasileiro especializado em leitura e triagem de peças "
    "processuais (petições, sentenças, acórdãos, contratos, autos). Extraia dados estruturados e "
    "produza um diagnóstico técnico. " + REGRAS
)

_AVISO = (
    "MINUTA gerada por IA a partir da leitura automática do documento — sujeita a erros de OCR e "
    "interpretação. Revisão obrigatória do advogado responsável (OAB) antes de qualquer uso."
)


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
    user_msg = f"DOCUMENTO:\n\n{texto_para_ia}\n\n---\n{ESQUEMA}"
    try:
        resp = await ai_gateway.chat(
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": user_msg}],
            task_type="analise_juridica",
            temperature=0.1,
            max_tokens=3200,
        )
    except Exception as e:
        logger.warning(f"Falha na IA de extração: {e}")
        return {"ok": False, "erro": "IA indisponível no momento. Tente novamente."}

    dados = _parse_json(resp.texto)
    if not dados:
        return {
            "ok": True,
            "parcial": True,
            "texto_extraido": texto_para_ia[:2000],
            "resumo_executivo": {"fatos": resp.texto[:1500]},
            "_aviso": _AVISO,
            "pii_removida": houve_pii,
        }

    # 3) Honorários sugeridos (tabela OAB via RAG) + jurisprudência semelhante
    if enriquecer_rag and db is not None:
        try:
            dados["honorarios_sugeridos"] = await _sugerir_honorarios(db, dados)
        except Exception as e:
            logger.warning(f"Honorários RAG falhou: {e}")
        try:
            dados["referencias_internas"] = await _buscar_referencias(db, dados, texto)
        except Exception as e:
            logger.warning(f"Referências RAG falhou: {e}")

    dados["ok"] = True
    dados["_aviso"] = _AVISO
    dados["_modelo"] = f"{resp.provedor}/{resp.modelo}"
    dados["caracteres_lidos"] = len(texto)
    dados["pii_removida"] = houve_pii
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


async def _buscar_referencias(db, dados: dict, texto: str) -> list:
    """Busca jurisprudência/precedentes internos semelhantes (RAG semântico)."""
    from app.services.ai_service import buscar_contexto_rag
    area = (dados.get("classificacao") or {}).get("area") or ""
    fatos = (dados.get("resumo_executivo") or {}).get("fatos") or texto[:400]
    consulta = f"{area} {fatos}"[:500]
    ctx = await buscar_contexto_rag(db, consulta, limite=5, modo_or=True)
    return [
        {"titulo": c.get("titulo"), "categoria": c.get("categoria"),
         "fonte": c.get("fonte"), "trecho": (c.get("conteudo") or "")[:280],
         "score": c.get("score")}
        for c in ctx
    ]
