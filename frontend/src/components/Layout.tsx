import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Activity,
  AlarmClock,
  BarChart3,
  Bell,
  Brain,
  BrainCircuit,
  BookOpen,
  Bot,
  Briefcase,
  Building2,
  CalendarClock,
  CheckSquare,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Coins,
  FileSignature,
  FileText,
  FolderOpen,
  Gavel,
  GitBranch,
  Inbox,
  LayoutDashboard,
  LayoutGrid,
  Library,
  ListChecks,
  LogOut,
  Menu,
  Moon,
  Newspaper,
  Plus,
  Receipt,
  Scale,
  ScrollText,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  Swords,
  Trash2,
  Users,
  Wallet,
  X,
} from "lucide-react";
import { toast } from "./Toast";
import CommandPalette from "./CommandPalette";
import OnboardingTour from "./OnboardingTour";
import SecurityMenu from "./SecurityMenu";
import { Button, Tooltip, cn } from "./UI";
import { useTheme } from "../hooks/useTheme";
import { useAuth } from "../stores/auth";
import api, { logout } from "../lib/api";

const BRAND_LOGO = "/brand/de-paula-teixeira-logo.jpg";

type NavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  group: string;
  roles?: string[];
  end?: boolean;
  onClick?: () => void;
};

const NAV: NavItem[] = [
  // ── Operação ──
  {
    to: "/",
    label: "Dashboard",
    icon: LayoutDashboard,
    group: "Operacao",
    end: true,
  },
  {
    to: "/central-relacionamento",
    label: "Atendimento",
    icon: CalendarClock,
    group: "Operacao",
    roles: ["superadmin", "admin", "socio"],
  },
  { to: "/crm-leads", label: "CRM", icon: Users, group: "Operacao" },
  { to: "/clientes", label: "Clientes", icon: Briefcase, group: "Operacao" },

  // ── Jurídico ──
  { to: "/casos", label: "Casos", icon: Gavel, group: "Juridico" },
  { to: "/datajud", label: "Processos", icon: Scale, group: "Juridico" },
  { to: "/prazos", label: "Prazos", icon: AlarmClock, group: "Juridico" },
  { to: "/intimacoes", label: "Intimacoes", icon: Inbox, group: "Juridico" },
  {
    to: "/atividades",
    label: "Agenda",
    icon: CalendarClock,
    group: "Juridico",
  },
  { to: "/tarefas", label: "Tarefas", icon: CheckSquare, group: "Juridico" },
  {
    to: "/casos?filtro=ativos",
    label: "Sala de Guerra",
    icon: Swords,
    group: "Juridico",
    onClick: () =>
      toast.info("Selecione um caso para acessar a Sala de Guerra"),
  },
  { to: "/ramos", label: "Ramos do Direito", icon: Scale, group: "Juridico" },

  // ── Produção ──
  {
    to: "/documentos",
    label: "Documentos",
    icon: FolderOpen,
    group: "Producao",
  },
  { to: "/pecas", label: "Pecas", icon: FileText, group: "Producao" },
  {
    to: "/checklists",
    label: "Checklists",
    icon: ListChecks,
    group: "Producao",
  },
  { to: "/workflow", label: "Workflows", icon: GitBranch, group: "Producao" },
  {
    to: "/assinaturas",
    label: "Assinaturas",
    icon: FileSignature,
    group: "Producao",
  },

  // ── Gestão / Financeiro ──
  {
    to: "/financeiro",
    label: "Financeiro",
    icon: Wallet,
    group: "Financeiro",
    roles: ["superadmin", "admin", "socio", "financeiro"],
  },
  {
    to: "/honorarios",
    label: "Honorarios",
    icon: Coins,
    group: "Financeiro",
    roles: ["superadmin", "admin", "socio", "advogado", "financeiro"],
  },
  { to: "/despesas", label: "Despesas", icon: Receipt, group: "Gestao" },
  { to: "/sociedade", label: "Sociedade", icon: Building2, group: "Financeiro" },

  // ── Inteligência ──
  {
    to: "/inteligencia",
    label: "IA Juridica",
    icon: Sparkles,
    group: "Inteligencia",
    roles: [
      "superadmin",
      "admin",
      "socio",
      "advogado",
      "advogado_auxiliar",
      "estagiario",
    ],
  },
  {
    to: "/ferramentas-ia",
    label: "Ferramentas IA",
    icon: Bot,
    group: "Inteligencia",
    roles: [
      "superadmin",
      "admin",
      "socio",
      "advogado",
      "advogado_auxiliar",
      "estagiario",
    ],
  },
  {
    to: "/licitacao-auditoria",
    label: "Auditoria de licitacao",
    icon: Gavel,
    group: "Juridico",
  },
  {
    to: "/radar-regulatorio",
    label: "Radar regulatorio",
    icon: Bell,
    group: "Inteligencia",
  },
  {
    to: "/victory-vault",
    label: "Victory Vault",
    icon: Gavel,
    group: "Inteligencia",
    roles: [
      "superadmin",
      "admin",
      "socio",
      "advogado",
      "advogado_auxiliar",
      "estagiario",
    ],
  },
  {
    to: "/conhecimento",
    label: "Conhecimento",
    icon: BookOpen,
    group: "Inteligencia",
    roles: ["superadmin", "admin", "socio"],
  },
  {
    to: "/jurimetria",
    label: "Jurimetria",
    icon: BarChart3,
    group: "Inteligencia",
  },
  {
    to: "/ia-governanca",
    label: "Governanca IA",
    icon: BrainCircuit,
    group: "Inteligencia",
    roles: ["superadmin", "admin", "socio"],
  },
  { to: "/kanban", label: "Kanban", icon: LayoutGrid, group: "Inteligencia" },

  // ── Biblioteca / Conhecimento ──
  { to: "/wiki", label: "Wiki", icon: BookOpen, group: "Biblioteca" },
  { to: "/biblioteca", label: "Biblioteca", icon: Library, group: "Biblioteca" },
  { to: "/memoria", label: "Memoria", icon: Brain, group: "Biblioteca" },
  { to: "/noticias", label: "Noticias", icon: Newspaper, group: "Biblioteca" },
  {
    to: "/diario-oficial",
    label: "Diario Oficial",
    icon: ScrollText,
    group: "Biblioteca",
  },

  // ── Administração ──
  {
    to: "/auditoria",
    label: "Auditoria",
    icon: ShieldCheck,
    group: "Administracao",
    roles: ["superadmin", "admin", "socio"],
  },
  {
    to: "/produtividade",
    label: "Produtividade",
    icon: Activity,
    group: "Administracao",
  },
  {
    to: "/lixeira",
    label: "Lixeira",
    icon: Trash2,
    group: "Administracao",
    roles: ["superadmin", "admin", "socio"],
  },
  {
    to: "/usuarios",
    label: "Configuracoes",
    icon: Settings,
    group: "Administracao",
    roles: ["superadmin", "admin"],
  },
];

