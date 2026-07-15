"""Seleção contextual e classificação local para as AI Skills do EJC.

Este módulo não cria uma nova área funcional. Ele traduz o contexto das telas
existentes (caso, documentos, prazos, audiências, finanças e teses) em uma lista
curta de skills já cadastradas. A classificação é determinística, auditável e
não envia conteúdo a provedor externo.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def _normalizar(valor: str | None) -> str:
    texto = unicodedata.normalize("NFKD", valor or "")
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


_AREA_ALIASES = {
    "civil": "civel",
    "civel-e-processual": "civel",
    "direito-civil": "civel",
    "direito-do-consumidor": "consumidor",
    "familia-e-sucessoes": "familia",
    "imobiliario-e-posse": "imobiliario",
    "penal-e-defesa-criminal": "penal",
    "previdenciario-inss": "previdenciario",
    "saude": "saude",
    "trabalhista-ia": "trabalhista",
    "tributario-e-cobranca": "tributario",
}


def normalizar_area(area: str | None) -> str:
    chave = _normalizar(area)
    return _AREA_ALIASES.get(chave, chave)


_SURFACE_GROUP = {
    "resumo": "visao",
    "processos": "visao",
    "timeline": "visao",
    "score": "visao",
    "risco": "visao",
    "dossie": "visao",
    "iadefensiva": "visao",
    "ferramentas": "visao",
    "mensagens": "cliente",
    "partes": "cliente",
    "etiquetas": "organizacao",
    "checklists": "organizacao",
    "documentos": "documentos",
    "contratos": "documentos",
    "procuracoes": "documentos",
    "provas": "provas",
    "prazos": "prazos",
    "audiencias": "audiencias",
    "financeiro": "financeiro",
    "custos": "financeiro",
    "liquidez": "financeiro",
    "teses": "teses",
    "teses-sugeridas": "teses",
    "jurisprudencia": "teses",
    "precedentes": "teses",
    "memoria": "teses",
}


_SURFACE_SKILLS = {
    "visao": [
        "raio-x-processual",
        "sintese-processo",
        "casador-de-fatos",
        "detector-contradicoes",
        "auditor-pedidos",
        "simulador-defesa-adversarial",
    ],
    "cliente": [
        "assistente-reuniao",
        "dicionario-estrategico",
        "casador-de-fatos",
        "gerador-notificacao-extrajudicial",
    ],
    "organizacao": [
        "raio-x-processual",
        "sintese-processo",
        "prescricao-decadencia",
        "auditor-pedidos",
    ],
    "documentos": [
        "scanner-anti-sabotagem",
        "revisor-contratos",
        "sintese-processo",
        "raio-x-processual",
        "embargos-declaracao",
    ],
    "provas": [
        "detector-contradicoes",
        "casador-de-fatos",
        "detetive-prints",
        "desmistificador-laudos",
        "scanner-anti-sabotagem",
    ],
    "prazos": [
        "prescricao-decadencia",
        "raio-x-processual",
        "embargos-declaracao",
        "tutelas-liminares",
    ],
    "audiencias": [
        "roteirista-audiencia",
        "transcritor-midias-audiencia",
        "assistente-reuniao",
        "detector-contradicoes",
        "memoriais-alegacoes-finais",
    ],
    "financeiro": [
        "proposta-honorarios",
        "superendividamento-repactuacao",
        "revisional-juros-bancarios",
        "auditoria-atrasados-inss",
        "impugnacao-liquidacao-trabalhista",
    ],
    "teses": [
        "validador-teses-precedentes",
        "validador-teses",
        "distinguishing-precedentes",
        "distinguishing",
        "raio-x-processual",
        "simulador-defesa-adversarial",
    ],
}


_AREA_SKILLS = {
    "civel": ["raio-x-processual", "auditor-pedidos", "tutela-urgencia"],
    "consumidor": ["consumidor-bancario", "negativacao-indevida", "vicio-defeito-produto-servico"],
    "familia": ["divorcio-uniao-estavel-partilha", "acao-alimentos", "guarda-convivencia"],
    "imobiliario": ["acao-despejo", "acao-usucapiao", "acao-possessoria"],
    "penal": ["contraponto-penal", "resposta-acusacao", "raio-x-inquerito"],
    "previdenciario": ["raio-x-cnis", "indeferimento-recurso-inss", "incapacidade-previdenciaria"],
    "saude": ["plano-saude-negativa-liminar", "execucao-decisao-saude", "liminar-saude"],
    "trabalhista": ["contestacao-trabalhista", "reclamacao-trabalhista", "mapa-risco-condenacao-trabalhista"],
    "tributario": ["raio-x-cda", "defesa-administrativa-tributaria", "excecao-pre-executividade"],
}


@dataclass(frozen=True)
class RegraDocumento:
    tipo: str
    termos: tuple[str, ...]
    skills: tuple[str, ...]
    surface: str


_REGRAS_DOCUMENTO = (
    RegraDocumento("contestacao", ("contestacao", "preliminarmente", "impugnacao especifica"), ("maquina-replica", "detector-contradicoes", "replica-estrategica"), "documentos"),
    RegraDocumento("peticao_inicial", ("peticao inicial", "dos fatos", "dos pedidos", "requer a citacao"), ("auditor-pedidos", "simulador-defesa-adversarial", "raio-x-processual"), "documentos"),
    RegraDocumento("decisao_judicial", ("sentenca", "acordao", "decisao interlocutoria", "julgo", "dispositivo"), ("embargos-declaracao", "maquina-recursos", "auditoria-recurso"), "documentos"),
    RegraDocumento("recurso", ("razoes recursais", "apelacao", "agravo", "recurso ordinario", "recurso de revista"), ("contrarrazoes-recursais", "auditoria-recurso", "validador-teses-precedentes"), "documentos"),
    RegraDocumento("intimacao", ("intimacao", "fica intimado", "diario da justica", "prazo de"), ("prescricao-decadencia", "raio-x-processual"), "prazos"),
    RegraDocumento("contrato", ("contrato", "contratante", "contratada", "clausula", "objeto do contrato"), ("revisor-contratos", "minuta-acordo", "simulador-defesa-adversarial"), "documentos"),
    RegraDocumento("laudo_pericial", ("laudo pericial", "perito", "quesitos", "conclusao pericial"), ("desmistificador-laudos", "detector-contradicoes", "incapacidade-quesitos"), "provas"),
    RegraDocumento("audiencia", ("ata de audiencia", "depoimento", "testemunha", "termo de audiencia"), ("detector-contradicoes", "roteirista-audiencia", "memoriais-alegacoes-finais"), "audiencias"),
    RegraDocumento("inquerito", ("inquerito policial", "auto de prisao", "autoridade policial", "indiciado"), ("raio-x-inquerito", "contraponto-penal", "resposta-acusacao"), "provas"),
    RegraDocumento("cnis", ("cnis", "cadastro nacional de informacoes sociais", "nit", "indicador previdenciario"), ("raio-x-cnis", "indeferimento-recurso-inss"), "provas"),
    RegraDocumento("ppp", ("perfil profissiografico previdenciario", "ppp", "agente nocivo", "ltcat"), ("raio-x-ppp", "desmistificador-laudos"), "provas"),
)


def classificar_documento(filename: str | None, texto: str | None) -> dict[str, Any]:
    """Classifica sem IA e retorna apenas sinais auditáveis, nunca trechos."""
    nome = _normalizar(Path(filename or "documento").stem).replace("-", " ")
    corpo = _normalizar((texto or "")[:30_000]).replace("-", " ")
    base = f"{nome} {corpo}"
    candidatos: list[tuple[int, RegraDocumento, list[str]]] = []
    for regra in _REGRAS_DOCUMENTO:
        encontrados = [termo for termo in regra.termos if termo in base]
        if encontrados:
            pontos = len(encontrados) * 2 + (2 if any(t in nome for t in encontrados) else 0)
            candidatos.append((pontos, regra, encontrados[:4]))
    if not candidatos:
        return {
            "tipo": "documento_juridico",
            "confianca": 0.35,
            "sinais": ["nenhum marcador específico encontrado"],
            "surface_sugerida": "documentos",
            "skills_sugeridas": ["raio-x-processual", "sintese-processo", "scanner-anti-sabotagem"],
            "metodo": "regras_locais_v1",
        }
    pontos, regra, sinais = max(candidatos, key=lambda item: item[0])
    return {
        "tipo": regra.tipo,
        "confianca": min(0.96, 0.48 + pontos * 0.08),
        "sinais": sinais,
        "surface_sugerida": regra.surface,
        "skills_sugeridas": list(regra.skills),
        "metodo": "regras_locais_v1",
    }


def _atributo(skill: Any, nome: str, padrao: Any = None) -> Any:
    if isinstance(skill, dict):
        return skill.get(nome, padrao)
    return getattr(skill, nome, padrao)


def ranquear_skills_contextuais(
    skills: Iterable[Any],
    *,
    surface: str | None,
    area: str | None,
    phase: str | None = None,
    document_type: str | None = None,
    document_skills: Iterable[str] | None = None,
    has_case: bool = True,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Ranqueia o catálogo existente e devolve uma lista pequena e explicável."""
    surface_key = _normalizar(surface).replace("-", "")
    grupo = _SURFACE_GROUP.get(surface_key, _SURFACE_GROUP.get(_normalizar(surface), "visao"))
    area_key = normalizar_area(area)
    preferidas = list(document_skills or [])
    preferidas += _SURFACE_SKILLS.get(grupo, [])
    preferidas += _AREA_SKILLS.get(area_key, [])
    preferidas = list(dict.fromkeys(preferidas))
    indice = {nome: pos for pos, nome in enumerate(preferidas)}
    fase = _normalizar(phase)
    tipo_doc = _normalizar(document_type)

    avaliadas: list[dict[str, Any]] = []
    for skill in skills:
        nome = str(_atributo(skill, "name", ""))
        if not nome or (not has_case and bool(_atributo(skill, "requires_case", False))):
            continue
        skill_area = normalizar_area(str(_atributo(skill, "area", "")))
        score = 0
        motivos: list[str] = []
        if nome in indice:
            score += max(35, 120 - indice[nome] * 7)
            motivos.append("adequada à etapa atual")
        if area_key and skill_area == area_key:
            score += 45
            motivos.append(f"especializada em {area_key}")
        elif skill_area in {"juridico", "estrategia", "provas"}:
            score += 12
        termos = _normalizar(
            f"{_atributo(skill, 'display_name', '')} {_atributo(skill, 'description', '')}"
        )
        if fase and fase in termos:
            score += 10
            motivos.append("compatível com a fase")
        if tipo_doc and tipo_doc in termos:
            score += 12
            motivos.append("compatível com o documento")
        if score <= 0:
            continue
        avaliadas.append({"skill": skill, "score": score, "reason": "; ".join(motivos[:2]) or "ação geral"})
    avaliadas.sort(
        key=lambda item: (
            -item["score"],
            str(_atributo(item["skill"], "display_name", "")),
        )
    )
    return avaliadas[: max(1, min(limit, 8))]


