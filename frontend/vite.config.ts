import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FE-10: vendors estáveis em chunks próprios — o hash de `react`/`router`/
// `icons` só muda quando a dependência muda, então o cache do navegador (e do
// service worker, restrito a /assets/) sobrevive aos deploys da aplicação.
// Vite 8 é Rolldown: `manualChunks` (objeto) não é suportado; o equivalente é
// `output.codeSplitting.groups` (nomes reais das deps em package.json —
// o roteador é `react-router` v7+, não `react-router-dom`).
const VENDOR_CHUNKS: { name: string; test: RegExp }[] = [
  { name: "react", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
  { name: "router", test: /node_modules[\\/]react-router[\\/]/ },
  { name: "icons", test: /node_modules[\\/]lucide-react[\\/]/ },
];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true, ws: true } },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: VENDOR_CHUNKS.map((g, i) => ({
            name: g.name,
            test: g.test,
            priority: 100 - i,
          })),
        },
      },
    },
  },
});
