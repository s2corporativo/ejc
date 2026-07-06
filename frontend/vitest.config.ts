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
  },
});
