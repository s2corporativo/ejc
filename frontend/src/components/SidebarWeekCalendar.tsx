import { useEffect, useMemo, useState } from "react";
import { addDays, addWeeks, format, isSameDay, startOfWeek } from "date-fns";
import { ptBR } from "date-fns/locale";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router";
import api from "../lib/api";
import { asList } from "../lib/list";

interface ActivitySummary {
  id?: string;
  date?: string;
  titulo?: string;
  status?: string;
}

function dateKey(value: Date | string): string {
  if (typeof value === "string") return value.slice(0, 10);
  return format(value, "yyyy-MM-dd");
}

export default function SidebarWeekCalendar() {
  const navigate = useNavigate();
  const [weekOffset, setWeekOffset] = useState(0);
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const [activities, setActivities] = useState<ActivitySummary[]>([]);
  const [agendaUnavailable, setAgendaUnavailable] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .get("/atividades", { params: { apenas_pendentes: false } })
      .then((response) => {
        if (!active) return;
        setActivities(asList(response.data));
        setAgendaUnavailable(false);
      })
      .catch(() => {
        if (!active) return;
        setActivities([]);
        setAgendaUnavailable(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const weekStart = useMemo(
    () => addWeeks(startOfWeek(new Date(), { weekStartsOn: 1 }), weekOffset),
    [weekOffset],
  );
  const days = useMemo(
    () => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)),
    [weekStart],
  );
  const activityDates = useMemo(
    () =>
      new Set(
        activities
          .map((item) => item.date)
          .filter(Boolean)
          .map(String)
          .map(dateKey),
      ),
    [activities],
  );

  const openDay = (day: Date) => {
    setSelectedDate(day);
    navigate(`/atividades/dia/${dateKey(day)}`);
  };

  return (
    <section
      className="ejc-sidebar-week"
      aria-label="Calendário semanal integrado à agenda"
    >
      <div className="ejc-sidebar-week__header">
        <div>
          <div className="ejc-sidebar-week__eyebrow">Agenda</div>
          <div className="ejc-sidebar-week__title">
            {format(weekStart, "dd MMM", { locale: ptBR })} —{" "}
            {format(addDays(weekStart, 6), "dd MMM", { locale: ptBR })}
          </div>
        </div>
        <div className="ejc-sidebar-week__nav">
          <button
            type="button"
            onClick={() => setWeekOffset((value) => value - 1)}
            aria-label="Semana anterior"
          >
            <ChevronLeft aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setWeekOffset((value) => value + 1)}
            aria-label="Próxima semana"
          >
            <ChevronRight aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="ejc-sidebar-week__days">
        {days.map((day) => {
          const key = dateKey(day);
          const selected = isSameDay(day, selectedDate);
          const today = isSameDay(day, new Date());
          const hasActivity = activityDates.has(key);
          return (
            <button
              key={key}
              type="button"
              onClick={() => openDay(day)}
              className={selected ? "is-selected" : undefined}
              aria-current={today ? "date" : undefined}
              aria-label={`${format(day, "EEEE, dd 'de' MMMM", { locale: ptBR })}${
                hasActivity ? ", possui compromissos" : ""
              }`}
            >
              <span>{format(day, "EEEEE", { locale: ptBR })}</span>
              <strong>{format(day, "dd")}</strong>
              <i className={hasActivity ? "has-activity" : undefined} />
            </button>
          );
        })}
      </div>

      {agendaUnavailable && (
        <p role="status" className="ejc-sidebar-week__status">
          Agenda temporariamente indisponível
        </p>
      )}
    </section>
  );
}
