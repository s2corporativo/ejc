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
// Design de referência aprovado em 16/08/2026. Mantém os componentes
// específicos do dashboard e do AppShell já homologados.
import "./styles/ejc-reference-2026.css";
// Camada final system-wide: estende o mesmo idioma visual às páginas internas,
// portal e login sem alterar lógica, rotas, contratos de API ou permissões.
import "./styles/ejc-reference-systemwide.css";

initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);