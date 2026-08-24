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

/**
 * Taxa de êxito de tese em percentual inteiro ("75%").
 *
 * O backend grava `teses.taxa_sucesso` como FRAÇÃO 0–1
 * (`routers/teses.py::_recalcular_taxa` → `vezes_venceu / vezes_usada`), mas o
 * campo é nullable sem default e existe base semeada em 0–100. Este helper
 * aceita as duas convenções (`<= 1` é fração) para que a mesma tese nunca
 * apareça como "0,75%" numa tela e "75%" na outra — divergência real observada
 * entre `DossieEstrategicoCaso` (renderizava o valor cru) e `TabTeses`.
 *
 * `null`/`undefined` significa SEM HISTÓRICO (nenhum vínculo com resultado
 * registrado) — devolve travessão, nunca "0%", que o advogado leria como
 * "tese que nunca venceu".
 */
export function fmtTaxaSucesso(v?: number | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return `${Math.round(n <= 1 ? n * 100 : n)}%`;
}
