import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  ChevronDown,
  Lightbulb,
  Search,
  Sparkles,
} from "lucide-react";
import { Badge, EmptyState, PageHeader } from "../components/UI";
import { canRoleAccessPath } from "../config/moduleRegistry";
import { useAuth } from "../stores/auth";
import {
  GUIA_SISTEMA,
  PERFIL_LABEL,
  type FerramentaGuia,
  type GrupoGuia,
} from "../content/guiaSistema";

// Central de Ajuda — Guia Intuitivo do Sistema.
// Manual navegável que ensina cada ferramenta REAL do EJC (fonte:
// content/guiaSistema.ts, derivado de config/moduleRegistry.tsx). Busca por
// título/conteúdo, navegação por grupo e "Abrir ferramenta" para a rota real.

// Rotas dinâmicas (com ":") abrem em contexto de um caso/cliente — não há URL
// direta. Resolvemos o ponto de entrada navegável (a base da rota) e sinalizamos.
function baseNavegavel(rota: string): string {
  const dyn = rota.indexOf("/:");
  return dyn >= 0 ? rota.slice(0, dyn) || "/" : rota;
}

function ehContextual(rota: string): boolean {
  return rota.includes("/:");
}

function texto(f: FerramentaGuia): string {
  return [
    f.titulo,
    f.oQueE,
    f.paraQueServe,
    f.comoUsar.join(" "),
    f.dica ?? "",
    f.rota,
    f.badge ?? "",
  ]
    .join(" ")
    .toLowerCase();
}

function AberturaLink({ ferramenta }: { ferramenta: FerramentaGuia }) {
  const contextual = ehContextual(ferramenta.rota);
  const destino = baseNavegavel(ferramenta.rota);
  return (
    <Link
      to={destino}
      className="btn-primary w-fit"
      title={
        contextual
          ? "Abre dentro de um caso — leva à tela de entrada"
          : `Abrir ${ferramenta.titulo}`
      }
    >
      {contextual ? "Ir para a tela de entrada" : "Abrir ferramenta"}
      <ArrowUpRight className="h-4 w-4" />
    </Link>
  );
}

