import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search as SearchIcon,
  Users,
  Briefcase,
  CalendarClock,
  FileText,
  FileUp,
  Headset,
  PenLine,
  ScanSearch,
} from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import { getNavigationModules, ROLES } from "../config/moduleRegistry";
import {
  NOVO_CASO_DOCUMENTO_PATH,
  NOVO_CASO_MANUAL_PATH,
} from "../lib/novoCaso";

const ICON: Record<string, typeof Users> = {
  cliente: Users,
  caso: Briefcase,
  peca: FileText,
};
const LABEL: Record<string, string> = {
  cliente: "Cliente",
  caso: "Caso",
  peca: "Peça",
};

type TipoBusca = "tudo" | "parte" | "cpf" | "processo";

interface ResultadoBusca {
  tipo: "cliente" | "caso" | "peca";
  id: number | string;
  titulo: string;
  subtitulo?: string | null;
  link: string;
}

interface QuickAction {
  path: string;
  label: string;
  description: string;
  icon: typeof Users;
}

const TIPOS: { value: TipoBusca; label: string }[] = [
  { value: "tudo", label: "Tudo" },
  { value: "parte", label: "Parte" },
  { value: "cpf", label: "CPF" },
  { value: "processo", label: "Nº Processo" },
];

const PLACEHOLDER: Record<TipoBusca, string> = {
  tudo: "Buscar clientes, casos, peças…",
  parte: "Nome da parte…",
  cpf: "CPF ou CNPJ da parte/cliente…",
  processo: "Número do processo (CNJ ou interno)…",
};

const OPTION_ID = (index: number) => `cmdk-option-${index}`;

