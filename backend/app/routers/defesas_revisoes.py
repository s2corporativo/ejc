"""Módulo unificado de Defesas e Revisões com Entrada Universal."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.document_intake import DocumentIntakeBatch
from app.models.user import User
from app.services.ai.core.orchestrator import orchestrator
from app.services.entrada_universal_service import expandir_arquivo, extrair_paginas, montar_dossie
from app.services.motor_peca_service import CATALOGO_PECAS

router = APIRouter(prefix="/defesas-revisoes", tags=["Defesas e Revisões"])

JURIDICO_ROLES = {
    "superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario",
}
ADVOGADO_ROLES = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}
# O Motor de Peça usa o limiar advogado+: o advogado_auxiliar participa da
# análise, mas não encaminha redação sem revisão do responsável. Subconjunto
# PRÓPRIO do módulo — nunca mutar ADVOGADO_ROLES (compartilhado) no import.
ROLES_MOTOR_PECA = ADVOGADO_ROLES - {"advogado_auxiliar"}

MODALIDADES: dict[str, dict[str, Any]] = {
    "multa_transito": {
        "titulo": "Recurso de multa de trânsito", "area": "transito",
        "descricao": "Defesa prévia, JARI, CETRAN e processo de suspensão/cassação.",
        "pecas": ["defesa_administrativa", "recurso_administrativo", "mandado_seguranca"],
        "documentos": ["notificação de autuação ou penalidade", "auto de infração", "documento do veículo e do condutor", "provas do local, sinalização e circunstâncias"],
        "diretriz": "Diferencie autuação, penalidade, decisão da JARI, suspensão e cassação. Extraia o prazo da notificação e nunca presuma data fatal.",
    },
    "multa_ambiental": {
        "titulo": "Defesa ou recurso de multa ambiental", "area": "ambiental",
        "descricao": "Autos federais, estaduais ou municipais, embargo e medidas correlatas.",
        "pecas": ["recurso_administrativo", "defesa_administrativa_ambiental", "mandado_seguranca"],
        "documentos": ["auto de infração e relatório de fiscalização", "notificação e comprovante da ciência", "laudos, fotografias, licenças e autorizações", "processo administrativo integral"],
        "diretriz": "Diferencie norma federal, estadual e municipal. Prazo, rito e autoridade dependem da norma específica e da notificação.",
    },
    "multa_administrativa": {
        "titulo": "Defesa ou recurso administrativo", "area": "administrativo",
        "descricao": "Autos e sanções de órgãos públicos, vigilância, MTE, contratos e PAD.",
        "pecas": ["defesa_administrativa", "recurso_administrativo", "mandado_seguranca"],
        "documentos": ["auto, notificação ou decisão recorrida", "norma e regulamento do órgão autuador", "processo administrativo integral", "documentos técnicos e prova da regularidade"],
        "diretriz": "A regra do órgão autuador prevalece. Verifique competência, motivação, contraditório, tipicidade, autoria, materialidade, dosimetria, prescrição e proporcionalidade.",
    },
    "revisao_contratual": {
        "titulo": "Revisão de contrato", "area": "contratual",
        "descricao": "Leitura de cláusulas, riscos, desequilíbrio, rescisão e recomposição.",
        "pecas": ["peticao_inicial", "notificacao", "parecer"],
        "documentos": ["contrato e aditivos", "comprovantes de execução e pagamentos", "comunicações entre as partes", "planilhas, notas fiscais e documentos do dano"],
        "diretriz": "Classifique a relação como civil, empresarial ou de consumo. Inventarie objeto, preço, reajuste, multa, rescisão, garantias, responsabilidade, foro, vigência e inadimplemento.",
    },
    "revisao_bancaria": {
        "titulo": "Revisão bancária e financeira", "area": "bancario",
        "descricao": "Juros, CET, capitalização, tarifas, seguros, encargos e saldo devedor.",
        "pecas": ["peticao_inicial", "notificacao", "parecer"],
        "documentos": ["contrato ou cédula de crédito", "planilha de evolução da dívida e extratos", "comprovantes de parcelas pagas", "CET informado, tarifas, seguros e demonstrativos"],
        "diretriz": "Extraia valor liberado, taxa mensal/anual, CET, parcelas, amortização, capitalização, IOF, seguros e tarifas. Abusividade é indício a validar por cálculo determinístico.",
    },
}

_SCHEMA = """
Responda APENAS com JSON válido:
{
  "tipo_documento": null, "fase": null, "area": null, "orgao_ou_instituicao": null, "resumo": null,
  "datas_eventos": [{"evento": null, "data": null, "documento": null, "pagina": null, "origem_literal": null, "confianca": 0.0}],
  "prazo": {"termo_inicial": null, "data_expressa_no_documento": null, "regra": "verificar", "contagem": "verificar", "dias": null, "requer_confirmacao_humana": true},
  "vicios_formais": [{"titulo": null, "fundamento": "verificar", "trecho_origem": null, "risco": "medio"}],
  "questoes_de_merito": [{"titulo": null, "analise": null, "risco": "medio"}],
  "teses": [{"titulo": null, "fundamento": "verificar", "fatos": [], "provas": [], "precedentes": [], "forca": 0, "risco": "medio", "contra_argumento": null, "resposta_ao_contra_argumento": null}],
  "juros_taxas": {"taxa_mensal": null, "taxa_anual": null, "cet": null, "capitalizacao": "indefinido", "sistema_amortizacao": null, "tarifas_seguros_encargos": [], "necessita_calculo_deterministico": false},
  "inventario_clausulas": [],
  "peca_recomendada": {"codigo": null, "nome": null, "justificativa": null, "alternativas": []},
  "checklist_obrigatorio": [{"item": null, "status": "confirmar", "impeditivo": true, "fonte": null}],
  "documentos_faltantes": [],
  "estrategias_alternativas": {"principal": null, "conservadora": null, "agressiva": null, "extrajudicial": null, "subsidiaria": null},
  "estrategia": {"objetivo_principal": null, "pedidos_principais": [], "pedidos_subsidiarios": [], "provas_prioritarias": [], "riscos": [], "proximos_passos": []},
  "alertas": []
}
"""


def _role_value(user: User) -> str:
    role = getattr(user, "role", "")
    return role.value if hasattr(role, "value") else str(role)


def _exigir_juridico(user: User) -> None:
    if _role_value(user) not in JURIDICO_ROLES:
        raise HTTPException(403, "Acesso restrito à equipe jurídica")


def _parse_json(texto: str) -> Optional[dict]:
    if not texto:
        return None
    try:
        obj = json.loads(texto)
        return obj if isinstance(obj, dict) else None
    except Exception:
        match = re.search(r"\{.*\}", texto, re.DOTALL)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None


def _lista(value: Any) -> list:
    return value if isinstance(value, list) else []


def _fallback_peca(modalidade: str, resultado: dict) -> str:
    cfg = MODALIDADES[modalidade]
    if modalidade == "multa_ambiental":
        orgao = str(resultado.get("orgao_ou_instituicao") or "").lower()
        fase = str(resultado.get("fase") or "").lower()
        if "ibama" in orgao and "defesa" in fase:
            return "defesa_administrativa_ambiental"
        return "recurso_administrativo"
    return cfg["pecas"][0]


def _normalizar_resultado(modalidade: str, data: Optional[dict], bruto: str) -> dict:
    cfg = MODALIDADES[modalidade]
    resultado = dict(data) if isinstance(data, dict) else {
        "resumo": bruto[:4000],
        "alertas": ["A resposta não veio em JSON estruturado; revisar integralmente."],
    }
    resultado["area"] = cfg["area"]
    for chave in (
        "datas_eventos", "vicios_formais", "questoes_de_merito", "teses",
        "inventario_clausulas", "checklist_obrigatorio", "documentos_faltantes", "alertas",
    ):
        resultado[chave] = _lista(resultado.get(chave))

    peca = resultado.get("peca_recomendada")
    if not isinstance(peca, dict):
        peca = {}
    codigo = str(peca.get("codigo") or "").strip()
    if codigo not in cfg["pecas"]:
        codigo = _fallback_peca(modalidade, resultado)
        peca = {
            "codigo": codigo,
            "nome": codigo.replace("_", " ").title(),
            "justificativa": "Providência inicial segura do catálogo; confirmar órgão, fase, documentos e prazo.",
            "alternativas": [],
        }
    else:
        peca["codigo"] = codigo
        peca["nome"] = str(peca.get("nome") or codigo.replace("_", " ").title())
        peca["alternativas"] = _lista(peca.get("alternativas"))
    resultado["peca_recomendada"] = peca
    resultado["motor_peca_codigo"] = codigo if codigo in CATALOGO_PECAS else None
    resultado["documentos_recomendados"] = cfg["documentos"]
    resultado["modalidade"] = modalidade
    resultado["status"] = "rascunho"
    resultado["revisao_obrigatoria"] = True

    impeditivos = [
        item for item in resultado["checklist_obrigatorio"]
        if isinstance(item, dict) and item.get("impeditivo") and item.get("status") != "atendido"
    ]
    if impeditivos or resultado["documentos_faltantes"]:
        completude = "nao_apto_para_redacao"
    elif resultado["checklist_obrigatorio"]:
        completude = "apto_para_redacao"
    else:
        completude = "apto_com_ressalvas"
    resultado["completude_juridica"] = {
        "nivel": completude,
        "impeditivos": impeditivos,
        "pode_gerar_peca": completude != "nao_apto_para_redacao",
    }
    resultado["matriz_teses"] = [
        {
            "tipo": "formal" if origem == "vicios_formais" else "merito",
            "tese": item.get("titulo") or "Tese a confirmar",
            "fatos": _lista(item.get("fatos")),
            "provas": _lista(item.get("provas")),
            "fundamento": item.get("fundamento") or "verificar",
            "precedentes": _lista(item.get("precedentes")),
            "forca": item.get("forca"),
            "risco": item.get("risco") or "medio",
            "contra_argumento": item.get("contra_argumento"),
            "resposta": item.get("resposta_ao_contra_argumento"),
        }
        for origem in ("vicios_formais", "teses")
        for item in resultado[origem]
        if isinstance(item, dict)
    ]
    return resultado


async def _texto_upload(file: UploadFile) -> str:
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "Arquivo vazio")
    try:
        virtuais = expandir_arquivo(file.filename or "documento", raw, file.content_type)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
    itens = []
    for ordem, virtual in enumerate(virtuais, 1):
        try:
            # OCR em thread (não bloqueia o event loop) — mesmo padrão de documents.upload.
            meta = await asyncio.to_thread(
                extrair_paginas, virtual["conteudo"], virtual["extensao"], virtual["mimetype"]
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        itens.append({"filename": virtual["nome"], "source_order": ordem, "extraction_meta": meta, "classification": {}})
    return montar_dossie(itens)


async def _obter_lote(db: AsyncSession, cu: User, batch_id: str) -> tuple[DocumentIntakeBatch, dict[str, Any]]:
    batch = (await db.execute(select(DocumentIntakeBatch).where(DocumentIntakeBatch.id == batch_id))).scalar_one_or_none()
    if not batch:
        raise HTTPException(404, "Lote da Entrada Universal não encontrado")
    if batch.case_id:
        await verificar_acesso_caso(db, cu, batch.case_id)
    elif not is_gestao(cu) and batch.created_by != cu.id:
        raise HTTPException(403, "Sem permissão para este lote")
    return batch, dict(batch.resultado or {})


@router.get("/meta")
async def meta(cu: User = Depends(get_current_user)):
    _exigir_juridico(cu)
    return {
        "modalidades": [
            {
                "codigo": codigo, "titulo": cfg["titulo"], "area": cfg["area"],
                "descricao": cfg["descricao"], "pecas": cfg["pecas"], "documentos": cfg["documentos"],
            }
            for codigo, cfg in MODALIDADES.items()
        ],
        "entrada_universal_obrigatoria": True,
        "pode_usar_motor_peca": _role_value(cu) in ROLES_MOTOR_PECA,
        "aviso": "Toda análise é rascunho e depende de revisão do advogado responsável.",
    }


@router.post("/analisar", dependencies=[Depends(rate_limit("defesas-revisoes-analisar", 8))])
async def analisar(
    modalidade: str = Form(...),
    case_id: Optional[str] = Form(None),
    batch_id: Optional[str] = Form(None),
    texto: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_juridico(cu)
    if modalidade not in MODALIDADES:
        raise HTTPException(422, f"Modalidade inválida. Use: {', '.join(MODALIDADES)}")
    if case_id:
        await verificar_acesso_caso(db, cu, case_id)

    universal: dict[str, Any] = {}
    conteudo = (texto or "").strip()
    if batch_id:
        batch, universal = await _obter_lote(db, cu, batch_id)
        if case_id and batch.case_id and case_id != batch.case_id:
            raise HTTPException(422, "O lote pertence a outro caso")
        conteudo = f"{conteudo}\n\n{universal.get('texto_consolidado') or ''}".strip()
    if file is not None:
        conteudo = f"{conteudo}\n\n{await _texto_upload(file)}".strip()
    if len(conteudo) < 80:
        raise HTTPException(422, "Importe documentos legíveis pela Entrada Universal ou cole o texto")

    cfg = MODALIDADES[modalidade]
    prontidao = universal.get("prontidao") or {}
    mensagem = (
        "Atue como advogado brasileiro sênior, jurista e revisor técnico. Analise o pacote documental abaixo.\n\n"
        f"MODALIDADE: {cfg['titulo']}\nÁREA CANÔNICA: {cfg['area']}\nPEÇAS PERMITIDAS: {', '.join(cfg['pecas'])}\n"
        f"DIRETRIZ ESPECIAL: {cfg['diretriz']}\n"
        f"PRONTIDÃO DETERMINÍSTICA: {json.dumps(prontidao, ensure_ascii=False)[:6000]}\n"
        f"COMPARAÇÕES DOCUMENTAIS: {json.dumps(universal.get('comparacoes') or [], ensure_ascii=False)[:6000]}\n\n"
        "REGRAS: cite documento e página; não invente dados, prazo, lei ou precedente; diferencie fato e inferência; "
        "separe vícios formais de mérito; vincule tese, fato, prova, fundamento e precedente; apresente estratégias "
        "principal, conservadora, agressiva, extrajudicial e subsidiária; escolha somente peça permitida; se não apto, "
        "bloqueie a peça; abusividade bancária depende de cálculo determinístico.\n"
        f"{_SCHEMA}\n\nPACOTE DOCUMENTAL:\n{conteudo[:42000]}"
    )
    nucleo = await orchestrator.run(
        db=db, user=cu, task_type="document_analysis", domain=f"defesas_revisoes:{modalidade}",
        mensagem=mensagem, case_id=case_id, usar_rag=True, nivel_inteligencia="alto",
    )
    bruto = str(nucleo.get("conteudo") or "")
    resultado = _normalizar_resultado(modalidade, _parse_json(bruto), bruto)
    faltantes = list(dict.fromkeys(_lista(universal.get("documentos_faltantes")) + resultado["documentos_faltantes"]))
    resultado.update({
        "batch_id": batch_id,
        "nivel_prontidao": universal.get("nivel_prontidao") or resultado["completude_juridica"]["nivel"],
        "prontidao": prontidao,
        "documentos_importados": _lista(universal.get("documentos")),
        "comparacoes": _lista(universal.get("comparacoes")),
        "pacote": _lista(universal.get("pacote")),
        "documentos_faltantes": faltantes,
        "fontes": _lista(nucleo.get("fontes")),
        "citacoes": _lista(nucleo.get("citacoes")),
        "alertas_nucleo": _lista(nucleo.get("alertas")),
        "critica_adversarial": nucleo.get("critica_adversarial"),
        "sem_base_verificavel": bool(nucleo.get("sem_base_verificavel", False)),
        "modelo": nucleo.get("modelo"), "provider": nucleo.get("provider"), "log_id": nucleo.get("log_id"),
        "aviso": "Análise gerada como rascunho. Confirme originais, páginas, datas, prazo, enquadramento, provas, cálculos, fontes e peça.",
    })
    if resultado.get("nivel_prontidao") == "nao_apto_para_redacao" or faltantes:
        resultado["motor_peca_codigo"] = None
        resultado["completude_juridica"]["nivel"] = "nao_apto_para_redacao"
        resultado["completude_juridica"]["pode_gerar_peca"] = False
        resultado.setdefault("alertas", []).append("Geração da peça bloqueada: resolva as pendências documentais impeditivas.")
    return resultado
