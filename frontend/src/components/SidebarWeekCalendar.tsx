import { useEffect, useMemo, useState } from "react";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import { ptBR } from "date-fns/locale";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
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

const WEEKDAYS = ["D", "S", "T", "Q", "Q", "S", "S"];

/**
 * Calendário compacto da barra lateral.
 *
 * Mantém o endpoint e a navegação já existentes, mas troca a antiga visão
 * semanal pela visão mensal aprovada no shell de referência. Nenhuma regra de
 * prazo é calculada aqui: os pontos apenas indicam datas que vieram da API de
 * atividades e o clique abre a agenda do dia.
 */
export default function SidebarWeekCalendar() {
  const navigate = useNavigate();
  const [monthOffset, setMonthOffset] = useState(0);
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

  const visibleMonth = useMemo(
    () => addMonths(startOfMonth(new Date()), monthOffset),
    [monthOffset],
  );

  const days = useMemo(() => {
    const start = startOfWeek(startOfMonth(visibleMonth), { weekStartsOn: 0 });
    const end = endOfWeek(endOfMonth(visibleMonth), { weekStartsOn: 0 });
    return eachDayOfInterval({ start, end });
  }, [visibleMonth]);

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
      className="ejc-sidebar-month"
      aria-label="Calendário mensal integrado à agenda"
    >
      <div className="ejc-sidebar-month__header">
        <div className="ejc-sidebar-month__title">
          {format(visibleMonth, "MMMM yyyy", { locale: ptBR })}
        </div>
        <div className="ejc-sidebar-month__nav">
          <button
            type="button"
            onClick={() => setMonthOffset((value) => value - 1)}
            aria-label="Mês anterior"
          >
            <ChevronLeft aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setMonthOffset((value) => value + 1)}
            aria-label="Próximo mês"
          >
            <ChevronRight aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="ejc-sidebar-month__weekdays" aria-hidden="true">
        {WEEKDAYS.map((label, index) => (
          <span key={`${label}-${index}`}>{label}</span>
        ))}
      </div>

      <div className="ejc-sidebar-month__grid">
        {days.map((day) => {
          const key = dateKey(day);
          const today = isSameDay(day, new Date());
          const selected = isSameDay(day, selectedDate);
          const outside = !isSameMonth(day, visibleMonth);
          const hasActivity = activityDates.has(key);
          return (
            <button
              key={key}
              type="button"
              onClick={() => openDay(day)}
              className={`${outside ? "is-outside " : ""}${selected && !today ? "is-selected" : ""}`.trim() || undefined}
              aria-current={today ? "date" : undefined}
              aria-label={`${format(day, "EEEE, dd 'de' MMMM", { locale: ptBR })}${
                hasActivity ? ", possui compromissos" : ""
              }`}
            >
              <span>{format(day, "d")}</span>
              <i className={hasActivity ? "has-activity" : undefined} />
            </button>
          );
        })}
      </div>

      {agendaUnavailable && (
        <p role="status" className="ejc-sidebar-month__status">
          Agenda temporariamente indisponível
        </p>
      )}

      <button
        type="button"
        className="ejc-sidebar-month__footer"
        onClick={() => navigate("/atividades?view=calendario")}
      >
        Ver agenda completa <ArrowRight aria-hidden="true" size={11} />
      </button>
    </section>
  );
}
