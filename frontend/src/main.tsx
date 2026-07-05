import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme } from "./stores/theme";
import "./index.css";

// Aplica o tema salvo (claro/escuro/sistema) ANTES do primeiro render —
// o index.html tem CSP script-src 'self' (sem script inline), então a
// inicialização síncrona vive aqui para não haver flash de tema errado.
initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
