// validators.ts — Validadores determinísticos pré-geração.
//
// Roda em <50ms. Sem LLM. Identifica problemas formais antes de gastar
// tokens gerando peça. Cada validador retorna lista de issues (severity
// = error | warning | info).

export type Severity = "error" | "warning" | "info";

export interface ValidationIssue {
  rule: string;
  severity: Severity;
  field?: string;
  message: string;
  fix?: string;
}

export interface ValidationInput {
  fatos: string;
  pedidos?: string;
  valorCausa?: string;
  area: string;
  templateSlug: string;
}

/** Detecção de menção a OAB do signatário. */
function checkOAB(input: ValidationInput): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (!/OAB[\/\s]?[A-Z]{2}\b/i.test(input.fatos + (input.pedidos ?? ""))) {
    issues.push({
      rule: "OAB_SIGNATARIO",
      severity: "warning",
      message: "Não detectamos a OAB do advogado signatário (formato: OAB/MG 123456).",
      fix: "Adicione 'OAB/UF 000000' no campo de qualificação.",
    });
  }
  return issues;
}

/** Valor da causa obrigatório e em formato monetário. */
function checkValorCausa(input: ValidationInput): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (!input.valorCausa) {
    issues.push({
      rule: "VALOR_CAUSA_OBRIGATORIO",
      severity: "error",
      field: "valorCausa",
      message: "Valor da causa é obrigatório (CPC art. 291-294).",
      fix: "Preencha o campo 'Valor da causa' no formulário.",
    });
  } else if (!/R\$\s*\d|R\$\s*\d+,\d+|\d{1,3}(\.\d{3})*,\d{2}/.test(input.valorCausa)) {
    issues.push({
      rule: "VALOR_CAUSA_FORMATO",
      severity: "warning",
      field: "valorCausa",
      message: "Formato do valor da causa não é monetário padrão (R$ 0,00).",
      fix: "Use o formato 'R$ 1.234,56'.",
    });
  }
  return issues;
}

/** Identificação das partes (autor e réu). */
function checkPartes(input: ValidationInput): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const text = input.fatos.toLowerCase();
  const hasAutor = /autor|requerente|exequente|impetrante|reclamante/.test(text);
  const hasReu = /r[uú]e|requerido|executado|coator|impetrado|reclamad[ao]/.test(text);
  if (!hasAutor) {
    issues.push({
      rule: "PARTES_AUTOR",
      severity: "warning",
      message: "Não detectamos menção clara à parte autora (autor/requerente/exequente).",
      fix: "Identifique a parte autora no início da narrativa dos fatos.",
    });
  }
  if (!hasReu) {
    issues.push({
      rule: "PARTES_REU",
      severity: "warning",
      message: "Não detectamos menção clara à parte ré (réu/requerido/executado).",
      fix: "Identifique a parte ré no início da narrativa dos fatos.",
    });
  }
  return issues;
}

/** Pedidos devem ser claros e específicos. */
function checkPedidos(input: ValidationInput): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const p = input.pedidos ?? "";
  if (p.length === 0) {
    issues.push({
      rule: "PEDIDOS_VAZIOS",
      severity: "info",
      message: "Pedidos não detalhados — a IA vai inferir do caso.",
    });
  } else if (p.length < 20) {
    issues.push({
      rule: "PEDIDOS_CURTOS",
      severity: "warning",
      field: "pedidos",
      message: "Pedidos muito curtos podem gerar peça imprecisa.",
      fix: "Detalhe cada pedido: principal, subsidiário, alternativos, tutela de urgência.",
    });
  }
  return issues;
}

/** Datas e local. */
function checkDataLocal(input: ValidationInput): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (!/\b\d{1,2}\s+de\s+\w+\s+de\s+\d{4}|data\s*[:=]|\d{2}\/\d{2}\/\d{4}/i.test(input.fatos)) {
    issues.push({
      rule: "DATA_FATOS",
      severity: "info",
      message: "Não detectamos datas explícitas nos fatos.",
      fix: "Considere incluir datas relevantes ('em 15/03/2024', 'no dia 5 de janeiro').",
    });
  }
  if (!/\b(Comarca|Munic[íi]pio|Estado)\s+de\s+\w+|-\s*[A-Z]{2}\b/.test(input.fatos)) {
    issues.push({
      rule: "LOCAL_FATOS",
      severity: "info",
      message: "Não detectamos menção clara ao local (Comarca/Estado).",
      fix: "Indique a comarca competente para fins de competência (CPC art. 46).",
    });
  }
  return issues;
}

/** Validação de área jurídica. */
function checkArea(input: ValidationInput): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const areasValidas = ["civil", "processo_civil", "consumidor", "trabalhista", "previdenciario", "penal", "processo_penal", "tributario", "administrativo", "ambiental", "digital", "constitucional"];
  if (!areasValidas.includes(input.area)) {
    issues.push({
      rule: "AREA_INVALIDA",
      severity: "error",
      field: "area",
      message: `Área '${input.area}' não reconhecida. Use: ${areasValidas.join(", ")}.`,
    });
  }
  return issues;
}

/** Validador composto (executa todos). */
export function validatePeticao(input: ValidationInput): ValidationIssue[] {
  return [
    ...checkArea(input),
    ...checkPartes(input),
    ...checkOAB(input),
    ...checkValorCausa(input),
    ...checkPedidos(input),
    ...checkDataLocal(input),
  ];
}

export function summarizeIssues(issues: ValidationIssue[]): { errors: number; warnings: number; infos: number } {
  return {
    errors: issues.filter((i) => i.severity === "error").length,
    warnings: issues.filter((i) => i.severity === "warning").length,
    infos: issues.filter((i) => i.severity === "info").length,
  };
}