from __future__ import annotations

from typing import Any

from app.services.ai.core.ejc_skill_catalog import NativeSkillSpec, native_skill_specs

from .contracts import LegalSkillContract, SkillStatus


_DEFAULT_VERSION = "1.0.0"
_OVERLAY_VERSION = "1.1.0"

# Overlay METODOLÓGICO: deriva os pontos de saneamento do método já aprovado no
# catálogo nativo. Não contém lei, precedente, tese ou conteúdo documental e,
# portanto, não cria uma segunda base jurídica. Áreas sem método canônico NÃO
# ganham overlay por aproximação: continuam visíveis em native_skill_coverage().
_LEGAL_OVERLAYS: dict[str, dict[str, tuple[str, ...]]] = {
    "empresarial": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas"),
        "required_questions": (
            "Qual é a estrutura societária, o vínculo obrigacional e o objetivo jurídico?",
            "Quais poderes, garantias, eventos de inadimplemento ou crise precisam ser confirmados?",
            "O caso é preventivo, negocial, contencioso ou de reestruturação?",
        ),
        "required_evidence": (
            "atos societários e procurações relevantes",
            "contratos, garantias e comunicações",
            "cronologia de obrigações, pagamentos e inadimplementos",
        ),
    },
    "civil": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Qual é a relação jurídica, obrigação ou fato gerador da pretensão?",
            "Quais fatos sustentam inadimplemento, dano, nexo e regime de responsabilidade?",
            "Qual tutela, competência, prazo material/processual e prova precisam ser confirmados?",
        ),
        "required_evidence": (
            "contrato, título ou documento da relação jurídica",
            "cronologia e comunicações relevantes",
            "provas do fato, dano, pagamento e demais consequências alegadas",
        ),
    },
    "criminal": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas"),
        "required_questions": (
            "Qual é a imputação, fase procedimental e situação processual atual?",
            "Quais fatos sustentam autoria, materialidade e elemento subjetivo e quais são controvertidos?",
            "Há questão de competência, cautelar, nulidade, cadeia de custódia ou prazo a confirmar?",
        ),
        "required_evidence": (
            "peças oficiais da investigação ou processo disponíveis",
            "mídias, laudos, depoimentos e documentos com origem identificada",
            "cronologia de atos, intimações e medidas cautelares",
        ),
    },
    "trabalhista": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas"),
        "required_questions": (
            "Quais foram período, função, remuneração, jornada e forma de término?",
            "Quais elementos da relação de trabalho estão documentados ou controvertidos?",
            "Há norma coletiva, prescrição, pedido ou cálculo que dependa de confirmação?",
        ),
        "required_evidence": (
            "contratos, registros funcionais e documentos rescisórios",
            "comprovantes de pagamento, jornada e comunicações",
            "normas coletivas e documentos de SST quando pertinentes ao caso",
        ),
    },
    "administrativo": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Qual ente, órgão e autoridade praticaram o ato e em qual procedimento?",
            "Qual foi a motivação, ciência, oportunidade de defesa e efeito concreto do ato?",
            "Qual recurso, sanção, prazo ou medida urgente precisa ser confirmado?",
        ),
        "required_evidence": (
            "processo administrativo e ato impugnado",
            "notificações, ciência e manifestações das partes",
            "documentos técnicos, contratuais ou funcionais ligados ao ato",
        ),
    },
    "bancario": {
        "issue_types": ("bancario_contrato_encargos", "prescricao_decadencia", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Qual produto financeiro, período, contratação e garantia estão em discussão?",
            "Quais CET, taxas, tarifas, seguros, pagamentos, renegociações e eventos de mora estão documentados?",
            "Qual divergência exige cálculo determinístico ou comparação com série oficial equivalente?",
        ),
        "required_evidence": (
            "contrato integral, CET e aditivos",
            "extratos, faturas, planilha de evolução e comprovantes",
            "documentos de garantia, cobrança, renegociação e comunicação bancária",
        ),
    },
    "tributario": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Qual ente, tributo, período, fato gerador e sujeito estão em discussão?",
            "Qual lançamento, ciência, cobrança ou via administrativa/judicial ocorreu?",
            "Quais marcos temporais, base, alíquota, responsabilidade ou garantia precisam ser confirmados?",
        ),
        "required_evidence": (
            "auto, lançamento, CDA ou documento fiscal pertinente",
            "notificações, intimações e decisões administrativas",
            "documentos contábeis/fiscais e cronologia dos fatos geradores e pagamentos",
        ),
    },
    "ambiental": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Qual órgão, local, atividade, licença, auto ou embargo estão envolvidos?",
            "Quais fato, área, período, nexo e responsabilidade estão comprovados ou controvertidos?",
            "Há necessidade de perícia, regularização ou medida urgente?",
        ),
        "required_evidence": (
            "licenças, autos, notificações e processo administrativo",
            "mapas, coordenadas, fotografias, laudos e demais provas técnicas",
            "documentos de propriedade/posse, atividade e cronologia da intervenção",
        ),
    },
    "consumidor": {
        "issue_types": ("relacao_consumo_responsabilidade", "competencia_rito", "prescricao_decadencia", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Quem integra a cadeia de fornecimento e qual produto ou serviço está em discussão?",
            "O problema alegado é de oferta, contratação, cobrança, vício, defeito ou prática comercial?",
            "Quais protocolos, prazos, danos e tentativas de solução estão documentados?",
        ),
        "required_evidence": (
            "oferta, contrato e comprovantes de pagamento",
            "notas, protocolos e comunicações com fornecedores",
            "provas do evento, do problema e dos danos efetivamente alegados",
        ),
    },
    "familia": {
        "issue_types": ("competencia_rito", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Quais pessoas, vínculos familiares, interesses e medidas estão em discussão?",
            "Quais renda, necessidades, bens, guarda, convivência ou consenso precisam ser confirmados?",
            "Há urgência ou interesse de criança/adolescente que exija tratamento específico do caso?",
        ),
        "required_evidence": (
            "documentos de estado civil e filiação pertinentes",
            "comprovantes financeiros e patrimoniais necessários ao objeto",
            "documentos e registros que sustentem os fatos familiares alegados",
        ),
    },
    "imobiliario": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Qual imóvel, relação possessória/contratual e direito alegado estão em discussão?",
            "Qual cadeia documental, ônus, pagamento, notificação ou situação registral precisa ser confirmada?",
            "O conflito envolve obrigação, posse, propriedade, locação, condomínio ou regularização?",
        ),
        "required_evidence": (
            "matrícula e documentos registrais disponíveis",
            "contratos, notificações e comprovantes de pagamento",
            "provas da posse, uso, benfeitorias ou situação física do imóvel quando relevantes",
        ),
    },
    "previdenciario": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Qual benefício, requerimento e período contributivo ou condição estão em discussão?",
            "Quais filiação, categoria, carência, qualidade e marcos do benefício precisam ser confirmados?",
            "Qual decisão administrativa e quais documentos laborais ou médicos sustentam o pedido?",
        ),
        "required_evidence": (
            "CNIS e documentos contributivos disponíveis",
            "requerimento, decisão e processo administrativo previdenciário",
            "documentos laborais, pessoais ou médicos pertinentes ao benefício",
        ),
    },
    "digital_lgpd": {
        "issue_types": ("competencia_rito", "prova_onus_lacunas", "tutela_urgencia"),
        "required_questions": (
            "Quais agentes, titulares, dados, finalidades e operações estão envolvidos?",
            "Qual compartilhamento, retenção, medida de segurança, incidente ou direito do titular precisa ser confirmado?",
            "Quais fatos dependem de prova digital, logs ou cadeia de custódia?",
        ),
        "required_evidence": (
            "contratos, avisos, registros de consentimento ou bases documentadas pertinentes",
            "inventários, registros de operação e evidências técnicas disponíveis",
            "logs, comunicações e documentação do incidente ou atendimento ao titular quando existentes",
        ),
    },
    "transito": {
        "issue_types": ("competencia_rito", "prescricao_decadencia", "prova_onus_lacunas"),
        "required_questions": (
            "Qual órgão, auto, enquadramento, veículo, condutor, data e local estão em discussão?",
            "Qual fase administrativa, notificação, pontuação ou penalidade precisa ser confirmada?",
            "Há equipamento, indicação de condutor ou documento técnico relevante ao fato?",
        ),
        "required_evidence": (
            "auto de infração e notificações recebidas",
            "documentos do veículo e do condutor pertinentes ao caso",
            "fotografias, registros do equipamento e decisões administrativas disponíveis",
        ),
    },
}


