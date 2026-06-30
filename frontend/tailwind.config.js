/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /*
         * Identidade De Paula Teixeira — bronze/ouro/espresso sobre marfim.
         * `blue`/`violet`/`purple` são REMAPEADOS para que os ~151 usos literais
         * legados (bg-blue-600, text-violet-700…) exibam a marca automaticamente,
         * sem precisar editar 40 telas. `slate` segue como cinza neutro.
         */
        // Re-skin de literais legados
        blue: {
          50: "#FAF5EF", 100: "#F0E4D2", 200: "#E2CBA8", 300: "#CBA877",
          400: "#B98A3C", 500: "#A6792F", 600: "#8C6A33", 700: "#6E5228",
          800: "#5A431F", 900: "#473414", 950: "#2A1F0C",
        },
        violet: {
          50: "#ECF4F3", 100: "#D2E7E4", 200: "#A8D0CB", 300: "#73B0A9",
          400: "#459089", 500: "#2F7A72", 600: "#266761", 700: "#1F534E",
          800: "#1B433F", 900: "#173734", 950: "#0B201E",
        },
        purple: {
          50: "#ECF4F3", 100: "#D2E7E4", 200: "#A8D0CB", 300: "#73B0A9",
          400: "#459089", 500: "#2F7A72", 600: "#266761", 700: "#1F534E",
          800: "#1B433F", 900: "#173734", 950: "#0B201E",
        },

        // Sidebar — espresso (era azul-marinho)
        sidebar: {
          DEFAULT: "#2A2017",
          light:   "#3A2E22",
          hover:   "#33271C",
          active:  "#211910",
        },
        // Primária — bronze (era azul)
        primary: {
          DEFAULT: "#8C6A33",
          50:  "#FAF5EF",
          100: "#F0E4D2",
          500: "#A6792F",
          600: "#8C6A33",
          700: "#6E5228",
          800: "#5A431F",
        },
        // navy — repintado para espresso (era azul)
        navy: {
          DEFAULT: "#2A2017",
          950: "#15100A", 900: "#1F1710", 800: "#2D241A",
          700: "#3A2E22", 600: "#4A3A2A", 100: "#ECE5DA", 50: "#F5F1EA",
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
          DEFAULT: "#2A2017",
          light:   "#5A4733",
        },
        canvas: "#F7F3EE",
        parchment: "#F0E8DD",
      },
      fontFamily: {
        sans:  ['"DM Sans"', "system-ui", "sans-serif"],
        serif: ['"Cormorant Garamond"', "Georgia", "Cambria", "serif"],
      },
      fontSize: {
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
      },
      animation: {
        "fade-in": "fade-in .25s ease-out",
        "rise":    "rise .3s cubic-bezier(.2,.7,.3,1)",
        "pop":     "pop .18s cubic-bezier(.2,.7,.3,1)",
      },
    },
  },
  plugins: [],
};
