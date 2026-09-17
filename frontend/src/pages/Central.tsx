// Central unificada: fusão de CentralAtividades (/atividades) e
// CentralRelacionamento (/central-relacionamento, agora redirect) em uma
// única tela com abas. A aba é controlada por ?tab= para deep links; o
// parâmetro ?view= continua sendo lido pela aba de atividades (compatível
// com os redirects /agenda e /kanban).
import { lazy, Suspense } from "react";
import { useSearchParams } from "react-router";
import { CalendarClock, Users } from "lucide-react";
import { useAuth } from "../stores/auth";
import { ROLES } from "../config/moduleRegistry";
import { Spinner } from "../components/UI";

// Code-splitting por aba (auditoria §2.6 #4): as duas centrais são grandes —
// carregadas sob demanda conforme a aba ativa.
const CentralAtividades = lazy(() => import("./CentralAtividades"));
const CentralRelacionamento = lazy(() => import("./CentralRelacionamento"));

export type CentralTab = "atividades" | "relacionamento";

export function isCentralTab(value: string | null): value is CentralTab {
  return value === "atividades" || value === "relacionamento";
}

const TABS: { key: CentralTab; label: string; icon: typeof Users }[] = [
  { key: "atividades", label: "Agenda, Prazos e Tarefas", icon: CalendarClock },
  { key: "relacionamento", label: "Atendimentos de Clientes", icon: Users },
];

export default function Central() {
  const [searchParams, setSearchParams] = useSearchParams();
  const user = useAuth((state) => state.user) as { role?: string } | null;

  // Espelha a matriz _ATENDIMENTO_ROLES do backend/routers/atendimentos.py:
  // superadmin, admin, socio, advogado e secretaria. O backend permanece a
  // fonte de verdade e restringe edição por autoria/responsabilidade quando
  // o perfil não é gestor.
  const canSeeRelacionamento = Boolean(
    user?.role && (ROLES.clientes as readonly string[]).includes(user.role),
  );

  const rawTab = searchParams.get("tab");
  const tab: CentralTab =
    isCentralTab(rawTab) &&
    (rawTab !== "relacionamento" || canSeeRelacionamento)
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
            className="grid w-full grid-cols-1 gap-1 rounded-xl bg-slate-900/[0.05] p-1 sm:inline-flex sm:w-auto dark:bg-white/[0.07]"
          >
            {TABS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={`flex min-w-0 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors sm:justify-start sm:py-1.5 ${
                  tab === key
                    ? "bg-navy text-white"
                    : "text-slate-600 hover:bg-slate-900/[0.09] dark:text-slate-300 dark:hover:bg-white/[0.12]"
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
        <Suspense
          fallback={
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          }
        >
          <CentralRelacionamento />
        </Suspense>
      ) : (
        <Suspense
          fallback={
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          }
        >
          <CentralAtividades />
        </Suspense>
      )}
    </div>
  );
}
