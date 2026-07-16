"""Seleção contextual e classificação local para as AI Skills do EJC.

Este módulo não cria uma nova área funcional. Ele traduz o contexto das telas
existentes em uma lista curta de skills já cadastradas. A classificação é
determinística, auditável e não envia conteúdo a provedor externo.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.services.rito_engine import identificar_rito


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
    "direito-das-sucessoes": "sucessoes",
    "imobiliario-e-posse": "imobiliario",
    "penal-e-defesa-criminal": "penal",
    "criminal": "penal",
    "previdenciario-inss": "previdenciario",
    "saude": "saude",
    "direito-da-saude": "saude",
    "trabalhista-ia": "trabalhista",
    "tributario-e-cobranca": "tributario",
    "direito-bancario": "bancario",
    "contratos-bancarios": "bancario",
    "direito-de-transito": "transito",
    "multas-de-transito": "transito",
    "direito-administrativo": "administrativo",
    "licitacoes-e-contratos": "administrativo",
    "direito-ambiental": "ambiental",
    "direito-empresarial": "empresarial",
    "direito-digital-e-lgpd": "digital_lgpd",
    "direito-constitucional": "constitucional",
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
        "raio-x-processual", "sintese-processo", "casador-de-fatos",
        "detector-contradicoes", "auditor-pedidos", "simulador-defesa-adversarial",
    ],
    "cliente": [
        "assistente-reuniao", "dicionario-estrategico", "casador-de-fatos",
        "gerador-notificacao-extrajudicial",
    ],
    "organizacao": [
        "raio-x-processual", "sintese-processo", "prescricao-decadencia", "auditor-pedidos",
    ],
    "documentos": [
        "scanner-anti-sabotagem", "revisor-contratos", "sintese-processo",
        "raio-x-processual", "embargos-declaracao",
    ],
    "provas": [
        "detector-contradicoes", "casador-de-fatos", "detetive-prints",
        "desmistificador-laudos", "scanner-anti-sabotagem",
    ],
    "prazos": [
        "prescricao-decadencia", "raio-x-processual", "embargos-declaracao", "tutelas-liminares",
    ],
    "audiencias": [
        "roteirista-audiencia", "transcritor-midias-audiencia", "assistente-reuniao",
        "detector-contradicoes", "memoriais-alegacoes-finais",
    ],
    "financeiro": [
        "proposta-honorarios", "superendividamento-repactuacao", "revisional-juros-bancarios",
        "auditoria-atrasados-inss", "impugnacao-liquidacao-trabalhista",
    ],
    "teses": [
        "validador-teses-precedentes", "validador-teses", "distinguishing-precedentes",
        "distinguishing", "raio-x-processual", "simulador-defesa-adversarial",
    ],
}


_AREA_SKILLS = {
    "civel": ["raio-x-processual", "auditor-pedidos", "tutela-urgencia"],
    "consumidor": ["consumidor-bancario", "negativacao-indevida", "vicio-defeito-produto-servico"],
    "familia": ["divorcio-uniao-estavel-partilha", "acao-alimentos", "guarda-convivencia"],
    "sucessoes": ["inventario-partilha", "raio-x-processual", "revisor-contratos"],
    "imobiliario": ["acao-despejo", "acao-usucapiao", "acao-possessoria"],
    "penal": ["contraponto-penal", "resposta-acusacao", "raio-x-inquerito"],
    "previdenciario": ["raio-x-cnis", "indeferimento-recurso-inss", "incapacidade-previdenciaria"],
    "saude": ["plano-saude-negativa-liminar", "execucao-decisao-saude", "liminar-saude"],
    "trabalhista": ["contestacao-trabalhista", "reclamacao-trabalhista", "mapa-risco-condenacao-trabalhista"],
    "tributario": ["raio-x-cda", "defesa-administrativa-tributaria", "excecao-pre-executividade"],
    "bancario": ["revisional-juros-bancarios", "consumidor-bancario", "revisor-contratos"],
    "transito": ["defesa-multa-transito", "recurso-jari-cetran", "prescricao-decadencia"],
    "administrativo": ["defesa-administrativa", "recurso-administrativo", "raio-x-processual"],
    "ambiental": ["defesa-auto-infracao-ambiental", "raio-x-processual", "desmistificador-laudos"],
    "empresarial": ["revisor-contratos", "simulador-defesa-adversarial", "gerador-notificacao-extrajudicial"],
    "digital_lgpd": ["scanner-anti-sabotagem", "detetive-prints", "gerador-notificacao-extrajudicial"],
    "constitucional": ["validador-teses-precedentes", "maquina-recursos", "tutelas-liminares"],
}


@dataclass(frozen=True)
class RegraDocumento:
    tipo: str
    termos: tuple[str, ...]
    skills: tuple[str, ...]
    surface: str
    area: str | None = None
    subarea: str | None = None
    rito: str | None = None
    campos_esperados: tuple[str, ...] = ()


_REGRAS_DOCUMENTO = (
    RegraDocumento(
        "multa_transito",
        ("auto de infracao de transito", "codigo da infracao", "renavam", "orgao autuador", "jari", "cetran", "identificacao do condutor"),
        ("defesa-multa-transito", "recurso-jari-cetran", "prescricao-decadencia"),
        "prazos", "transito", "multa de transito", "administrativo de transito",
        ("auto de infracao", "placa", "renavam", "enquadramento", "data", "prazo", "orgao autuador"),
    ),
    RegraDocumento(
        "suspensao_cnh",
        ("suspensao do direito de dirigir", "cassacao da cnh", "pontuacao", "carteira nacional de habilitacao"),
        ("defesa-multa-transito", "recurso-jari-cetran", "raio-x-processual"),
        "prazos", "transito", "suspensao ou cassacao", "administrativo de transito",
        ("condutor", "processo administrativo", "pontuacao", "prazo de defesa"),
    ),
    RegraDocumento(
        "contrato_bancario",
        ("custo efetivo total", "taxa efetiva", "instituicao financeira", "cedula de credito", "saldo devedor", "credito consignado", "sistema de amortizacao"),
        ("revisional-juros-bancarios", "consumidor-bancario", "revisor-contratos"),
        "financeiro", "bancario", "contrato bancario", "contratual ou consumerista",
        ("valor liberado", "parcelas", "taxa mensal", "taxa anual", "cet", "tarifas", "seguros", "saldo devedor"),
    ),
    RegraDocumento(
        "auto_infracao_ambiental",
        ("auto de infracao ambiental", "embargo ambiental", "apreensao", "orgao ambiental", "reparacao do dano ambiental"),
        ("defesa-auto-infracao-ambiental", "raio-x-processual", "desmistificador-laudos"),
        "prazos", "ambiental", "infracao ambiental", "administrativo ambiental",
        ("orgao", "numero do auto", "conduta", "enquadramento", "multa", "prazo", "area afetada"),
    ),
    RegraDocumento(
        "licitacao_contrato_administrativo",
        ("edital de licitacao", "pregao eletronico", "ata de registro de precos", "contrato administrativo", "nota de empenho", "sancao administrativa"),
        ("defesa-administrativa", "recurso-administrativo", "revisor-contratos"),
        "documentos", "administrativo", "licitacoes e contratos", "administrativo",
        ("orgao", "edital", "processo", "objeto", "item", "prazo", "sancao", "contrato"),
    ),
    RegraDocumento(
        "juizado_especial_civel",
        ("juizado especial civel", "recurso inominado", "turma recursal", "lei 9 099"),
        ("raio-x-processual", "embargos-declaracao", "maquina-recursos"),
        "documentos", "civel", "juizado especial", "Juizado Especial Cível",
        ("valor da causa", "competencia", "audiencia", "sentenca", "recurso inominado"),
    ),
    RegraDocumento(
        "juizado_especial_federal",
        ("juizado especial federal", "turma nacional de uniformizacao", "tnu", "lei 10 259"),
        ("raio-x-processual", "indeferimento-recurso-inss", "maquina-recursos"),
        "documentos", "previdenciario", "juizado especial federal", "Juizado Especial Federal",
        ("beneficio", "der", "sentenca", "recurso inominado", "rpv"),
    ),
    RegraDocumento(
        "sentenca_acordao",
        ("sentenca", "acordao", "julgo procedente", "julgo improcedente", "dispositivo", "relator"),
        ("embargos-declaracao", "maquina-recursos", "auditoria-recurso"),
        "documentos", None, "decisao judicial", None,
        ("relatorio", "fundamentos", "dispositivo", "sucumbencia", "prazo recursal"),
    ),
    RegraDocumento(
        "recurso_especial",
        ("recurso especial", "agravo em recurso especial", "aresp", "superior tribunal de justica"),
        ("auditoria-recurso", "validador-teses-precedentes", "contrarrazoes-recursais"),
        "teses", None, "stj", "Recurso Especial e tramitação no STJ",
        ("prequestionamento", "questao federal", "admissibilidade", "obices", "dissidio"),
    ),
    RegraDocumento(
        "recurso_extraordinario",
        ("recurso extraordinario", "agravo em recurso extraordinario", "repercussao geral", "supremo tribunal federal"),
        ("auditoria-recurso", "validador-teses-precedentes", "contrarrazoes-recursais"),
        "teses", "constitucional", "stf", "Recurso Extraordinário e tramitação no STF",
        ("questao constitucional", "repercussao geral", "prequestionamento", "admissibilidade"),
    ),
    RegraDocumento(
        "reclamacao_trabalhista",
        ("reclamacao trabalhista", "reclamante", "reclamado", "vara do trabalho", "verbas rescisorias"),
        ("contestacao-trabalhista", "mapa-risco-condenacao-trabalhista", "roteirista-audiencia"),
        "documentos", "trabalhista", "reclamacao trabalhista", "procedimento trabalhista",
        ("vinculo", "periodo", "funcao", "salario", "jornada", "pedidos", "rito"),
    ),
    RegraDocumento(
        "indeferimento_inss",
        ("instituto nacional do seguro social", "indeferimento", "numero do beneficio", "der", "carta de decisao"),
        ("indeferimento-recurso-inss", "raio-x-cnis", "incapacidade-previdenciaria"),
        "prazos", "previdenciario", "indeferimento de beneficio", "administrativo previdenciario",
        ("beneficio", "nb", "der", "motivo", "cnis", "carencia", "qualidade de segurado"),
    ),
    RegraDocumento(
        "plano_saude_negativa",
        ("plano de saude", "negativa de cobertura", "procedimento medico", "ans", "urgencia medica"),
        ("plano-saude-negativa-liminar", "liminar-saude", "gerador-notificacao-extrajudicial"),
        "documentos", "saude", "negativa de cobertura", "consumerista ou comum",
        ("operadora", "beneficiario", "procedimento", "relatorio medico", "urgencia", "negativa"),
    ),
    RegraDocumento(
        "inventario_sucessoes",
        ("inventario", "espólio", "herdeiros", "autor da heranca", "partilha", "testamento"),
        ("inventario-partilha", "raio-x-processual", "revisor-contratos"),
        "documentos", "sucessoes", "inventario e partilha", "inventario judicial ou extrajudicial",
        ("falecido", "herdeiros", "bens", "dividas", "testamento", "partilha"),
    ),
    RegraDocumento(
        "familia",
        ("divorcio", "guarda", "alimentos", "uniao estavel", "convivencia", "poder familiar"),
        ("divorcio-uniao-estavel-partilha", "acao-alimentos", "guarda-convivencia"),
        "documentos", "familia", "familia", "procedimento de familia",
        ("partes", "filhos", "renda", "bens", "guarda", "alimentos"),
    ),
    RegraDocumento(
        "imobiliario",
        ("contrato de locacao", "matricula do imovel", "despejo", "usucapiao", "posse", "incorporacao imobiliaria"),
        ("acao-despejo", "acao-usucapiao", "acao-possessoria"),
        "documentos", "imobiliario", "imobiliario", "comum ou especial",
        ("imovel", "matricula", "posse", "proprietario", "contrato", "valor"),
    ),
    RegraDocumento(
        "tributario",
        ("certidao de divida ativa", "execucao fiscal", "auto de infracao tributario", "credito tributario", "lancamento fiscal"),
        ("raio-x-cda", "defesa-administrativa-tributaria", "excecao-pre-executividade"),
        "prazos", "tributario", "tributario", "administrativo ou execução fiscal",
        ("tributo", "periodo", "lancamento", "cda", "valor", "prescricao", "garantia"),
    ),
    RegraDocumento(
        "digital_lgpd",
        ("lei geral de protecao de dados", "lgpd", "incidente de seguranca", "dados pessoais", "controlador", "anpd"),
        ("scanner-anti-sabotagem", "detetive-prints", "gerador-notificacao-extrajudicial"),
        "documentos", "digital_lgpd", "proteção de dados", "administrativo ou civil",
        ("titular", "controlador", "operador", "dados", "incidente", "base legal"),
    ),
    RegraDocumento("contestacao", ("contestacao", "preliminarmente", "impugnacao especifica"), ("maquina-replica", "detector-contradicoes", "replica-estrategica"), "documentos"),
    RegraDocumento("peticao_inicial", ("peticao inicial", "dos fatos", "dos pedidos", "requer a citacao"), ("auditor-pedidos", "simulador-defesa-adversarial", "raio-x-processual"), "documentos"),
    RegraDocumento("recurso", ("razoes recursais", "apelacao", "agravo", "recurso ordinario", "recurso de revista"), ("contrarrazoes-recursais", "auditoria-recurso", "validador-teses-precedentes"), "documentos"),
    RegraDocumento("intimacao", ("intimacao", "fica intimado", "diario da justica", "prazo de"), ("prescricao-decadencia", "raio-x-processual"), "prazos"),
    RegraDocumento("contrato", ("contrato", "contratante", "contratada", "clausula", "objeto do contrato"), ("revisor-contratos", "minuta-acordo", "simulador-defesa-adversarial"), "documentos"),
    RegraDocumento("laudo_pericial", ("laudo pericial", "perito", "quesitos", "conclusao pericial"), ("desmistificador-laudos", "detector-contradicoes", "incapacidade-quesitos"), "provas"),
    RegraDocumento("audiencia", ("ata de audiencia", "depoimento", "testemunha", "termo de audiencia"), ("detector-contradicoes", "roteirista-audiencia", "memoriais-alegacoes-finais"), "audiencias"),
    RegraDocumento("inquerito", ("inquerito policial", "auto de prisao", "autoridade policial", "indiciado"), ("raio-x-inquerito", "contraponto-penal", "resposta-acusacao"), "provas", "penal"),
    RegraDocumento("cnis", ("cnis", "cadastro nacional de informacoes sociais", "nit", "indicador previdenciario"), ("raio-x-cnis", "indeferimento-recurso-inss"), "provas", "previdenciario"),
    RegraDocumento("ppp", ("perfil profissiografico previdenciario", "ppp", "agente nocivo", "ltcat"), ("raio-x-ppp", "desmistificador-laudos"), "provas", "previdenciario"),
)


def _resultado_regra(regra: RegraDocumento | None, pontos: int, sinais: list[str], filename: str | None, texto: str | None) -> dict[str, Any]:
    if regra is None:
        area = None
        tipo = "documento_juridico"
        surface = "documentos"
        skills = ["raio-x-processual", "sintese-processo", "scanner-anti-sabotagem"]
        subarea = None
        rito = None
        expected: list[str] = []
        confidence = 0.35
    else:
        area = regra.area
        tipo = regra.tipo
        surface = regra.surface
        skills = list(regra.skills)
        subarea = regra.subarea
        rito = regra.rito
        expected = list(regra.campos_esperados)
        confidence = min(0.96, 0.48 + pontos * 0.08)

    jornada = identificar_rito({
        "area": area,
        "subarea": subarea,
        "rito": rito,
        "tipo_documento": tipo,
        "texto": (texto or "")[:30_000],
    })
    return {
        "tipo": tipo,
        "confianca": confidence,
        "sinais": sinais or ["nenhum marcador específico encontrado"],
        "surface_sugerida": surface,
        "skills_sugeridas": skills,
        "area_sugerida": area,
        "subarea_sugerida": subarea,
        "rito_sugerido": rito or jornada.get("nome"),
        "fase_sugerida": jornada.get("etapa_atual"),
        "instancia_sugerida": jornada.get("instancia"),
        "jornada_sugerida": jornada,
        "campos_esperados": expected,
        "metodo": "regras_locais_v3_motor_ritos",
        "requer_confirmacao_humana": True,
        "arquivo_considerado": Path(filename or "documento").name[:255],
    }


def classificar_documento(filename: str | None, texto: str | None) -> dict[str, Any]:
    """Classifica localmente e acrescenta rito/jornada sem expor o texto bruto."""
    nome = _normalizar(Path(filename or "documento").stem).replace("-", " ")
    corpo = _normalizar((texto or "")[:30_000]).replace("-", " ")
    base = f"{nome} {corpo}"
    candidatos: list[tuple[int, RegraDocumento, list[str]]] = []
    for regra in _REGRAS_DOCUMENTO:
        encontrados = [termo for termo in regra.termos if termo in base]
        if encontrados:
            pontos = len(encontrados) * 2 + (2 if any(termo in nome for termo in encontrados) else 0)
            candidatos.append((pontos, regra, encontrados[:4]))
    if not candidatos:
        return _resultado_regra(None, 0, [], filename, texto)
    pontos, regra, sinais = max(candidatos, key=lambda item: item[0])
    return _resultado_regra(regra, pontos, sinais, filename, texto)


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
    group = _SURFACE_GROUP.get(surface_key, _SURFACE_GROUP.get(_normalizar(surface), "visao"))
    area_key = normalizar_area(area)
    preferred = list(document_skills or [])
    preferred += _SURFACE_SKILLS.get(group, [])
    preferred += _AREA_SKILLS.get(area_key, [])
    preferred = list(dict.fromkeys(preferred))
    index = {name: position for position, name in enumerate(preferred)}
    phase_key = _normalizar(phase)
    document_key = _normalizar(document_type)

    evaluated: list[dict[str, Any]] = []
    for skill in skills:
        name = str(_atributo(skill, "name", ""))
        if not name or (not has_case and bool(_atributo(skill, "requires_case", False))):
            continue
        skill_area = normalizar_area(str(_atributo(skill, "area", "")))
        score = 0
        reasons: list[str] = []
        if name in index:
            score += max(35, 120 - index[name] * 7)
            reasons.append("adequada à etapa atual")
        if area_key and skill_area == area_key:
            score += 45
            reasons.append(f"especializada em {area_key}")
        elif skill_area in {"juridico", "estrategia", "provas"}:
            score += 12
        terms = _normalizar(f"{_atributo(skill, 'display_name', '')} {_atributo(skill, 'description', '')}")
        if phase_key and phase_key in terms:
            score += 10
            reasons.append("compatível com a fase")
        if document_key and document_key in terms:
            score += 12
            reasons.append("compatível com o documento")
        if score <= 0:
            continue
        evaluated.append({"skill": skill, "score": score, "reason": "; ".join(reasons[:2]) or "ação geral"})
    evaluated.sort(key=lambda item: (-item["score"], str(_atributo(item["skill"], "display_name", ""))))
    return evaluated[:limit]


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
    "revisional-juros-bancarios": ["revisor-contratos", "simulador-defesa-adversarial"],
    "defesa-multa-transito": ["recurso-jari-cetran", "prescricao-decadencia"],
    "transcritor-midias-audiencia": ["detector-contradicoes", "memoriais-alegacoes-finais"],
}


def proximas_skills(skill_name: str | None) -> list[str]:
    name = _normalizar(skill_name)
    if name in _NEXT_ACTIONS:
        return list(_NEXT_ACTIONS[name])
    if any(term in name for term in ("recurso", "agravo", "embargos")):
        return ["validador-teses-precedentes", "simulador-defesa-adversarial"]
    if any(term in name for term in ("raio-x", "auditoria", "scanner", "detector")):
        return ["casador-de-fatos", "simulador-defesa-adversarial"]
    return ["simulador-defesa-adversarial", "validador-teses-precedentes"]