export default function CommandPalette() {
  const nav = useNavigate();
  const user = useAuth((state) => state.user);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState<TipoBusca>("tudo");
  const [res, setRes] = useState<ResultadoBusca[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const role = user?.role ?? "";
  const canCreateCase = (ROLES.clientes as readonly string[]).includes(role);
  const canUseLegalAI = (ROLES.juridico as readonly string[]).includes(role);
  const quickActions = useMemo<QuickAction[]>(
    () => [
      ...(canCreateCase
        ? [
            {
              path: NOVO_CASO_DOCUMENTO_PATH,
              label: "Novo caso por documento",
              description: "Enviar arquivos, revisar os dados e criar o caso",
              icon: FileUp,
            },
            {
              path: NOVO_CASO_MANUAL_PATH,
              label: "Novo caso manual",
              description: "Preencher um cadastro passo a passo",
              icon: PenLine,
            },
          ]
        : []),
      ...(canUseLegalAI
        ? [
            {
              path: "/raio-x",
              label: "Analisar processo externo",
              description: "Fazer uma análise preliminar sem criar caso",
              icon: ScanSearch,
            },
          ]
        : []),
      ...(canCreateCase
        ? [
            {
              path: "/atividades?tab=relacionamento",
              label: "Registrar atendimento",
              description: "Abrir a linha do tempo do cliente",
              icon: Headset,
            },
          ]
        : []),
      {
        path: "/atividades",
        label: "Abrir Agenda e Prazos",
        description: "Ver compromissos, tarefas e vencimentos",
        icon: CalendarClock,
      },
    ],
    [canCreateCase, canUseLegalAI],
  );
  const shortcuts = useMemo(
    () => getNavigationModules(user?.role).filter((item) => item.essential),
    [user?.role],
  );
  const matchingQuickActions = useMemo(() => {
    const query = q.trim().toLocaleLowerCase("pt-BR");
    if (query.length < 2) return quickActions;
    return quickActions.filter((action) =>
      `${action.label} ${action.description}`
        .toLocaleLowerCase("pt-BR")
        .includes(query),
    );
  }, [q, quickActions]);

  // Lista plana navegável por teclado: ações seguras para o perfil aparecem
  // antes dos resultados e dos sete destinos essenciais.
  const navItems = useMemo<{ key: string; link: string }[]>(() => {
    if (q.trim().length >= 2) {
      return [
        ...matchingQuickActions.map((action) => ({
          key: `action-${action.path}`,
          link: action.path,
        })),
        ...res.map((result, index) => ({
          key: `${result.tipo}-${result.id}-${index}`,
          link: result.link,
        })),
      ];
    }
    return [
      ...quickActions.map((action) => ({
        key: `action-${action.path}`,
        link: action.path,
      })),
      ...shortcuts.map((item) => ({ key: item.path, link: item.path })),
    ];
  }, [matchingQuickActions, q, quickActions, res, shortcuts]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
      if (event.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("ejc-open-search", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("ejc-open-search", onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 40);
    else {
      setQ("");
      setRes([]);
      setTipo("tudo");
    }
  }, [open]);

  // Sempre que a lista navegável mudar, reposiciona o destaque no topo.
  useEffect(() => {
    setActiveIndex(0);
  }, [navItems]);

  // Mantém o item ativo visível dentro do container rolável.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(
      `[data-index="${activeIndex}"]`,
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  useEffect(() => {
    if (!open) return;
    if (q.trim().length < 2) {
      setRes([]);
      setLoading(false);
      return;
    }
    let stale = false;
    setLoading(true);
    const timer = setTimeout(() => {
      api
        .get("/search", { params: { q, tipo } })
        .then((response) => {
          if (!stale)
            setRes(
              Array.isArray(response.data?.resultados)
                ? (response.data.resultados as ResultadoBusca[])
                : [],
            );
        })
        .catch(() => {
          if (!stale) setRes([]);
        })
        .finally(() => {
          if (!stale) setLoading(false);
        });
    }, 250);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [q, tipo, open]);

  if (!open) return null;

  const go = (link: string) => {
    setOpen(false);
    nav(link);
  };

  const onKeyDownList = (event: React.KeyboardEvent) => {
    if (navItems.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % navItems.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex(
        (index) => (index - 1 + navItems.length) % navItems.length,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      const item = navItems[Math.min(activeIndex, navItems.length - 1)];
      if (item) go(item.link);
    }
  };

  const hasNav = navItems.length > 0;
  const displayedQuickActions =
    q.trim().length >= 2 ? matchingQuickActions : quickActions;

  return (
    <div
      className="fixed inset-0 z-[70] bg-slate-950/45 flex items-start justify-center pt-[12vh] px-4 animate-fade-in"
      onClick={() => setOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Busca global do sistema"
        className="w-full max-w-xl card shadow-float overflow-hidden animate-pop"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onKeyDownList}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100">
          <SearchIcon size={18} className="text-primary-600" />
          <input
            ref={inputRef}
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={PLACEHOLDER[tipo]}
            role="combobox"
            aria-expanded={hasNav}
            aria-controls="cmdk-listbox"
            aria-autocomplete="list"
            aria-activedescendant={hasNav ? OPTION_ID(activeIndex) : undefined}
            className="flex-1 bg-transparent outline-none text-sm text-slate-900 placeholder:text-slate-400"
          />
          <kbd className="text-[10px] text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">
            ESC
          </kbd>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 border-b border-slate-100">
          {TIPOS.map((item) => {
            const active = item.value === tipo;
            return (
              <button
                key={item.value}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  setTipo(item.value);
                  inputRef.current?.focus();
                }}
                className={
                  active
                    ? "rounded-full border border-primary-300 bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-700 transition-colors"
                    : "rounded-full border border-slate-200 bg-transparent px-2.5 py-1 text-xs text-slate-500 transition-colors hover:bg-primary-50 hover:text-slate-900"
                }
              >
                {item.label}
              </button>
            );
          })}
        </div>
        <div
          ref={listRef}
          id="cmdk-listbox"
          role="listbox"
          aria-label="Resultados da busca"
          className="max-h-80 overflow-auto"
        >
          {loading && (
            <div className="p-6 text-center text-sm text-slate-400">
              Buscando…
            </div>
          )}
          {!loading &&
            q.trim().length >= 2 &&
            res.length === 0 &&
            displayedQuickActions.length === 0 && (
              <div className="p-6 text-center text-sm text-slate-400">
                Nenhum resultado para “{q}”.
              </div>
            )}
          {displayedQuickActions.length > 0 && (
            <div className="p-3 pb-1">
              <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Ações rápidas
              </div>
              <div className="grid gap-1 sm:grid-cols-2">
                {displayedQuickActions.map(
                  ({ path, label, description, icon: Icon }, index) => {
                    const isActive = index === activeIndex;
                    return (
                      <button
                        key={path}
                        id={OPTION_ID(index)}
                        data-index={index}
                        role="option"
                        aria-selected={isActive}
                        type="button"
                        onMouseEnter={() => setActiveIndex(index)}
                        onClick={() => go(path)}
                        className={`flex items-start gap-2 rounded-lg px-3 py-2 text-left transition-colors ${
                          isActive
                            ? "bg-primary-50 text-slate-900"
                            : "text-slate-600 hover:bg-primary-50/60 hover:text-slate-900"
                        }`}
                      >
                        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary-600" />
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">
                            {label}
                          </span>
                          <span className="block line-clamp-2 text-xs text-slate-400">
                            {description}
                          </span>
                        </span>
                      </button>
                    );
                  },
                )}
              </div>
            </div>
          )}
          {res.map((result, index) => {
            const Icon = ICON[result.tipo] || FileText;
            const itemIndex = displayedQuickActions.length + index;
            const isActive = itemIndex === activeIndex;
            return (
              <button
                key={`${result.tipo}-${result.id}-${index}`}
                id={OPTION_ID(itemIndex)}
                data-index={itemIndex}
                role="option"
                aria-selected={isActive}
                onMouseEnter={() => setActiveIndex(itemIndex)}
                onClick={() => go(result.link)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                  isActive ? "bg-primary-50" : "hover:bg-primary-50/60"
                }`}
              >
                <span className="w-7 h-7 rounded-lg bg-primary-50 grid place-items-center text-primary-600 shrink-0">
                  <Icon size={15} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-slate-900 truncate">
                    {result.titulo}
                  </span>
                  <span className="block text-xs text-slate-400 truncate">
                    {LABEL[result.tipo] || result.tipo}
                    {result.subtitulo ? ` · ${result.subtitulo}` : ""}
                  </span>
                </span>
              </button>
            );
          })}
          {q.trim().length < 2 && (
            <div className="p-3">
              <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Atalhos do sistema
              </div>
              <div className="grid gap-1 sm:grid-cols-2">
                {shortcuts.map(({ path, label, icon: Icon }, index) => {
                  const itemIndex = quickActions.length + index;
                  const isActive = itemIndex === activeIndex;
                  return (
                    <button
                      key={path}
                      id={OPTION_ID(itemIndex)}
                      data-index={itemIndex}
                      role="option"
                      aria-selected={isActive}
                      type="button"
                      onMouseEnter={() => setActiveIndex(itemIndex)}
                      onClick={() => go(path)}
                      className={`flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                        isActive
                          ? "bg-primary-50 text-slate-900"
                          : "text-slate-600 hover:bg-primary-50/60 hover:text-slate-900"
                      }`}
                    >
                      <Icon className="h-4 w-4 text-primary-600" />
                      <span className="truncate">{label}</span>
                    </button>
                  );
                })}
              </div>
              <div className="mt-2 text-center text-xs text-slate-400">
                Digite ao menos 2 caracteres para buscar dados. Atalho:{" "}
                <kbd className="border border-slate-200 rounded px-1">
                  Ctrl/⌘ K
                </kbd>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
