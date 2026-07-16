import { NavLink, Outlet } from "react-router-dom";
import {
  Briefcase,
  FileText,
  Home,
  LogOut,
  MessageCircle,
  PenLine,
  Wallet,
} from "lucide-react";
import { logout } from "../lib/api";
import { useAuth } from "../stores/auth";
import "../styles/option-one.css";

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
  const user = useAuth((state) => state.user);

  return (
    <div className="ejc-option-one-shell min-h-screen bg-canvas">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 shadow-sm backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex min-w-0 items-center gap-4">
            <img
              src={BRAND_LOGO}
              alt="EJC — Escritório Jurídico Clovis"
              className="h-12 w-auto max-w-[220px] object-contain sm:h-14 sm:max-w-[280px]"
            />
            <div className="hidden border-l border-slate-200 pl-4 sm:block">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-700">
                Portal do Cliente
              </div>
              <div className="mt-0.5 max-w-56 truncate text-xs text-slate-500">
                Acompanhamento seguro e transparente
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <div className="max-w-48 truncate text-sm font-semibold text-slate-900">
                {user?.full_name || "Cliente"}
              </div>
              <div className="text-[11px] text-slate-500">Acesso protegido</div>
            </div>
            <button
              type="button"
              onClick={logout}
              className="ejc-option-one-icon-button"
              aria-label="Sair do portal"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>

        <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `relative flex shrink-0 items-center gap-2 rounded-t-xl px-4 py-3 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-amber-50 text-primary-950 after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:bg-amber-600"
                    : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="ejc-option-one-main mx-auto min-h-[calc(100vh-166px)] max-w-6xl px-4 py-6 md:py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white py-5 text-center text-[11px] text-slate-400">
        EJC · Escritório Jurídico Clovis · Betim/MG
      </footer>
    </div>
  );
}
