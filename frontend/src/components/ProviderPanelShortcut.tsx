import { Link, useLocation } from "react-router";
import { Activity } from "lucide-react";

export default function ProviderPanelShortcut() {
  const location = useLocation();
  if (location.pathname !== "/ia-governanca") return null;

  return (
    <Link
      to="/ia-governanca/provedores"
      className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-xl bg-navy px-4 py-3 text-sm font-medium text-white shadow-xl transition hover:-translate-y-0.5 hover:shadow-2xl focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2"
      title="Abrir métricas de Anthropic, Maritaca e Groq"
    >
      <Activity className="h-4 w-4" />
      Painel dos provedores
    </Link>
  );
}
