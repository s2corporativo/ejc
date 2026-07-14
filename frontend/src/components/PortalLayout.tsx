// ── Portal do Cliente: layout simplificado e acolhedor ──
import { NavLink, Outlet } from "react-router-dom";
import {
  Home,
  Briefcase,
  Wallet,
  PenLine,
  MessageCircle,
  FileText,
  LogOut,
} from "lucide-react";
import { logout } from "../lib/api";
import { useAuth } from "../stores/auth";

// Logomarca HD com fundo transparente (nunca a versão JPG com fundo)
const BRAND_LOGO = "/brand/logo-hd.png";

const NAV = [
  { to: "/portal", label: "Início", icon: Home, end: true },
  { to: "/portal/casos", label: "Casos", icon: Briefcase },
  { to: "/portal/financeiro", label: "Financeiro", icon: Wallet },
  { to: "/portal/assinaturas", label: "Assinaturas", icon: PenLine },
  { to: "/portal/mensagens", label: "Mensagens", icon: MessageCircle },
  { to: "/portal/documentos", label: "Documentos", icon: FileText },
];

export default function PortalLayout() {
  const { user } = useAuth();
  return (
    <div className="ejc-modern-scope min-h-screen bg-canvas">
      {/* Header claro premium: superfície branca, hairline dourada sutil,
          logo transparente maior e abas com filete dourado fino. */}
      <header className="border-b border-black/[0.05] bg-white/95 shadow-sm backdrop-blur-xl">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img
              src={BRAND_LOGO}
              alt="De Paula Teixeira Sociedade de Advogados"
              className="brand-logo-img h-12 w-auto max-w-[220px] sm:h-14 sm:max-w-[260px]"
            />
            <div className="hidden text-[10px] font-semibold uppercase tracking-[0.25em] text-ouro-profundo sm:block">
              Portal do Cliente
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-slate-600 hidden sm:block">
              {user?.full_name}
            </span>
            <button
              onClick={logout}
              className="icon-btn h-9 w-9"
              aria-label="Sair"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
        <nav className="max-w-4xl mx-auto px-4 flex gap-1 overflow-x-auto">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `relative flex shrink-0 items-center gap-2 px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? "font-semibold text-ouro-profundo after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:bg-ouro-claro"
                    : "text-slate-500 hover:text-slate-900"
                }`
              }
            >
              <Icon size={15} /> {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="max-w-4xl mx-auto px-4 py-6">
        <Outlet />
      </main>
      <footer className="text-center text-[11px] text-slate-400 pb-6">
        De Paula Teixeira Sociedade de Advogados · Betim/MG
      </footer>
    </div>
  );
}
