import { useEffect, useState } from "react";
import { Inbox, RefreshCcw } from "lucide-react";
import { ErrorState, Spinner } from "../../components/UI";
import { getDptOpportunityQueue, type DptOpportunityQueueItem } from "./api";

function formatDateTime(value?: string | null) {
  if (!value) return "Data não informada";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("pt-BR");
}

export default function DptOpportunities() {
  const [items, setItems] = useState<DptOpportunityQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  async function load() {
    setLoading(true);
    setError(false);
    try {
      setItems(await getDptOpportunityQueue());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) {
    return (
      <div className="grid min-h-[260px] place-items-center rounded-2xl border border-slate-200 bg-white dark:border-white/10 dark:bg-white/[0.03]">
        <Spinner />
      </div>
    );
  }
  if (error) {
    return (
      <ErrorState message="Não foi possível carregar a fila de oportunidades empresariais." />
    );
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Inbox className="mt-0.5 h-5 w-5 text-amber-600" />
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              Oportunidades em triagem
            </h2>
            <p className="mt-1 text-sm leading-6 text-slate-500">
              Fila interna minimizada. Contatos, mensagem e demais dados do lead
              permanecem no rascunho canônico e não são replicados nesta visão.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 dark:border-white/10 dark:text-slate-200"
        >
          <RefreshCcw className="h-3.5 w-3.5" /> Atualizar
        </button>
      </div>

      {items.length === 0 ? (
        <div className="mt-5 rounded-xl border border-dashed border-slate-200 p-6 text-sm text-slate-500 dark:border-white/10">
          Nenhuma oportunidade pendente está visível no seu escopo.
        </div>
      ) : (
        <div className="mt-5 divide-y divide-slate-100 dark:divide-white/10">
          {items.map((item) => (
            <div
              key={item.intake_id}
              className="grid gap-2 py-3 sm:grid-cols-[1fr_auto] sm:items-center"
            >
              <div>
                <div className="text-sm font-semibold text-slate-900 dark:text-white">
                  Intake {item.intake_id.slice(0, 8)}…
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {item.origem || "Origem não informada"} ·{" "}
                  {formatDateTime(item.created_at)}
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-[11px] font-semibold">
                <span className="rounded-full bg-amber-50 px-2.5 py-1 text-amber-700 dark:bg-amber-400/10 dark:text-amber-300">
                  {item.status}
                </span>
                {item.urgencia_declarada ? (
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600 dark:bg-white/10 dark:text-slate-300">
                    Urgência declarada: {item.urgencia_declarada}
                  </span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
