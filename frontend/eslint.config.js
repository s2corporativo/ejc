// ESLint flat config (ESLint 10+) — migrado do antigo .eslintrc.cjs.
// Mantém o foco mínimo: padronização de tipos (item #32) com no-explicit-any
// em nível WARN para não quebrar o build.
import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  {
    // Escopo do antigo script `eslint "src/**/*.{ts,tsx}"`: só código-fonte TS/TSX.
    // Scripts de runtime (public/**) e utilitários Node (tests/**) nunca eram linkados.
    ignores: [
      "dist",
      "node_modules",
      "public",
      "tests",
      "*.cjs",
      "eslint.config.js",
      "vite.config.ts",
      "vitest.config.ts",
    ],
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsparser,
      parserOptions: { ecmaVersion: 2020, sourceType: "module" },
      // Equivalente ao antigo env: { browser: true, es2020: true }.
      globals: { ...globals.browser, ...globals.es2020 },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      "react-hooks": reactHooks,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...tseslint.configs.recommended.rules,
      // no-undef é redundante em TS (o compilador já valida) e gera falsos-positivos
      // com tipos globais do DOM/lib — recomendação oficial do typescript-eslint.
      "no-undef": "off",
      "@typescript-eslint/no-explicit-any": "warn",
      // React hooks como warn (deps referenciadas em comentários eslint-disable do código):
      "react-hooks/rules-of-hooks": "warn",
      "react-hooks/exhaustive-deps": "warn",
      // Regras ruidosas / falsos-positivos que não são o foco desta padronização mínima:
      "@typescript-eslint/no-unused-vars": "off",
      "@typescript-eslint/no-empty-function": "off",
      "@typescript-eslint/ban-ts-comment": "off",
      "no-empty": "off",
      "no-useless-escape": "off",
      "no-constant-condition": "off", // while(true) legítimo nos leitores SSE
      "no-control-regex": "off",
    },
  },
];
