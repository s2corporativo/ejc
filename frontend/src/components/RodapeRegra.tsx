// ── Rodapé discreto de metadados de regra das calculadoras dos ramos ─────────
// As respostas da Onda 2 (correção jurídica) trazem `fontes[]`, `vigencia_regra`
// e `versao_regra`. Este rodapé exibe esses metadados em uma linha pequena,
// fora da tabela de resultados.

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
  const fontes: string[] = Array.isArray(data.fontes)
    ? data.fontes.map(textoFonte).filter(Boolean)
    : [];
  const partes = [
    fontes.length ? `Fontes: ${fontes.join(" · ")}` : null,
    data.vigencia_regra ? `vigência ${String(data.vigencia_regra)}` : null,
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
