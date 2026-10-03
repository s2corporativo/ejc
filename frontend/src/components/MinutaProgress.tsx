import { Loader2, CheckCircle2 } from "lucide-react";
import { ETAPAS_MINUTA, type StatusEtapa } from "../lib/minuta";

export default function MinutaProgress({
  etapas,
}: {
  etapas: Record<number, StatusEtapa>;
}) {
  return (
    <>
      {ETAPAS_MINUTA.map((e) => {
        const st = etapas[e.num] ?? "aguardando";
        return (
          <div
            key={e.num}
            className={`flex items-center gap-3 px-4 py-2.5 rounded-xl border transition-colors ${
              st === "concluido"
                ? "bg-success-50 border-success-200"
                : st === "em_andamento"
                  ? "bg-bronze-50/40 border-bronze-pale"
                  : "bg-white border-slate-100"
            }`}
          >
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-[11px] font-medium ${
                st === "concluido"
                  ? "bg-success-600 text-white"
                  : st === "em_andamento"
                    ? "bg-bronze text-white"
                    : "bg-slate-100 text-slate-400"
              }`}
            >
              {st === "em_andamento" ? (
                <Loader2 size={12} className="animate-spin" />
              ) : st === "concluido" ? (
                <CheckCircle2 size={12} />
              ) : (
                e.num
              )}
            </div>
            <span
              className={`text-sm ${
                st === "aguardando" ? "text-slate-400" : "text-navy"
              }`}
            >
              {e.titulo}
            </span>
          </div>
        );
      })}
    </>
  );
}
