import { useState } from "react";
import { Navigate, useSearchParams } from "react-router";
import {
  BarChart3,
  Wallet,
  TrendingDown,
  FileText,
  Building2,
  Calculator,
  Calendar,
  Receipt,
  MoreHorizontal,
  ChevronDown,
} from "lucide-react";
import FinanceiroDashboard from "./FinanceiroDashboard";
import Honorarios from "./Honorarios";
import NotasFiscais from "./NotasFiscais";
import Despesas from "./Despesas";
import DespesasRecorrentes from "./DespesasRecorrentes";
import OfficeContracts from "./OfficeContracts";
import ErrorBoundary from "../components/ErrorBoundary";
import { PageHeader } from "../components/UI";
import { useAuth } from "../stores/auth";

const TABS = [
  { k: "visao", label: "Visão geral", icon: BarChart3 },
  { k: "honorarios", label: "Recebimentos", icon: Wallet },
  { k: "despesas", label: "Despesas", icon: TrendingDown },
  { k: "nfse", label: "Notas fiscais (NFS-e)", icon: Receipt },
  { k: "contratos", label: "Contratos do escritório", icon: FileText },
  { k: "recorrentes", label: "Despesas recorrentes", icon: MoreHorizontal },
  // Deep-links históricos: não aparecem mais no menu Financeiro.
  { k: "societaria", label: "Sociedade", icon: Building2 },
  { k: "estimador", label: "Estimador de honorários", icon: Calculator },
] as const;

const PRINCIPAIS: ReadonlySet<FinanceTab> = new Set([
  "visao",
  "honorarios",
  "despesas",
]);
const MAIS: ReadonlyArray<FinanceTab> = ["nfse", "contratos"];
const SOCIEDADE_ROLES = new Set(["superadmin", "admin", "socio"]);

export type FinanceTab = (typeof TABS)[number]["k"];

export const isFinanceTab = (value: string | null): value is FinanceTab =>
  TABS.some((tab) => tab.k === value);

export const isCompetencia = (value: string | null): value is string =>
  !!value && /^\d{4}-(0[1-9]|1[0-2])$/.test(value);

export function competenciaAtual(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function nextFinanceParams(
  current: URLSearchParams,
  next: FinanceTab,
  extra?: Record<string, string>,
): URLSearchParams {
  const params = new URLSearchParams(current);
  params.set("tab", next);
  if (next !== "societaria") params.delete("sub");
  params.delete("status");
  if (extra) {
    for (const [k, v] of Object.entries(extra)) params.set(k, v);
  }
  return params;
}

const TABS_COM_COMPETENCIA: ReadonlySet<FinanceTab> = new Set([
  "visao",
  "despesas",
]);

export default function FinanceiroWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [maisAberto, setMaisAberto] = useState(false);
  const user = useAuth((s) => s.user);
  const podeSociedade = SOCIEDADE_ROLES.has(user?.role ?? "");

  const raw = searchParams.get("tab");
  const tabSolicitada: FinanceTab = isFinanceTab(raw) ? raw : "visao";

  if (tabSolicitada === "societaria" && podeSociedade) {
    const sub = searchParams.get("sub");
    const destino = sub
      ? `/gestao-escritorio/sociedade?sub=${encodeURIComponent(sub)}`
      : "/gestao-escritorio/sociedade";
    return <Navigate to={destino} replace />;
  }
  if (tabSolicitada === "estimador") {
    return <Navigate to="/inteligencia?tab=honorarios" replace />;
  }

  const tab: FinanceTab =
    tabSolicitada === "societaria" && !podeSociedade
      ? "visao"
      : tabSolicitada;
  const rawComp = searchParams.get("comp");
  const competencia = isCompetencia(rawComp) ? rawComp : competenciaAtual();
  const mostraCompetencia = TABS_COM_COMPETENCIA.has(tab);

  const setTab = (next: FinanceTab, extra?: Record<string, string>) => {
    setMaisAberto(false);
    setSearchParams(nextFinanceParams(searchParams, next, extra), {
      replace: true,
    });
  };

  const setCompetencia = (value: string) => {
    const params = new URLSearchParams(searchParams);
    if (isCompetencia(value)) params.set("comp", value);
    else params.delete("comp");
    setSearchParams(params, { replace: true });
  };

  const principais = TABS.filter((item) => PRINCIPAIS.has(item.k));
  const extras = TABS.filter((item) => MAIS.includes(item.k));

  return (
    <div className="executive-workspace space-y-5">
      <PageHeader
        eyebrow="Gestão financeira"
        title="Financeiro"
        subtitle="Receber, pagar e acompanhar o caixa do escritório em um único fluxo operacional."
        actions={
          mostraCompetencia ? (
            <label className="input flex w-auto items-center gap-2 py-1.5">
              <Calendar className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-medium text-slate-500">
                Competência
              </span>
              <input
                type="month"
                aria-label="Competência financeira"
                className="text-sm text-slate-700 outline-none bg-transparent"
                value={competencia}
                onChange={(e) => setCompetencia(e.target.value)}
              />
            </label>
          ) : undefined
        }
      />

      <div className="flex items-center gap-2 overflow-visible">
        <div className="flex w-fit gap-1 rounded-xl bg-slate-900/[0.05] p-1 dark:bg-white/[0.07]">
          {principais.map(({ k, label, icon: Icon }) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`flex h-9 items-center gap-1.5 whitespace-nowrap rounded-lg px-4 text-sm font-medium transition-all ${
                tab === k
                  ? "bg-primary-600 text-white shadow-sm shadow-primary-600/20"
                  : "text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              }`}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>

        <div className="relative">
          <button
            type="button"
            onClick={() => setMaisAberto((v) => !v)}
            className={`flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium transition-all ${
              MAIS.includes(tab)
                ? "bg-slate-800 text-white"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            }`}
            aria-expanded={maisAberto}
          >
            Mais <ChevronDown size={14} />
          </button>
          {maisAberto && (
            <div className="absolute left-0 top-11 z-30 min-w-64 rounded-xl border border-slate-200 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900">
              {extras.map(({ k, label, icon: Icon }) => (
                <button
                  key={k}
                  onClick={() => setTab(k)}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/[0.06]"
                >
                  <Icon size={15} /> {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="min-w-0">
        <ErrorBoundary key={tab}>
          {tab === "visao" && (
            <FinanceiroDashboard
              competencia={competencia}
              onDrillDown={(destino, status) =>
                setTab(destino, status ? { status } : undefined)
              }
              onNavigate={(destino) => setTab(destino)}
            />
          )}
          {tab === "honorarios" && <Honorarios />}
          {tab === "despesas" && <Despesas competencia={competencia} />}
          {tab === "nfse" && <NotasFiscais />}
          {tab === "contratos" && <OfficeContracts />}
          {tab === "recorrentes" && <DespesasRecorrentes />}
        </ErrorBoundary>
      </div>
    </div>
  );
}
