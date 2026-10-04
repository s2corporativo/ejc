// legal_calculator.ts — Cálculos jurídicos determinísticos (diferencial sobre MinutaIA)
//
// Lacuna do MinutaIA: cálculos ficam a cargo de ferramentas externas.
// Este módulo faz cálculos determinísticos auditáveis: prazos, correção,
// juros, prescrição — sem delegar aritmética ao LLM.
//
// Base normativa:
// - Prazos: art. 219 e 224 do CPC, Lei 11.419/06
// - Correção: INPC/IPCA (fonte BCB/IBGE)
// - Juros: art. 406 do CC (1% ao mês), Súmula 482 STJ (0,5%)
// - Prescrição: art. 205 CC (10 anos), art. 206 CC (5 anos), art. 23 CBC
// - Verbas trabalhistas: CLT art. 477, Súmula 381 TST

// ── Cálculo de Prazos Processuais ─────────────────────────────────────────

export interface DeadlineResult {
  vencimento: Date;
  tipoContagem: "uteis" | "corridos";
  diasUteis: number;
  diasCorridos: number;
  observacoes: string[];
}

/**
 * Calcula prazo processual.
 * NOTA: não considera feriados locais (requer calendário do tribunal).
 * O sistema alerta: "Verifique feriados locais e suspensões do tribunal".
 */
export function calculateDeadline(
  marcoInicial: Date,
  prazoDias: number,
  tipoContagem: "uteis" | "corridos" = "uteis"
): DeadlineResult {
  const observacoes: string[] = [];
  const vencimento = new Date(marcoInicial);

  if (tipoContagem === "corridos") {
    // Dias corridos: soma direta (ex: prazo de 15 dias corridos)
    vencimento.setDate(vencimento.getDate() + prazoDias);
    observacoes.push("Contagem em dias corridos (verificar se o rito exige úteis)");
  } else {
    // Dias úteis: pula sábados e domingos
    let added = 0;
    while (added < prazoDias) {
      vencimento.setDate(vencimento.getDate() + 1);
      const day = vencimento.getDay();
      if (day !== 0 && day !== 6) { // não é domingo (0) nem sábado (6)
        added++;
      }
    }
    observacoes.push("Contagem em dias úteis (exclui sábados e domingos)");
  }

  // Prorrogação: se vence em dia sem expediente, vai para o próximo dia útil
  const vencDay = vencimento.getDay();
  if (vencDay === 0 || vencDay === 6) {
    while (vencimento.getDay() === 0 || vencimento.getDay() === 6) {
      vencimento.setDate(vencimento.getDate() + 1);
    }
    observacoes.push("Vencimento caiu em fim de semana — prorrogado para o próximo dia útil");
  }

  observacoes.push("⚠ Verifique feriados locais, feriados forenses e suspensões do tribunal");
  observacoes.push("⚠ A IA nunca confirma prazo — confira manualmente com o calendário oficial");

  const diasCorridos = Math.round((vencimento.getTime() - marcoInicial.getTime()) / (1000 * 60 * 60 * 24));

  return {
    vencimento,
    tipoContagem,
    diasUteis: prazoDias,
    diasCorridos,
    observacoes,
  };
}

// ── Cálculo de Correção Monetária ─────────────────────────────────────────

export interface CorrectionResult {
  valorCorrigido: number;
  fatorCorrecao: number;
  memoriaCalculo: string;
  indiceUsado: string;
  observacoes: string[];
}

/**
 * Calcula correção monetária usando índice informado.
 * Para uso real, buscar índices do IBGE/SIDRA via /api/fontes/ibge.
 */
export function calculateCorrection(
  valorOriginal: number,
  fatorAcumulado: number, // fator de correção acumulado (ex: 1.5 = 50% de correção)
  indice: string = "IPCA"
): CorrectionResult {
  const valorCorrigido = valorOriginal * fatorAcumulado;
  const observacoes: string[] = [];

  observacoes.push(`Índice usado: ${indice}`);
  observacoes.push(`Fator acumulado: ${fatorAcumulado.toFixed(4)}`);
  observacoes.push(`Valor original: R$ ${valorOriginal.toFixed(2)}`);
  observacoes.push(`Valor corrigido: R$ ${valorCorrigido.toFixed(2)}`);
  observacoes.push("⚠ Confirme o índice e período via /api/fontes/ibge");

  return {
    valorCorrigido,
    fatorCorrecao: fatorAcumulado,
    memoriaCalculo: `${valorOriginal.toFixed(2)} × ${fatorAcumulado.toFixed(4)} = ${valorCorrigido.toFixed(2)}`,
    indiceUsado: indice,
    observacoes,
  };
}

// ── Cálculo de Juros de Mora ──────────────────────────────────────────────

export interface InterestResult {
  valorJuros: number;
  valorTotal: number;
  taxaMensal: number;
  meses: number;
  memoriaCalculo: string;
  base: string;
}

