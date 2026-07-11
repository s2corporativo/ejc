// Central unificada: fusão de CentralAtividades (/atividades) e
// CentralRelacionamento (/central-relacionamento, agora redirect) em uma
// única tela com abas. A aba é controlada por ?tab= para deep links; o
// parâmetro ?view= continua sendo lido pela aba de atividades (compatível
// com os redirects /agenda e /kanban).
import { useSearchParams } from "react-router-dom";
import { CalendarClock, Users } from "lucide-react";
import { useAuth } from "../stores/auth";
import { ROLES } from "../config/moduleRegistry";
import CentralAtividades from "./CentralAtividades";
import CentralRelacionamento from "./CentralRelacionamento";

export type CentralTab = "atividades" | "relacionamento";

export function isCentralTab(value: string | null): value is CentralTab {
  return value === "atividades" || value === "relacionamento";
}

const TABS: { key: CentralTab; label: string; icon: typeof Users }[] = [
  { key: "atividades", label: "Agenda e Atividades", icon: CalendarClock },
  { key: "relacionamento", label: "Relacionamento", icon: Users },
];

export default function Central() {
  const [searchParams, setSearchParams] = useSearchParams();
  const user = useAuth((state) => state.user) as { role?: string } | null;
  // A antiga rota /central-relacionamento era restrita a gestores; o gate
  // de UI é preservado aqui (o backend segue como fonte de verdade do RBAC).
  const canSeeRelacionamento = Boolean(
    user?.role && (ROLES.gestores as readonly string[]).includes(user.role),
  );

  const rawTab = searchParams.get("tab");
  const tab: CentralTab =
    isCentralTab(rawTab) && (rawTab !== "relacionamento" || canSeeRelacionamento)
      ? rawTab
      : "atividades";

  const setTab = (next: CentralTab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  return (
    <div>
      {canSeeRelacionamento && (
        <div className="px-6 pt-4 max-w-7xl mx-auto">
          <div
            role="tablist"
            aria-label="Seções da central"
            className="inline-flex gap-1 rounded-xl border border-slate-200 bg-white p-1"
          >
            {TABS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  tab === key
                    ? "bg-navy text-white"
                    : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
      {tab === "relacionamento" ? (
        <CentralRelacionamento />
      ) : (
        <CentralAtividades />
      )}
    </div>
  );
}
