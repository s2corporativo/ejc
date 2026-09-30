import { useEffect, useState } from "react";
import { Clock3, Star } from "lucide-react";
import { Link } from "react-router";
import {
  getRecentCases,
  RECENT_CASES_EVENT,
  type RecentCaseItem,
} from "../lib/recentCases";

export default function RecentCasesNav({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const [items, setItems] = useState<RecentCaseItem[]>(() =>
    getRecentCases().slice(0, 5),
  );

  useEffect(() => {
    const refresh = () => setItems(getRecentCases().slice(0, 5));
    window.addEventListener(RECENT_CASES_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(RECENT_CASES_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  if (collapsed || items.length === 0) return null;

  return (
    <section
      className="ejc-sidebar-recents"
      aria-label="Casos recentes e favoritos"
    >
      <div className="ejc-sidebar-recents__title">
        <Clock3 aria-hidden="true" />
        <span>Recentes</span>
      </div>
      <div className="ejc-sidebar-recents__list">
        {items.map((item) => (
          <Link
            key={item.id}
            to={`/casos/${item.id}`}
            onClick={onNavigate}
            title={item.titulo}
          >
            {item.favorite ? (
              <Star className="is-favorite" aria-label="Favorito" />
            ) : (
              <span className="ejc-sidebar-recents__dot" aria-hidden="true" />
            )}
            <span>
              <strong>{item.titulo}</strong>
              {item.area && <small>{item.area}</small>}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
