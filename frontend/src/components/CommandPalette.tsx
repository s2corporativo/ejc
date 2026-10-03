import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
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
  Wrench,
  ClipboardCheck,
  Timer,
  WalletCards,
  Library,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { filterModulesByLifecycle } from "../lib/moduleLifecycle";
import { useAuth } from "../stores/auth";
import { useModuleLifecycleStore } from "../stores/moduleLifecycle";
import {
  getNavigationModules,
  ROLES,
  STAFF_ROUTES,
} from "../config/moduleRegistry";
import { NOVO_CASO_MANUAL_PATH } from "../lib/novoCaso";

const ICON: Record<string, typeof Users> = {
  cliente: Users,
  caso: Briefcase,
  peca: FileText,
  documento: FileText,
  tarefa: ClipboardCheck,
  prazo: Timer,
  financeiro: WalletCards,
};
const LABEL: Record<string, string> = {
  cliente: "Cliente",
  caso: "Caso",
  peca: "Peça",
  documento: "Documento",
  tarefa: "Tarefa",
  prazo: "Prazo",
  financeiro: "Financeiro",
};

type TipoBusca = "tudo" | "parte" | "cpf" | "processo";

interface ResultadoBusca {
  tipo:
    | "cliente"
    | "caso"
    | "peca"
    | "documento"
    | "tarefa"
    | "prazo"
    | "financeiro";
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

type NaturalCommand = {
  kind: "deadline" | "navigate";
  label: string;
  detail: string;
  path?: string;
  caseId?: string;
  date?: string;
  title?: string;
  ready: boolean;
};

const TIPOS: { value: TipoBusca; label: string }[] = [
  { value: "tudo", label: "Tudo" },
  { value: "parte", label: "Parte" },
  { value: "cpf", label: "CPF" },
  { value: "processo", label: "Nº Processo" },
];

const PLACEHOLDER: Record<TipoBusca, string> = {
  tudo: "Buscar clientes, casos, documentos, peças, tarefas…",
  parte: "Nome da parte…",
  cpf: "CPF ou CNPJ da parte/cliente…",
  processo: "Número do processo (CNJ ou interno)…",
};

const OPTION_ID = (index: number) => `cmdk-option-${index}`;

const SEARCHABLE_MODULE_KEYS = new Set([
  "atividades",
  "pecas",
  "inteligencia",
  "documentos",
  "banco-teses",
  "radar",
  "produtividade",
  "tributario",
]);

/** Nomes históricos retirados da lateral continuam sendo termos de descoberta. */
export const MODULE_SEARCH_ALIASES: Record<string, readonly string[]> = {
  atividades: ["Agenda e Prazos"],
  inteligencia: ["Inteligência Jurídica", "Conhecimento Jurídico"],
  radar: ["Radar Operacional"],
  produtividade: ["Relatórios"],
};

export function normalizarBusca(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
}

export function textoBuscaModulo(item: {
  key: string;
  label: string;
  description: string;
}): string {
  return normalizarBusca(
    [
      item.label,
      item.description,
      item.key,
      ...(MODULE_SEARCH_ALIASES[item.key] ?? []),
    ].join(" "),
  );
}

function naturalDate(token: string): string | null {
  const normalized = normalizarBusca(token);
  const date = new Date();
  if (normalized === "amanha") date.setDate(date.getDate() + 1);
  else if (normalized !== "hoje") {
    const match = token.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!match) return null;
    date.setFullYear(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
  }
  const ano = date.getFullYear();
  const mes = String(date.getMonth() + 1).padStart(2, "0");
  const dia = String(date.getDate()).padStart(2, "0");
  return `${ano}-${mes}-${dia}`;
}

export default function CommandPalette({
  privacyMode = false,
}: {
  privacyMode?: boolean;
}) {
  const nav = useNavigate();
  const user = useAuth((state) => state.user);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState<TipoBusca>("tudo");
  const [res, setRes] = useState<ResultadoBusca[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [naturalCommand, setNaturalCommand] = useState<NaturalCommand | null>(
    null,
  );
  const [commandRunning, setCommandRunning] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const role = user?.role ?? "";
  const lifecycleSettings = useModuleLifecycleStore((state) => state.settings);
  const canCreateCase = (ROLES.clientes as readonly string[]).includes(role);
  const canUseLegalAI = (ROLES.juridico as readonly string[]).includes(role);
  const canUseFinanceiroGlobal = (
    ROLES.financeiro as readonly string[]
  ).includes(role);
  const canRegisterCaseReceipt = [
    "superadmin",
    "admin",
    "socio",
    "advogado",
  ].includes(role);
  const quickActions = useMemo<QuickAction[]>(
    () => [
      ...(canCreateCase
        ? [
            {
              path: "/entrada",
              label: "Nova demanda",
              description:
                "Abrir a Entrada Jurídica para analisar com IA ou cadastrar rapidamente",
              icon: PenLine,
            },
          ]
        : []),
      ...(canUseLegalAI
        ? [
            {
              path: "/raio-x",
              // "Caso", e não "processo": o Raio-X analisa a entrada/potencial
              // caso a partir de documentos — não consulta processo judicial
              // por número CNJ (isso é o DataJud).
              label: "Analisar caso externo",
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
      ...(canUseLegalAI
        ? [
            {
              path: "/teses",
              label: "Buscar tese / Banco de teses",
              description: "Pesquisar teses, fundamentos e memória jurídica",
              icon: Library,
            },
            {
              path: "/pecas",
              label: "Produzir contestação ou peça",
              description: "Abrir produção jurídica, revisão e aprovação",
              icon: PenLine,
            },
          ]
        : []),
      {
        // Hub "Mais Ferramentas": sem esta entrada, o catálogo de módulos
        // avançados só era alcançável por URL direta (auditoria de
        // alcançabilidade 18/09/2026 — o hub não tinha NENHUM link de
        // entrada no app). Disponível a todos os perfis autenticados.
        path: "/ferramentas",
        label: "Mais ferramentas",
        description: "Abrir o catálogo de módulos avançados do escritório",
        icon: Wrench,
      },
      {
        path: "/atividades?tipo=prazo",
        label: "Prazos hoje",
        description: "Ver prazos e vencimentos que exigem atenção",
        icon: Timer,
      },
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
    const query = normalizarBusca(q.trim());
    if (query.length < 2) return quickActions;
    return quickActions.filter((action) =>
      normalizarBusca(`${action.label} ${action.description}`).includes(query),
    );
  }, [q, quickActions]);

  const searchableModules = useMemo(
    () =>
      filterModulesByLifecycle(
        STAFF_ROUTES.filter((item) => {
          if (!SEARCHABLE_MODULE_KEYS.has(item.key)) return false;
          if (item.status === "legacy") return false;
          if (!item.roles) return true;
          return Boolean(role && item.roles.includes(role));
        }),
        lifecycleSettings,
        "catalogo",
      ),
    [lifecycleSettings, role],
  );
  const matchingModules = useMemo(() => {
    const query = normalizarBusca(q.trim());
    if (query.length < 2) return [];
    const quickActionPaths = new Set(
      matchingQuickActions.map((action) => action.path),
    );
    return searchableModules.filter(
      (item) =>
        !quickActionPaths.has(item.path) &&
        textoBuscaModulo(item).includes(query),
    );
  }, [matchingQuickActions, q, searchableModules]);

  // Lista plana navegável por teclado: ações seguras para o perfil aparecem
  // antes dos resultados e dos sete destinos essenciais.
  const navItems = useMemo<{ key: string; link: string }[]>(() => {
    if (q.trim().length >= 2) {
      return [
        ...matchingQuickActions.map((action) => ({
          key: `action-${action.path}`,
          link: action.path,
        })),
        ...matchingModules.map((item) => ({
          key: `module-${item.key}`,
          link: item.path,
        })),
        ...(privacyMode
          ? []
          : res.map((result, index) => ({
              key: `${result.tipo}-${result.id}-${index}`,
              link: result.link,
            }))),
      ];
    }
    return [
      ...quickActions.map((action) => ({
        key: `action-${action.path}`,
        link: action.path,
      })),
      ...shortcuts.map((item) => ({ key: item.path, link: item.path })),
    ];
  }, [
    matchingModules,
    matchingQuickActions,
    privacyMode,
    q,
    quickActions,
    res,
    shortcuts,
  ]);

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
      setNaturalCommand(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open || privacyMode) {
      setNaturalCommand(null);
      return;
    }

    const raw = q.trim();
    const normalized = normalizarBusca(raw);
    if (raw.length < 3) {
      setNaturalCommand(null);
      return;
    }

    const staticCommands: Array<[string[], NaturalCommand]> = [
      [
        ["novo caso", "criar caso"],
        {
          kind: "navigate",
          label: "Abrir Nova demanda",
          detail: "Entrada Jurídica com opção de cadastro rápido.",
          path: "/entrada",
          ready: canCreateCase,
        },
      ],
      [
        ["entrada por ia", "analisar documento", "nova demanda"],
        {
          kind: "navigate",
          label: "Abrir Nova demanda",
          detail: "Enviar documentos, relatar o caso ou usar cadastro rápido.",
          path: "/entrada",
          ready: canCreateCase,
        },
      ],
      [
        ["financeiro", "abrir financeiro", "ir para financeiro"],
        {
          kind: "navigate",
          label: "Abrir Financeiro",
          detail: "Ir para recebimentos, pagamentos e caixa.",
          path: "/financeiro",
          ready: canUseFinanceiroGlobal,
        },
      ],
      [
        ["agenda", "abrir agenda", "ir para agenda"],
        {
          kind: "navigate",
          label: "Abrir Agenda",
          detail: "Ir para prazos, tarefas e compromissos.",
          path: "/atividades",
          ready: true,
        },
      ],
    ];

    for (const [aliases, command] of staticCommands) {
      if (aliases.includes(normalized)) {
        setNaturalCommand(command);
        return;
      }
    }

    const deadlineMatch = raw.match(
      /^criar\s+prazo\s+(hoje|amanhã|amanha|\d{1,2}\/\d{1,2}\/\d{4})(?:\s+para\s+(.+?))?\s+no\s+caso\s+(.+)$/i,
    );
    const paymentMatch = raw.match(
      /^registrar\s+pagamento(?:\s+de)?\s+(?:r\$\s*)?([\d.,]+)\s+no\s+caso\s+(.+)$/i,
    );
    const openCaseMatch = raw.match(/^abrir\s+caso\s+(.+)$/i);

    const caseTerm =
      deadlineMatch?.[3]?.trim() ||
      paymentMatch?.[2]?.trim() ||
      openCaseMatch?.[1]?.trim();

    if (!caseTerm) {
      setNaturalCommand(null);
      return;
    }

    let stale = false;
    setNaturalCommand({
      kind: "navigate",
      label: "Localizando caso…",
      detail: caseTerm,
      ready: false,
    });

    const timer = setTimeout(() => {
      api
        .get("/search", { params: { q: caseTerm, tipo: "tudo" } })
        .then((response) => {
          if (stale) return;
          const resultados = Array.isArray(response.data?.resultados)
            ? (response.data.resultados as ResultadoBusca[])
            : [];
          const caso = resultados.find((item) => item.tipo === "caso");
          if (!caso) {
            setNaturalCommand({
              kind: "navigate",
              label: "Caso não localizado",
              detail: "Refine o nome do caso no comando.",
              ready: false,
            });
            return;
          }

          if (deadlineMatch) {
            const date = naturalDate(deadlineMatch[1]);
            const title = deadlineMatch[2]?.trim() || "Providência jurídica";
            setNaturalCommand({
              kind: "deadline",
              label: "Criar prazo",
              detail:
                caso.titulo +
                " · " +
                (date || deadlineMatch[1]) +
                " · " +
                title,
              caseId: String(caso.id),
              date: date || undefined,
              title,
              ready: Boolean(date && canCreateCase),
            });
            return;
          }

          if (paymentMatch) {
            const rawValue = paymentMatch[1]
              .replace(/\./g, "")
              .replace(",", ".");
            const value = Number(rawValue);
            setNaturalCommand({
              kind: "navigate",
              label: "Preparar registro de pagamento",
              detail:
                caso.titulo +
                (Number.isFinite(value)
                  ? " · " +
                    value.toLocaleString("pt-BR", {
                      style: "currency",
                      currency: "BRL",
                    })
                  : ""),
              path:
                "/casos/" +
                caso.id +
                "?tab=financeiro&recebimento=" +
                encodeURIComponent(Number.isFinite(value) ? String(value) : ""),
              ready: canRegisterCaseReceipt,
            });
            return;
          }

          setNaturalCommand({
            kind: "navigate",
            label: "Abrir caso",
            detail: caso.titulo,
            path: caso.link,
            ready: true,
          });
        })
        .catch(() => {
          if (!stale) setNaturalCommand(null);
        });
    }, 220);

    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [
    canCreateCase,
    canRegisterCaseReceipt,
    canUseFinanceiroGlobal,
    canUseLegalAI,
    open,
    privacyMode,
    q,
  ]);

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
    if (privacyMode) {
      setRes([]);
      setLoading(false);
      return;
    }
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
  }, [q, tipo, open, privacyMode]);

  if (!open) return null;

  const go = (link: string) => {
    setOpen(false);
    nav(link);
  };

  const executeNaturalCommand = async () => {
    if (!naturalCommand?.ready || commandRunning) return;
    if (naturalCommand.kind === "navigate") {
      if (naturalCommand.path) go(naturalCommand.path);
      return;
    }

    if (
      naturalCommand.kind === "deadline" &&
      naturalCommand.caseId &&
      naturalCommand.date &&
      naturalCommand.title
    ) {
      setCommandRunning(true);
      try {
        await api.post("/deadlines/", {
          titulo: naturalCommand.title,
          tipo: "processual",
          prioridade: "media",
          data_prazo: naturalCommand.date,
          case_id: naturalCommand.caseId,
        });
        toast.success("Prazo criado e vinculado ao caso.");
        setOpen(false);
        nav("/casos/" + naturalCommand.caseId + "?tab=prazos");
      } catch (error: any) {
        toast.error(
          error?.response?.data?.detail || "Não foi possível criar o prazo.",
        );
      } finally {
        setCommandRunning(false);
      }
    }
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
      className="fixed inset-0 z-[90] bg-slate-950/45 flex items-start justify-center pt-[12vh] px-4 animate-fade-in"
      onClick={() => setOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Busca global do sistema"
        className="w-full max-w-xl card overflow-hidden shadow-lg animate-pop"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onKeyDownList}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100">
          <SearchIcon size={18} className="text-primary-600" />
          <input
            ref={inputRef}
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={
              privacyMode ? "Buscar módulos e ferramentas…" : PLACEHOLDER[tipo]
            }
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
        {!privacyMode && (
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
        )}
        <div
          ref={listRef}
          id="cmdk-listbox"
          role="listbox"
          aria-label="Resultados da busca"
          className="max-h-80 overflow-auto"
        >
          {naturalCommand && (
            <div className="ejc-command-preview">
              <div>
                <span>Comando interpretado</span>
                <strong>{naturalCommand.label}</strong>
                <small>{naturalCommand.detail}</small>
              </div>
              <button
                type="button"
                disabled={!naturalCommand.ready || commandRunning}
                onClick={executeNaturalCommand}
              >
                {commandRunning
                  ? "Executando…"
                  : naturalCommand.kind === "deadline"
                    ? "Confirmar criação"
                    : "Executar"}
              </button>
            </div>
          )}
          {loading && (
            <div className="p-6 text-center text-sm text-slate-400">
              Buscando…
            </div>
          )}
          {!loading &&
            q.trim().length >= 2 &&
            res.length === 0 &&
            displayedQuickActions.length === 0 &&
            matchingModules.length === 0 && (
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
          {q.trim().length >= 2 && matchingModules.length > 0 && (
            <div className="p-3 pb-1">
              <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Módulos
              </div>
              <div className="grid gap-1 sm:grid-cols-2">
                {matchingModules.map(
                  ({ key, path, label, description, icon: Icon }, index) => {
                    const itemIndex = displayedQuickActions.length + index;
                    const isActive = itemIndex === activeIndex;
                    return (
                      <button
                        key={key}
                        id={OPTION_ID(itemIndex)}
                        data-index={itemIndex}
                        role="option"
                        aria-selected={isActive}
                        type="button"
                        onMouseEnter={() => setActiveIndex(itemIndex)}
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
          {!privacyMode &&
            res.map((result, index) => {
              const Icon = ICON[result.tipo] || FileText;
              const itemIndex =
                displayedQuickActions.length + matchingModules.length + index;
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
