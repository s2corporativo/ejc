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

from app.schemas.document_intake import (
    CampoExtraido, CasoExtraido, ClienteExtraido, DocumentoIntakeResult,
    ParteExtraida, PedidoExtraido, PrazoExtraido, RiscoExtraido, TeseSugerida,
)
from app.services import ai_gateway, ocr_service
from app.services.extracao_estruturada import extrair_estruturas, parse_data_br
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
 "prazos": [{"tipo": null, "data_base": null, "termo_final": null, "fatal": false, "base_legal": null}],
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
- "prazos": inclua um item SOMENTE para cada prazo/data fatal EXPLÍCITO no documento
  (ex.: prazo de contestação, recurso, audiência, prescrição). "termo_final" = a
  DATA FATAL exatamente como consta, no formato "dd/mm/aaaa" ou "aaaa-mm-dd"; "tipo" =
  o nome do prazo (ex.: "contestação", "recurso", "audiência"). Se o documento NÃO
  trouxer uma data fatal clara, deixe "prazos" como [] — NUNCA calcule nem invente datas.
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


def _txt(v) -> Optional[str]:
    """Coage para str não-vazia limpa, ou None (lacuna). Nunca levanta."""
    if v is None:
        return None
    try:
        s = str(v).strip()
    except Exception:
        return None
    return s or None


def _flt(v) -> Optional[float]:
    """Coage para float em [0,1], ou None. Nunca levanta."""
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        # OverflowError: inteiro JSON gigante vindo do LLM (ex.: 10**400).
        return None
    if f != f or f in (float("inf"), float("-inf")):
        # NaN/inf escapam do clamp min/max e serializariam como JSON inválido
        # (`NaN`/`Infinity`) — o JSON.parse do navegador quebraria. Tratar como lacuna.
        return None
    return min(max(f, 0.0), 1.0)


def _campo_det(ocorrencias) -> Optional["CampoExtraido"]:
    """Primeira ocorrência determinística (extrair_estruturas) → CampoExtraido.

    O valor é literal do texto, então `trecho_origem` = o próprio valor e a
    confiança é 1.0 (regex + DV, sem IA). Lacuna → None.
    """
    if not isinstance(ocorrencias, list):
        return None
    for oc in ocorrencias:
        if isinstance(oc, dict):
            valor = _txt(oc.get("valor"))
        else:
            valor = _txt(oc)
        if valor:
            return CampoExtraido(valor=valor, trecho_origem=valor, confianca=1.0)
    return None


def _campo_llm(campos_v2, chave: str) -> Optional["CampoExtraido"]:
    """Extrai um CampoExtraido do bloco `campos_v2` do LLM (fail-safe)."""
    if not isinstance(campos_v2, dict):
        return None
    campo = campos_v2.get(chave)
    if not isinstance(campo, dict):
        return None
    valor = campo.get("valor")
    if valor in (None, ""):
        return None
    return CampoExtraido(
        valor=valor,
        trecho_origem=_txt(campo.get("trecho_origem")),
        confianca=_flt(campo.get("confianca")),
    )


def _lista_str(v) -> list:
    """Normaliza para lista de strings limpas (aceita str única). Sem levantar."""
    if v is None:
        return []
    itens = v if isinstance(v, (list, tuple)) else [v]
    return [s for s in (_txt(x) for x in itens) if s]


def _prazos_extraidos(llm: dict) -> list["PrazoExtraido"]:
    """Prazos do LLM → `PrazoExtraido`, SÓ quando há data fatal parseável.

    Não inventa (#83 Gap C): item sem `termo_final` (nem `data_prazo`) que
    parseie para uma data é DESCARTADO — o documento sem data clara não vira
    prazo. `termo_final` é normalizado para ISO (aaaa-mm-dd) p/ materialização
    determinística em `cases.aplicar_extracao`. Fail-safe: nunca levanta.
    """
    brutos = llm.get("prazos")
    if not isinstance(brutos, list):
        return []
    saida: list[PrazoExtraido] = []
    for item in brutos:
        if not isinstance(item, dict):
            continue
        data_fatal = parse_data_br(item.get("termo_final") or item.get("data_prazo"))
        if data_fatal is None:
            continue  # sem data fatal clara → não materializa (nunca inventa)
        saida.append(PrazoExtraido(
            tipo=_txt(item.get("tipo")),
            data_base=_txt(item.get("data_base")),
            termo_final=data_fatal.isoformat(),
            fatal=bool(item.get("fatal")),
            base_legal=_txt(item.get("base_legal")),
        ))
        if len(saida) >= 50:  # teto defensivo contra saída patológica do LLM
            break
    return saida


