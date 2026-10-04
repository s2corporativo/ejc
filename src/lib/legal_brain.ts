// legal_brain.ts — Motor determinístico de raciocínio jurídico (adaptado do PROMPT MESTRE)
// Princípio: começar determinístico, depois enriquecer com IA.
// Princípio 18: Falha do LLM nunca deve destruir o resultado determinístico.

import { createEvidence, type EvidenceRefRecord } from "@/lib/evidence";

// ── Tipos ───────────────────────────────────────────────────────────────────

export type AssertionKind = "fact" | "inference" | "gap" | "risk" | "rule" | "precedent" | "conclusion";
export type SupportStatus = "supported" | "partial" | "absent" | "conflicting";
export type ReviewStatus = "pending" | "confirmed" | "corrected" | "rejected";

export interface LegalIssue {
  key: string;
  title: string;
  area: string;
  question: string;
  matchedTerms: string[];
  requiredEvidence: string[];
  risks: string[];
}

export interface MapperFact {
  text: string;
  evidenceRefIds: string[];
  confidence: number;
}

export interface MapperEvent {
  description: string;
  date: string | null;
  dateStatus: "exact" | "approximate" | "unknown";
  evidenceRefIds: string[];
}

export interface MapperAssertion {
  text: string;
  kind: AssertionKind;
  evidenceRefIds: string[];
  supportStatus: SupportStatus;
}

export interface CaseMapperOutput {
  facts: MapperFact[];
  events: MapperEvent[];
  assertions: MapperAssertion[];
  warnings: string[];
}

// ── Issue Engine determinístico (sem LLM) ────────────────────────────────────
// Identifica questões jurídicas por keywords — não usa IA para tudo.

const ISSUE_PATTERNS: { pattern: RegExp; issue: Omit<LegalIssue, "matchedTerms"> }[] = [
  {
    pattern: /prescriç[ãa]o|prescric/gi,
    issue: {
      key: "prescription",
      title: "Prescrição",
      area: "processual",
      question: "Existe prescrição aplicável ao caso?",
      requiredEvidence: ["data do fato", "marcos interruptivos", "ajuizamento"],
      risks: ["Perda do direito de ação", "Necessidade de demonstrar interrupção"],
    },
  },
  {
    pattern: /dano moral|danos morais/gi,
    issue: {
      key: "moral_damage",
      title: "Dano Moral",
      area: "civil",
      question: "O dano moral é demonstrável e quantificável?",
      requiredEvidence: ["fato gerador", "nexo causal", "extensão do dano"],
      risks: ["Quantificação excessiva", "Ausência de prova do abalo"],
    },
  },
  {
    pattern: /SERASA|SPC|cadastro de proteç|negativaç|inscriç[ãa]o indevida/gi,
    issue: {
      key: "improper_registration",
      title: "Inscrição Indevida em Cadastro",
      area: "consumer",
      question: "A inscrição em cadastro de proteção ao crédito foi indevida?",
      requiredEvidence: ["comprovante de quitação", "data da inscrição", "comunicação prévia"],
      risks: ["Dano moral in re ipsa", "Necessidade de comprovar ausência de débito"],
    },
  },
  {
    pattern: /indenizaç[ãa]o|reparaç[ãa]o civil/gi,
    issue: {
      key: "civil_liability",
      title: "Responsabilidade Civil",
      area: "civil",
      question: "A responsabilidade civil é subjetiva ou objetiva?",
      requiredEvidence: ["conduta", "dano", "nexo causal", "culpa (se subjetiva)"],
      risks: ["Culpa exclusiva da vítima", "Caso fortuito/força maior"],
    },
  },
  {
    pattern: /contrato|cl[áa]usula|adess[ãa]o/gi,
    issue: {
      key: "contract",
      title: "Contrato",
      area: "civil",
      question: "Há cláusulas abusivas ou vícios de consentimento?",
      requiredEvidence: ["contrato", "cláusulas", "assinatura"],
      risks: ["Cláusulas abusivas (art. 51 CDC)", "Vício de consentimento"],
    },
  },
  {
    pattern: /consumidor|fornecedor|relaç[ãa]o de consumo/gi,
    issue: {
      key: "consumer",
      title: "Direito do Consumidor",
      area: "consumer",
      question: "Há relação de consumo caracterizada?",
      requiredEvidence: ["fornecedor", "produto/serviço", "destinatário final"],
      risks: ["Inversão do ônus da prova", "Hipossuficiência"],
    },
  },
  {
    pattern: /trabalho|empregad|CLT|verbas rescis|horas extras|FGTS/gi,
    issue: {
      key: "labor",
      title: "Direito Trabalhista",
      area: "trabalhista",
      question: "Há verbas trabalhistas devidas?",
      requiredEvidence: ["CTPS", "holerith", "jornada", "dispensa"],
      risks: ["Prescrição quinquenal", "Justa causa"],
    },
  },
  {
    pattern: /tributo|imposto|ICMS|ISS|IRPF|IRPJ|lançamento fiscal/gi,
    issue: {
      key: "tax",
      title: "Direito Tributário",
      area: "tributario",
      question: "O lançamento tributário é válido?",
      requiredEvidence: ["auto de infração", "CTN aplicável", "base de cálculo"],
      risks: ["Decadência", "Prescrição"],
    },
  },
  {
    pattern: /tutela|urgência|liminar|antecipaç[ãa]o de tutela/gi,
    issue: {
      key: "injunction",
      title: "Tutela de Urgência",
      area: "processual",
      question: "São atendidos os requisitos da tutela de urgência (art. 300 CPC)?",
      requiredEvidence: ["probabilidade do direito", "perigo de dano"],
      risks: ["Ausência de perigo", "Contracautela"],
    },
  },
  {
    pattern: /honor[áa]rios|advogad|OAB|sucumb[êe]ncia/gi,
    issue: {
      key: "fees",
      title: "Honorários Advocatícios",
      area: "processual",
      question: "Os honorários são devidos e quantificáveis (art. 85 CPC)?",
      requiredEvidence: ["valor da condenação", "atos processuais", "grau de zelo"],
      risks: ["Quantificação baixa", "Honorários por equidade"],
    },
  },
];

