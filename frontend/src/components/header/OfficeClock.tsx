import { useEffect, useMemo, useState } from "react";
import { Clock3 } from "lucide-react";
import { OFFICE_CONFIG } from "../../config/office";

function formatParts(date: Date) {
  const time = new Intl.DateTimeFormat("pt-BR", {
    timeZone: OFFICE_CONFIG.timezone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);

  const day = new Intl.DateTimeFormat("pt-BR", {
    timeZone: OFFICE_CONFIG.timezone,
    weekday: "long",
    day: "2-digit",
    month: "long",
  }).format(date);

  return {
    time,
    day: day.charAt(0).toUpperCase() + day.slice(1),
  };
}

export default function OfficeClock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const delay = 60_000 - (Date.now() % 60_000);
    let interval: number | undefined;
    const timeout = window.setTimeout(() => {
      setNow(new Date());
      interval = window.setInterval(() => setNow(new Date()), 60_000);
    }, delay);
    return () => {
      window.clearTimeout(timeout);
      if (interval) window.clearInterval(interval);
    };
  }, []);

  const formatted = useMemo(() => formatParts(now), [now]);

  return (
    <div className="ejc-office-clock" aria-label={`${formatted.time}, ${formatted.day}`}>
      <span className="ejc-office-clock-icon" aria-hidden="true">
        <Clock3 className="h-4 w-4" />
      </span>
      <span className="min-w-0">
        <strong>{formatted.time}</strong>
        <small>{formatted.day}</small>
      </span>
    </div>
  );
}
