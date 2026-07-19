import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, HelpCircle } from "lucide-react";
import api from "../lib/api";
import Markdown from "./Markdown";
import { getModuleTitleByHelpKey } from "../config/moduleRegistry";
import { Drawer, EmptyState, SearchBar, Skeleton, cn } from "./UI";

// ── Ajuda contextual (R1) ────────────────────────────────────────────────────
// Botão "?" discreto que abre um Drawer com os tópicos de ajuda do módulo
// atual (GET /module-help/{moduleKey}). Sem moduleKey, vira atalho para a
// Central de Ajuda (/ajuda). Busca global via GET /module-help/?q=.

interface HelpTopic {
  id?: number | string;
  module_key?: string;
  titulo: string;
  conteudo_md?: string | null;
}

// Título humano do módulo: primeiro o registro oficial (moduleRegistry, ex.:
// "inteligencia" → "Inteligência Jurídica"); este mapa cobre apenas apelidos
// que não têm entrada 1:1 no registry. NUNCA exibir o slug técnico cru.
const MODULE_TITLES: Record<string, string> = {
  casos: "Casos",
  prazos: "Prazos",
  documentos: "Documentos",
  pecas: "Peças",
  clientes: "Clientes",
  workflow: "Workflows",
  checklists: "Checklists",
};

function tituloHumano(moduleKey: string): string {
  return (
    MODULE_TITLES[moduleKey] ??
    getModuleTitleByHelpKey(moduleKey) ??
    // Último recurso: slug legível ("gestao_documental" → "Gestao documental")
    moduleKey
      .replace(/[-_]/g, " ")
      .replace(/^\w/, (c) => c.toUpperCase())
  );
}

// Aceita tanto lista pura quanto envelope { data: [...] } — defensivo.
function normalizarTopicos(payload: unknown): HelpTopic[] {
  const lista: unknown[] = Array.isArray(payload)
    ? payload
    : payload &&
        typeof payload === "object" &&
        Array.isArray((payload as { data?: unknown[] }).data)
      ? ((payload as { data: unknown[] }).data as unknown[])
      : [];
  return lista.filter(
    (t): t is HelpTopic =>
      !!t &&
      typeof t === "object" &&
      typeof (t as HelpTopic).titulo === "string",
  );
}

function LinkCentralAjuda({ onClick }: { onClick?: () => void }) {
  return (
    <Link
      to="/ajuda"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-primary-700 underline underline-offset-2 hover:text-primary-800"
    >
      Abrir Central de Ajuda
      <ExternalLink className="h-3.5 w-3.5" />
    </Link>
  );
}

export default function HelpButton({
  moduleKey,
  className,
}: {
  /** Chave do módulo atual (casos, prazos...). null → atalho para /ajuda. */
  moduleKey: string | null;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(false);
  const [topicos, setTopicos] = useState<HelpTopic[]>([]);
  const [busca, setBusca] = useState("");
  const [resultados, setResultados] = useState<HelpTopic[] | null>(null);
  const [buscando, setBuscando] = useState(false);

  // Tópicos do módulo — carrega ao abrir o drawer
  useEffect(() => {
    if (!open || !moduleKey) return;
    setLoading(true);
    setErro(false);
    api
      .get<unknown>(`/module-help/${moduleKey}`)
      .then((r) => setTopicos(normalizarTopicos(r.data)))
      .catch(() => {
        setErro(true);
        setTopicos([]);
      })
      .finally(() => setLoading(false));
  }, [open, moduleKey]);

  // Busca global com debounce
  useEffect(() => {
    if (!open) return;
    const q = busca.trim();
    if (!q) {
      setResultados(null);
      setBuscando(false);
      return;
    }
    setBuscando(true);
    const timer = setTimeout(() => {
      api
        .get<unknown>("/module-help/", { params: { q } })
        .then((r) => setResultados(normalizarTopicos(r.data)))
        .catch(() => setResultados([]))
        .finally(() => setBuscando(false));
    }, 350);
    return () => clearTimeout(timer);
  }, [busca, open]);

  const fechar = () => {
    setOpen(false);
    setBusca("");
    setResultados(null);
  };

  const btnClass = cn("icon-btn", className);

  // Sem módulo mapeado: o "?" leva direto à Central de Ajuda
  if (!moduleKey) {
    return (
      <Link
        to="/ajuda"
        className={btnClass}
        aria-label="Central de Ajuda"
        title="Central de Ajuda"
      >
        <HelpCircle className="h-4 w-4" />
      </Link>
    );
  }

  const tituloModulo = tituloHumano(moduleKey);
  const exibidos = resultados ?? topicos;
  const carregando = loading || buscando;
  const emBusca = resultados !== null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={btnClass}
        aria-label={`Ajuda — ${tituloModulo}`}
        title={`Ajuda — ${tituloModulo}`}
      >
        <HelpCircle className="h-4 w-4" />
      </button>

      <Drawer
        open={open}
        onClose={fechar}
        title={`Ajuda — ${tituloModulo}`}
        width="md"
        footer={<LinkCentralAjuda onClick={fechar} />}
      >
        <div className="mb-4">
          <SearchBar
            value={busca}
            onChange={setBusca}
            placeholder="Buscar em toda a ajuda..."
          />
        </div>

        {carregando ? (
          <div className="space-y-4">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="card p-4"
              >
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="mt-3 h-3 w-full" />
                <Skeleton className="mt-2 h-3 w-5/6" />
              </div>
            ))}
          </div>
        ) : erro && !emBusca ? (
          <EmptyState
            icon={HelpCircle}
            title="Não foi possível carregar a ajuda deste módulo"
            message="Tente novamente mais tarde ou consulte a Central de Ajuda."
            action={<LinkCentralAjuda onClick={fechar} />}
          />
        ) : exibidos.length === 0 ? (
          <EmptyState
            icon={HelpCircle}
            title={
              emBusca
                ? "Nenhum tópico encontrado para a busca"
                : "Nenhum tópico de ajuda cadastrado para este módulo"
            }
            message="A Central de Ajuda reúne os tutoriais completos do sistema."
            action={<LinkCentralAjuda onClick={fechar} />}
          />
        ) : (
          <div className="space-y-4">
            {emBusca && (
              <p className="text-xs text-slate-500">
                {exibidos.length} tópico(s) encontrado(s) em toda a ajuda
              </p>
            )}
            {exibidos.map((t, i) => (
              <section
                key={t.id ?? `${t.titulo}-${i}`}
                className="card p-4"
              >
                <h3 className="mb-2 text-sm font-semibold text-slate-900">
                  {t.titulo}
                </h3>
                <Markdown
                  source={t.conteudo_md}
                  className="text-sm leading-relaxed text-slate-600"
                />
              </section>
            ))}
          </div>
        )}
      </Drawer>
    </>
  );
}