export function identifyIssues(text: string, area: string | null): LegalIssue[] {
  const issues: LegalIssue[] = [];
  const seen = new Set<string>();

  for (const { pattern, issue } of ISSUE_PATTERNS) {
    const matches = text.match(pattern);
    if (matches && !seen.has(issue.key)) {
      seen.add(issue.key);
      issues.push({
        ...issue,
        area: area || issue.area,
        matchedTerms: matches,
      });
    }
  }

  return issues;
}

// ── Case Mapper determinístico (sem LLM) ────────────────────────────────────
// Extrai fatos, eventos e afirmações a partir do texto colado, usando regex.
// Princípio 18: Falha do LLM nunca deve destruir o resultado determinístico.

export async function mapCaseDeterministic(
  caseId: string,
  text: string
): Promise<{ output: CaseMapperOutput; evidence: EvidenceRefRecord[] }> {
  const evidence: EvidenceRefRecord[] = [];
  const facts: MapperFact[] = [];
  const events: MapperEvent[] = [];
  const assertions: MapperAssertion[] = [];
  const warnings: string[] = [];

  // Cria evidência do texto original (todo o texto colado é a primeira evidência)
  const textEvidence = await createEvidence({
    caseId,
    quote: text.slice(0, 500), // primeiros 500 chars como trecho de referência
    sourceKind: "text",
    retrievalMethod: "deterministic",
    documentId: "pasted-text",
    pageNumber: 1,
  });
  evidence.push(textEvidence);

  // Extrai datas (eventos)
  const datePattern = /(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+de\s+(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+\d{2,4})/gi;
  const dateMatches = text.match(datePattern) || [];
  for (const date of dateMatches.slice(0, 10)) {
    const eventEvidence = await createEvidence({
      caseId,
      quote: `Data mencionada: ${date}`,
      sourceKind: "text",
      retrievalMethod: "deterministic",
      documentId: "pasted-text",
      pageNumber: 1,
    });
    evidence.push(eventEvidence);
    events.push({
      description: `Data mencionada no texto: ${date}`,
      date,
      dateStatus: "exact",
      evidenceRefIds: [eventEvidence.id],
    });
  }

  // Extrai valores monetários (fatos)
  const valuePattern = /R\$\s*\d[\d.,]*\d{0,2}/gi;
  const valueMatches = text.match(valuePattern) || [];
  for (const value of valueMatches.slice(0, 10)) {
    const valEvidence = await createEvidence({
      caseId,
      quote: `Valor mencionado: ${value}`,
      sourceKind: "text",
      retrievalMethod: "deterministic",
      documentId: "pasted-text",
      pageNumber: 1,
    });
    evidence.push(valEvidence);
    facts.push({
      text: `Valor mencionado: ${value}`,
      evidenceRefIds: [valEvidence.id],
      confidence: 0.95,
    });
  }

  // Extrai CPFs/CNPJs (fatos)
  const cpfPattern = /\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}\b/g;
  const cpfMatches = text.match(cpfPattern) || [];
  for (const cpf of cpfMatches.slice(0, 5)) {
    const cpfEvidence = await createEvidence({
      caseId,
      quote: `Documento mencionado: [ANONIMIZADO]`,
      sourceKind: "text",
      retrievalMethod: "deterministic",
      documentId: "pasted-text",
      pageNumber: 1,
      metadata: { original: cpf }, // mantém no metadata, não no quote
    });
    evidence.push(cpfEvidence);
    facts.push({
      text: "Documento de identificação mencionado (anonimizado)",
      evidenceRefIds: [cpfEvidence.id],
      confidence: 0.9,
    });
  }

  // Questões jurídicas identificadas (afirmações do tipo rule)
  const issues = identifyIssues(text, null);
  for (const issue of issues) {
    assertions.push({
      text: issue.question,
      kind: "rule",
      evidenceRefIds: [textEvidence.id],
      supportStatus: "partial",
    });
    for (const risk of issue.risks) {
      assertions.push({
        text: `Risco: ${risk}`,
        kind: "risk",
        evidenceRefIds: [textEvidence.id],
        supportStatus: "absent",
      });
    }
  }

  // Warning se não há fatos extraídos
  if (facts.length === 0 && events.length === 0) {
    warnings.push("Não foi possível extrair fatos ou eventos automaticamente — enriquecimento por IA recomendado");
  }

  return {
    output: { facts, events, assertions, warnings },
    evidence,
  };
}

