# ── app/services/case_intel.py ────────────────────────────────────────────────
# NÚCLEO COGNITIVO — gatilhos automáticos do CASO (ETAPA 1 do prompt mestre).
#
# triagem_caso(case_id): roda em BackgroundTask logo após a criação do caso.
# A IA, via gateway central, lê os fatos e devolve JSON estruturado; preenchemos os campos
# que JÁ EXISTEM em `cases` (tese_principal, pontos_fortes, pontos_fracos) —
# SOMENTE se estiverem vazios (nunca sobrescreve o que o advogado escreveu).
# Tudo é RASCUNHO (Provimento OAB 205/2021): registramos AILog + movimento.
#
# Reutiliza primitivas existentes: AI Gateway, sanitizar_pii, AILog, AsyncSessionLocal.
# Não cria tabela nova. Não reescreve analisar_caso (que faz análise em prosa).
from __future__ import annotations
import json
import logging
from uuid import uuid4

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.taxonomia import (
    AREAS_TRIAGEM, SENTINELA_OUTRO, areas_para_prompt, normalizar_area,
)
from app.models.case import Case, CaseMovimento
from app.models.client import Client
from app.models.legal_doc import LegalDoc
from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
from app.services.ai_gateway import chat as gw_chat, GatewayResponse
from app.services.ingestion_service import upsert_documento
from app.services.sanitizer import sanitizar_pii

logger = logging.getLogger("ejc.case_intel")
settings = get_settings()

SYS_TRIAGEM = (
    "Você é um advogado sênior fazendo a TRIAGEM inicial de um caso a partir dos "
    "fatos relatados. Responda APENAS um objeto JSON válido (sem texto fora do JSON, "
    "sem markdown), com exatamente estas chaves:\n"
    # Vocabulário de área DERIVADO da fonte única (taxonomia.AREAS_TRIAGEM,
    # slugs canônicos de CaseArea) + sentinela "outro". As grafias antigas do
    # prompt ("civel", "penal") seguem aceitas no parse via normalizar_area.
    '{"area": "<' + areas_para_prompt(AREAS_TRIAGEM, separador="|")
    + f'|{SENTINELA_OUTRO}>",'
    ' "assunto": "<tema jurídico em poucas palavras>",'
    ' "tese_principal": "<a tese central a sustentar, 1-3 frases>",'
    ' "teses_secundarias": ["<tese alternativa>", "..."],'
    ' "pontos_fortes": "<por que podemos vencer>",'
    ' "pontos_fracos": "<fragilidades e riscos>",'
    ' "provas_necessarias": ["<prova/documento>", "..."],'
    ' "oportunidades": "<oportunidades estratégicas>",'
    ' "chance_exito": <inteiro 0-100>,'
    ' "complexidade": "<baixa|media|alta>"}\n'
    "Baseie-se só nos fatos. NÃO invente jurisprudência nem números de processo. "
    "Se faltarem dados, seja conservador na chance de êxito."
)


def _parse_json(txt: str) -> dict | None:
    """Extrai o primeiro objeto JSON do texto (tolerante a cercas/ruído)."""
    if not txt:
        return None
    s = txt.strip()
    if s.startswith("```"):
        s = s.split("```")[1] if "```" in s[3:] else s[3:]
        s = s.lstrip("json").strip()
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1:
        return None
    try:
        return json.loads(s[i:j + 1])
    except Exception:
        return None



async def _gateway_json(
    system_prompt: str,
    user_prompt: str,
    task_type: str = "analise_juridica",
    temperature: float = 0.1,
    max_tokens: int = 1000,
    nivel: str = "alto",
    entidades: dict[str, list[str]] | None = None,
) -> tuple[str, GatewayResponse]:
    resp = await gw_chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        task_type=task_type,
        temperature=temperature,
        max_tokens=max_tokens,
        nivel_inteligencia=nivel,
        entidades=entidades or None,
    )
    return resp.texto, resp


def _modelo_log(resp: object) -> str:
    modelo = getattr(resp, "modelo", None) or settings.GROQ_MODEL
    provedor = getattr(resp, "provedor", None)
    return f"{provedor}/{modelo}" if provedor else modelo

