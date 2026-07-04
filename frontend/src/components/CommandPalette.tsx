import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Search as SearchIcon, Users, Briefcase, FileText } from "lucide-react";
import api from "../lib/api";

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
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState<TipoBusca>("tudo");
  const [res, setRes] = useState<ResultadoBusca[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Atalho Cmd/Ctrl+K + evento do botão do header
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
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

  // Busca com debounce
  useEffect(() => {
    if (!open) return;
    if (q.trim().length < 2) {
      setRes([]);
      return;
    }
    setLoading(true);
    const t = setTimeout(() => {
      api
        .get("/search", { params: { q, tipo } })
        .then((r) => setRes(r.data.resultados as ResultadoBusca[]))
        .catch(() => setRes([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
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
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-bronze-pale">
          <SearchIcon size={18} className="text-bronze" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={PLACEHOLDER[tipo]}
            className="flex-1 bg-transparent outline-none text-sm text-navy-900 placeholder:text-slate-400"
          />
          <kbd className="text-[10px] text-slate-400 border border-bronze-pale rounded px-1.5 py-0.5">
            ESC
          </kbd>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 border-b border-bronze-pale">
          {TIPOS.map((t) => {
            const ativo = t.value === tipo;
            return (
              <button
                key={t.value}
                type="button"
                aria-pressed={ativo}
                onClick={() => {
                  setTipo(t.value);
                  inputRef.current?.focus();
                }}
                className={
                  ativo
                    ? "rounded-full border border-bronze bg-bronze-50 px-2.5 py-1 text-xs font-medium text-bronze transition-colors"
                    : "rounded-full border border-bronze-pale bg-transparent px-2.5 py-1 text-xs text-slate-500 transition-colors hover:bg-bronze-50 hover:text-navy-900"
                }
              >
                {t.label}
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
          {res.map((r, i) => {
            const Icon = ICON[r.tipo] || FileText;
            return (
              <button
                key={i}
                onClick={() => go(r.link)}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-bronze-50 text-left transition-colors"
              >
                <span className="w-7 h-7 rounded-lg bg-bronze-50 grid place-items-center text-bronze shrink-0">
                  <Icon size={15} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-navy-900 truncate">
                    {r.titulo}
                  </span>
                  <span className="block text-xs text-slate-400 truncate">
                    {LABEL[r.tipo] || r.tipo}
                    {r.subtitulo ? ` · ${r.subtitulo}` : ""}
                  </span>
                </span>
              </button>
            );
          })}
          {q.trim().length < 2 && (
            <div className="p-6 text-center text-xs text-slate-400">
              Digite ao menos 2 caracteres. Atalho:{" "}
              <kbd className="border border-bronze-pale rounded px-1">
                Ctrl/⌘ K
              </kbd>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
