// ── Rodapé discreto de metadados de regra das calculadoras dos ramos ─────────
// As respostas da Onda 2 (correção jurídica) trazem `fontes[]`, `vigencia_regra`
// e `versao_regra`. Este rodapé exibe esses metadados em uma linha pequena,
// fora da tabela de resultados.

/** Chaves de metadados que saem da tabela de resultados e vão para o rodapé. */
export const METADADOS_REGRA = [
  "fontes",
  "fonte",
  "vigencia_regra",
  "vigencia_tabela",
  "versao_regra",
];

function textoFonte(f: unknown): string {
  if (typeof f === "string") return f;
  if (f && typeof f === "object") {
    const o = f as { titulo?: unknown; nome?: unknown; fonte?: unknown };
    for (const v of [o.titulo, o.nome, o.fonte]) {
      if (typeof v === "string" && v) return v;
    }
  }
  return "";
}

export default function RodapeRegra({ data }: { data: any }) {
  if (!data || typeof data !== "object") return null;
  // `fontes[]` (plural) e `fonte` (singular, tabelas do tributário) coexistem.
  const brutas = Array.isArray(data.fontes)
    ? data.fontes
    : data.fonte
      ? [data.fonte]
      : [];
  const fontes: string[] = brutas.map(textoFonte).filter(Boolean);
  const vigencia = data.vigencia_regra ?? data.vigencia_tabela;
  const partes = [
    fontes.length ? `Fontes: ${fontes.join(" · ")}` : null,
    vigencia ? `vigência ${String(vigencia)}` : null,
    data.versao_regra
      ? `regra v${String(data.versao_regra).replace(/^v/i, "")}`
      : null,
  ].filter(Boolean);
  if (partes.length === 0) return null;
  return (
    <p className="mt-2 pt-2 border-t border-gold-200 text-[10px] text-slate-400">
      {partes.join(" · ")}
    </p>
  );
}
