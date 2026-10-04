// proof_matrix.ts — Matriz fato→prova→ônus (diferencial sobre MinutaIA)
//
// Lacuna do MinutaIA: liga o fato à página, mas não à análise de ônus probatório.
// Este módulo constrói a matriz: cada alegação → tem prova? → quem prova? → risco?
//
// Base normativa:
// - art. 373 do CPC (ônus da prova — autor prova os fatos constitutivos, réu os extintivos)
// - art. 6º, VIII, do CDC (inversão do ônus da prova no consumidor hipossuficiente)
// - art. 818 da CLT (ônus no processo trabalhista)
// - art. 373, §1º, CPC (distribuição dinâmica do ônus)

export interface ProofMatrixEntry {
  fact: string;
  hasProof: boolean;
  proofType: string | null;
  proofDescription: string | null;
  burdenOfProof: "autor" | "reu" | "distribuido" | "invertido";
  burdenReason: string | null;
  riskLevel: "baixo" | "medio" | "alto";
  riskDescription: string | null;
  evidenceRefId: string | null;
}

export interface ProofMatrixResult {
  entries: ProofMatrixEntry[];
  summary: {
    totalFacts: number;
    factsWithProof: number;
    factsWithoutProof: number;
    highRiskFacts: number;
    invertedBurden: boolean;
  };
  recommendations: string[];
}

/**
 * Constrói a matriz fato→prova→ônus a partir das afirmações do caso.
 * Recebe as assertions já extraídas pelo Case Mapper/Cérebro.
 */
export function buildProofMatrix(params: {
  assertions: { text: string; kind: string; evidenceRefIds: string[] }[];
  area: string;
  isConsumer: boolean;
  isHypossufficient: boolean;
}): ProofMatrixResult {
  const { assertions, area, isConsumer, isHypossufficient } = params;
  const entries: ProofMatrixEntry[] = [];
  const recommendations: string[] = [];

  const hasInvertedBurden = isConsumer && isHypossufficient;

  for (const a of assertions) {
    const hasProof = a.evidenceRefIds.length > 0;
    const kind = a.kind.toLowerCase();

    // Determina ônus da prova
    let burdenOfProof: ProofMatrixEntry["burdenOfProof"] = "autor";
    let burdenReason: string | null = null;

    if (hasInvertedBurden) {
      burdenOfProof = "invertido";
      burdenReason = `Inversão do ônus (CDC art. 6º VIII) — consumidor hipossuficiente + verossimilhança das alegações`;
    } else if (area === "trabalhista") {
      burdenOfProof = "autor";
      burdenReason = "CLT art. 818 — ônus do autor (empregado) para fatos constitutivos";
    } else {
      burdenOfProof = "autor";
      burdenReason = "CPC art. 373, I — ônus do autor para fatos constitutivos";
    }

    // Se for fato extintivo (alegado pelo réu), o ônus é do réu
    if (kind.includes("extint") || kind.includes("impedi") || kind.includes("modifi")) {
      burdenOfProof = "reu";
      burdenReason = "CPC art. 373, II — ônus do réu para fatos extintivos/impeditivos/modificativos";
    }

    // Risco
    let riskLevel: ProofMatrixEntry["riskLevel"] = "medio";
    let riskDescription: string | null = null;

    if (!hasProof) {
      riskLevel = "alto";
      riskDescription = "Fato sem prova documental — risco de improcedência por insuficiência probatória";
    } else if (kind === "inference") {
      riskLevel = "medio";
      riskDescription = "Inferência da IA — precisa de confirmação por advogado";
    } else if (kind === "fact") {
      riskLevel = "baixo";
      riskDescription = "Fato extraído com evidência vinculada";
    }

    entries.push({
      fact: a.text,
      hasProof,
      proofType: hasProof ? "documental" : null,
      proofDescription: hasProof ? `Evidência: ${a.evidenceRefIds.join(", ")}` : "Sem prova vinculada",
      burdenOfProof,
      burdenReason,
      riskLevel,
      riskDescription,
      evidenceRefId: a.evidenceRefIds[0] || null,
    });
  }

  // Recomendações
  const factsWithoutProof = entries.filter((e) => !e.hasProof);
  const highRiskFacts = entries.filter((e) => e.riskLevel === "alto");

  if (factsWithoutProof.length > 0) {
    recommendations.push(`${factsWithoutProof.length} fato(s) sem prova — risque ao cliente para obter documentação`);
  }
  if (highRiskFacts.length > 0) {
    recommendations.push(`${highRiskFacts.length} fato(s) de alto risco — considere produção de outras provas (testemunhal, pericial)`);
  }
  if (hasInvertedBurden) {
    recommendations.push("Ônus da prova invertido (CDC art. 6º VIII) — documente a hipossuficiência e verossimilhança");
  }
  recommendations.push("Verifique se há fatos extintivos/impeditivos que o réu precisará provar (CPC art. 373, II)");

  return {
    entries,
    summary: {
      totalFacts: entries.length,
      factsWithProof: entries.filter((e) => e.hasProof).length,
      factsWithoutProof: factsWithoutProof.length,
      highRiskFacts: highRiskFacts.length,
      invertedBurden: hasInvertedBurden,
    },
    recommendations,
  };
}
