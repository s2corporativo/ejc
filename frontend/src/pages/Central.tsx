// Central unificada: fusão de atividades e relacionamento em uma única tela.
// A aba é controlada por ?tab= para deep links. A experiência operacional de
// atividades usa a CentralAtividadesSimplificada. Links históricos que chegam
// com `?tipo=` ou `?view=` permanecem temporariamente na CentralAtividades
// antiga para preservar filtros/visualizações durante a transição.
import { useSearchParams } from "react-router";
import { CalendarClock, Users } from "lucide-react";
import { useAuth } from "../stores/auth";
import { ROLES } from "../config/moduleRegistry";
import CentralAtividades from "./CentralAtividades";
import CentralAtividadesSimplificada from "./CentralAtividadesSimplificada";
import CentralRelacionamento from "./CentralRelacionamento";

export type CentralTab = "atividades" | "relacionamento";

export function isCentralTab(value: string | null): value is CentralTab {
  return value === "atividades" || value === "relacionamento";
}

const TABS: { key: CentralTab; label: string; icon: typeof Users }[] = [
  { key: "atividades", label: "Atividades", icon: CalendarClock },
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

  // `/prazos`, `/tarefas`, `/intimacoes`, `/suspensoes`, `/agenda` e `/kanban`
  // ainda redirecionam usando `tipo`/`view`. Enquanto os redirects não forem
  // migrados, o modo compatível mantém a semântica anterior em vez de ignorar
  // silenciosamente filtros ou visualizações. `/atividades` limpa já usa a UX nova.
  const legacyDeepLink = Boolean(
    searchParams.get("tipo") || searchParams.get("view"),
  );

  return (
    <div>
      {canSeeRelacionamento && (
        <div className="px-6 pt-4 max-w-7xl mx-auto">
          <div
            role="tablist"
            aria-label="Seções da central"
            className="inline-flex gap-1 rounded-xl bg-slate-900/[0.05] p-1 dark:bg-white/[0.07]"
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
        <CentralRelacionamento />
      ) : legacyDeepLink ? (
        <CentralAtividades />
      ) : (
        <CentralAtividadesSimplificada />
      )}
    </div>
  );
}
