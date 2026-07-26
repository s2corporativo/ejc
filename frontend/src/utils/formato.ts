// Formatação pt-BR canônica de moeda e data/hora das telas do EJC.
// Implementação única dos helpers que viviam duplicados em páginas e
// componentes. `components/UI.tsx` re-exporta `fmtMoney`/`fmtDate`/`fmtDateTime`
// daqui — importar de qualquer um dos dois é válido; NÃO recrie
// toLocaleString local em tela nova.

/**
 * Formata um valor em Reais (R$ 1.234,56). `null`/`undefined`/NaN viram o
 * travessão padrão de "sem valor" das telas. `casasMax` permite mais precisão
 * (ex.: custo de tokens de IA usa 4 casas) sem perder o mínimo de 2.
 */
export function fmtMoney(v?: number | null, casasMax = 2): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
    maximumFractionDigits: casasMax,
  });
}

/**
 * Data curta pt-BR (dd/mm/aaaa). Datas "puras" (sem hora) são ancoradas ao
 * meio-dia para não recuar um dia por fuso horário. Vazio devolve travessão.
 */
export function fmtDate(d?: string | null): string {
  if (!d) return "—";
  const date = new Date(d.includes("T") ? d : d + "T12:00:00");
  return date.toLocaleDateString("pt-BR");
}

/** Data+hora curtas pt-BR (dd/mm/aaaa HH:MM). Vazio/inválido devolve `vazio`. */
export function fmtDateTime(d?: string | null, vazio = "—"): string {
  if (!d) return vazio;
  const date = new Date(d);
  if (Number.isNaN(date.getTime())) return vazio;
  return date.toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}
