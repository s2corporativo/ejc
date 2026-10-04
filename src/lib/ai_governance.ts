// ai_governance.ts — Governança de IA: Provider Registry, Sanitization Policy, Response Validator
// Portado dos módulos Python do EJC para TypeScript.

// ═══════════════════════════════════════════════════════════════════════════
// 1. PROVIDER REGISTRY
// ═══════════════════════════════════════════════════════════════════════════

export interface ProviderSpec {
  name: string;
  external: boolean;
  enabled: boolean;
  supportsJsonSchema: boolean;
  supportsTools: boolean;
  apiKey?: string;
}

/**
 * Registry central de providers de IA.
 * Nenhuma outra camada conhece configuração ou chave de API.
 */
export const PROVIDERS: Record<string, ProviderSpec> = {
  "zai": {
    name: "zai",
    external: true,      // z-ai-web-dev-sdk é externo (API cloud)
    enabled: true,        // habilitado por padrão
    supportsJsonSchema: true,
    supportsTools: false,
  },
  "ollama": {
    name: "ollama",
    external: false,      // local (se disponível)
    enabled: false,       // não configurado neste ambiente
    supportsJsonSchema: true,
    supportsTools: false,
  },
  "anthropic": {
    name: "anthropic",
    external: true,
    enabled: false,
    supportsJsonSchema: true,
    supportsTools: true,
  },
  "groq": {
    name: "groq",
    external: true,
    enabled: false,
    supportsJsonSchema: false,
    supportsTools: false,
  },
  "maritaca": {
    name: "maritaca",
    external: true,
    enabled: false,
    supportsJsonSchema: false,
    supportsTools: false,
  },
};

/** Kill-switch global de IA. Se false, NENHUM provider é elegível. */
export const AI_ENABLED = true;

/** Kill-switch de providers externos. Se false, só providers locais são elegíveis. */
export const AI_EXTERNAL_PROVIDERS_ALLOWED = true;

/**
 * Verifica se um provider é elegível considerando kill-switches.
 */
export function isProviderEligible(providerName: string): { eligible: boolean; reason?: string } {
  if (!AI_ENABLED) {
    return { eligible: false, reason: "kill-switch global de IA desligado (AI_ENABLED=false)" };
  }

  const spec = PROVIDERS[providerName];
  if (!spec) {
    return { eligible: false, reason: `provider '${providerName}' não registrado` };
  }

  if (!spec.enabled) {
    return { eligible: false, reason: `${providerName}_ENABLED=false` };
  }

  if (spec.external && !AI_EXTERNAL_PROVIDERS_ALLOWED) {
    return { eligible: false, reason: "kill-switch de provedores externos desligado (AI_EXTERNAL_PROVIDERS_ALLOWED=false)" };
  }

  return { eligible: true };
}

/**
 * Lista providers elegíveis.
 */
export function getEligibleProviders(): ProviderSpec[] {
  return Object.values(PROVIDERS).filter((p) => isProviderEligible(p.name).eligible);
}

/**
 * Verifica se há pelo menos um provider elegível. Fail-closed.
 */
