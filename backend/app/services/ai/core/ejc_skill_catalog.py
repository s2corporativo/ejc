"""Catálogo nativo de skills do Agente Coordenador EJC.

Este módulo é a fonte canônica das skills transversais por ramo do Direito e
por módulo funcional. A seleção é determinística e apenas acrescenta instruções
de método ao núcleo único; não cria outro gateway, provider ou fluxo de IA.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from app.services.module_registry import MODULE_REGISTRY


@dataclass(frozen=True)
class NativeSkillSpec:
    name: str
    display_name: str
    description: str
    kind: str
    key: str
    area: str
    system_prompt: str
    requires_case: bool = False
    oab_restricted: bool = False


@dataclass(frozen=True)
class NativeSkillPlan:
    legal_area: str | None
    module_key: str | None
    skill_names: tuple[str, ...]
    prompt_blocks: tuple[str, ...]


_LEGAL_BASE = """SKILL NATIVA DE RAMO DO DIREITO
Atue como assistente jurídico interno especializado, sempre subordinado ao
Agente Coordenador EJC e ao advogado responsável.

REGRAS
- Trabalhe apenas com fatos, documentos e fontes efetivamente disponíveis.
- Diferencie fato documentado, alegação, inferência e dado ausente.
- Confirme vigência, competência, rito, fase, prazo e fonte oficial na data-base.
- Apresente argumentos favoráveis e contrários, prova, riscos e diligências.
- Não invente precedentes, dispositivos, datas, valores ou probabilidade.
- Não prometa resultado e não trate a saída como orientação final ao cliente.
- Toda produção jurídica é rascunho com revisão humana obrigatória.
"""

_MODULE_BASE = """SKILL NATIVA DE MÓDULO DO EJC
Atue dentro dos limites funcionais do módulo selecionado e preserve as regras
do núcleo único de IA.

REGRAS
- Use somente dados que o perfil autenticado pode acessar.
- Não alegue que registro, envio, protocolo, cálculo ou sincronização ocorreu
  sem retorno positivo da ferramenta correspondente.
- Antes de mutação, apresente prévia, impacto e campos pendentes; exija
  confirmação humana para ações jurídicas, financeiras ou externas.
- Preserve IDs, origem, versão, data, responsável e trilha de auditoria.
- Não crie rota, módulo ou cadastro paralelo quando a capacidade já existir.
- Se a solicitação exigir mérito jurídico, combine esta skill com a skill do
  ramo do Direito; esta skill operacional não substitui análise jurídica.