async def triagem_caso(case_id: str) -> None:
    if not settings.AI_ENABLED:
        return
    try:
        async with AsyncSessionLocal() as db:
            case = await db.get(Case, case_id)
            if not case or case.deleted_at is not None:
                return
            fatos = (case.descricao_fatos or "").strip()
            if len(fatos) < 20:
                return  # nada relevante para analisar

            texto_limpo, houve_pii = sanitizar_pii(fatos)
            area_atual = getattr(case.area, "value", None) or str(case.area or "")
            user_msg = f"ÁREA INFORMADA: {area_atual or 'não informada'}\n\nFATOS:\n{texto_limpo}"

            # Nomes próprios do caso → marcadores reversíveis antes do provider
            # externo (estrategia = EXTERNO_PSEUDONIMIZADO). sanitizar_pii acima
            # só cobre PII estrutural; `entidades` cobre cliente/parte/advogado.
            from app.services.ai.entidades_caso import entidades_do_caso
            entidades = await entidades_do_caso(db, case_id)

            bruto, resp = await _gateway_json(
                SYS_TRIAGEM, user_msg, task_type="estrategia",
                temperature=0.1, max_tokens=1300, nivel="alto",
                entidades=entidades,
            )
            data = _parse_json(bruto)
            if not data:
                logger.warning(f"[case_intel] JSON inválido para caso {case_id}")
                return

            # ── Persistir SOMENTE em campos vazios (nunca sobrescreve o advogado) ──
            tese = (data.get("tese_principal") or "").strip()
            sec = data.get("teses_secundarias") or []
            fortes = (data.get("pontos_fortes") or "").strip()
            opp = (data.get("oportunidades") or "").strip()
            fracos = (data.get("pontos_fracos") or "").strip()
            provas = data.get("provas_necessarias") or []
            chance = data.get("chance_exito")
            complex_ = (data.get("complexidade") or "").strip()
            assunto = (data.get("assunto") or "").strip()
            # Normaliza para o canônico (aceita valores legados "civel"/"penal");
            # sem correspondência segura, preserva o texto bruto para o revisor.
            area_bruta = (data.get("area") or "").strip()
            area_sug = normalizar_area(area_bruta) or area_bruta

            marca = "  ⟦rascunho IA — revisar (OAB)⟧"
            if tese and not (case.tese_principal or "").strip():
                extra = ("\n\nTeses alternativas: " + "; ".join(sec)) if sec else ""
                case.tese_principal = tese + extra + marca
            if fortes and not (case.pontos_fortes or "").strip():
                extra = ("\n\nOportunidades: " + opp) if opp else ""
                case.pontos_fortes = fortes + extra + marca
            if fracos and not (case.pontos_fracos or "").strip():
                extra = ("\n\nProvas necessárias: " + "; ".join(provas)) if provas else ""
                case.pontos_fracos = fracos + extra + marca

            resumo_mov = (
                f"IA – Triagem automática: área≈{area_sug or area_atual} · "
                f"assunto={assunto or '—'} · chance≈{chance}% · "
                f"complexidade={complex_ or '—'}. RASCUNHO — revisão por advogado (OAB)."
            )
            db.add(CaseMovimento(
                id=str(uuid4()), case_id=case.id, tipo="ia",
                descricao=resumo_mov, created_by=None,
            ))
            db.add(AILog(
                id=str(uuid4()), user_id=case.advogado_responsavel_id, case_id=case.id,
                tipo_uso=AITipoUso.analise_caso, modelo=_modelo_log(resp),
                prompt_sanitizado=texto_limpo[:8000], pii_removida=houve_pii,
                resposta=bruto[:8000], status_hitl=AIStatusHITL.gerado,
            ))
            await db.commit()
            logger.info(f"[case_intel] Triagem concluída para caso {case_id}")
    except Exception as e:
        logger.warning(f"[case_intel] Falha na triagem do caso {case_id}: {str(e)[:200]}")


# ── ETAPA 1.3 + 6 + 7 — aprendizado ao ENCERRAR o caso ────────────────────────
# Quando um caso vira status=encerrado: grava lição na Memória Institucional e
# uma tese no Banco de Teses (sugerida_ia/rascunho). Idempotente. A Jurimetria
# se alimenta naturalmente dos casos encerrados (resultado/area/data).
SYS_ENCERRAMENTO = (
    "Você é um advogado sênior consolidando o APRENDIZADO institucional de um caso "
    "encerrado. Responda APENAS JSON válido com as chaves:\n"
    '{"titulo_licao": "<título curto da lição>",'
    ' "licao": "<o que aprendemos: estratégia aplicada, o que funcionou, o que evitar — 3-6 frases>",'
    ' "fatores_exito": "<fatores que contribuíram para o resultado>",'
    ' "fatores_insucesso": "<fragilidades/erros, se houver>",'
    ' "tese_consolidada": "<a tese jurídica reutilizável extraída do caso, 1-2 frases>"}\n'
    "Baseie-se SÓ nos dados do caso. Não invente. Seja objetivo e prático."
)
# Vocabulário alinhado ao router (cases.py EncerrarCasoReq): exito|exito_parcial|
# acordo|derrota|desistencia|arquivado. "exito_total"/"improcedente" mantidos
# como aliases p/ dados históricos.
_EXITO = {"exito", "exito_total", "exito_parcial", "acordo"}