def _montar_intake_result(
    dados: Optional[dict],
    dados_estruturados: Optional[dict],
    tipo_documento: Optional[str] = None,
    confianca_classificacao: Optional[float] = None,
) -> "DocumentoIntakeResult":
    """Valida/coage o dict cru do LLM + a extração determinística local para
    `DocumentoIntakeResult`. **Fail-safe**: qualquer entrada inválida (None,
    parcial, tipos errados) degrada para um resultado com listas vazias e
    `necessita_revisao_humana=True` — nunca levanta exceção.

    A PII exata (CPF/CNPJ/nº CNJ) vem SEMPRE de `dados_estruturados`
    (extrair_estruturas, local), preservando `trecho_origem` — nunca de novo
    parsing nem do texto sanitizado do LLM.
    """
    llm = dados if isinstance(dados, dict) else {}
    det = dados_estruturados if isinstance(dados_estruturados, dict) else {}

    # Campos determinísticos (locais) com trecho_origem literal.
    cnj_det = _campo_det(det.get("processos_cnj"))
    cpf_det = _campo_det(det.get("cpfs"))
    cnpj_det = _campo_det(det.get("cnpjs"))

    def _get(chave: str) -> dict:
        v = llm.get(chave)
        return v if isinstance(v, dict) else {}

    ident = _get("identificacao_processual")
    classif = _get("classificacao")
    resumo = _get("resumo_executivo")
    partes_llm = _get("partes")
    pessoais = _get("dados_pessoais")
    diag = _get("diagnostico")
    brechas = _get("brechas_processuais")
    campos_v2 = llm.get("campos_v2")

    resumo_fatos = _txt(resumo.get("fatos"))

    try:
        # numero_cnj: prefere o determinístico (nº real + trecho); senão o do LLM.
        numero_cnj = cnj_det or _campo_llm(campos_v2, "numero_processo")
        if numero_cnj is None:
            n = _txt(ident.get("numero_processo"))
            if n:
                numero_cnj = CampoExtraido(valor=n)

        valor_causa = _campo_llm(campos_v2, "valor_causa")
        if valor_causa is None and llm.get("valor_causa_estimado") not in (None, ""):
            valor_causa = CampoExtraido(valor=llm.get("valor_causa_estimado"))

        caso = CasoExtraido(
            area=_txt(classif.get("area")),
            subramo=_txt(classif.get("subarea")),
            numero_cnj=numero_cnj,
            orgao=_txt(ident.get("comarca")),
            vara=_txt(ident.get("vara")),
            tribunal=_txt(ident.get("tribunal")),
            valor_causa=valor_causa,
            resumo_fatos=resumo_fatos,
        )
    except Exception:
        caso = None

    try:
        cliente = ClienteExtraido(
            nome=_txt(pessoais.get("nome")),
            cpf=cpf_det,
            cnpj=cnpj_det,
            email=_txt(pessoais.get("email")),
            telefone=_txt(pessoais.get("telefone")),
            endereco=_txt(pessoais.get("endereco")),
        )
        if not any(getattr(cliente, c) for c in
                   ("nome", "cpf", "cnpj", "email", "telefone", "endereco")):
            cliente = None
    except Exception:
        cliente = None

    partes: list = []
    try:
        for chave, papel in (("autor", "autor"), ("reu", "reu")):
            nome = _txt(partes_llm.get(chave))
            if nome:
                partes.append(ParteExtraida(nome=nome, papel=papel))
        for terceiro in _lista_str(partes_llm.get("terceiros")):
            partes.append(ParteExtraida(nome=terceiro, papel="terceiro"))
    except Exception:
        partes = []

    pedidos: list = []
    try:
        ped = _txt(resumo.get("pedidos"))
        if ped:
            pedidos.append(PedidoExtraido(descricao=ped))
    except Exception:
        pedidos = []

    riscos: list = []
    try:
        riscos = [RiscoExtraido(descricao=r) for r in _lista_str(diag.get("riscos"))]
    except Exception:
        riscos = []

    teses: list = []
    try:
        teses = [TeseSugerida(titulo=t)
                 for t in _lista_str(brechas.get("teses_defensivas"))]
    except Exception:
        teses = []

    try:
        prazos = _prazos_extraidos(llm)
    except Exception:
        prazos = []

    try:
        return DocumentoIntakeResult(
            tipo_documento=_txt(tipo_documento),
            confianca_classificacao=_flt(confianca_classificacao),
            cliente=cliente,
            caso=caso,
            partes=partes,
            pedidos=pedidos,
            prazos=prazos,
            riscos=riscos,
            teses=teses,
            resumo_fatos=resumo_fatos,
            necessita_revisao_humana=True,
        )
    except Exception:
        # Última barreira: contrato mínimo válido, jamais 500.
        return DocumentoIntakeResult(necessita_revisao_humana=True)


