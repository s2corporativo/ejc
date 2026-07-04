// Fonte única dos tipos de peça jurídica (values canônicos do backend +
// values legados ainda presentes em documentos existentes).
// Usada por Pecas.tsx e PecaGeneratorModal.tsx — não duplicar listas locais.

export interface PecaTipo {
  value: string;
  label: string;
}

// Tipos aceitos pelo pipeline de GERAÇÃO (backend peca_service.TIPOS_PECA —
// o endpoint /peca-geracao valida contra essa lista e responde 422 fora dela).
export const PECA_TIPOS_GERACAO: PecaTipo[] = [
  { value: "peticao_inicial", label: "Petição Inicial" },
  { value: "contestacao", label: "Contestação" },
  { value: "replica", label: "Réplica" },
  { value: "recurso_ordinario", label: "Recurso Ordinário" },
  { value: "apelacao", label: "Apelação" },
  { value: "agravo_de_instrumento", label: "Agravo de Instrumento" },
  { value: "contrarrazoes", label: "Contrarrazões" },
  { value: "memorias", label: "Memoriais" },
  { value: "acordo", label: "Proposta de Acordo" },
  { value: "parecer", label: "Parecer Jurídico" },
  { value: "notificacao", label: "Notificação" },
  { value: "contrato", label: "Minuta de Contrato" },
  { value: "impugnacao", label: "Impugnação" },
];

// Lista completa para telas de DOCUMENTOS (legal_docs aceita também os values
// legados abaixo, presentes em registros já salvos).
export const PECA_TIPOS: PecaTipo[] = [
  ...PECA_TIPOS_GERACAO,
  { value: "recurso", label: "Recurso" },
  { value: "agravo", label: "Agravo" },
  { value: "procuracao", label: "Procuração" },
  { value: "notificacao_extrajudicial", label: "Notificação Extrajudicial" },
  { value: "defesa_ambiental", label: "Defesa Ambiental" },
  { value: "outro", label: "Outro" },
];

export const PECA_TIPO_LABELS: Record<string, string> = Object.fromEntries(
  PECA_TIPOS.map((t) => [t.value, t.label]),
);

export function pecaTipoLabel(value: string): string {
  return PECA_TIPO_LABELS[value] ?? value.replace(/_/g, " ");
}
