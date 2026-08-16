import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme } from "./stores/theme";
import "./styles/fonts.css";
import "./index.css";
import "./styles/bronze-elegance.css";
import "./styles/site-system.css";
// Polimento específico da página Financeiro (escopo .executive-workspace).
// Não duplica o site-system e mantém o padrão branco+ouro (aba ativa escura é exceção permitida).
import "./styles/workspace-executive.css";
// Camadas legadas preservadas para rollback visual isolado.
import "./styles/premium-shell.css";
import "./styles/premium-dashboard.css";
// Camada final do AppShell v2 e do dashboard ultra: somente apresentação,
// sem alterar regras de negócio, rotas, RBAC ou contratos de API.
import "./styles/saas-ultra-v2.css";
import "./styles/saas-ultra-accessibility.css";
// Design de referência aprovado em 16/08/2026. Importado por último para
// repintar o shell e os componentes existentes sem alterar a lógica das telas.
import "./styles/ejc-reference-2026.css";

initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
