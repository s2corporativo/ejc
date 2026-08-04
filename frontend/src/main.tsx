import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme } from "./stores/theme";
import "./styles/fonts.css";
import "./index.css";
import "./styles/site-system.css";
// Polimento específico da página Financeiro (escopo .executive-workspace).
// Não duplica o site-system e mantém o padrão branco+ouro (aba ativa escura é exceção permitida).
import "./styles/workspace-executive.css";
// Shell e dashboard v2: classes próprias, carregadas por último para manter a
// identidade visual isolada sem repintar indiscriminadamente os módulos.
import "./styles/ejc-shell-v2.css";
import "./styles/ejc-shell-v2-refinements.css";

initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
