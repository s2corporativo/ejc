/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /*
         * SaaS tech moderno — indigo/violet sobre superfícies claras.
         * Nomes de tokens preservados (fan-in alto nas 64 páginas); apenas
         * os VALORES foram repintados: primary=indigo, ai=violet,
         * bronze/gold/navy=neutros slate/indigo (legado).
         */

        // Sidebar — dark refinado com tint indigo sutil
        sidebar: {
          DEFAULT: "#0B0F1A",
          light:   "#151B2C",
          hover:   "#141B30",
          active:  "#1A2240",
        },
        // Primária — indigo moderno (ação/marca)
        primary: {
          DEFAULT: "#4F46E5",
          50:  "#EEF2FF", 100: "#E0E7FF", 200: "#C7D2FE", 300: "#A5B4FC",
          400: "#818CF8", 500: "#6366F1", 600: "#4F46E5", 700: "#4338CA",
          800: "#3730A3", 900: "#312E81", 950: "#1E1B4B",
        },
        // IA — violet tech (superfícies de inteligência)
        ai: {
          DEFAULT: "#7C3AED",
          50:  "#F5F3FF", 100: "#EDE9FE", 200: "#DDD6FE", 300: "#C4B5FD",
          400: "#A78BFA", 500: "#8B5CF6", 600: "#7C3AED", 700: "#6D28D9",
          800: "#5B21B6", 900: "#4C1D95", 950: "#2E1065",
        },
        // navy — slate escuro (legado)
        navy: {
          DEFAULT: "#0F172A",
          950: "#020617", 900: "#0F172A", 800: "#1E293B",
          700: "#334155", 600: "#475569", 100: "#F1F5F9", 50: "#F8FAFC",
        },
        // bronze/gold — legados repintados para neutros slate/indigo suaves
        bronze: {
          DEFAULT: "#475569",
          dark:    "#334155",
          deep:    "#1E293B",
          medium:  "#64748B",
          light:   "#A5B4FC",
          pale:    "#E0E7FF",
          50:      "#F8FAFC",
          30:      "#FBFCFE",
        },
        gold: {
          DEFAULT: "#A5B4FC",
          dark:    "#818CF8",
          light:   "#C7D2FE",
          700:     "#4338CA",
          600:     "#4F46E5",
          50:      "#EEF2FF",
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
        sans:  ['"Inter"', "system-ui", "-apple-system", "sans-serif"],
        serif: ["Georgia", "Cambria", '"Times New Roman"', "serif"],
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
        card:        "0 1px 2px rgba(15,23,42,0.04), 0 1px 3px rgba(15,23,42,0.06)",
        "card-hover":"0 2px 4px rgba(15,23,42,0.04), 0 8px 24px rgba(15,23,42,0.08)",
        float:       "0 4px 12px rgba(15,23,42,0.08), 0 24px 48px rgba(15,23,42,0.14)",
        logo:        "0 2px 8px rgba(30,27,75,0.12)",
        sm:          "0 1px 2px rgba(15,23,42,0.05)",
        md:          "0 2px 4px rgba(15,23,42,0.04), 0 4px 10px rgba(15,23,42,0.07)",
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
