import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme } from "./stores/theme";

// Ordem das camadas visuais (única fonte de verdade do idioma visual):
//   1. fonts        — faces tipográficas
//   2. index        — tokens da marca, base Tailwind e componentes utilitários
//   3. app-shell    — barra superior, navegação lateral e área de trabalho
//   4. site-system  — acabamento global de cards, inputs, tabelas e badges
//   5. ejc-reference-2026 / -systemwide — idioma de referência das páginas
//   6. workspace-executive — polimento pontual do workspace Financeiro
// Camadas inalcançáveis foram removidas; `npm run audit:css` impede regressão.
import "./styles/fonts.css";
import "./index.css";
import "./styles/app-shell.css";
import "./styles/site-system.css";
import "./styles/ejc-reference-2026.css";
import "./styles/ejc-reference-systemwide.css";
import "./styles/workspace-executive.css";

initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
