"""Enriquecimento determinístico do relatório preliminar do Raio-X.

O módulo consolida estruturas já extraídas do documento sem transformar
inferência em fato. Toda saída mantém a fonte, indica correlação aproximada e
exige validação humana antes de produzir efeitos no caso oficial.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date
from typing import Any, Iterable

from app.services.rito_engine import identificar_rito


def valor(campo: Any) -> Any:
    if isinstance(campo, dict):
        for key in ("valor", "value", "texto", "descricao", "conteudo"):
            if key in campo:
                return campo.get(key)
    return campo


def lista(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def normalizar(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(valor(value) or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", text)).strip().lower()


def data_iso(value: Any) -> str | None:
    raw = str(valor(value) or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    match = re.search(r"(\d{4})[./-](\d{2})[./-](\d{2})", raw)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


def unicos(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for item in values:
        key = normalizar(item)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _tokens(value: Any) -> set[str]:
    stop = {
        "para", "com", "sem", "uma", "que", "dos", "das", "por", "em", "de", "do", "da",
        "ao", "aos", "as", "os", "no", "na", "nos", "nas", "foi", "sao", "ser", "seu",
        "sua", "como", "mais", "processo", "documento", "parte",
    }
    return {token for token in normalizar(value).split() if len(token) >= 4 and token not in stop}


def _origem(doc: Any, item: Any | None = None) -> dict[str, Any]:
    source = {
        "documento_id": getattr(doc, "id", None),
        "arquivo": getattr(doc, "nome_original", None),
        "tipo": getattr(doc, "tipo_documento", None),
        "hash": getattr(doc, "sha256", None),
    }
    if isinstance(item, dict):
        source["pagina"] = item.get("pagina") or item.get("page")
        source["trecho"] = item.get("trecho_origem") or item.get("trecho") or item.get("fonte")
    return source


def _intake(doc: Any) -> dict[str, Any]:
    result = getattr(doc, "resultado_analise", None) or {}
    intake = result.get("intake_result") or result
    return intake if isinstance(intake, dict) else {}


def _coletar(documentos: list[Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for doc in documentos:
        intake = _intake(doc)
        result = getattr(doc, "resultado_analise", None) or {}
        containers = [intake, result]
        for container in containers:
            for key in keys:
                for item in lista(container.get(key)):
                    if item in (None, "", []):
                        continue
                    output.append({"item": item, "origem": _origem(doc, item)})
    return output


def _texto_item(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("fato", "alegacao", "descricao", "titulo", "evento", "texto", "valor", "pedido", "risco"):
            if item.get(key):
                return str(valor(item.get(key)))
        return "; ".join(f"{key}: {valor(val)}" for key, val in item.items() if val not in (None, "", [], {}))
    return str(valor(item) or "")


def construir_matriz_fatos_provas(documentos: list[Any]) -> list[dict[str, Any]]:
    fatos = _coletar(documentos, ("fatos", "alegacoes", "fatos_alegados", "resumo_fatos"))
    provas = _coletar(documentos, ("provas", "documentos_probatorios", "evidencias"))
    if not fatos:
        for doc in documentos:
            intake = _intake(doc)
            resumo = valor(intake.get("resumo_fatos"))
            if resumo:
                fatos.append({"item": resumo, "origem": _origem(doc)})

    matrix: list[dict[str, Any]] = []
    for fato in fatos:
        fato_text = _texto_item(fato["item"])
        fato_tokens = _tokens(fato_text)
        matches: list[tuple[float, dict[str, Any]]] = []
        for prova in provas:
            prova_text = _texto_item(prova["item"])
            prova_tokens = _tokens(prova_text)
            if not fato_tokens or not prova_tokens:
                continue
            overlap = len(fato_tokens & prova_tokens) / max(1, len(fato_tokens | prova_tokens))
            if overlap >= 0.08:
                matches.append((overlap, prova))
        matches.sort(key=lambda pair: pair[0], reverse=True)
        related = [
            {
                "prova": _texto_item(prova["item"]),
                "origem": prova["origem"],
                "aderencia_lexical": round(score, 2),
                "forca_aparente": "moderada" if score >= 0.25 else "baixa",
            }
            for score, prova in matches[:4]
        ]
        matrix.append({
            "fato": fato_text,
            "origem_fato": fato["origem"],
            "provas_relacionadas": related,
            "estado": "correlacao_localizada" if related else "sem_prova_correlacionada",
            "observacao": (
                "Correlação lexical preliminar; o advogado deve verificar autenticidade, admissibilidade e força probatória."
                if related else
                "Nenhuma prova foi correlacionada automaticamente; verificar documentos e esclarecer o fato."
            ),
            "confirmado": False,
        })
    return unicos(matrix)


def construir_cronologia(documentos: list[Any]) -> list[dict[str, Any]]:
    eventos = _coletar(documentos, ("cronologia", "eventos", "movimentacoes", "andamentos", "decisoes", "prazos"))
    output: list[dict[str, Any]] = []
    for wrapper in eventos:
        item = wrapper["item"]
        if isinstance(item, dict):
            when = data_iso(
                item.get("data") or item.get("data_evento") or item.get("termo_final")
                or item.get("data_prazo") or item.get("publicacao")
            )
            event = _texto_item(item)
            actor = valor(item.get("responsavel") or item.get("autor") or item.get("ator") or item.get("orgao"))
            consequence = valor(item.get("consequencia") or item.get("providencia") or item.get("resultado"))
        else:
            when = data_iso(item)
            event = _texto_item(item)
            actor = None
            consequence = None
        output.append({
            "data": when,
            "evento": event,
            "responsavel": actor,
            "consequencia": consequence,
            "origem": wrapper["origem"],
            "confirmado": False,
        })
    output.sort(key=lambda item: (item.get("data") or "9999-12-31", normalizar(item.get("evento"))))
    return unicos(output)


def construir_decisoes(documentos: list[Any]) -> list[dict[str, Any]]:
    decisions = _coletar(documentos, ("decisoes", "sentencas", "acordaos", "determinacoes"))
    output: list[dict[str, Any]] = []
    for wrapper in decisions:
        item = wrapper["item"]
        if isinstance(item, dict):
            output.append({
                "tipo": valor(item.get("tipo") or item.get("classe") or "decisão"),
                "data": data_iso(item.get("data") or item.get("publicacao")),
                "fundamento": valor(item.get("fundamento") or item.get("fundamentos")),
                "comando": valor(item.get("comando") or item.get("dispositivo") or item.get("resultado") or item.get("descricao")),
                "obrigacao": valor(item.get("obrigacao") or item.get("providencia")),
                "prazo": valor(item.get("prazo")),
                "origem": wrapper["origem"],
                "confirmado": False,
            })
        else:
            output.append({
                "tipo": "decisão",
                "data": data_iso(item),
                "comando": _texto_item(item),
                "origem": wrapper["origem"],
                "confirmado": False,
            })
    return unicos(output)


def detectar_contradicoes_documentais(documentos: list[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    explicit = _coletar(documentos, ("contradicoes", "inconsistencias", "divergencias"))
    for wrapper in explicit:
        output.append({
            "tipo": "contradicao_extraida",
            "descricao": _texto_item(wrapper["item"]),
            "fontes": [wrapper["origem"]],
            "confirmado": False,
        })

    monitored = {
        "numero_processo": ("numero_processo",),
        "tribunal": ("tribunal",),
        "valor_causa": ("valor_causa", "valor", "valor_total"),
        "data_fato": ("data_fato", "data_evento"),
        "cliente": ("cliente",),
    }
    observed: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for doc in documentos:
        intake = _intake(doc)
        case_data = valor(intake.get("caso"))
        containers = [intake, case_data if isinstance(case_data, dict) else {}]
        for label, aliases in monitored.items():
            for container in containers:
                for alias in aliases:
                    candidate = valor(container.get(alias))
                    if candidate in (None, "", [], {}):
                        continue
                    observed[label][normalizar(candidate)].append({
                        "valor": candidate,
                        "origem": _origem(doc, container.get(alias)),
                    })
    for field, values in observed.items():
        if len(values) <= 1:
            continue
        output.append({
            "tipo": "divergencia_de_campo",
            "campo": field,
            "descricao": f"Foram encontrados valores divergentes para {field.replace('_', ' ')}.",
            "valores": [items[0]["valor"] for items in values.values()],
            "fontes": [item["origem"] for items in values.values() for item in items[:1]],
            "confirmado": False,
        })
    return unicos(output)


def avaliar_risco_urgencia(relatorio: dict[str, Any]) -> dict[str, Any]:
    score = 0
    motivos: list[str] = []
    urgent = False
    overdue = False
    today = date.today()

    for item in relatorio.get("prazos_potenciais", []):
        if not isinstance(item, dict):
            continue
        raw = data_iso(item.get("termo_final") or item.get("data") or item.get("data_prazo"))
        if not raw:
            score += 1
            motivos.append("Prazo mencionado sem termo final validado")
            continue
        try:
            delta = (date.fromisoformat(raw) - today).days
        except ValueError:
            continue
        if delta < 0:
            overdue = True
            urgent = True
            score += 5
            motivos.append("Há prazo documental aparentemente vencido; verificar imediatamente")
        elif delta <= 3:
            urgent = True
            score += 4
            motivos.append("Há prazo potencial em até 3 dias")
        elif delta <= 7:
            urgent = True
            score += 3
            motivos.append("Há prazo potencial em até 7 dias")
        elif delta <= 15:
            score += 1
            motivos.append("Há prazo potencial em até 15 dias")

    if relatorio.get("contradicoes"):
        score += 1
        motivos.append("Existem contradições ou divergências documentais")
    missing = relatorio.get("documentos_pendentes") or []
    if missing:
        score += min(3, len(missing))
        motivos.append("Há informações ou documentos essenciais pendentes")
    unproved = [item for item in relatorio.get("fatos_provas", []) if item.get("estado") == "sem_prova_correlacionada"]
    if unproved:
        score += min(3, len(unproved))
        motivos.append("Há fatos sem prova automaticamente correlacionada")

    text = normalizar(" ".join(str(item) for item in relatorio.get("riscos", [])))
    for marker in ("prescricao", "decadencia", "preclusao", "intempestividade", "suspensao", "cassacao", "prisao", "bloqueio"):
        if marker in text:
            score += 2
            motivos.append(f"Risco mencionado: {marker}")

    if overdue or score >= 8:
        level = "critico"
    elif score >= 5:
        level = "elevado"
    elif score >= 2:
        level = "moderado"
    else:
        level = "baixo"
    return {
        "risco_nivel": level,
        "prazo_urgente": urgent,
        "score_interno": score,
        "motivos": unicos(motivos),
        "aviso": "Classificação operacional interna; não representa probabilidade de êxito.",
    }


def enriquecer_relatorio(documentos: list[Any], base: dict[str, Any]) -> dict[str, Any]:
    matrix = construir_matriz_fatos_provas(documentos)
    chronology = construir_cronologia(documentos)
    decisions = construir_decisoes(documentos)
    contradictions = detectar_contradicoes_documentais(documentos)

    identification = base.get("identificacao") or {}
    rito_context = {
        **identification,
        "area": identification.get("area") or base.get("area"),
        "subarea": identification.get("subarea") or base.get("subarea"),
        "fase": identification.get("fase") or base.get("fase"),
        "tribunal": identification.get("tribunal") or base.get("tribunal"),
        "rito": identification.get("rito") or base.get("rito"),
        "resumo": base.get("sintese_executiva"),
        "pedidos": base.get("pedidos"),
        "decisoes": decisions,
        "eventos": chronology,
        "prazos": base.get("prazos_potenciais"),
    }
    rito = identificar_rito(rito_context)
    identification["rito"] = identification.get("rito") or rito.get("nome")
    identification["instancia"] = identification.get("instancia") or rito.get("instancia")
    identification["etapa_atual"] = rito.get("etapa_atual")

    base.update({
        "identificacao": identification,
        "cronologia": chronology,
        "fatos_provas": matrix,
        "contradicoes": contradictions,
        "decisoes": decisions,
        "rito_jornada": rito,
    })

    strengths: list[str] = []
    weaknesses: list[str] = list(base.get("pontos_fracos") or [])
    if decisions:
        strengths.append("Há decisão ou determinação identificada para análise do comando e dos efeitos.")
    supported = [item for item in matrix if item.get("estado") == "correlacao_localizada"]
    if supported:
        strengths.append(f"{len(supported)} fato(s) possuem prova(s) potencialmente relacionada(s).")
    unsupported = [item for item in matrix if item.get("estado") == "sem_prova_correlacionada"]
    if unsupported:
        weaknesses.append(f"{len(unsupported)} fato(s) permanecem sem prova correlacionada automaticamente.")
    if contradictions:
        weaknesses.append(f"Há {len(contradictions)} contradição(ões) ou divergência(s) a conferir.")
    base["pontos_fortes"] = unicos(strengths + list(base.get("pontos_fortes") or []))
    base["pontos_fracos"] = unicos(weaknesses)

    next_steps = list(base.get("proximos_passos") or [])
    next_steps.extend(rito.get("acoes_recomendadas") or [])
    if unsupported:
        next_steps.append("Solicitar ou localizar provas para os fatos sem suporte documental.")
    if contradictions:
        next_steps.append("Conferir e resolver divergências antes de definir a estratégia ou protocolar peça.")
    if base.get("prazos_potenciais"):
        next_steps.insert(0, "Validar imediatamente os termos inicial e final dos prazos identificados.")
    base["proximos_passos"] = unicos(next_steps)

    risk = avaliar_risco_urgencia(base)
    base["avaliacao_risco"] = risk
    base["risco_nivel"] = risk["risco_nivel"]
    base["prazo_urgente"] = risk["prazo_urgente"]
    base["confianca_global"] = (
        "moderada_com_revisao_obrigatoria"
        if base.get("fontes") and identification.get("numero_processo") and base.get("partes")
        else "insuficiente_para_automatizacao"
    )
    return base
