import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  CalendarClock,
  CheckSquare2,
  Clock3,
  FileText,
  Gavel,
  MapPin,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { EmptyState, ErrorState, PageHeader, Spinner, StatusBadge } from "../components/UI";
import api from "../lib/api";
import { asList } from "../lib/list";

interface ActivityItem {
  id?: string;
  tipo?: string;
  subtipo?: string;
  fonte?: string;
  titulo?: string;
  descricao?: string;
  date?: string;
  status?: string;
  case_id?: string;
  caso_titulo?: string;
  responsavel_id?: string;
  prioridade?: string;
}

interface AgendaEvent {
  id?: string;
  tipo?: string;
  hora?: string;
  local?: string;
}

interface DayActivity extends ActivityItem {
  hora?: string;
  local?: string;
}

const TYPE_CONFIG: Record<
  string,
  { label: string; icon: LucideIcon; className: string }
> = {
  prazo: {
    label: "Prazo",
    icon: Clock3,
    className: "bg-danger-50 text-danger-700 ring-danger-200",
  },
  tarefa: {
    label: "Tarefa",
    icon: CheckSquare2,
    className: "bg-primary-50 text-primary-700 ring-primary-200",
  },
  audiencia: {
    label: "Audiência",
    icon: Gavel,
    className: "bg-warn-50 text-warn-700 ring-warn-200",
  },
  reuniao: {
    label: "Reunião",
    icon: Users,
    className: "bg-slate-100 text-slate-700 ring-slate-200",
  },
  diligencia: {
    label: "Diligência",
    icon: MapPin,
    className: "bg-success-50 text-success-700 ring-success-200",
  },
  compromisso: {
    label: "Compromisso",
    icon: CalendarClock,
    className: "bg-ouro-palha text-ouro-profundo ring-ouro-claro/60",
  },
};

function isValidDateKey(value?: string): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T12:00:00`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function formatDay(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function activityType(item: DayActivity) {
  const raw = item.subtipo || item.tipo || item.fonte || "compromisso";
  if (raw === "agenda") return "compromisso";
  return raw;
}

export default function AgendaDia() {
  const { date } = useParams<{ date: string }>();
  const validDate = isValidDateKey(date) ? date : null;
  const [items, setItems] = useState<DayActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!validDate) {
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    setError(false);

    Promise.allSettled([
      api.get("/atividades", { params: { apenas_pendentes: false } }),
      api.get("/agenda-eventos/", { params: { page_size: 500 } }),
    ])
      .then(([activitiesResult, agendaResult]) => {
        if (!active) return;
        if (activitiesResult.status !== "fulfilled") {
          setError(true);
          setItems([]);
          return;
        }

        const agendaMap = new Map<string, AgendaEvent>();
        if (agendaResult.status === "fulfilled") {
          for (const event of asList<AgendaEvent>(agendaResult.value.data)) {
            if (event.id) agendaMap.set(event.id, event);
          }
        }

        const dayItems = asList<ActivityItem>(activitiesResult.value.data)
          .filter((item) => item.date?.slice(0, 10) === validDate)
          .map((item) => {
            const event = item.id ? agendaMap.get(item.id) : undefined;
            return {
              ...item,
              subtipo: item.subtipo || event?.tipo,
              hora: event?.hora,
              local: event?.local,
            };
          })
          .sort((a, b) => {
            const timeA = a.hora || "23:59";
            const timeB = b.hora || "23:59";
            return timeA.localeCompare(timeB) || (a.titulo || "").localeCompare(b.titulo || "");
          });

        setItems(dayItems);
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [validDate]);

  const title = useMemo(
    () => (validDate ? formatDay(validDate) : "Data inválida"),
    [validDate],
  );

  if (!validDate) {
    return (
      <div className="mx-auto w-full max-w-4xl">
        <ErrorState message="A data informada não é válida." />
        <div className="mt-4 text-center">
          <Link to="/atividades?view=calendario" className="btn-secondary">
            Voltar para a agenda
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5">
      <PageHeader
        eyebrow="Agenda do dia"
        title={title}
        subtitle="Prazos, tarefas, audiências e compromissos provenientes da agenda real do EJC."
        actions={
          <Link
            to="/atividades?view=calendario"
            className="btn-secondary"
          >
            <ArrowLeft className="h-4 w-4" />
            Agenda completa
          </Link>
        }
      />

      {loading ? (
        <div className="grid min-h-56 place-items-center rounded-xl border border-slate-200 bg-white">
          <Spinner />
        </div>
      ) : error ? (
        <ErrorState message="Não foi possível carregar a agenda deste dia." />
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <EmptyState
            icon={CalendarClock}
            title="Nenhuma atividade neste dia"
            message="A agenda real não retornou prazos, tarefas ou compromissos para a data selecionada."
          />
        </div>
      ) : (
        <section
          aria-label={`Atividades de ${title}`}
          className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
        >
          <div className="divide-y divide-slate-100">
            {items.map((item, index) => {
              const type = activityType(item);
              const config = TYPE_CONFIG[type] || {
                label: "Atividade",
                icon: FileText,
                className: "bg-slate-100 text-slate-700 ring-slate-200",
              };
              const Icon = config.icon;
              const destination = item.case_id
                ? `/casos/${item.case_id}`
                : "/atividades?view=calendario";

              return (
                <Link
                  key={`${item.fonte || type}-${item.id || index}`}
                  to={destination}
                  className="group flex items-start gap-4 px-4 py-4 transition-colors hover:bg-ouro-palha/30 sm:px-5"
                >
                  <span
                    className={`mt-0.5 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ring-1 ring-inset ${config.className}`}
                  >
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <strong className="truncate text-sm font-semibold text-slate-900">
                        {item.titulo || "Atividade sem título"}
                      </strong>
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-ouro-profundo">
                        {config.label}
                      </span>
                    </span>
                    <span className="mt-1 block text-xs text-slate-500">
                      {[item.hora, item.local, item.caso_titulo]
                        .filter(Boolean)
                        .join(" · ") || "Sem detalhes adicionais"}
                    </span>
                    {item.descricao && (
                      <span className="mt-1 block line-clamp-2 text-xs leading-5 text-slate-400">
                        {item.descricao}
                      </span>
                    )}
                  </span>

                  <span className="flex shrink-0 flex-col items-end gap-2">
                    {item.hora && (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold tabular-nums text-slate-700">
                        <Clock3 className="h-3.5 w-3.5 text-ouro-profundo" />
                        {item.hora}
                      </span>
                    )}
                    {item.status && <StatusBadge value={item.status} />}
                  </span>
                </Link>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