_NEXT_ACTIONS = {
    "raio-x-processual": ["casador-de-fatos", "detector-contradicoes", "auditor-pedidos"],
    "sintese-processo": ["casador-de-fatos", "raio-x-processual", "prescricao-decadencia"],
    "casador-de-fatos": ["validador-teses-precedentes", "simulador-defesa-adversarial"],
    "detector-contradicoes": ["replica-estrategica", "roteirista-audiencia", "maquina-recursos"],
    "auditor-pedidos": ["simulador-defesa-adversarial", "tutela-urgencia"],
    "contestacao-trabalhista": ["replica-trabalhista", "mapa-risco-condenacao-trabalhista"],
    "contestacao-trabalhista-ia": ["replica-trabalhista", "simulador-defesa-adversarial"],
    "maquina-replica": ["detector-contradicoes", "simulador-defesa-adversarial"],
    "replica-estrategica": ["simulador-defesa-adversarial", "validador-teses-precedentes"],
    "embargos-declaracao": ["auditoria-recurso", "validador-teses-precedentes"],
    "maquina-recursos": ["validador-teses-precedentes", "contrarrazoes-recursais"],
    "revisor-contratos": ["minuta-acordo", "simulador-defesa-adversarial"],
    "transcritor-midias-audiencia": ["detector-contradicoes", "memoriais-alegacoes-finais"],
}


def proximas_skills(skill_name: str | None) -> list[str]:
    nome = _normalizar(skill_name)
    if nome in _NEXT_ACTIONS:
        return list(_NEXT_ACTIONS[nome])
    if any(t in nome for t in ("recurso", "agravo", "embargos")):
        return ["validador-teses-precedentes", "simulador-defesa-adversarial"]
    if any(t in nome for t in ("raio-x", "auditoria", "scanner", "detector")):
        return ["casador-de-fatos", "simulador-defesa-adversarial"]
    return ["simulador-defesa-adversarial", "validador-teses-precedentes"]
