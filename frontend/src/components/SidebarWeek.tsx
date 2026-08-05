import { useEffect, useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { asList } from "../lib/list";
import { cn } from "./UI";

type AgendaEvent = {
  id?: string;
  data_evento?: string;
  concluido?: boolean;
};

function startOfWeek(value: Date) {
  const date = new Date(value);
  date.setHours(12, 0, 0, 0);
  const day = date.getDay();
  const offset = day === 0 ? -6 : 1 - day;
  date.setDate(date.getDate() + offset);
  return date;
}

function addDays(date: Date, amount: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + amount);
  return next;
}

function isoDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const DAY_LABELS = ["S", "T", "Q", "Q", "S", "S", "D"];

export default function SidebarWeek({ collapsed }: { collapsed: boolean }) {
  const navigate = useNavigate();
  const [anchor, setAnchor] = useState(() => startOfWeek(new Date()));
  const [events, setEvents] = useState<AgendaEvent[]>([]);

  useEffect(() => {
    let active = true;
    api
      .get("/agenda-eventos/?page_size=500")
      .then((response) => {
        if (active) setEvents(asList(response.data));
      })
      .catch(() => {
        if (active) setEvents([]);
      });
    return () => {
      active = false;
    };
  }, []);

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, index) => addDays(anchor, index)),
    [anchor],
  );
  const eventDates = useMemo(
    () =>
      new Set(
        events
          .filter((event) => !event.concluido && event.data_evento)
          .map((event) => String(event.data_evento).slice(0, 10)),
      ),
    [events],
  );
  const today = isoDate(new Date());

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => navigate("/atividades")}
        className="ejc-sidebar-week-collapsed"
        title="Abrir agenda"
        aria-label="Abrir agenda"
      >
        <CalendarDays className="h-4 w-4" />
      </button>
    );
  }

  const monthLabel = new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
  }).format(anchor);

  return (
    <section className="ejc-sidebar-week" aria-label="Agenda semanal">
      <div className="ejc-sidebar-week-header">
        <span className="min-w-0">
          <strong>Agenda semanal</strong>
          <small>{monthLabel}</small>
        </span>
        <span className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setAnchor((date) => addDays(date, -7))}
            aria-label="Semana anterior"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setAnchor((date) => addDays(date, 7))}
            aria-label="Próxima semana"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </span>
      </div>

      <div className="ejc-sidebar-week-grid">
        {days.map((date, index) => {
          const iso = isoDate(date);
          const isToday = iso === today;
          const hasEvent = eventDates.has(iso);
          return (
            <button
              key={iso}
              type="button"
              className={cn(
                "ejc-sidebar-day",
                isToday && "is-today",
                hasEvent && "has-event",
              )}
              onClick={() => navigate(`/atividades?data=${iso}`)}
              aria-label={`Abrir agenda de ${date.toLocaleDateString("pt-BR")}`}
            >
              <small>{DAY_LABELS[index]}</small>
              <strong>{date.getDate()}</strong>
              <i aria-hidden="true" />
            </button>
          );
        })}
      </div>

      <button
        type="button"
        onClick={() => navigate("/atividades")}
        className="ejc-sidebar-week-open"
      >
        Ver agenda completa
      </button>
    </section>
  );
}
