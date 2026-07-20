import { Badge } from "./UI";
import {
  type HealthIndicator,
  SEVERITY_LABELS,
  ordenarIndicadores,
} from "./caseHealthModel";

export default function CaseHealthIndicators({ indicators }: {
  indicators: HealthIndicator[];
}) {
  const ordered = ordenarIndicadores(indicators);
  if (ordered.length === 0) {
    return (
      <section>
        <h3 className="font-semibold text-slate-950">Pendências e ações</h3>
        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
          Nenhuma pendência automática foi identificada pelos critérios atuais.
        </div>
      </section>
    );
  }
  return (
    <section>
      <h3 className="font-semibold text-slate-950">Pendências e ações</h3>
      <div className="mt-3 space-y-3">
        {ordered.map((indicator) => (
          <div key={indicator.code} className="rounded-xl border border-slate-200 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge>{SEVERITY_LABELS[indicator.severity]}</Badge>
              {typeof indicator.count === "number" && (
                <span className="text-xs text-slate-500">
                  {indicator.count} ocorrência(s)
                </span>
              )}
            </div>
            <p className="mt-2 text-sm font-medium text-slate-900">
              {indicator.message}
            </p>
            <p className="mt-1 text-sm text-slate-600">
              Próxima ação: {indicator.recommended_action}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
