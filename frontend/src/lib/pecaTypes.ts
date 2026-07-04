// Fonte única dos tipos de peça jurídica (values canônicos do backend +
// values legados ainda presentes em documentos existentes).
// Usada por Pecas.tsx e PecaGeneratorModal.tsx — não duplicar listas locais.

export interface PecaTipo {
  value: string;
  label: string;
}

export const PECA_TIPOS: PecaTipo[] = [
  // Values canônicos do backend
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
  // Values legados (preservados para compatibilidade com documentos existentes)
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
