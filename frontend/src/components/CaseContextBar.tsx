import { useEffect } from "react";
import { Link, useLocation } from "react-router";
import { ArrowRight, CalendarClock, FolderOpen, X } from "lucide-react";
import { CASE_NAV_SECTIONS } from "../config/caseNav";
import { useCaseContext } from "../stores/caseContext";

// Rotas /casos/:id/* ativam o modo caso; /casos/novo é o wizard (não é caso).
const CASE_ROUTE = /^\/casos\/([^/]+)/;

function prazoCurto(valor?: string): string | null {
  if (!valor) return null;
  const data = new Date(valor);
  if (Number.isNaN(data.getTime())) return null;
  return data.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/**
 * Faixa persistente do "Modo Caso".
 *
 * Além de identificar o caso ativo, oferece cinco destinos canônicos para que o
 * usuário não precise conhecer as dezenas de subabas do workspace. A próxima
 * ação permanece visível em qualquer superfície do caso, reforçando a pergunta
 * operacional central: "o que precisa ser feito agora?".
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

  const baseCaso = `/casos/${caso.id}`;
  const rotaRaizDoCaso = pathname === baseCaso || pathname === `${baseCaso}/`;
  const tabAtiva =
    new URLSearchParams(search).get("tab") || (rotaRaizDoCaso ? "resumo" : "");
  const prazo = prazoCurto(caso.proxima_acao_prazo);

  return (
    <div className="border-b border-primary-200/60 bg-primary-50/95">
      <div className="px-4 md:px-7">
        <div className="flex min-h-10 items-center gap-2 py-1.5 text-xs">
          <FolderOpen
            className="h-3.5 w-3.5 shrink-0 text-primary-700"
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <Link
              to={baseCaso}
              className="block min-w-0 truncate font-medium text-primary-900 hover:underline"
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
            {caso.proxima_acao && (
              <Link
                to={`${baseCaso}?tab=resumo`}
                className="mt-0.5 flex min-w-0 items-center gap-1 text-[11px] text-primary-700 hover:text-primary-950"
                title={`Próxima ação: ${caso.proxima_acao}${prazo ? ` · ${prazo}` : ""}`}
              >
                <ArrowRight className="h-3 w-3 shrink-0" aria-hidden="true" />
                <span className="shrink-0 font-semibold">Próxima:</span>
                <span className="truncate">{caso.proxima_acao}</span>
                {prazo && (
                  <span className="ml-1 inline-flex shrink-0 items-center gap-1 text-primary-600">
                    <CalendarClock className="h-3 w-3" aria-hidden="true" />
                    {prazo}
                  </span>
                )}
              </Link>
            )}
          </div>
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
          {CASE_NAV_SECTIONS.map((item) => {
            const Icon = item.icon;
            const ativaPorTab = item.tabs.includes(tabAtiva);
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
