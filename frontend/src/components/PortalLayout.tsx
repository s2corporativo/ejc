// ── Portal do Cliente: layout simplificado e acolhedor ──
import { NavLink, Outlet } from "react-router-dom";
import {
  Home,
  Briefcase,
  Wallet,
  PenLine,
  MessageCircle,
  LogOut,
} from "lucide-react";
import { logout } from "../lib/api";
import { useAuth } from "../stores/auth";

const BRAND_LOGO = "/brand/de-paula-teixeira-logo.jpg";

const NAV = [
  { to: "/portal", label: "Início", icon: Home, end: true },
  { to: "/portal/casos", label: "Processos", icon: Briefcase },
  { to: "/portal/financeiro", label: "Financeiro", icon: Wallet },
  { to: "/portal/assinaturas", label: "Assinaturas", icon: PenLine },
  { to: "/portal/mensagens", label: "Mensagens", icon: MessageCircle },
];

export default function PortalLayout() {
  const { user } = useAuth();
  return (
    <div className="ejc-modern-scope min-h-screen bg-[#F7F8FA]">
      <header className="border-b border-amber-300/20 bg-[#2f2119] text-white shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-white px-2 py-1 ring-1 ring-white/20">
              <img
                src={BRAND_LOGO}
                alt="De Paula Teixeira Sociedade de Advogados"
                className="brand-logo-img h-10 w-auto max-w-[170px]"
              />
            </div>
            <div className="hidden text-[10px] uppercase tracking-[0.25em] text-amber-100 sm:block">
              Portal do Cliente
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm hidden sm:block">{user?.full_name}</span>
            <button
              onClick={logout}
              className="p-2 rounded-lg text-blue-100 hover:bg-white/10 hover:text-white"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
        <nav className="max-w-4xl mx-auto px-4 flex gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2 px-4 py-2.5 text-sm rounded-t-lg ${
                  isActive
                    ? "bg-[#F7F8FA] text-[#4b3527] font-medium"
                    : "text-slate-300 hover:text-white"
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
