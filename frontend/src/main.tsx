import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme } from "./stores/theme";
import "./index.css";

// Aplica o tema salvo (claro/escuro/sistema) ANTES do primeiro render.
// A CSP (script-src 'self', sem inline) é aplicada pelo Nginx do container
// (frontend/nginx.conf) e pelo Nginx do HOST — não pelo index.html. Por isso
// a inicialização síncrona vive aqui (módulo 'self'), evitando flash de tema.
initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