function initials(name?: string): string {
  return (name || "?")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export default function Layout() {
  const { theme, toggle } = useTheme();
  const { user } = useAuth();
  const nav = useNavigate();
  const [notifCount, setNotifCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifs, setNotifs] = useState<any[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  // Grupos do menu colapsáveis (abertos por padrão; estado persiste no navegador)
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("ejc_menu_groups") || "{}");
    } catch {
      return {};
    }
  });
  const toggleGroup = (g: string) =>
    setOpenGroups((prev) => {
      const next = { ...prev, [g]: prev[g] === false };
      try {
        localStorage.setItem("ejc_menu_groups", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });

  useEffect(() => {
    const load = () =>
      api
        .get("/notifications/?apenas_nao_lidas=false&limit=15")
        .then((r) => {
          setNotifs(r.data.data ?? []);
          setNotifCount(r.data.nao_lidas ?? 0);
        })
        .catch(() => {});
    load();
    const timer = setInterval(load, 60_000);
    return () => clearInterval(timer);
  }, []);

  const visible = useMemo(
    () =>
      NAV.filter(
        (item) => !item.roles || (user && item.roles.includes(user.role)),
      ),
    [user],
  );

  const groups = useMemo(() => {
    const map = new Map<string, NavItem[]>();
    for (const item of visible)
      map.set(item.group, [...(map.get(item.group) || []), item]);
    return Array.from(map.entries());
  }, [visible]);

  const sidebarWidth = collapsed ? "md:w-[5.25rem]" : "md:w-72";
  const contentMargin = collapsed ? "md:ml-[5.25rem]" : "md:ml-72";

  return (
    <div className="min-h-screen bg-[#F7F8FA] text-slate-900">
      <CommandPalette />

      {menuOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-slate-950/45 backdrop-blur-sm md:hidden"
          aria-label="Fechar menu"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex-col border-r border-slate-200 bg-white/95 backdrop-blur-xl transition-all",
          sidebarWidth,
          menuOpen ? "flex w-72 md:flex" : "hidden md:flex",
        )}
      >
        <div className="flex h-16 items-center gap-3 border-b border-slate-100 px-4">
          <Link
            to="/"
            className={cn(
              "flex min-w-0 items-center",
              collapsed ? "w-10 justify-center" : "max-w-[190px]",
            )}
            aria-label="De Paula Teixeira - EJC"
          >
            <img
              src={BRAND_LOGO}
              alt="De Paula Teixeira Sociedade de Advogados"
              className={cn(
                "brand-logo-img",
                collapsed ? "h-10 w-10 rounded-lg object-cover object-top" : "h-12 w-auto max-w-[190px]",
              )}
            />
          </Link>
          <button
            type="button"
            className="ml-auto hidden rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 md:block"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </button>
          <button
            type="button"
            className="ml-auto rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 md:hidden"
            onClick={() => setMenuOpen(false)}
            aria-label="Fechar menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {!collapsed && (
          <div className="brand-panel mx-3 mt-3 rounded-xl border p-3">
            <div className="brand-kicker text-xs font-semibold">
              Sociedade de Advogados
            </div>
            <div className="mt-1 text-[11px] text-slate-600">
              Operacao juridica empresarial
            </div>
            <div className="brand-accent-line mt-3 h-0.5 rounded-full" />
          </div>
        )}

        <nav className="flex-1 overflow-y-auto px-3 py-4 scrollbar-thin">
          {groups.map(([group, items]) => {
            const isOpen = openGroups[group] !== false;
            return (
              <div key={group} className="mb-4">
                {!collapsed && (
                  <button
                    type="button"
                    onClick={() => toggleGroup(group)}
                    className="mb-2 flex w-full items-center justify-between px-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400 transition-colors hover:text-slate-600"
                    aria-expanded={isOpen}
                  >
                    <span>{group}</span>
                    <ChevronDown
                      className={cn(
                        "h-3 w-3 transition-transform",
                        !isOpen && "-rotate-90",
                      )}
                    />
                  </button>
                )}
                {(collapsed || isOpen) && (
                  <div className="space-y-1">
                    {items.map(({ to, label, icon: Icon, end, onClick }) => {
                      const content = (
                        <NavLink
                          key={to}
                          to={to}
                          end={end}
                          onClick={() => {
                            setMenuOpen(false);
                            onClick?.();
                          }}
                          className={({ isActive }) =>
                            cn(
                              "group flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-all",
                              collapsed && "justify-center px-0",
                              isActive
                                ? "bg-[#b5822e] text-white shadow-sm ring-1 ring-amber-200/40"
                                : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                            )
                          }
                        >
                          <Icon className="h-4 w-4 shrink-0" />
                          {!collapsed && <span className="truncate">{label}</span>}
                        </NavLink>
                      );
                      return collapsed ? (
                        <Tooltip key={to} label={label}>
                          {content}
                        </Tooltip>
                      ) : (
                        content
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="border-t border-slate-100 p-3">
          <div
            className={cn(
              "flex items-center gap-3 rounded-xl bg-slate-50 p-2",
              collapsed && "justify-center",
            )}
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-xs font-semibold text-white">
              {initials(user?.full_name)}
            </div>
            {!collapsed && (
              <>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-semibold text-slate-900">
                    {user?.full_name || "Usuario"}
                  </div>
                  <div className="truncate text-[11px] capitalize text-slate-500">
                    {user?.role || ""}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={logout}
                  className="rounded-lg p-2 text-slate-400 hover:bg-white hover:text-red-600"
                  aria-label="Sair"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </>
            )}
          </div>
        </div>
      </aside>

      <div
        className={cn(
          "flex min-h-screen flex-col transition-all",
          contentMargin,
        )}
      >
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 px-4 py-3 backdrop-blur-xl md:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 md:hidden"
              onClick={() => setMenuOpen(true)}
              aria-label="Abrir menu"
            >
              <Menu className="h-5 w-5" />
            </button>

            <button
              type="button"
              onClick={() => window.dispatchEvent(new Event("ejc-open-search"))}
              className="flex h-10 min-w-0 flex-1 items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 text-left text-sm text-slate-500 transition-all hover:border-amber-300/60 hover:bg-amber-50/50 md:max-w-xl"
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="truncate">
                Buscar cliente, caso, processo ou documento
              </span>
              <kbd className="ml-auto hidden rounded-md border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-slate-400 sm:block">
                Ctrl K
              </kbd>
            </button>

            <Link to="/casos" className="hidden sm:inline-flex">
              <Button size="md" icon={<Plus className="h-4 w-4" />}>
                Novo caso
              </Button>
            </Link>

            <button
              type="button"
              onClick={toggle}
              className="hidden h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 sm:flex"
              aria-label="Alternar tema"
            >
              {theme === "dark" ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Moon className="h-4 w-4" />
              )}
            </button>

            <div className="relative">
              <button
                type="button"
                onClick={() => setNotifOpen((v) => !v)}
                className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                aria-label="Notificacoes"
              >
                <Bell className="h-4 w-4" />
                {notifCount > 0 && (
                  <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white ring-2 ring-white">
                    {notifCount}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className="absolute right-0 mt-2 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
                  <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                    <div className="text-sm font-semibold text-slate-950">
                      Notificacoes
                    </div>
                    <button
                      type="button"
                      className="text-xs font-medium text-blue-600 hover:text-blue-700"
                      onClick={() =>
                        api
                          .post("/notifications/ler-todas")
                          .then(() => setNotifCount(0))
                      }
                    >
                      Marcar lidas
                    </button>
                  </div>
                  <div className="max-h-96 overflow-y-auto">
                    {notifs.length === 0 ? (
                      <div className="px-4 py-8 text-center text-sm text-slate-400">
                        Sem notificacoes
                      </div>
                    ) : (
                      notifs.map((n) => (
                        <button
                          key={n.id}
                          type="button"
                          onClick={() => {
                            if (n.link) nav(n.link);
                            setNotifOpen(false);
                          }}
                          className={cn(
                            "w-full border-b border-slate-50 px-4 py-3 text-left hover:bg-blue-50/60",
                            !n.lida && "bg-blue-50/40",
                          )}
                        >
                          <div className="text-sm font-medium text-slate-900">
                            {n.titulo}
                          </div>
                          <div className="mt-1 line-clamp-2 text-xs text-slate-500">
                            {n.mensagem}
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            <SecurityMenu user={user} />
          </div>
        </header>

        <main className="ejc-modern-scope flex-1 px-4 py-5 md:px-7 md:py-7">
          <div className="mx-auto w-full max-w-[1440px] animate-rise">
            <Outlet />
          </div>
        </main>
      </div>

      <OnboardingTour />
      <Link
        to="/assistente-ia"
        className="fixed bottom-5 right-5 z-30 hidden h-12 w-12 items-center justify-center rounded-2xl bg-violet-600 text-white shadow-lg shadow-violet-600/25 hover:bg-violet-700 md:flex"
        aria-label="Assistente IA"
      >
        <Bot className="h-5 w-5" />
      </Link>
    </div>
  );
}
