import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router";
import {
  ArrowRight,
  CalendarClock,
  FileText,
  FolderOpen,
  Gavel,
  Scale,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useCaseContext } from "../stores/caseContext";

// Rotas /casos/:id/* ativam o modo caso; /casos/novo é o wizard (não é caso).
const CASE_ROUTE = /^\/casos\/([^/]+)/;

type CaseWorkflowStep = {
  label: string;
  tab?: string;
  hash?: string;
  external?: boolean;
  icon: LucideIcon;
};

const CASE_WORKFLOW: readonly CaseWorkflowStep[] = [
  { label: "Fatos", tab: "resumo", icon: FolderOpen },
  { label: "Provas", tab: "provas", icon: ShieldCheck },
  { label: "Teses", tab: "teses", icon: Scale },
  { label: "Estratégia", tab: "dossie", icon: Sparkles },
  { label: "Peça", tab: "pecas", icon: FileText },
  { label: "Revisão", tab: "pecas", hash: "#revisao", icon: Gavel },
  { label: "Ajuizamento", external: true, icon: Send },
];

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
 * Além de identificar o caso ativo, oferece o mesmo fluxo jurídico de sete
 * etapas usado no dashboard. As subabas detalhadas continuam no workspace, mas
 * deixam de ser a navegação primária. A próxima ação permanece visível em
 * qualquer superfície do caso, reforçando a pergunta operacional central:
 * "o que precisa ser feito agora?".
 */
export default function CaseContextBar() {
  const { pathname, search, hash } = useLocation();
  const caso = useCaseContext((state) => state.caso);
  const ativar = useCaseContext((state) => state.ativar);
  const sair = useCaseContext((state) => state.sair);
  const [pecas, setPecas] = useState<
    { id: string; status?: string; titulo?: string }[]
  >([]);

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

  useEffect(() => {
    if (!caso?.id) {
      setPecas([]);
      return;
    }
    let ativo = true;
    api
      .get("/legal-docs/", {
        params: { case_id: caso.id, page: 1, page_size: 50 },
      })
      .then((response) => {
        if (ativo) setPecas(asList(response.data));
      })
      .catch(() => {
        if (ativo) setPecas([]);
      });
    return () => {
      ativo = false;
    };
  }, [caso?.id]);

  if (!caso) return null;

  const baseCaso = `/casos/${caso.id}`;
  const rotaRaizDoCaso = pathname === baseCaso || pathname === `${baseCaso}/`;
  const tabAtiva =
    new URLSearchParams(search).get("tab") || (rotaRaizDoCaso ? "resumo" : "");
  const prazo = prazoCurto(caso.proxima_acao_prazo);
  const revisoesPendentes = pecas.filter((peca) =>
    ["em_revisao", "corrigida"].includes(peca.status ?? ""),
  ).length;
  const prontasAjuizamento = pecas.filter((peca) =>
    ["aprovada", "final"].includes(peca.status ?? ""),
  ).length;

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
          aria-label="Fluxo jurídico do caso"
          className="ejc-case-flow flex gap-1 overflow-x-auto pb-2 scrollbar-thin"
        >
          {CASE_WORKFLOW.map((item, index) => {
            const Icon = item.icon;
            const revisao = item.label === "Revisão";
            const ativo = item.external
              ? pathname === "/ajuizamento"
              : item.tab === "pecas"
                ? tabAtiva === "pecas" &&
                  (revisao ? hash === "#revisao" : hash !== "#revisao")
                : tabAtiva === item.tab;
            const destino = item.external
              ? `/ajuizamento?caso=${caso.id}`
              : `${baseCaso}?tab=${item.tab ?? "resumo"}${item.hash ?? ""}`;

            return (
              <Link
                key={item.label}
                to={destino}
                aria-current={ativo ? "step" : undefined}
                className={`ejc-case-flow__step ${ativo ? "is-active" : ""}`}
              >
                <small aria-hidden="true">
                  {item.label === "Revisão" && revisoesPendentes > 0
                    ? String(revisoesPendentes)
                    : item.label === "Ajuizamento" && prontasAjuizamento > 0
                      ? "✓"
                      : String(index + 1).padStart(2, "0")}
                </small>
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
