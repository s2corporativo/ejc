/* ESLint mínimo — foco em padronização de tipos (item #32).
 * no-explicit-any em nível WARN (não error) para não quebrar o build. */
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: 2020, sourceType: "module" },
  plugins: ["@typescript-eslint", "react-hooks"],
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended"],
  ignorePatterns: ["dist", "node_modules", "*.cjs", "vite.config.ts", "vitest.config.ts"],
  rules: {
    "@typescript-eslint/no-explicit-any": "warn",
    // React hooks como warn (deps referenciadas em comentários eslint-disable do código):
    "react-hooks/rules-of-hooks": "warn",
    "react-hooks/exhaustive-deps": "warn",
    // Regras ruidosas / falsos-positivos que não são o foco desta padronização mínima:
    "@typescript-eslint/no-unused-vars": [
      "error",
      {
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
        caughtErrorsIgnorePattern: "^_",
        ignoreRestSiblings: true,
      },
    ],
    "@typescript-eslint/no-empty-function": "off",
    "@typescript-eslint/ban-ts-comment": "off",
    "no-empty": "off",
    "no-useless-escape": "off",
    "no-constant-condition": "off", // while(true) legítimo nos leitores SSE
    "no-control-regex": "off",
  },
};