function CardFerramenta({
  ferramenta,
  aberto,
  onToggle,
}: {
  ferramenta: FerramentaGuia;
  aberto: boolean;
  onToggle: () => void;
}) {
  const contextual = ehContextual(ferramenta.rota);
  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={aberto}
        className="flex w-full items-start gap-3 p-4 text-left transition-colors hover:bg-slate-900/[0.02] dark:hover:bg-white/[0.04]"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">
              {ferramenta.titulo}
            </h3>
            {ferramenta.badge && <Badge tone="ouro">{ferramenta.badge}</Badge>}
            <Badge tone="slate">{PERFIL_LABEL[ferramenta.perfil]}</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {ferramenta.oQueE}
          </p>
        </div>
        <ChevronDown
          className={`mt-1 h-4 w-4 shrink-0 text-slate-400 transition-transform ${
            aberto ? "rotate-180" : ""
          }`}
        />
      </button>

      {aberto && (
        <div className="space-y-4 border-t border-black/[0.05] px-4 pb-4 pt-4 dark:border-white/[0.08]">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Para que serve
            </p>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {ferramenta.paraQueServe}
            </p>
          </div>

          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Como usar
            </p>
            <ol className="mt-2 space-y-2">
              {ferramenta.comoUsar.map((passo, i) => (
                <li key={i} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-navy text-xs font-bold text-white">
                    {i + 1}
                  </span>
                  <p className="pt-0.5 text-sm text-slate-600 dark:text-slate-300">
                    {passo}
                  </p>
                </li>
              ))}
            </ol>
          </div>

          {ferramenta.dica && (
            <div className="flex items-start gap-2 rounded-xl bg-warn-50 px-4 py-3 ring-1 ring-inset ring-warn-200/60 dark:bg-warn-500/10">
              <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-warn-600" />
              <p className="text-sm text-warn-800 dark:text-warn-200">
                {ferramenta.dica}
              </p>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <AberturaLink ferramenta={ferramenta} />
            {contextual && (
              <span className="text-xs text-slate-400">
                Abre dentro de um caso específico.
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Ajuda() {
  const role = useAuth((state) => state.user?.role);
  const [q, setQ] = useState("");
  const [grupoAtivo, setGrupoAtivo] = useState<string | null>(null);
  const [abertos, setAbertos] = useState<Set<string>>(new Set());

  const toggle = (id: string) =>
    setAbertos((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // O guia só exibe ferramentas que o PERFIL do usuário pode de fato abrir
  // (mesma matriz RBAC das rotas: canRoleAccessPath/moduleRegistry) — sem
  // isso, um financeiro via verbetes de telas que devolveriam "sem acesso".
  const gruposDoPerfil = useMemo<GrupoGuia[]>(
    () =>
      GUIA_SISTEMA.map((grupo) => ({
        ...grupo,
        ferramentas: grupo.ferramentas.filter((f) =>
          canRoleAccessPath(role, f.rota),
        ),
      })).filter((grupo) => grupo.ferramentas.length > 0),
    [role],
  );

  const totalDoPerfil = useMemo(
    () => gruposDoPerfil.reduce((soma, g) => soma + g.ferramentas.length, 0),
    [gruposDoPerfil],
  );

  // Grupos filtrados por busca (título/conteúdo) e pelo grupo ativo.
  const gruposFiltrados = useMemo<GrupoGuia[]>(() => {
    const termo = q.trim().toLowerCase();
    return gruposDoPerfil
      .map((grupo) => {
        if (grupoAtivo && grupo.id !== grupoAtivo) {
          return { ...grupo, ferramentas: [] };
        }
        if (!termo) return grupo;
        const ferramentas = grupo.ferramentas.filter((f) =>
          texto(f).includes(termo),
        );
        return { ...grupo, ferramentas };
      })
      .filter((grupo) => grupo.ferramentas.length > 0);
  }, [q, grupoAtivo, gruposDoPerfil]);

  const totalEncontrado = gruposFiltrados.reduce(
    (soma, g) => soma + g.ferramentas.length,
    0,
  );

  const chipBase =
    "rounded-full px-3 py-1.5 text-xs font-medium transition-colors";

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <PageHeader
        eyebrow="Central de Ajuda"
        title="Guia do Sistema"
        subtitle={`Aprenda para que serve e como usar cada uma das ${totalDoPerfil} ferramentas disponíveis para o seu perfil. Busque um tema ou navegue pelos grupos, na ordem em que você trabalha.`}
        actions={
          <span className="badge-info inline-flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5" />
            {totalDoPerfil} ferramentas
          </span>
        }
      />

      {/* Busca */}
      <div className="relative mb-4 max-w-md">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
        <input
          className="input pl-9"
          placeholder="Buscar ferramenta ou assunto..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Buscar no guia do sistema"
        />
      </div>

      {/* Navegação por grupo */}
      <div className="mb-6 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setGrupoAtivo(null)}
          className={`${chipBase} ${
            grupoAtivo === null
              ? "bg-navy text-white"
              : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300 dark:hover:bg-white/[0.12]"
          }`}
        >
          Todos
        </button>
        {gruposDoPerfil.map((grupo) => (
          <button
            key={grupo.id}
            type="button"
            onClick={() =>
              setGrupoAtivo((atual) => (atual === grupo.id ? null : grupo.id))
            }
            className={`${chipBase} ${
              grupoAtivo === grupo.id
                ? "bg-navy text-white"
                : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300 dark:hover:bg-white/[0.12]"
            }`}
          >
            {grupo.titulo}
          </button>
        ))}
      </div>

      {q.trim() && (
        <p className="mb-4 text-xs text-slate-500">
          {totalEncontrado} ferramenta(s) encontrada(s) para “{q.trim()}”.
        </p>
      )}

      {gruposFiltrados.length === 0 ? (
        <EmptyState
          icon={Search}
          title={`Nenhuma ferramenta encontrada para "${q.trim()}".`}
          message="Tente outro termo ou limpe a busca para ver todos os grupos."
        />
      ) : (
        <div className="space-y-8">
          {gruposFiltrados.map((grupo) => (
            <section key={grupo.id}>
              <div className="mb-3">
                <h2 className="font-serif text-lg font-semibold text-slate-900 dark:text-slate-100">
                  {grupo.titulo}
                </h2>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {grupo.descricao}
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {grupo.ferramentas.map((ferramenta) => (
                  <CardFerramenta
                    key={ferramenta.id}
                    ferramenta={ferramenta}
                    aberto={abertos.has(ferramenta.id)}
                    onToggle={() => toggle(ferramenta.id)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
