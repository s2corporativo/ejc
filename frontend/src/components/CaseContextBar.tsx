import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Activity,
  FileStack,
  FolderOpen,
  LayoutDashboard,
  Scale,
  WalletCards,
  X,
} from "lucide-react";
import { useCaseContext } from "../stores/caseContext";

// Rotas /casos/:id/* ativam o modo caso; /casos/novo é o wizard (não é caso).
const CASE_ROUTE = /^\/casos\/([^/]+)/;

const CASE_NAV = [
  {
    label: "Visão",
    tab: "resumo",
    icon: LayoutDashboard,
    aliases: ["resumo", "orquestrador", "processos", "partes", "etiquetas"],
    routeAliases: ["/jornada", "/entrevista"],
  },
  {
    label: "Atividades",
    tab: "timeline",
    icon: Activity,
    aliases: ["timeline", "mensagens", "prazos", "audiencias", "checklists"],
  },
  {
    label: "Arquivos",
    tab: "documentos",
    icon: FileStack,
    aliases: ["documentos", "provas", "contratos", "procuracoes"],
  },
  {
    label: "Estratégia",
    tab: "teses",
    icon: Scale,
    aliases: [
      "teses",
      "teses-sugeridas",
      "jurisprudencia",
      "precedentes",
      "score",
      "risco",
      "memoria",
      "dossie",
      "iaDefensiva",
      "ferramentas",
    ],
    routeAliases: ["/sala-de-guerra"],
  },
  {
    label: "Financeiro",
    tab: "financeiro",
    icon: WalletCards,
    aliases: ["financeiro", "custos", "liquidez"],
  },
] as const;

/**
 * Faixa persistente do "Modo Caso".
 *
 * Além de identificar o caso ativo, oferece cinco destinos canônicos para que o
 * usuário não precise conhecer as dezenas de subabas do workspace. As telas
 * avançadas continuam acessíveis nas subabas internas; esta barra apenas reduz
 * o custo cognitivo da navegação principal.
 */
export default function CaseContextBar() {
  const { pathname, search } = useLocation();
  const caso = useCaseContext((state) => state.caso);
  const ativar = useCaseContext((state) => state.ativar);
  const sair = useCaseContext((state) => state.sair);

  useEffect(() => {
    const match = CASE_ROUTE.exec(pathname);
    const id = match?.[1];
    if (id && id !== "novo") void ativar(id);
  }, [pathname, ativar]);

  if (!caso) return null;

  const tabAtiva = new URLSearchParams(search).get("tab") || "resumo";
  const baseCaso = `/casos/${caso.id}`;

  return (
    <div className="border-b border-primary-200/60 bg-primary-50/95">
      <div className="px-4 md:px-7">
        <div className="flex h-9 items-center gap-2 text-xs">
          <FolderOpen
            className="h-3.5 w-3.5 shrink-0 text-primary-700"
            aria-hidden="true"
          />
          <Link
            to={baseCaso}
            className="min-w-0 truncate font-medium text-primary-900 hover:underline"
            title={
              caso.numero_processo
                ? `${caso.titulo} · Processo ${caso.numero_processo}`
                : caso.titulo
            }
          >
            {caso.titulo}
            {caso.cliente && (
              <span className="font-normal text-primary-700/80">
                {" — "}
                {caso.cliente}
              </span>
            )}
          </Link>
          <button
            type="button"
            onClick={sair}
            className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-primary-600 transition-colors hover:bg-primary-100 hover:text-primary-900"
            title="Sair do modo caso"
            aria-label="Sair do modo caso"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <nav
          aria-label="Navegação principal do caso"
          className="flex gap-1 overflow-x-auto pb-2 scrollbar-thin"
        >
          {CASE_NAV.map((item) => {
            const Icon = item.icon;
            const ativaPorTab = item.aliases.includes(tabAtiva as never);
            const ativaPorRota = item.routeAliases?.some((rota) =>
              pathname.startsWith(`${baseCaso}${rota}`),
            );
            const ativo = ativaPorTab || Boolean(ativaPorRota);

            return (
              <Link
                key={item.tab}
                to={`${baseCaso}?tab=${item.tab}`}
                aria-current={ativo ? "page" : undefined}
                className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-colors ${
                  ativo
                    ? "bg-primary-700 text-white shadow-sm"
                    : "text-primary-800 hover:bg-primary-100"
                }`}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