// ── Validar output do LLM contra evidências permitidas ─────────────────────
// Princípio 7: Um modelo não pode inventar evidence_ref_id.

import { validateEvidenceIds, validateEvidenceIntegrity } from "@/lib/evidence";

export async function validateMapperOutput(
  caseId: string,
  output: CaseMapperOutput,
  evidenceRefs: EvidenceRefRecord[]
): Promise<CaseMapperOutput> {
  const allowed = new Set(evidenceRefs.map((r) => r.id));

  // Valida fatos
  const validFacts: MapperFact[] = [];
  for (const fact of output.facts) {
    try {
      validateEvidenceIds(fact.evidenceRefIds, allowed);
      for (const eid of fact.evidenceRefIds) {
        await validateEvidenceIntegrity(caseId, eid);
      }
      validFacts.push(fact);
    } catch (e) {
      // Rejeita fato com evidência inválida (não quebra o pipeline)
      console.warn(`Fato rejeitado: ${(e as Error).message}`);
    }
  }

  // Valida assertions
  const validAssertions = output.assertions.filter((a) => {
    try {
      validateEvidenceIds(a.evidenceRefIds, allowed);
      return true;
    } catch {
      return false;
    }
  });

  return {
    ...output,
    facts: validFacts,
    assertions: validAssertions,
    warnings: [
      ...output.warnings,
      ...(output.facts.length !== validFacts.length
        ? [`${output.facts.length - validFacts.length} fato(s) rejeitado(s) por evidência inválida`]
        : []),
    ],
  };
}
