import React from "react";
import { Sparkles, ShieldCheck, AlertTriangle } from "lucide-react";
import { Markdown } from "../Markdown";

/**
 * AIResponse — componente PADRÃO para exibir respostas/análises da IA do EJC.
 *
 * Resolve o problema de Markdown bruto (asteriscos) renderizando o conteúdo
 * pelo <Markdown> seguro (elementos React, sem dangerouslySetInnerHTML) e
 * padroniza o visual: cabeçalho com ícone de IA, badge opcional de grau de
 * confiança, estados de loading/erro e aviso discreto de validação humana
 * (OAB Prov. 205/2021). Use em qualquer tela que exiba texto gerado por IA.
 */

type Confianca = "alta" | "media" | "baixa" | string;

const CONF_STYLE: Record<string, string> = {
  alta: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  media: "bg-amber-50 text-amber-700 ring-amber-200",
  baixa: "bg-rose-50 text-rose-700 ring-rose-200",
};

export function AIResponse({
  source,
  title = "Análise da IA",
  confianca,
  loading = false,
  error,
  aviso = true,
  className = "",
  children,
}: {
  source?: string | null;
  title?: string;
  confianca?: Confianca | null;
  loading?: boolean;
  error?: string | null;
  aviso?: boolean;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={`rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden ${className}`}
    >
      {/* Cabeçalho */}
      <div className="flex items-center gap-3 border-b border-slate-100 bg-slate-50/60 px-4 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-sm">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-slate-800">{title}</p>
        </div>
        {confianca && (
          <span
            className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1 ${
              CONF_STYLE[String(confianca).toLowerCase()] ||
              "bg-slate-100 text-slate-600 ring-slate-200"
            }`}
          >
            Confiança: {confianca}
          </span>
        )}
      </div>

      {/* Corpo */}
      <div className="px-4 py-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-violet-500" />
            Gerando análise…
          </div>
        ) : error ? (
          <div className="flex items-start gap-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : children ? (
          children
        ) : (
          <Markdown source={source} className="text-sm leading-relaxed text-slate-700" />
        )}
      </div>

      {/* Aviso de validação humana (discreto) */}
      {aviso && !loading && !error && (
        <div className="flex items-center gap-2 border-t border-slate-100 bg-slate-50/60 px-4 py-2 text-[11px] text-slate-500">
          <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          <span>
            Conteúdo gerado por IA. Requer validação do advogado responsável (OAB
            Prov. 205/2021).
          </span>
        </div>
      )}
    </div>
  );
}

export default AIResponse;