def _overlay_for(spec: NativeSkillSpec) -> dict[str, tuple[str, ...]] | None:
    """Retorna overlay apenas para ramo jurídico que já possui método canônico."""

    if spec.kind != "legal_area":
        return None
    return _LEGAL_OVERLAYS.get(spec.area)


def _contract_from_native(spec: NativeSkillSpec) -> LegalSkillContract:
    """Converte skill canônica em contrato versionável sem copiar o Direito.

    Overlays enriquecem apenas método de saneamento. Referências jurídicas ficam
    vazias até haver curadoria oficial identificada por ID/proveniência.
    """

    overlay: dict[str, Any] = _overlay_for(spec) or {}
    return LegalSkillContract(
        key=spec.name,
        version=_OVERLAY_VERSION if overlay else _DEFAULT_VERSION,
        area=spec.area,
        display_name=spec.display_name,
        description=spec.description,
        issue_types=tuple(overlay.get("issue_types", ())),
        required_questions=tuple(overlay.get("required_questions", ())),
        required_evidence=tuple(overlay.get("required_evidence", ())),
        source_refs=(),
        precedent_refs=(),
        thesis_refs=(),
        status=SkillStatus.ATIVA,
        requires_case=spec.requires_case,
        oab_restricted=spec.oab_restricted,
    )


def native_legal_skill_contracts() -> tuple[LegalSkillContract, ...]:
    """Snapshot versionado das skills existentes, derivado da fonte canônica."""

    return tuple(_contract_from_native(spec) for spec in native_skill_specs())


def get_native_legal_skill_contract(name: str) -> LegalSkillContract | None:
    """Busca contrato derivado pelo nome canônico da skill."""

    normalized = str(name or "").strip()
    for contract in native_legal_skill_contracts():
        if contract.key == normalized:
            return contract
    return None
