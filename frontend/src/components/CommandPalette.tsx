import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search as SearchIcon, Users, Briefcase, FileText } from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import { getNavigationModules } from "../config/moduleRegistry";

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

export default function CommandPalette() {
  const nav = useNavigate();
  const user = useAuth((state) => state.user);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState<TipoBusca>("tudo");
  const [res, setRes] = useState<ResultadoBusca[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const shortcuts = useMemo(
    () => getNavigationModules(user?.role).slice(0, 10),
    [user?.role],
  );

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

  return (
    <div
      className="fixed inset-0 z-[70] bg-navy-950/50 backdrop-blur-sm flex items-start justify-center pt-[12vh] px-4 animate-fade-in"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-xl card shadow-float overflow-hidden animate-pop"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-bronze-pale">
          <SearchIcon size={18} className="text-bronze" />
          <input
            ref={inputRef}
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={PLACEHOLDER[tipo]}
            className="flex-1 bg-transparent outline-none text-sm text-navy-900 placeholder:text-slate-400"
          />
          <kbd className="text-[10px] text-slate-400 border border-bronze-pale rounded px-1.5 py-0.5">
            ESC
          </kbd>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 border-b border-bronze-pale">
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
                    ? "rounded-full border border-bronze bg-bronze-50 px-2.5 py-1 text-xs font-medium text-bronze transition-colors"
                    : "rounded-full border border-bronze-pale bg-transparent px-2.5 py-1 text-xs text-slate-500 transition-colors hover:bg-bronze-50 hover:text-navy-900"
                }
              >
                {item.label}
              </button>
            );
          })}
        </div>
        <div className="max-h-80 overflow-auto">
          {loading && (
            <div className="p-6 text-center text-sm text-slate-400">
              Buscando…
            </div>
          )}
          {!loading && q.trim().length >= 2 && res.length === 0 && (
            <div className="p-6 text-center text-sm text-slate-400">
              Nenhum resultado para “{q}”.
            </div>
          )}
          {res.map((result, index) => {
            const Icon = ICON[result.tipo] || FileText;
            return (
              <button
                key={`${result.tipo}-${result.id}-${index}`}
                onClick={() => go(result.link)}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-bronze-50 text-left transition-colors"
              >
                <span className="w-7 h-7 rounded-lg bg-bronze-50 grid place-items-center text-bronze shrink-0">
                  <Icon size={15} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-navy-900 truncate">
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
                {shortcuts.map(({ path, label, icon: Icon }) => (
                  <button
                    key={path}
                    type="button"
                    onClick={() => go(path)}
                    className="flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-600 hover:bg-bronze-50 hover:text-navy-900"
                  >
                    <Icon className="h-4 w-4 text-bronze" />
                    <span className="truncate">{label}</span>
                  </button>
                ))}
              </div>
              <div className="mt-2 text-center text-xs text-slate-400">
                Digite ao menos 2 caracteres para buscar dados. Atalho:{" "}
                <kbd className="border border-bronze-pale rounded px-1">
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