async def aprendizado_encerramento(case_id: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            case = await db.get(Case, case_id)
            if not case:
                return
            # Idempotência: não duplicar aprendizado do mesmo encerramento.
            ja = (await db.execute(text(
                "SELECT 1 FROM memoria_institucional WHERE case_id=:i AND deleted_at IS NULL "
                "AND metadados->>'fonte'='auto_encerramento' LIMIT 1"), {"i": case_id})).first()
            if ja:
                return

            area = getattr(case.area, "value", None) or str(case.area or "")
            resultado = (case.resultado or "").strip()
            exito = resultado in _EXITO
            perdeu = resultado in ("derrota", "improcedente")

            base = (
                f"Caso: {case.titulo}\nÁrea: {area}\nResultado: {resultado or 'não informado'}\n"
                f"Tese principal: {case.tese_principal or '—'}\n"
                f"Motivo do resultado: {case.motivo_resultado or '—'}\n"
                f"Provas determinantes: {case.provas_determinantes or '—'}\n"
                f"Lições anotadas: {case.licoes_aprendidas or '—'}\n"
                f"Pontos fortes: {case.pontos_fortes or '—'}\nPontos fracos: {case.pontos_fracos or '—'}"
            )
            base_limpo, houve_pii = sanitizar_pii(base)

            data = None
            bruto = ""
            if settings.AI_ENABLED:
                try:
                    from app.services.ai.entidades_caso import entidades_do_caso
                    entidades = await entidades_do_caso(db, case_id)
                    bruto, resp = await _gateway_json(
                        SYS_ENCERRAMENTO, base_limpo, task_type="estrategia",
                        temperature=0.1, max_tokens=1200, nivel="alto",
                        entidades=entidades,
                    )
                    data = _parse_json(bruto)
                except Exception as e:
                    logger.warning(f"[case_intel] IA encerramento falhou ({case_id}): {str(e)[:120]}")

            if data:
                titulo = (data.get("titulo_licao") or f"Aprendizado: {case.titulo}")[:200]
                conteudo = (
                    f"{data.get('licao', '')}\n\n"
                    f"Fatores de êxito: {data.get('fatores_exito', '—')}\n"
                    f"Fatores de insucesso: {data.get('fatores_insucesso', '—')}"
                )
                tese_txt = (data.get("tese_consolidada") or case.tese_principal or "").strip()
            else:
                # Fallback sem IA — registra o que existe no próprio caso.
                titulo = f"Aprendizado: {case.titulo}"[:200]
                conteudo = (
                    f"Tese: {case.tese_principal or '—'}\n"
                    f"Motivo do resultado: {case.motivo_resultado or '—'}\n"
                    f"Lições: {case.licoes_aprendidas or '—'}"
                )
                tese_txt = (case.tese_principal or "").strip()

            tipo_mem = "tese_vencedora" if exito else "estrategia"
            tags = json.dumps([t for t in [area, resultado] if t], ensure_ascii=False)
            meta = json.dumps({"fonte": "auto_encerramento", "tribunal": case.tribunal,
                               "valor_causa": str(case.valor_causa) if case.valor_causa else None},
                              ensure_ascii=False)

            await db.execute(text(
                "INSERT INTO memoria_institucional "
                "(id, case_id, advogado_id, tipo, titulo, conteudo, resultado, area_direito, "
                " tags, metadados, created_by, created_at) VALUES "
                "(:id,:cid,:adv,:tipo,:tit,:cont,:res,:area, CAST(:tags AS jsonb), CAST(:meta AS jsonb), :adv, now())"),
                {"id": str(uuid4()), "cid": case.id, "adv": case.advogado_responsavel_id,
                 "tipo": tipo_mem, "tit": titulo, "cont": conteudo, "res": resultado or None,
                 "area": area or None, "tags": tags, "meta": meta})

            db.add(CaseMovimento(
                id=str(uuid4()), case_id=case.id, tipo="ia",
                descricao=f"IA – Aprendizado institucional registrado ao encerrar (resultado: {resultado or '—'}).",
                created_by=None))
            if bruto:
                db.add(AILog(
                    id=str(uuid4()), user_id=case.advogado_responsavel_id, case_id=case.id,
                    tipo_uso=AITipoUso.outro, modelo=_modelo_log(resp),
                    prompt_sanitizado=base_limpo[:8000], pii_removida=houve_pii,
                    resposta=bruto[:8000], status_hitl=AIStatusHITL.gerado))
            await db.commit()

            # Banco de Teses (transação separada — falha aqui não desfaz a memória).
            if tese_txt:
                try:
                    await db.execute(text(
                        "INSERT INTO teses (id, titulo, descricao, area_juridica, tribunal, "
                        " tipo, status, vezes_usada, vezes_venceu, vezes_perdeu, taxa_sucesso, "
                        " created_by, created_at) VALUES "
                        "(:id,:tit,:desc,:area,:trib, CAST(:tp AS tesetipo), CAST(:st AS tesestatus), "
                        " 1,:vv,:vp,:ts,:cb, now())"),
                        {"id": str(uuid4()), "tit": (tese_txt[:120] or case.titulo),
                         "desc": tese_txt, "area": area or None, "trib": case.tribunal,
                         "tp": "sugerida_ia", "st": "rascunho",
                         "vv": 1 if exito else 0, "vp": 1 if perdeu else 0,
                         "ts": 100.0 if exito else (0.0 if perdeu else None),
                         "cb": case.advogado_responsavel_id})
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    logger.warning(f"[case_intel] Tese não criada ({case_id}): {str(e)[:120]}")
            logger.info(f"[case_intel] Aprendizado de encerramento registrado: {case_id}")
    except Exception as e:
        logger.warning(f"[case_intel] Falha no aprendizado de encerramento {case_id}: {str(e)[:200]}")


# ── ETAPA 2 + Módulo 6 — indexar PEÇA INTERNA na RAG (produção do escritório) ─
# Ao criar/revisar uma peça: classifica (área/assunto/tese) e indexa na Base RAG
# como conhecimento INTERNO (prioridade máxima na busca). Sanitiza PII (LGPD).
# Reutiliza upsert_documento (chunk + embeddings + dedup por hash + rastreabilidade).
SYS_CLASSIFICAR = (
    "Classifique a peça jurídica abaixo. Responda APENAS JSON válido com as chaves: "
    '{"area": "<área do direito>", "assunto": "<tema em poucas palavras>", '
    '"tese": "<tese central da peça, 1 frase>", "palavras_chave": ["...", "..."]}. '
    "Baseie-se só no texto."
)


async def indexar_peca_rag(legal_doc_id: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            d = await db.get(LegalDoc, legal_doc_id)
            if not d or d.deleted_at is not None:
                return
            conteudo = (d.conteudo or "").strip()
            if len(conteudo) < 50:
                return

            # Escopo de isolamento (Fase 3B) + nomes a proteger na sanitização.
            client_id = None
            nomes_proteger: list[str] = []
            if d.case_id:
                caso = await db.get(Case, d.case_id)
                if caso:
                    client_id = caso.client_id
                    if getattr(caso, "parte_contraria", None):
                        nomes_proteger.append(caso.parte_contraria)
                    if caso.client_id:
                        cli = await db.get(Client, caso.client_id)
                        if cli:
                            for n in (getattr(cli, "nome", None),
                                      getattr(cli, "razao_social", None),
                                      getattr(cli, "nome_fantasia", None)):
                                if n:
                                    nomes_proteger.append(n)

            # LGPD — NUNCA indexar PII na RAG. Mascara também nomes próprios
            # (cliente, parte contrária) — antes a indexação vazava nomes
            # identificáveis na base GLOBAL (laudo RAG-02).
            limpo, _ = sanitizar_pii(conteudo, nomes_proteger or None)

            meta: dict = {
                "tipo_peca": getattr(d.tipo_peca, "value", None) or str(d.tipo_peca or ""),
                "case_id": d.case_id,
                "human_reviewed": bool(getattr(d, "human_reviewed", False)),
                "fonte_tipo": "producao_interna",
            }
            # Módulo 6 — classificação automática (best effort).
            if settings.AI_ENABLED:
                try:
                    bruto, _resp = await _gateway_json(
                        SYS_CLASSIFICAR, limpo[:6000], task_type="analise_juridica",
                        temperature=0.05, max_tokens=600, nivel="alto",
                    )
                    cls = _parse_json(bruto)
                    if cls:
                        meta.update({k: cls.get(k) for k in ("area", "assunto", "tese", "palavras_chave")})
                except Exception as e:
                    logger.warning(f"[case_intel] Classificação da peça falhou: {str(e)[:120]}")

            res = await upsert_documento(
                db, titulo=(d.titulo or f"Peça {legal_doc_id[:8]}"),
                categoria="peca_interna", conteudo=limpo,
                chave_origem=f"legaldoc:{d.id}", fonte="escritorio", extra=meta,
                client_id=client_id, case_id=d.case_id,
            )
            await db.commit()
            logger.info(f"[case_intel] Peça indexada na RAG ({res}): {legal_doc_id}")
    except Exception as e:
        logger.warning(f"[case_intel] Falha ao indexar peça {legal_doc_id}: {str(e)[:200]}")
