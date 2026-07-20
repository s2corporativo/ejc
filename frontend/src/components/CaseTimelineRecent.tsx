import { Clock3 } from "lucide-react";
import {
  SOURCE_LABELS,
  type TimelineResponse,
  formatarDataEvento,
} from "./caseHealthModel";

export default function CaseTimelineRecent({ timeline }: {
  timeline: TimelineResponse | null;
}) {
  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold text-slate-950">Eventos recentes</h3>
        {(timeline?.truncated || timeline?.has_more) && (
          <span className="text-xs text-amber-700">
            Visualização parcial; consulte a linha do tempo completa.
          </span>
        )}
      </div>
      {!timeline?.items?.length ? (
        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
          Nenhum evento foi localizado para este caso.
        </div>
      ) : (
        <ol className="mt-3 space-y-3">
          {timeline.items.map((item) => (
            <li
              key={item.id}
              className="flex gap-3 rounded-xl border border-slate-200 p-4"
            >
              <span className="mt-0.5 rounded-lg bg-slate-100 p-2">
                <Clock3 className="h-4 w-4 text-slate-600" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">
                    {item.title}
                  </p>
                  <time className="text-xs text-slate-500">
                    {formatarDataEvento(item.occurred_at)}
                  </time>
                </div>
                {item.description && (
                  <p className="mt-1 line-clamp-3 text-sm text-slate-600">
                    {item.description}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                  <span>Origem: {SOURCE_LABELS[item.source] || item.source}</span>
                  {item.status && <span>Status: {item.status}</span>}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
