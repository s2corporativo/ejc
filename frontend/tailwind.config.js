/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /*
         * Identidade De Paula Teixeira — bronze/ouro/espresso sobre marfim.
         * `blue`/`violet`/`purple` voltam a ser as cores padrão do Tailwind
         * (Fase 3): os usos literais legados são migrados para `primary-*`
         * (ação/marca, era o remap de `blue`) e `ai-*` (superfície de IA, era
         * o remap de `violet`/`purple`) em vez de continuar re-pintando as
         * cores nativas do Tailwind.
         */

        // Sidebar — slate (era espresso/azul-marinho)
        sidebar: {
          DEFAULT: "#0F172A",
          light:   "#1E293B",
          hover:   "#172033",
          active:  "#0B111F",
        },
        // Primária — bronze (ação/marca, substitui o remap de `blue`)
        primary: {
          DEFAULT: "#8C6A33",
          50:  "#FAF5EF", 100: "#F0E4D2", 200: "#E2CBA8", 300: "#CBA877",
          400: "#B98A3C", 500: "#A6792F", 600: "#8C6A33", 700: "#6E5228",
          800: "#5A431F", 900: "#473414", 950: "#2A1F0C",
        },
        // IA — teal (superfície de IA, substitui o remap de `violet`/`purple`)
        ai: {
          DEFAULT: "#266761",
          50:  "#ECF4F3", 100: "#D2E7E4", 200: "#A8D0CB", 300: "#73B0A9",
          400: "#459089", 500: "#2F7A72", 600: "#266761", 700: "#1F534E",
          800: "#1B433F", 900: "#173734", 950: "#0B201E",
        },
        // navy — repintado para slate (era espresso/azul)
        navy: {
          DEFAULT: "#0F172A",
          950: "#020617", 900: "#0F172A", 800: "#1E293B",
          700: "#334155", 600: "#475569", 100: "#F1F5F9", 50: "#F8FAFC",
        },
        // Bronze / ouro — marca
        bronze: {
          DEFAULT: "#8C6A33",
          dark:    "#6E5228",
          deep:    "#5A431F",
          medium:  "#9A7742",
          light:   "#C6A158",
          pale:    "#E8D6AE",
          50:      "#FAF5EF",
          30:      "#FDF9F5",
        },
        gold: {
          DEFAULT: "#C6A158",
          dark:    "#9A7742",
          light:   "#DBC084",
          700:     "#6E5228",
          600:     "#8C6A33",
          50:      "#FAF5EF",
        },
        ink: {
          DEFAULT: "#111827",
          light:   "#374151",
        },
        canvas: "#f7f8fa",
        parchment: "#F1F5F9",
        muted: "#6b7280",
        border: "#e5e7eb",
        // Status — formalizados (Fase 3), escala completa Tailwind padrão
        // (success=emerald, warn=amber, danger=red, info=sky — mesmos hex)
        success: {
          DEFAULT: "#10b981",
          50: "#ecfdf5", 100: "#d1fae5", 200: "#a7f3d0", 300: "#6ee7b7",
          400: "#34d399", 500: "#10b981", 600: "#059669", 700: "#047857",
          800: "#065f46", 900: "#064e3b", 950: "#022c22",
        },
        warn: {
          DEFAULT: "#f59e0b",
          50: "#fffbeb", 100: "#fef3c7", 200: "#fde68a", 300: "#fcd34d",
          400: "#fbbf24", 500: "#f59e0b", 600: "#d97706", 700: "#b45309",
          800: "#92400e", 900: "#78350f", 950: "#451a03",
        },
        warning: {
          DEFAULT: "#f59e0b",
          50: "#fffbeb", 100: "#fef3c7", 200: "#fde68a", 300: "#fcd34d",
          400: "#fbbf24", 500: "#f59e0b", 600: "#d97706", 700: "#b45309",
          800: "#92400e", 900: "#78350f", 950: "#451a03",
        },
        danger: {
          DEFAULT: "#ef4444",
          50: "#fef2f2", 100: "#fee2e2", 200: "#fecaca", 300: "#fca5a5",
          400: "#f87171", 500: "#ef4444", 600: "#dc2626", 700: "#b91c1c",
          800: "#991b1b", 900: "#7f1d1d", 950: "#450a0a",
        },
        error: {
          DEFAULT: "#ef4444",
          50: "#fef2f2", 100: "#fee2e2", 200: "#fecaca", 300: "#fca5a5",
          400: "#f87171", 500: "#ef4444", 600: "#dc2626", 700: "#b91c1c",
          800: "#991b1b", 900: "#7f1d1d", 950: "#450a0a",
        },
        info: {
          DEFAULT: "#0ea5e9",
          50: "#f0f9ff", 100: "#e0f2fe", 200: "#bae6fd", 300: "#7dd3fc",
          400: "#38bdf8", 500: "#0ea5e9", 600: "#0284c7", 700: "#0369a1",
          800: "#075985", 900: "#0c4a6e", 950: "#082f49",
        },
      },
      fontFamily: {
        sans:  ['"DM Sans"', "system-ui", "sans-serif"],
        serif: ['"Cormorant Garamond"', "Georgia", "Cambria", "serif"],
        // Mono de sistema — dados processuais (nº CNJ, CPF/CNPJ, valores).
        // Sem fonte externa: usa o que já existe no SO.
        mono: [
          "ui-monospace",
          '"Cascadia Code"',
          '"JetBrains Mono"',
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        // Papéis semânticos (Fase 2 do redesign)
        display: ["2.25rem", { lineHeight: "2.6rem" }], // números de dashboard, heros
        caption: ["0.7rem",  { lineHeight: "1rem" }],   // metadados, legendas
        "2xs": ["0.65rem",  { lineHeight: "1rem" }],
        xs:    ["0.75rem",  { lineHeight: "1.125rem" }],
        sm:    ["0.8125rem",{ lineHeight: "1.25rem" }],
        base:  ["0.9375rem",{ lineHeight: "1.6rem" }],
        lg:    ["1.0625rem",{ lineHeight: "1.65rem" }],
        xl:    ["1.1875rem",{ lineHeight: "1.75rem" }],
        "2xl": ["1.375rem", { lineHeight: "1.9rem" }],
        "3xl": ["1.75rem",  { lineHeight: "2.1rem" }],
        "4xl": ["2.25rem",  { lineHeight: "2.5rem" }],
      },
      fontWeight: {
        light:    "300",
        normal:   "400",
        medium:   "500",
        semibold: "600",
      },
      letterSpacing: {
        tightest: "-0.04em",
        tighter:  "-0.02em",
        tight:    "-0.01em",
        normal:   "0",
        wide:     "0.02em",
        wider:    "0.06em",
        widest:   "0.18em",
      },
      boxShadow: {
        card:        "0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)",
        "card-hover":"0 4px 16px rgba(0,0,0,0.10), 0 2px 4px rgba(0,0,0,0.06)",
        float:       "0 20px 40px rgba(0,0,0,0.18), 0 4px 12px rgba(0,0,0,0.10)",
        logo:        "0 2px 8px rgba(59,37,23,0.12)",
        sm:          "0 1px 2px rgba(0,0,0,0.06)",
        md:          "0 4px 8px rgba(0,0,0,0.08)",
      },
      keyframes: {
        "fade-in": { from:{opacity:"0"}, to:{opacity:"1"} },
        "rise": {
          from:{opacity:"0", transform:"translateY(6px)"},
          to:  {opacity:"1", transform:"translateY(0)"},
        },
        "pop": {
          from:{opacity:"0", transform:"scale(.97)"},
          to:  {opacity:"1", transform:"scale(1)"},
        },
        "slide-in-right": {
          from:{opacity:"0", transform:"translateX(100%)"},
          to:  {opacity:"1", transform:"translateX(0)"},
        },
      },
      animation: {
        "fade-in": "fade-in .25s ease-out",
        "rise":    "rise .3s cubic-bezier(.2,.7,.3,1)",
        "pop":     "pop .18s cubic-bezier(.2,.7,.3,1)",
        "slide-in-right": "slide-in-right .25s cubic-bezier(.2,.7,.3,1)",
      },
    },
  },
  plugins: [],
};
