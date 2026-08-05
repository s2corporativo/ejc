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
// Camada final e isolada do AppShell premium preto, branco e dourado.
// Mantém regras de negócio, rotas e componentes funcionais intactos.
import "./styles/premium-shell.css";

initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