"""


def _legal_prompt(method: str) -> str:
    return f"{_LEGAL_BASE}\nMÉTODO ESPECÍFICO\n{method}\n"


def _module_prompt(method: str) -> str:
    return f"{_MODULE_BASE}\nMÉTODO DO MÓDULO\n{method}\n"


_LEGAL_DATA: dict[str, tuple[str, str, str]] = {
    "empresarial": (
        "Direito Empresarial",
        "Sociedades, contratos empresariais, governança, crise e atividade econômica.",
        "Delimite empresário/sociedade, estrutura societária, poderes, contrato, obrigação, governança, garantias, insolvência e impactos tributários ou trabalhistas conexos. Separe prevenção, negociação, contencioso e reestruturação.",
    ),
    # Chaves = taxonomia CANÔNICA (app/core/taxonomia.AREAS_CANONICAS): "civil"
    # e "criminal" (não "civel"/"penal"); os nomes forenses seguem como alias.
    "civil": (
        "Direito Civil",
        "Obrigações, contratos, responsabilidade, bens, cobrança e processo civil.",
        "Identifique relação jurídica, obrigação, inadimplemento, dano, nexo, culpa ou regime objetivo, prescrição/decadência, tutela adequada, competência, prova e exequibilidade. Separe direito material e técnica processual.",
    ),
    "criminal": (
        "Direito Penal",
        "Análise penal e processual penal com garantias, prova e estratégia defensiva.",
        "Reconstrua cronologia, imputação, tipicidade, autoria, materialidade, elemento subjetivo, excludentes, competência, fase, cautelares, nulidades, prova lícita, cadeia de custódia, prescrição e alternativas legalmente cabíveis.",
    ),
    "trabalhista": (
        "Direito do Trabalho",
        "Relações de trabalho, vínculo, jornada, verbas, prova e processo trabalhista.",
        "Confirme partes, período, função, remuneração, subordinação, pessoalidade, habitualidade, onerosidade, jornada, término, norma coletiva, prescrição, pedidos individualizados, ônus da prova e memória de cálculo determinística.",
    ),
    "administrativo": (
        "Direito Administrativo",
        "Atos, processos, sanções, servidores, contratos públicos e controle.",
        "Identifique ente, órgão, autoridade, competência, ato, motivação, finalidade, procedimento, ciência, contraditório, tipicidade, proporcionalidade, sanção, recurso, efeitos e norma específica do órgão ou regime.",
    ),
    "bancario": (
        "Direito Bancário",
        "Contratos financeiros, extratos, fraudes, encargos, garantias e regulação.",
        "Classifique produto e período, extraia CET, taxas, tarifas, seguros, amortização, pagamentos, mora, garantias e autenticação. Compare somente com séries oficiais equivalentes e envie cálculos ao motor determinístico.",
    ),
    "tributario": (
        "Direito Tributário",
        "Tributos, obrigações, lançamento, cobrança, fiscalização e contencioso.",
        "Confirme ente, tributo, competência, fato gerador, período, sujeito, regime, lançamento, ciência, decadência, prescrição, base, alíquota, responsabilidade, garantia, via administrativa/judicial e regras temporais.",
    ),
    "ambiental": (
        "Direito Ambiental",
        "Licenciamento, infrações, responsabilidade, áreas protegidas e regularização.",
        "Identifique órgão, competência, local, atividade, licença, auto, embargo, enquadramento, prova técnica, área e período. Separe responsabilidades administrativa, civil e penal, nexo, reparação, regularização e necessidade de perícia.",
    ),
    "consumidor": (
        "Direito do Consumidor",
        "Relações de consumo, vícios, defeitos, práticas, contratos e reparação.",
        "Confirme cadeia de fornecimento, destinatário, produto/serviço, oferta, contrato, vício ou fato, protocolos, prazos, responsabilidade, excludentes, inversão probatória, dano efetivamente demonstrado e solução extrajudicial.",
    ),
    "familia": (
        "Direito de Família",
        "Família, filiação, guarda, convivência, alimentos e partilha.",
        "Delimite vínculo familiar, pessoas envolvidas, capacidade, regime patrimonial, renda, necessidades, bens, consenso, urgência, competência e prova. Preserve intimidade e o melhor interesse de crianças e adolescentes quando aplicável.",
    ),
    "imobiliario": (
        "Direito Imobiliário",
        "Imóveis, posse, propriedade, locação, condomínio, incorporação e registro.",
        "Confira matrícula, cadeia dominial, posse, contrato, destinação, ônus, pagamentos, notificações, condomínio, regularidade urbanística/registral, competência e diferença entre obrigação, posse e direito real.",
    ),
    "previdenciario": (
        "Direito Previdenciário",
        "RGPS, benefícios, custeio, requerimentos, prova e revisão.",
        "Confirme filiação, categoria, CNIS, períodos, carência, qualidade, benefício, DER/DIB/DCB, requerimento, decisão, documentos médicos ou laborais, prescrição/decadência e regra vigente em cada período.",
    ),
    "digital_lgpd": (
        "Direito Digital e LGPD",
        "Dados pessoais, tecnologia, contratos digitais, incidentes e evidência eletrônica.",
        "Mapeie agentes, titulares, dados, finalidade, operação, base legal, transparência, segurança, compartilhamento, retenção, direitos, incidente e competência. Preserve prova digital e diferencie obrigação jurídica de boa prática técnica.",
    ),
    "transito": (
        "Direito de Trânsito",
        "Autuações, penalidades, CNH, recursos, veículos e responsabilização.",
        "Identifique órgão, auto, enquadramento, veículo, condutor, data, local, equipamento, notificações, fase, competência recursal, pontuação e penalidade. Não presuma nulidade nem prazo sem documento e norma vigente.",
    ),
}


MODULE_METHODS: dict[str, str] = {
    "dashboard": "Consolide prioridades do usuário, pendências críticas, próximos compromissos, notícias jurídicas e atalhos existentes. Não exponha informação financeira quando a configuração do painel a ocultar.",
    "clientes": "Localize ou prepare o cadastro sem duplicidade; organize identidade, contatos, conflito, documentos, consentimentos, casos vinculados e linha do tempo de atendimento com data, hora, pedido, recado e atendimento.",
    "atendimento": "Registre demanda, canal, data/hora, responsável, orientação dada, documentos solicitados, pendência, retorno e confirmação de atendimento. Não enviar mensagem sem revisão e destinatário confirmado.",
    "crm": "Classifique lead, origem, interesse, urgência, estágio, próximo contato e motivo da decisão. Antes de converter, verifique duplicidade, conflito, documentos e condições de contratação.",
    "casos": "Organize abertura manual ou por documento, área, partes, objetivo, fase, rito, responsável, cronologia, provas, riscos, tarefas e próximo passo. Não alterar estado do caso sem confirmação.",
    "datajud": "Consulte e normalize dados processuais, registre fonte e data da consulta, diferencie ausência de resultado de inexistência do processo e compare movimentos antes de atualizar o caso.",
    "prazos": "Identifique evento inicial, ciência, regra, dias úteis/corridos, calendário, suspensões, termo final, prazo interno e responsável. Toda contagem exige dupla validação e fonte oficial.",
    "intimacoes": "Preserve a publicação, deduplique, vincule ao processo correto, classifique efeito, valide ciência e só então proponha prazo, tarefa e escalonamento.",
    "tarefas": "Defina ação executável, caso, responsável, prioridade, vencimento, dependências, checklist, evidência de conclusão e regra de escalonamento.",
    "ramos": "Identifique a área jurídica confirmada ou sugerida e acione a skill nativa do ramo. Não substituir a área do caso nem misturar regimes sem aprovação.",
    "documentos": "Preserve original, origem, hash quando calculado, OCR, versão, classificação, sigilo, acesso, vínculo, retenção e campos extraídos com âncora documental.",
    "pecas": "Monte minuta a partir do dossiê, matriz fato-prova-norma-pedido, fontes verificadas, campos pendentes, versão e revisão humana. Nunca classificar como pronta para protocolo.",
    "checklists": "Produza lista contextual por tipo de caso e fase, com item, finalidade, obrigatoriedade, responsável, prazo, dependência e evidência; não marcar conclusão sem comprovação.",
    "workflow": "Orquestre transições válidas, responsáveis, gatilhos, condições, idempotência, exceções e rollback. Não mover cards ou executar automação sem confirmação da operação.",
    "assinaturas": "Confira documento final, versão, signatários, poderes, ordem, canal, consentimento, validade, expiração e evidência. Nunca assinar ou aceitar em nome de pessoa.",
    "financeiro": "Organize lançamentos, competência, centro de custo, recebível, pagamento, conciliação, documento suporte, acesso e divergências. Não alterar saldo nem confirmar quitação sem evidência.",
    "honorarios": "Estruture escopo, exclusões, tabela OAB vigente, fixo, êxito, parcelas, despesas, inadimplência, impostos, rentabilidade e contrato, sem promessa de resultado.",
    "sociedade": "Controle regras societárias do escritório, aportes, rateios, retiradas, centros de responsabilidade, aprovações e documentos, respeitando permissões e trilha de auditoria.",
    "ia": "Use exclusivamente o núcleo único, policy de provider, sanitização, RAG autorizado, validação de fontes, custo, AILog e HITL. Não criar chamada direta a modelo.",
    "inteligencia": "Combine contexto do caso, teses, provas, risco, jurimetria e próximos passos sem falsa precisão. Indique fonte, data-base e limitações.",
    "ferramentas-ia": "Selecione poucas ações contextuais, exponha entrada, saída, risco e revisão; toda execução deve passar pelo catálogo, gateway, log e HITL existentes.",
    "conhecimento": "Curar fontes, teses e modelos com proveniência, jurisdição, vigência, versão, escopo de acesso, aprovação, revisão e retirada de conteúdo superado.",
    "jurimetria": "Defina pergunta, unidade, coorte, período, desfecho, denominadores, qualidade, vieses, incerteza e reprodutibilidade; não converter taxa histórica em chance do caso.",
    "radar-regulatorio": "Monitore fontes oficiais, data de publicação/vigência, área afetada, impacto, urgência e responsável. Mudança normativa não altera caso automaticamente.",
    "sala-juridica": "Conduza a análise conversacional com estado probatório versionado: fatos, provas, riscos e modos de atuação. Toda resposta é rascunho sob HITL; a conversão em caso exige conferência de cliente e conflito.",
    "diario-oficial": "Colete fonte oficial, disponibilidade, publicação, destinatário, processo, texto, retificação e efeito; encaminhe atos relevantes à triagem de intimações.",
    "portal": "Exiba ao cliente apenas dados autorizados do próprio caso, em linguagem clara, com documentos, mensagens, assinaturas e status revisados. O cliente externo não acessa o núcleo interno.",
    "auditoria": "Registre ator, data/hora, recurso, ação, estado anterior/posterior, justificativa, origem e correlação. Preserve imutabilidade e acesso proporcional.",
    "produtividade": "Meça trabalho com definições transparentes, período, denominador e contexto. Evite vigilância excessiva, ranking enganoso e exposição de dados sensíveis.",
    "usuarios": "Aplique menor privilégio, segregação de funções, MFA quando disponível, ciclo de acesso, revogação, sessões, chaves e auditoria. Nunca revelar credenciais.",
    "mapa-modulos": "Compare registro canônico, rotas, endpoints, ajuda, status, dependências, IA e cobertura de skills; destaque divergências sem criar módulo duplicado.",
    "central-diagnostico": "Diagnostique com evidência técnica, proponha plano, testes e rollback. Não aplicar patch automaticamente nem acessar segredos.",
}


def _module_area(group: str) -> str:
    normalized = _normalize(group)
    return {
        "operacao": "operacional",
        "juridico": "juridico",
        "producao": "juridico",
        "financeiro": "financeiro",
        # Nota: diario-oficial e noticias migraram do extinto grupo
        # "Biblioteca" para "Inteligência" na onda 2 — a área das skills
        # deles passa de "juridico" para "estrategia" por consequência
        # (monitoramento/radar é leitura estratégica, escolha consciente).
        "inteligencia": "estrategia",
        "portal": "operacional",
        "atendimento": "operacional",
        "administracao": "administrativo",
    }.get(normalized, "operacional")


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


LEGAL_AREA_SPECS: dict[str, NativeSkillSpec] = {
    key: NativeSkillSpec(
        name=f"ramo_{key}",
        display_name=f"Especialista — {display}",
        description=description,
        kind="legal_area",
        key=key,
        area=key,
        system_prompt=_legal_prompt(method),
        oab_restricted=True,
    )
    for key, (display, description, method) in _LEGAL_DATA.items()
}

_MODULE_BY_KEY = {str(item["module_key"]): item for item in MODULE_REGISTRY}

# Aliases canônicos derivados do próprio registro de módulos. O frontend pode
# informar a chave, o nome visível ou a rota; todos convergem para module_key.
# PRIMEIRO VENCE: módulos podem compartilhar frontend_route (ex.: conhecimento
# e victory-vault vivem ambos em /inteligencia?tab=conhecimento após a
# consolidação) — a rota resolve para o módulo CANÔNICO, que vem antes na
# lista do MODULE_REGISTRY; module_key e nome seguem únicos por construção.
MODULE_ALIASES: dict[str, str] = {}
for _module_key, _module in _MODULE_BY_KEY.items():
    for _alias in (
        _module_key,
        str(_module.get("nome") or ""),
        str(_module.get("frontend_route") or ""),
    ):
        if _normalize(_alias):
            MODULE_ALIASES.setdefault(_normalize(_alias), _module_key)
MODULE_ALIASES.update({
    "processo": "casos",
    "processos": "casos",
    "caso": "casos",
    "assistente_ia": "ia",
    "ferramentas": "ferramentas-ia",
    "modulos": "mapa-modulos",
})

MODULE_SKILL_SPECS: dict[str, NativeSkillSpec] = {
    key: NativeSkillSpec(
        name=f"modulo_{_normalize(key)}",
        display_name=f"Módulo — {str(module['nome'])}",
        description=f"Operar o módulo {module['nome']} com segurança, rastreabilidade e uso das rotas existentes.",
        kind="module",
        key=key,
        area=_module_area(str(module["grupo"])),
        system_prompt=_module_prompt(MODULE_METHODS[key]),
    )
    for key, module in _MODULE_BY_KEY.items()
    if key in MODULE_METHODS
}

LEGAL_AREA_ALIASES: dict[str, str] = {
    "empresarial": "empresarial",
    "societario": "empresarial",
    "civel": "civil",
    "civil": "civil",
    "penal": "criminal",
    "criminal": "criminal",
    "trabalhista": "trabalhista",
    "trabalho": "trabalhista",
    "administrativo": "administrativo",
    "bancario": "bancario",
    "tributario": "tributario",
    "fiscal": "tributario",
    "ambiental": "ambiental",
    "consumidor": "consumidor",
    "cdc": "consumidor",
    "familia": "familia",
    "imobiliario": "imobiliario",
    "previdenciario": "previdenciario",
    "inss": "previdenciario",
    "digital_lgpd": "digital_lgpd",
    "lgpd": "digital_lgpd",
    "transito": "transito",
}

LEGAL_AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "empresarial": ("sociedade", "socio", "falencia", "recuperacao judicial", "contrato empresarial"),
    "civil": ("civel", "responsabilidade civil", "cobranca", "indenizacao", "obrigacao civil"),
    "criminal": ("penal", "processo penal", "inquerito", "flagrante", "habeas corpus", "denuncia"),
    "trabalhista": ("clt", "vinculo", "jornada", "verbas rescisorias", "reclamacao trabalhista"),
    "administrativo": ("processo administrativo", "servidor publico", "improbidade", "ato administrativo"),
    "bancario": ("contrato bancario", "extrato", "tarifa", "emprestimo", "financiamento"),
    "tributario": ("tributo", "imposto", "execucao fiscal", "cda", "lancamento fiscal"),
    "ambiental": ("licenciamento ambiental", "auto de infracao ambiental", "embargo ambiental", "app", "reserva legal"),
    "consumidor": ("consumidor", "fornecedor", "produto com defeito", "cobranca indevida", "plano de saude"),
    "familia": ("divorcio", "guarda", "alimentos", "uniao estavel", "familia"),
    "imobiliario": ("imovel", "locacao", "despejo", "usucapiao", "condominio"),
    "previdenciario": ("inss", "cnis", "aposentadoria", "beneficio previdenciario", "bpc"),
    "digital_lgpd": ("lgpd", "dados pessoais", "anpd", "incidente de seguranca", "contrato saas"),
    "transito": ("multa de transito", "cnh", "jari", "cetran", "auto de infracao de transito"),
}
LEGAL_AREA_KEYWORDS = {
    key: tuple(dict.fromkeys((
        key.replace("_", " "),
        _normalize(_LEGAL_DATA[key][0]).replace("_", " "),
        *terms,
    )))
    for key, terms in LEGAL_AREA_KEYWORDS.items()
}

MODULE_KEYWORDS: dict[str, tuple[str, ...]] = {
    key: (
        _normalize(key).replace("_", " "),
        _normalize(str(module["nome"])).replace("_", " "),
        _normalize(str(module["frontend_route"])).replace("_", " ").replace("/", " "),
    )
    for key, module in _MODULE_BY_KEY.items()
}


def _resolve_exact(value: str | None, aliases: dict[str, str]) -> str | None:
    return aliases.get(_normalize(value))


def _best_keyword_match(text: str, candidates: dict[str, Iterable[str]]) -> str | None:
    """Melhor candidato por pontuação de termos. EMPATE → None: escolher o
    primeiro do dicionário seria decidir ramo/módulo pela ordem de declaração,
    não pelo texto — a decisão fica com o humano (HITL)."""
    normalized = _normalize(text).replace("_", " ")
    scored: list[tuple[int, str]] = []
    for key, terms in candidates.items():
        score = sum(max(1, len(term.split())) for term in terms if term and term in normalized)
        if score:
            scored.append((score, key))
    if not scored:
        return None
    melhor = max(score for score, _ in scored)
    empatados = [key for score, key in scored if score == melhor]
    return empatados[0] if len(empatados) == 1 else None


def resolve_native_skill_plan(
    *,
    task_type: str,
    domain: str | None,
    message: str,
    module_key: str | None = None,
    surface: str | None = None,
) -> NativeSkillPlan:
    """Resolver skill de ramo e de módulo sem chamada a modelo."""

    legal_area = _resolve_exact(domain, LEGAL_AREA_ALIASES)
    if legal_area is None:
        legal_area = _resolve_exact(task_type, LEGAL_AREA_ALIASES)
    if legal_area is None:
        legal_area = _best_keyword_match(message, LEGAL_AREA_KEYWORDS)

    module = None
    for value in (module_key, surface, domain, task_type):
        candidate = MODULE_ALIASES.get(_normalize(value))
        if candidate in MODULE_SKILL_SPECS:
            module = candidate
            break
    if module is None:
        module = _best_keyword_match(message, MODULE_KEYWORDS)
    if module not in MODULE_SKILL_SPECS:
        module = None

    specs = []
    if legal_area in LEGAL_AREA_SPECS:
        specs.append(LEGAL_AREA_SPECS[legal_area])
    if module in MODULE_SKILL_SPECS:
        specs.append(MODULE_SKILL_SPECS[module])

    return NativeSkillPlan(
        legal_area=legal_area,
        module_key=module,
        skill_names=tuple(spec.name for spec in specs),
        prompt_blocks=tuple(spec.system_prompt for spec in specs),
    )


def native_skill_specs() -> list[NativeSkillSpec]:
    return [*LEGAL_AREA_SPECS.values(), *MODULE_SKILL_SPECS.values()]


def native_skill_coverage() -> dict[str, object]:
    """Cobertura REAL das skills nativas.

    C7 (análise E2E 03/09): a versão anterior comparava `_LEGAL_DATA` consigo
    mesma e nunca acusava ramo faltante. Agora o esperado é a taxonomia
    canônica (`AREAS_CANONICAS`); `missing` lista as áreas SEM método de ramo —
    escrever esses métodos exige advogado, não se inventa aqui.
    """
    from app.core.taxonomia import AREAS_CANONICAS
    expected_modules = set(_MODULE_BY_KEY)
    covered_modules = set(MODULE_SKILL_SPECS)
    expected_areas = set(AREAS_CANONICAS)
    covered_areas = set(LEGAL_AREA_SPECS)
    return {
        "legal_areas": {
            "expected": len(expected_areas),
            "covered": len(covered_areas & expected_areas),
            "missing": sorted(expected_areas - covered_areas),
            # Chaves do catálogo fora do enum canônico (deveria ser vazio).
            "nao_canonicas": sorted(covered_areas - expected_areas),
        },
        "modules": {
            "expected": len(expected_modules),
            "covered": len(covered_modules),
            "missing": sorted(expected_modules - covered_modules),
            "extra": sorted(covered_modules - expected_modules),
        },
        "total_native_skills": len(covered_areas) + len(covered_modules),
        # `complete` é a métrica ASPIRACIONAL: todas as áreas canônicas têm
        # método de ramo. Hoje é False (faltam 11 áreas) e continua sendo a
        # verdade que o painel de cobertura deve mostrar — não se maquia.
        "complete": expected_modules == covered_modules and expected_areas <= covered_areas,
        # `estrutura_ok` é a métrica OPERACIONAL: o que o CÓDIGO controla —
        # todo módulo tem método, nenhuma área foge do enum canônico, e existe
        # pelo menos um ramo. Separar as duas conserta um defeito real: o seed
        # das skills nativas usava `complete` como portão e, como faltam 11
        # métodos jurídicos ("escrever esses métodos exige advogado, não se
        # inventa aqui"), ele levantava SEMPRE — as 48 skills válidas nunca
        # chegavam a `ejc_skills`. Lacuna de CONTEÚDO passava por defeito de
        # ESTRUTURA e bloqueava o que já estava pronto.
        "estrutura_ok": (
            expected_modules == covered_modules
            and not (covered_areas - expected_areas)
            and bool(covered_areas)
        ),
    }
