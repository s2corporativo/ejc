/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /*
         * Design System "De Paula Teixeira" — luxo jurídico DOURADO.
         * O papel do marrom/bronze foi transferido para a família OURO
         * (mesma família dos PDFs Visual Law — token `ouro` abaixo).
         * Tokens oficiais (fonte única — documentados aqui):
         *   Ouro Near-Black #3B2F0B — texto de destaque e início dos
         *     gradientes escuros (13,2:1 sobre branco, AAA).
         *   Ouro #8F7117 — ação/texto-acento (4,6:1 sobre branco = AA;
         *     texto branco sobre ele = 4,6:1 AA).
         *   Ouro Profundo #6F5711 — texto-acento forte (6,9:1 AA/AAA).
         *   Ouro Claro #C9A227 / Dourado #D4AF37 — destaques GRÁFICOS
         *     (filetes, ícones de KPI, fim de gradiente metálico). Não é
         *     texto sobre branco (2,1–2,4:1); no modo ESCURO o acento de
         *     texto é #E5CE7F (11,4:1 sobre #1C180E).
         *   Canvas Off-White quente + cards branco puro; raio 12–16px
         *     (rounded-xl/2xl); sombras muito suaves.
         * Nomes de tokens preservados (fan-in alto nas 64 páginas);
         * apenas os VALORES foram repintados (marrom → ouro).
         */

        // Sidebar — gradiente ouro-escuro (ver .sidebar-bronze no CSS)
        sidebar: {
          DEFAULT: "#3B2F0B",
          light: "#55420D",
          hover: "rgba(201,162,39,0.16)",
          active: "rgba(201,162,39,0.20)",
        },
        // Primária — escala OURO (ação/marca)
        primary: {
          DEFAULT: "#A6842A",
          50: "#FBF8EC",
          100: "#F7F1DC",
          200: "#EFE3B4",
          300: "#E5CE7F",
          400: "#D4AF37",
          // 500 calibrado: 3,5:1 sobre branco — só UI/ícone, nunca
          // texto pequeno sobre branco (para texto use 600+)
          500: "#A6842A",
          // 600 calibrado p/ WCAG AA: 4,6:1 sobre branco (texto-acento
          // ouro; #C9A227 puro = 2,4:1 falharia em texto pequeno)
          600: "#8F7117",
          700: "#6F5711",
          800: "#55420D",
          900: "#3B2F0B",
          950: "#251D06",
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
        // navy — token legado de "escuro/ação". Repintado para a família
        // OURO near-black (site branco + acento dourado): fills `bg-navy`
        // com texto branco = #3B2F0B (12:1 AAA); texto `text-navy-600..900`
        // sobre branco = ouro 4,6:1→13:1 (AA/AAA); `-50/-100` = palha quente.
        // Espelha a escala `primary`/`ouro` para acento gráfico consistente.
        navy: {
          DEFAULT: "#3B2F0B",
          950: "#251D06",
          900: "#3B2F0B",
          800: "#55420D",
          700: "#6F5711",
          600: "#8F7117",
          100: "#F7F1DC",
          50: "#FBF8EC",
        },
        // bronze/gold — legados repintados: bronze=neutro slate com pontas
        // douradas pálidas; gold=amarelo #FFD166 (acento da referência)
        bronze: {
          DEFAULT: "#475569",
          dark: "#334155",
          deep: "#1E293B",
          medium: "#64748B",
          light: "#E5CE7F",
          pale: "#F8F0D8",
          50: "#F8FAFC",
          30: "#FBFCFE",
        },
        gold: {
          DEFAULT: "#D4AF37",
          dark: "#B8952B",
          light: "#E5CE7F",
          700: "#8C6D1F",
          600: "#A6842A",
          50: "#FAF5E3",
        },
        /*
         * Ouro institucional "De Paula Teixeira" — paleta oficial dos PDFs
         * Visual Law (backend/app/services/visual_law_theme.py). Uso com
         * PARCIMÔNIA: cor de AÇÃO/DESTAQUE (botão primário, tab ativa,
         * badge de destaque, filetes de título) — nunca fundo dominante.
         * Contraste sobre branco: profundo #6F5711 = 6,9:1 (AA texto);
         * DEFAULT #8F7117 = 4,6:1 (AA com texto branco em botões);
         * claro #C9A227 = só filete/realce gráfico, nunca texto;
         * palha #F7F1DC = fundo suave (badges, quadros).
         */
        ouro: {
          profundo: "#6F5711",
          DEFAULT: "#8F7117",
          claro: "#C9A227",
          palha: "#F7F1DC",
        },
        ink: {
          DEFAULT: "#111827",
          light: "#374151",
        },
        // Canvas branco/off-white QUENTE (pedido do dono: base branca,
        // nada de cinza pesado) + hairline quente quase invisível.
        canvas: "#FAF9F6",
        parchment: "#F5F3EE",
        muted: "#8A94A6",
        border: "#ECE8E0",
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
        sans: [
          '"Inter"',
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          '"Segoe UI"',
          "Roboto",
          "sans-serif",
        ],
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
        // Raio oficial do DS: 12–16px (xl=12px padrão, 2xl=16px)
        "2xl": "1rem",
        "3xl": "1.25rem",
      },
      boxShadow: {
        // Soft elevation — sombras muito suaves e contidas
        soft: "0 4px 18px rgba(24,16,8,0.05)",
        card: "0 1px 2px rgba(24,16,8,0.03), 0 4px 18px rgba(24,16,8,0.05)",
        "card-hover":
          "0 2px 4px rgba(24,16,8,0.04), 0 8px 26px rgba(24,16,8,0.08)",
        float: "0 4px 12px rgba(24,16,8,0.07), 0 18px 40px rgba(24,16,8,0.12)",
        logo: "0 2px 8px rgba(24,16,8,0.10)",
        // Sombra do botão primário ouro (profundidade sem borda)
        gold: "0 6px 16px rgba(111,87,17,0.22)",
        "gold-hover": "0 8px 22px rgba(111,87,17,0.3)",
        sm: "0 1px 2px rgba(24,16,8,0.05)",
        md: "0 2px 4px rgba(24,16,8,0.04), 0 6px 22px rgba(24,16,8,0.06)",
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
