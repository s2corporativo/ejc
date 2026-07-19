import { Monitor, Moon, Sun } from "lucide-react";
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

export default function ThemeSelector({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  const { theme, setTheme } = useThemeStore();

  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-1.5 dark:border-white/10 dark:bg-white/[0.04]",
        className,
      )}
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
              {!compact && <span className="truncate">{THEME_LABELS[value]}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