export function hasAvailableProvider(): boolean {
  return getEligibleProviders().length > 0;
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. SANITIZATION POLICY (4 modos)
// ═══════════════════════════════════════════════════════════════════════════

export enum SanitizationMode {
  LOCAL_COMPLETO = "local_completo",               // só Ollama local, nunca externo
  EXTERNO_PSEUDONIMIZADO = "externo_pseudonimizado", // pseudonimiza → externo → reidrata
  EXTRACAO_LOCAL = "extracao_local",               // PII extraída localmente antes do gateway
  MASCARAMENTO = "mascaramento",                   // irreversível (legado)
}

/**
 * Mapeamento de tipo de tarefa → modo de sanitização.
 * Default revisável pelo titular do escritório.
 */
const TASK_SANITIZATION_MAP: Record<string, SanitizationMode> = {
  // Análise e minuta → pseudonimizado reversível (padrão)
  "analise_caso": SanitizationMode.EXTERNO_PSEUDONIMIZADO,
  "minuta": SanitizationMode.EXTERNO_PSEUDONIMIZADO,
  "dossie": SanitizationMode.EXTERNO_PSEUDONIMIZADO,
  "pesquisa": SanitizationMode.EXTERNO_PSEUDONIMIZADO,
  "resumo": SanitizationMode.EXTERNO_PSEUDONIMIZADO,
  // Áreas sensíveis → local completo (fail-closed sem IA local)
  "criminal": SanitizationMode.LOCAL_COMPLETO,
  "menores": SanitizationMode.LOCAL_COMPLETO,
  // Padrão para tarefas não mapeadas
  "default": SanitizationMode.EXTERNO_PSEUDONIMIZADO,
};

/**
 * Determina o modo de sanitização para uma tarefa.
 */
export function getSanitizationMode(taskType: string): SanitizationMode {
  return TASK_SANITIZATION_MAP[taskType] || TASK_SANITIZATION_MAP["default"];
}

/**
 * Verifica se um provider é permitido para um modo de sanitização.
 * LOCAL_COMPLETO → só providers locais (não-externos). Sem local → fail-closed.
 */
export function providerAllowedForMode(
  provider: ProviderSpec,
  mode: SanitizationMode
): boolean {
  if (mode === SanitizationMode.LOCAL_COMPLETO) {
    return !provider.external;
  }
  return true; // outros modos permitem externos
}

/**
 * Resolve providers elegíveis para uma tarefa, considerando modo de sanitização.
 * Fail-closed: se LOCAL_COMPLETO e nenhum local disponível, retorna vazio.
 */
export function resolveProviders(taskType: string): ProviderSpec[] {
  const mode = getSanitizationMode(taskType);
  const eligible = getEligibleProviders();
  return eligible.filter((p) => providerAllowedForMode(p, mode));
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. RESPONSE VALIDATOR
// ═══════════════════════════════════════════════════════════════════════════

export interface ValidationViolation {
  rule: string;
  severity: "error" | "warning";
  detail: string;
  excerpt?: string;
}

export interface ValidationResult {
  valid: boolean;
  violations: ValidationViolation[];
  markedAsDraft: boolean;
}

/**
 * Valida a saída do LLM contra regras jurídicas inegociáveis.
 * Princípio: a IA nunca deve prometer resultado, inventar lei ou produzir
 * jurisprudência inexistente.
 */
export function validateResponse(text: string): ValidationResult {
  const violations: ValidationViolation[] = [];
  const lower = text.toLowerCase();

  // Regra 1: Vedação de promessa de resultado (art. 2º, §1º EOAB + CDC)
  const promessaPatterns = [
    /vai\s+ganhar/gi,
    /100\s*%\s*(de\s+chance|de\s+probabilidade)/gi,
    /certeza\s+absoluta/gi,
    /garantia\s+de\s+(?:êxito|sucesso|vit[oó]ria)/gi,
    /sem\s+d[úu]vida\s+vencer/gi,
    /vit[oó]ria\s+garantida/gi,
  ];
  for (const pattern of promessaPatterns) {
    const match = text.match(pattern);
    if (match) {
      violations.push({
        rule: "VEDAÇÃO_PROMESSA_RESULTADO",
        severity: "error",
        detail: "A IA não pode prometer resultado — vedação do EOAB art. 2º §1º",
        excerpt: match[0],
      });
    }
  }

  // Regra 2: Vedação de aconselhamento sem ressalva
  if (lower.includes("você deve") && !lower.includes("revisão") && !lower.includes("advogado")) {
    violations.push({
      rule: "ACONSELHAMENTO_SEM_RESSALVA",
      severity: "warning",
      detail: "A IA sugere ação sem mencionar necessidade de revisão por advogado",
    });
  }

  // Regra 3: Detecção de jurisprudência potencialmente inventada
  // Padrões como "REsp 999.999.999" ou "Tema 9999" sem verificação
  const fakeJurisprudence = text.match(/(?:REsp|RE|AgInt|HC)\s*[\d.]{7,}/gi);
  if (fakeJurisprudence) {
    for (const match of fakeJurisprudence.slice(0, 3)) {
      violations.push({
        rule: "JURISPRUDENCIA_NAO_VERIFICADA",
        severity: "warning",
        detail: `Citação de jurisprudência '${match}' não foi verificada contra a base curada — confirme fonte oficial`,
        excerpt: match,
      });
    }
  }

  // Regra 4: Detectar ausência de marca "RASCUNHO"
  // Toda saída de IA deve ser marcada como rascunho
  const hasDraftMarker =
    lower.includes("rascunho") ||
    lower.includes("revisão humana") ||
    lower.includes("sujeito a revisão") ||
    lower.includes("draft");
  const markedAsDraft = hasDraftMarker;

  if (!markedAsDraft) {
    violations.push({
      rule: "AUSENCIA_MARCA_RASCUNHO",
      severity: "warning",
      detail: "A saída da IA não está marcada como rascunho — adicione aviso de revisão humana obrigatória",
    });
  }

  // Regra 5: Detecção de prazos calculados automaticamente
  const prazoPatterns = [
    /prazo\s+(?:de|para)\s+\d+\s+dias?\s+(?:úteis|corridos)/gi,
    /vence\s+em\s+\d+\s+dias/gi,
  ];
  for (const pattern of prazoPatterns) {
    const match = text.match(pattern);
    if (match) {
      violations.push({
        rule: "PRAZO_CALCULADO_AUTOMATICAMENTE",
        severity: "warning",
        detail: "Prazo processual calculado pela IA — confira calendário, feriados e rito aplicável",
        excerpt: match[0],
      });
    }
  }

  return {
    valid: violations.filter((v) => v.severity === "error").length === 0,
    violations,
    markedAsDraft,
  };
}

/**
 * Adiciona aviso de rascunho à saída se não estiver presente.
 */
export function ensureDraftMarker(text: string): string {
  const lower = text.toLowerCase();
  if (
    lower.includes("rascunho") ||
    lower.includes("revisão humana") ||
    lower.includes("sujeito a revisão")
  ) {
    return text;
  }
  return text + "\n\n---\n⚠ **RASCUNHO GERADO POR IA** — Revisão por advogado é OBRIGATÓRIA antes de qualquer uso ou protocolo. Não constitui aconselhamento jurídico.";
}
