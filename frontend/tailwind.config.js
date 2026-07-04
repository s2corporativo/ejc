/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /*
         * SaaS moderno claro — coral sobre canvas cinza-azulado (#EDF0F4)
         * com cartões brancos flutuantes. Nomes de tokens preservados
         * (fan-in alto nas 64 páginas); apenas os VALORES foram repintados:
         * primary=coral, ai=laranja quente, success=mint, danger=soft-red,
         * warn/gold=amarelo #FFD166, bronze/navy=neutros (legado).
         */

        // Sidebar — branca no novo tema (item ativo vira cartão com sombra)
        sidebar: {
          DEFAULT: "#FFFFFF",
          light: "#F8FAFC",
          hover: "#F3F5F9",
          active: "#FFF5F4",
        },
        // Primária — coral/vermelho-suave (ação/marca)
        primary: {
          DEFAULT: "#F4574D",
          50: "#FFF5F4",
          100: "#FFE8E6",
          200: "#FFD1CD",
          300: "#FDA9A2",
          400: "#F97F74",
          500: "#F4574D",
          // 600 calibrado p/ WCAG AA: 4,7:1 sobre branco (era #E04A40 = 4,0:1)
          600: "#D23F35",
          700: "#C93B32",
          800: "#A62F28",
          900: "#872A25",
          950: "#4A120F",
        },
        // IA — laranja quente (superfícies de inteligência / acento)
        ai: {
          DEFAULT: "#ED7D3A",
          50: "#FFF6EF",
          100: "#FFEBDB",
          200: "#FED7B5",
          300: "#FCB985",
          400: "#F79256",
          500: "#F0813F",
          600: "#ED7D3A",
          700: "#C75F24",
          800: "#9E4B1E",
          900: "#7F3E1C",
          950: "#451E0B",
        },
        // navy — slate escuro (legado)
        navy: {
          DEFAULT: "#0F172A",
          950: "#020617",
          900: "#0F172A",
          800: "#1E293B",
          700: "#334155",
          600: "#475569",
          100: "#F1F5F9",
          50: "#F8FAFC",
        },
        // bronze/gold — legados repintados: bronze=neutro slate com pontas
        // coral pálidas; gold=amarelo #FFD166 (acento da referência)
        bronze: {
          DEFAULT: "#475569",
          dark: "#334155",
          deep: "#1E293B",
          medium: "#64748B",
          light: "#FDA9A2",
          pale: "#FFE8E6",
          50: "#F8FAFC",
          30: "#FBFCFE",
        },
        gold: {
          DEFAULT: "#FFD166",
          dark: "#F7BE3F",
          light: "#FFE3A3",
          700: "#B37B12",
          600: "#D99A1B",
          50: "#FFF9E6",
        },
        ink: {
          DEFAULT: "#111827",
          light: "#374151",
        },
        canvas: "#EDF0F4",
        parchment: "#F1F5F9",
        muted: "#8A94A6",
        border: "#E5E9F0",
        // Status — success=mint (#0CA678), danger/error=soft-red (#E03131),
        // warn/warning=amarelo quente (#FFD166), info=sky (inalterado)
        success: {
          DEFAULT: "#0CA678",
          50: "#E6F7F1",
          100: "#D3F3E8",
          200: "#A8E8D3",
          300: "#74D9B8",
          400: "#3EC49A",
          500: "#12B886",
          600: "#0CA678",
          700: "#099268",
          800: "#087F5B",
          900: "#066649",
          950: "#033A2A",
        },
        warn: {
          DEFAULT: "#EFAE2E",
          50: "#FFF9E6",
          100: "#FFF3CC",
          200: "#FFE799",
          300: "#FFD166",
          400: "#F7C04A",
          500: "#EFAE2E",
          600: "#D99A1B",
          700: "#B37B12",
          800: "#8C5F0E",
          900: "#664409",
          950: "#3D2905",
        },
        warning: {
          DEFAULT: "#EFAE2E",
          50: "#FFF9E6",
          100: "#FFF3CC",
          200: "#FFE799",
          300: "#FFD166",
          400: "#F7C04A",
          500: "#EFAE2E",
          600: "#D99A1B",
          700: "#B37B12",
          800: "#8C5F0E",
          900: "#664409",
          950: "#3D2905",
        },
        danger: {
          DEFAULT: "#E03131",
          50: "#FDEBEC",
          100: "#FCDCDE",
          200: "#F8B9BC",
          300: "#F1898E",
          400: "#EA5A60",
          500: "#E03131",
          600: "#C92A2A",
          700: "#A61E1E",
          800: "#871B1B",
          900: "#6E1818",
          950: "#3D0A0A",
        },
        error: {
          DEFAULT: "#E03131",
          50: "#FDEBEC",
          100: "#FCDCDE",
          200: "#F8B9BC",
          300: "#F1898E",
          400: "#EA5A60",
          500: "#E03131",
          600: "#C92A2A",
          700: "#A61E1E",
          800: "#871B1B",
          900: "#6E1818",
          950: "#3D0A0A",
        },
        info: {
          DEFAULT: "#0ea5e9",
          50: "#f0f9ff",
          100: "#e0f2fe",
          200: "#bae6fd",
          300: "#7dd3fc",
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
          700: "#0369a1",
          800: "#075985",
          900: "#0c4a6e",
          950: "#082f49",
        },
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "-apple-system", "sans-serif"],
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
        caption: ["0.7rem", { lineHeight: "1rem" }], // metadados, legendas
        "2xs": ["0.65rem", { lineHeight: "1rem" }],
        xs: ["0.75rem", { lineHeight: "1.125rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.6rem" }],
        lg: ["1.0625rem", { lineHeight: "1.65rem" }],
        xl: ["1.1875rem", { lineHeight: "1.75rem" }],
        "2xl": ["1.375rem", { lineHeight: "1.9rem" }],
        "3xl": ["1.75rem", { lineHeight: "2.1rem" }],
        "4xl": ["2.25rem", { lineHeight: "2.5rem" }],
      },
      fontWeight: {
        light: "300",
        normal: "400",
        medium: "500",
        semibold: "600",
      },
      letterSpacing: {
        tightest: "-0.04em",
        tighter: "-0.02em",
        tight: "-0.01em",
        normal: "0",
        wide: "0.02em",
        wider: "0.06em",
        widest: "0.18em",
      },
      borderRadius: {
        // Cartões flutuantes da referência (~20-24px)
        "2xl": "1.25rem",
        "3xl": "1.5rem",
      },
      boxShadow: {
        // Sombras suaves e difusas dos cartões brancos flutuantes
        soft: "0 8px 30px rgba(16,24,40,0.06)",
        card: "0 1px 2px rgba(16,24,40,0.03), 0 8px 30px rgba(16,24,40,0.06)",
        "card-hover":
          "0 2px 4px rgba(16,24,40,0.04), 0 12px 36px rgba(16,24,40,0.10)",
        float:
          "0 4px 12px rgba(16,24,40,0.08), 0 24px 48px rgba(16,24,40,0.14)",
        logo: "0 2px 8px rgba(16,24,40,0.10)",
        sm: "0 1px 2px rgba(16,24,40,0.05)",
        md: "0 2px 4px rgba(16,24,40,0.04), 0 8px 30px rgba(16,24,40,0.07)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        rise: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pop: {
          from: { opacity: "0", transform: "scale(.97)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        "slide-in-right": {
          from: { opacity: "0", transform: "translateX(100%)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in .25s ease-out",
        rise: "rise .3s cubic-bezier(.2,.7,.3,1)",
        pop: "pop .18s cubic-bezier(.2,.7,.3,1)",
        "slide-in-right": "slide-in-right .25s cubic-bezier(.2,.7,.3,1)",
      },
    },
  },
  plugins: [],
};
