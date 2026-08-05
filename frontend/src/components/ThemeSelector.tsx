import { useEffect, useState } from "react";
import { AlertTriangle, Monitor, Moon, Sun } from "lucide-react";
import { useLocation } from "react-router";
import api from "../lib/api";
import { THEME_LABELS, useThemeStore } from "../stores/theme";
import type { ThemeMode } from "../stores/theme";
import { cn } from "./UI";

const THEME_OPTIONS: Array<{
  value: ThemeMode;
  icon: typeof Sun;
  description: string;
}> = [
  {
    value: "light",
    icon: Sun,
    description: "Interface clara para ambientes bem iluminados",
  },
  {
    value: "dark",
    icon: Moon,
    description: "Interface escura para reduzir luminosidade",
  },
  {
    value: "system",
    icon: Monitor,
    description: "Acompanha automaticamente o tema do dispositivo",
  },
];

const DEGRADED_LABELS: Record<string, string> = {
  casos: "Casos",
  casos_por_area: "Casos por área",
  prazos: "Prazos",
  financeiro: "Financeiro",
  ambiental_criticas: "Alertas ambientais",
  clientes_ativos: "Clientes ativos",
  pecas_aguardando_revisao: "Peças aguardando revisão",
};

export default function ThemeSelector({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  const { theme, setTheme } = useThemeStore();
  const { pathname } = useLocation();
  const [degradado, setDegradado] = useState<string[]>([]);
  const [dashboardIndisponivel, setDashboardIndisponivel] = useState(false);

  useEffect(() => {
    const paginaDashboard = pathname === "/" || pathname === "/dashboard";
    if (!paginaDashboard) {
      setDegradado([]);
      setDashboardIndisponivel(false);
      return;
    }

    let ativo = true;
    api
      .get("/dashboard/")
      .then((response) => {
        if (!ativo) return;
        const blocos = Array.isArray(response.data?.degradado)
          ? response.data.degradado.filter(
              (item: unknown): item is string => typeof item === "string",
            )
          : [];
        setDegradado(blocos);
        setDashboardIndisponivel(false);
      })
      .catch(() => {
        if (!ativo) return;
        setDegradado([]);
        setDashboardIndisponivel(true);
      });

    return () => {
      ativo = false;
    };
  }, [pathname]);

  const alertaVisivel = dashboardIndisponivel || degradado.length > 0;
  const blocosRotulados = degradado.map(
    (bloco) => DEGRADED_LABELS[bloco] || bloco,
  );
  const tituloAlerta = dashboardIndisponivel
    ? "Painel temporariamente indisponível"
    : "Dados temporariamente indisponíveis";
  const detalheAlerta = dashboardIndisponivel
    ? "Não considere os indicadores atuais como zero. Tente atualizar a página."
    : `${blocosRotulados.join(", ")}. Os valores exibidos nesses blocos não devem ser interpretados como zero.`;

  return (
    <div className={cn("space-y-2", className)}>
      {alertaVisivel && (
        <div
          role="alert"
          aria-live="polite"
          className="flex items-start gap-2 rounded-xl border border-warn-200 bg-warn-50 px-3 py-2 text-left text-xs leading-5 text-warn-800 dark:border-warn-500/30 dark:bg-warn-500/10 dark:text-warn-200"
        >
          <AlertTriangle
            className="mt-0.5 h-4 w-4 shrink-0"
            aria-hidden="true"
          />
          <div>
            <strong className="block font-semibold">{tituloAlerta}</strong>
            <span>{detalheAlerta}</span>
          </div>
        </div>
      )}

      <div
        className="rounded-xl border border-slate-200 bg-white p-1.5 dark:border-white/10 dark:bg-white/[0.04]"
        role="radiogroup"
        aria-label="Tema da interface"
      >
        <div className="grid grid-cols-3 gap-1">
          {THEME_OPTIONS.map(({ value, icon: Icon, description }) => {
            const active = theme === value;
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={active}
                aria-label={`${THEME_LABELS[value]}: ${description}`}
                title={description}
                onClick={() => setTheme(value)}
                className={cn(
                  "group flex min-w-0 items-center justify-center rounded-xl border px-3 py-2 text-xs font-semibold transition-all duration-150",
                  compact ? "gap-1.5" : "gap-2",
                  active
                    ? "border-primary-300 bg-primary-900 text-white shadow-sm dark:border-primary-400 dark:bg-primary-400 dark:text-primary-950"
                    : "border-transparent text-slate-500 hover:bg-slate-900/[0.05] hover:text-slate-800 dark:text-slate-400 dark:hover:bg-white/[0.06] dark:hover:text-slate-100",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {!compact && (
                  <span className="truncate">{THEME_LABELS[value]}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
