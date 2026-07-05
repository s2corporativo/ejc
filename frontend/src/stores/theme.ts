// ── Tema claro/escuro/sistema ──────────────────────────────────
// Store Zustand no padrão dos demais stores (stores/auth.ts).
// Persiste em localStorage ("ejc_theme") e aplica/remove a classe
// `dark` no <html> (Tailwind darkMode: "class" + variáveis --ejc-*).
//
// IMPORTANTE: chamar initTheme() no topo do main.tsx, ANTES do
// primeiro render — o index.html tem CSP script-src 'self' (sem
// script inline), então a aplicação síncrona acontece aqui.
import { create } from "zustand";

export type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "ejc_theme";
const MODES: ThemeMode[] = ["light", "dark", "system"];

export const THEME_LABELS: Record<ThemeMode, string> = {
  light: "Claro",
  dark: "Escuro",
  system: "Sistema",
};

function readStored(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    // valores legados do antigo useTheme ("light"/"dark") continuam válidos
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* ignore */
  }
  return "system";
}

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

function resolveIsDark(mode: ThemeMode): boolean {
  return mode === "dark" || (mode === "system" && systemPrefersDark());
}

function applyToDocument(mode: ThemeMode): boolean {
  const dark = resolveIsDark(mode);
  document.documentElement.classList.toggle("dark", dark);
  return dark;
}

interface ThemeState {
  /** Preferência do usuário (pode ser "system"). */
  theme: ThemeMode;
  /** Tema efetivamente aplicado no momento (resolve "system"). */
  isDark: boolean;
  setTheme: (mode: ThemeMode) => void;
  /** Ciclo do botão do header: claro → escuro → sistema. */
  cycleTheme: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: readStored(),
  isDark: resolveIsDark(readStored()),
  setTheme: (mode) => {
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* ignore */
    }
    set({ theme: mode, isDark: applyToDocument(mode) });
  },
  cycleTheme: () => {
    const { theme, setTheme } = get();
    setTheme(MODES[(MODES.indexOf(theme) + 1) % MODES.length]);
  },
}));

/**
 * Aplica o tema salvo de forma síncrona (antes do primeiro paint) e
 * registra o listener de mudança do SO para o modo "system".
 */
export function initTheme() {
  applyToDocument(useThemeStore.getState().theme);
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const onChange = () => {
    const { theme } = useThemeStore.getState();
    if (theme === "system")
      useThemeStore.setState({ isDark: applyToDocument("system") });
  };
  // addEventListener é o caminho moderno; addListener cobre WebKit antigo
  if (typeof mq.addEventListener === "function")
    mq.addEventListener("change", onChange);
  else if (typeof (mq as any).addListener === "function")
    (mq as any).addListener(onChange);
}
