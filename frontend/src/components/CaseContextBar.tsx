import { useEffect, useMemo } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { ArrowRight, CalendarClock, FolderOpen, X } from "lucide-react";
import { CASE_NAV_SECTIONS } from "../config/caseNav";
import { useCaseContext } from "../stores/caseContext";

// Rotas /casos/:id/* ativam o modo caso; /casos/novo é a entrada histórica.
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
 * Contexto persistente do caso.
 *
 * Regra de simplificação: esta faixa NÃO replica a jornada jurídica. Ela mostra
 * apenas a identidade do caso, a próxima ação e as cinco áreas canônicas do
 * workspace. A inteligência e os estados derivados continuam no backend e na
 * Visão do caso; aqui o advogado navega por intenção, não pela arquitetura.
 */
export default function CaseContextBar() {
  const { pathname, search } = useLocation();
  const caso = useCaseContext((state) => state.caso);
  const ativar = useCaseContext((state) => state.ativar);
  const sair = useCaseContext((state) => state.sair);
  const navigate = useNavigate();

  const idContextual = useMemo(() => {
    const match = CASE_ROUTE.exec(pathname);
    if (match?.[1] && match[1] !== "novo") return match[1];
    if (pathname === "/ajuizamento") {
      return new URLSearchParams(search).get("caso");
    }
    return null;
  }, [pathname, search]);

  useEffect(() => {
    if (idContextual) void ativar(idContextual);
  }, [idContextual, ativar]);

  if (!caso) return null;

  const baseCaso = `/casos/${caso.id}`;
  const rotaRaizDoCaso = pathname === baseCaso || pathname === `${baseCaso}/`;
  const tabAtiva =
    new URLSearchParams(search).get("tab") || (rotaRaizDoCaso ? "resumo" : "");
  const prazo = prazoCurto(caso.proxima_acao_prazo);

  const secaoAtiva =
    CASE_NAV_SECTIONS.find((secao) => secao.tabs.includes(tabAtiva)) ??
    CASE_NAV_SECTIONS.find((secao) =>
      secao.routeAliases?.some((alias) => pathname.endsWith(alias)),
    ) ??
    (pathname === "/ajuizamento"
      ? CASE_NAV_SECTIONS.find((secao) => secao.label === "Documentos")
      : undefined);

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
            onClick={() => {
              sair();
              // Esta faixa é a única navegação entre as cinco áreas: sair do
              // modo caso sem sair da rota /casos/:id deixaria o workspace sem
              // seletor de área (a reativação só ocorre quando o id muda).
              if (CASE_ROUTE.test(pathname)) navigate("/casos");
            }}
            className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-primary-600 transition-colors hover:bg-primary-100 hover:text-primary-900"
            title="Sair do modo caso"
            aria-label="Sair do modo caso"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <nav
          aria-label="Áreas do caso"
          className="ejc-case-flow flex gap-1 overflow-x-auto pb-2 scrollbar-thin"
        >
          {CASE_NAV_SECTIONS.map((secao) => {
            const Icon = secao.icon;
            const ativo = secaoAtiva?.label === secao.label;
            return (
              <Link
                key={secao.label}
                to={`${baseCaso}?tab=${secao.tab}`}
                aria-current={ativo ? "page" : undefined}
                className={`ejc-case-flow__step ${ativo ? "is-active" : ""}`}
                title={secao.descricao}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{secao.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
