import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Config de testes separada do build (vite.config.ts) — ambiente jsdom para
// testar componentes React com @testing-library.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    // Folga de tempo para o runner self-hosted (ver src/test-setup.ts). Precisa
    // ser MAIOR que o asyncUtilTimeout de lá, senão o vitest derruba o teste
    // antes de o `waitFor` esgotar o próprio orçamento e reportar o motivo real.
    setupFiles: ["./src/test-setup.ts"],
    testTimeout: 20000,
  },
});