_ERRO_FAIL_CLOSED = (
    "A interpretação por IA local (Ollama) está indisponível e o fallback para "
    "provedores externos está DESLIGADO (INTAKE_EXTERNAL_FALLBACK=false). "
    "Habilite o Ollama ou ligue INTAKE_EXTERNAL_FALLBACK no .env para permitir "
    "a cadeia externa (o texto vai sanitizado — sem CPF/CNPJ/nº de processo)."
)


async def extrair_e_analisar(
    filepath: str,
    mimetype: Optional[str],
    db=None,
    enriquecer_rag: bool = True,
    user_id: Optional[str] = None,
) -> dict:
    """
    Executa o pipeline completo. Retorna dict estruturado pronto para o frontend
    e para pré-preencher um novo caso.

    `user_id` (quando fornecido junto com `db`): grava AILog da chamada
    principal de interpretação — trilha "qual provedor viu qual documento"
    (art. 37 LGPD).
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

    # 1.b) Extração DETERMINÍSTICA local (regex, sem IA) sobre o texto BRUTO.
    # LGPD: o dado pessoal EXATO (CPF/CNPJ/nº CNJ/e-mail/telefone) é extraído
    # aqui, localmente, sem passar por nenhum LLM — e devolvido apenas ao
    # frontend autenticado. Nunca alimenta prompt de IA.
    dados_estruturados = extrair_estruturas(texto)

    texto_para_ia, houve_pii = sanitizar_pii(texto)

    # 2) Interpretação LLM (1 chamada de IA) — cadeia com fallback.
    # Decisão LGPD (híbrido determinístico + LLM):
    #   • O dado pessoal exato vem da extração determinística local acima.
    #   • O LLM (possivelmente EXTERNO via fallback ollama→anthropic→groq) só
    #     vê `texto_para_ia`, JÁ SANITIZADO por sanitizar_pii (CPF/CNPJ/nº de
    #     processo/e-mail/etc. viram marcadores [CPF], [PROCESSO], ...).
    #   • Segunda linha de defesa: o gateway aplica _sanitizar_messages_externo
    #     e PULA provedores externos se restar PII estrutural
    #     (AI_REQUIRE_SANITIZATION_FOR_EXTERNAL).
    # Por isso o fallback externo é seguro — e a importação não depende mais
    # exclusivamente do Ollama estar provisionado.
    #
    # Opt-out (INTAKE_EXTERNAL_FALLBACK=false): volta ao fail-closed antigo —
    # provider_override="ollama" (só local); indisponível → erro claro citando
    # a flag, sem jamais acionar provedor externo neste fluxo.
    from app.core.config import get_settings
    settings = get_settings()
    somente_local = not settings.INTAKE_EXTERNAL_FALLBACK
    if somente_local and not settings.OLLAMA_ENABLED:
        # Guarda: provider forçado inelegível faria o gateway cair na cadeia
        # automática (externa) — exatamente o que a flag proíbe.
        return {"ok": False, "erro": _ERRO_FAIL_CLOSED}

    user_msg = f"DOCUMENTO:\n\n{texto_para_ia}\n\n---\n{ESQUEMA}"
    try:
        resp = await ai_gateway.chat(
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": user_msg}],
            task_type="analise_juridica",
            temperature=0.1,
            max_tokens=3200,
            provider_override="ollama" if somente_local else None,
        )
    except Exception as e:
        logger.warning(f"Cadeia de IA falhou na análise do documento: {e}")
        if somente_local:
            # Fail-closed explícito escolhido pelo escritório via flag.
            return {"ok": False, "erro": _ERRO_FAIL_CLOSED}
        # 2.a) TODA a cadeia LLM falhou → degrada com sucesso parcial: a
        # extração determinística local + texto OCR continuam úteis para o
        # advogado. Nunca mais erro seco na importação.
        return {
            "ok": True,
            "parcial": True,
            "analise_llm_indisponivel": True,
            "aviso_llm": (
                "A interpretação por IA está indisponível no momento (nenhum "
                "provedor respondeu). Os dados abaixo foram extraídos "
                "localmente de forma determinística (sem IA) e o texto do "
                "documento foi lido — revise e preencha o caso manualmente."
            ),
            "dados_estruturados": dados_estruturados,
            # Contrato tipado (#83 Gap A): sem LLM, monta só a partir da
            # extração determinística — necessita_revisao_humana=True.
            "intake_result": _montar_intake_result(
                None, dados_estruturados).model_dump(mode="json"),
            "texto_extraido": texto_para_ia[:2000],
            "caracteres_lidos": len(texto),
            "pii_removida": houve_pii,
            "_aviso": _AVISO,
            "_texto_sanitizado": texto_para_ia[:6000],
        }

    # 2.b) Trilha de auditoria (art. 37 LGPD): AILog da chamada PRINCIPAL do
    # intake — registra qual provedor/modelo viu qual documento (prompt já
    # SANITIZADO). Mesmo padrão canônico de sugerir_tipo/executar_tarefa_ia
    # (ai_guard): erro de gravação PROPAGA — IA sem trilha deve falhar.
    intake_log_id: Optional[str] = None
    if db is not None and user_id:
        from app.models.ai_log import AITipoUso
        from app.services.ai_guard import registrar_ai_log
        intake_log_id = await registrar_ai_log(
            db,
            user_id=user_id,
            tipo_uso=AITipoUso.resumo_documento,
            case_id=None,
            prompt_sanitizado=("[intake analise_juridica] " + user_msg)[:8000],
            pii_removida=houve_pii,
            resposta=(resp.texto or "")[:4000],
            modelo=f"{resp.provedor}/{resp.modelo}",
            tokens_input=getattr(resp, "input_tokens", None),
            tokens_output=getattr(resp, "output_tokens", None),
            custo_estimado=getattr(resp, "custo_estimado_brl", None),
        )

    dados = _parse_json(resp.texto)
    if not dados:
        return {
            "ok": True,
            "parcial": True,
            "intake_log_id": intake_log_id,
            "dados_estruturados": dados_estruturados,
            # JSON do LLM ilegível → contrato tipado só com o determinístico.
            "intake_result": _montar_intake_result(
                None, dados_estruturados).model_dump(mode="json"),
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
    dados["dados_estruturados"] = dados_estruturados
    # Contrato tipado (#83 Gap A): valida/coage o dict do LLM + o determinístico
    # para DocumentoIntakeResult, ADITIVO ao dict legado (não o substitui).
    dados["intake_result"] = _montar_intake_result(
        dados, dados_estruturados).model_dump(mode="json")
    dados["_aviso"] = _AVISO
    dados["_modelo"] = f"{resp.provedor}/{resp.modelo}"
    dados["intake_log_id"] = intake_log_id
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