/**
 * Calcula juros de mora.
 * - CC art. 406: 1% ao mês (civil)
 * - Súmula 482 STJ: 0,5% ao mês (antes da Lei 12.506/2011)
 * - CLT (após 30/06/2009): 1% ao mês (Súmula 381 TST revogada, agora 1%)
 */
export function calculateInterest(
  valorPrincipal: number,
  meses: number,
  taxaMensal: number = 0.01, // 1% ao mês (padrão CC art. 406)
  base: "cc_art_406" | "stj_482" | "clt" = "cc_art_406"
): InterestResult {
  // Juros simples (não compostos, salvo previsão contratual)
  const valorJuros = valorPrincipal * taxaMensal * meses;
  const valorTotal = valorPrincipal + valorJuros;

  const baseLabels: Record<string, string> = {
    cc_art_406: "CC art. 406 (1% ao mês)",
    stj_482: "Súmula 482 STJ (0,5% ao mês — anterior à Lei 12.506/2011)",
    clt: "CLT — Justiça do Trabalho (1% ao mês)",
  };

  return {
    valorJuros,
    valorTotal,
    taxaMensal,
    meses,
    memoriaCalculo: `${valorPrincipal.toFixed(2)} × ${taxaMensal} × ${meses} meses = ${valorJuros.toFixed(2)} (juros simples)`,
    base: baseLabels[base] || base,
  };
}

// ── Verificação de Prescrição ──────────────────────────────────────────────

export interface PrescriptionResult {
  prescrito: boolean;
  prazoPrescricional: number; // anos
  baseNormativa: string;
  diasRestantes: number | null;
  observacoes: string[];
}

/**
 * Verifica prescrição de forma determinística.
 * Base: CC art. 205 (10 anos), CC art. 206 (5 anos), CBC art. 206 §3º (3 anos),
 * CLT art. 11 (5 anos + 2 anos após extinção), CTN art. 173 (5 anos).
 */
export function checkPrescription(
  dataFato: Date,
  dataajuizamento: Date,
  area: string = "civil"
): PrescriptionResult {
  const observacoes: string[] = [];
  let prazoAnos = 10;
  let baseNormativa = "CC art. 205 (10 anos — regra geral)";

  // Prazo por área
  switch (area.toLowerCase()) {
    case "civil":
      prazoAnos = 10;
      baseNormativa = "CC art. 205 (10 anos — regra geral)";
      break;
    case "consumer":
      prazoAnos = 5;
      baseNormativa = "CDC art. 27 (5 anos — pretensão à reparação por fato do produto/serviço)";
      break;
    case "trabalhista":
      prazoAnos = 5;
      baseNormativa = "CLT art. 11 (5 anos após extinção do contrato + 2 anos para ajuizar)";
      observacoes.push("CLT: 5 anos de crédito + 2 anos para ajuizar após extinção");
      break;
    case "tributario":
      prazoAnos = 5;
      baseNormativa = "CTN art. 173 (5 anos — pretensão para constituir crédito tributário)";
      break;
    case "penal":
      prazoAnos = 12; // média — depende do tipo penal (CP art. 109)
      baseNormativa = "CP art. 109 — prazo varia conforme a pena máxima (mínimo 3, máximo 20 anos)";
      observacoes.push("Penal: verifique a pena do crime específico (CP art. 109)");
      break;
    default:
      prazoAnos = 10;
      baseNormativa = "CC art. 205 (10 anos — regra geral)";
  }

  const limitePrescricao = new Date(dataFato);
  limitePrescricao.setFullYear(limitePrescricao.getFullYear() + prazoAnos);

  const prescrito = dataajuizamento > limitePrescricao;
  const diasRestantes = Math.round(
    (limitePrescricao.getTime() - dataajuizamento.getTime()) / (1000 * 60 * 60 * 24)
  );

  observacoes.push(`Data do fato: ${dataFato.toLocaleDateString("pt-BR")}`);
  observacoes.push(`Data do ajuizamento: ${dataajuizamento.toLocaleDateString("pt-BR")}`);
  observacoes.push(`Limite prescricional: ${limitePrescricao.toLocaleDateString("pt-BR")} (${prazoAnos} anos)`);
  if (prescrito) {
    observacoes.push("⚠ PRESCRITO — ajuizamento após o prazo prescricional");
  } else {
    observacoes.push(`Dias restantes até prescrição: ${diasRestantes}`);
  }
  observacoes.push("⚠ Verifique marcos interruptivos (art. 202 CC) — pode haver interrupção");
  observacoes.push("⚠ A IA nunca confirma prazo — confira manualmente");

  return {
    prescrito,
    prazoPrescricional: prazoAnos,
    baseNormativa,
    diasRestantes: prescrito ? null : diasRestantes,
    observacoes,
  };
}
