import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme } from "./stores/theme";
import "./index.css";
import "./styles/site-system.css";
import "./styles/clientes-casos-saas.css";
import "./styles/workspace-executive.css";
import "./styles/portal-premium.css";
import "./styles/ged-premium.css";
import "./styles/operacional-premium.css";

initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
