import { useSearchParams } from "react-router-dom";
import {
  BarChart3,
  Wallet,
  TrendingDown,
  FileText,
  Building2,
  Repeat,
  Calculator,
  Calendar,
  Receipt,
} from "lucide-react";
import FinanceiroDashboard from "./FinanceiroDashboard";
import Honorarios from "./Honorarios";
import NotasFiscais from "./NotasFiscais";
import Despesas from "./Despesas";
import DespesasRecorrentes from "./DespesasRecorrentes";
import OfficeContracts from "./OfficeContracts";
import Sociedade from "./Sociedade";
import EstimadorHonorarios from "../components/EstimadorHonorarios";
import ErrorBoundary from "../components/ErrorBoundary";
import { PageHeader } from "../components/UI";

const TABS = [
  { k: "visao", label: "Visão geral", icon: BarChart3 },
  { k: "honorarios", label: "Honorários e cobranças", icon: Wallet },
  { k: "nfse", label: "Notas fiscais (NFS-e)", icon: Receipt },
  { k: "despesas", label: "Despesas", icon: TrendingDown },
  { k: "recorrentes", label: "Despesas recorrentes", icon: Repeat },
  { k: "contratos", label: "Contratos do escritório", icon: FileText },
  { k: "societaria", label: "Sociedade", icon: Building2 },
  { k: "estimador", label: "Estimador OAB", icon: Calculator },
] as const;

export type FinanceTab = (typeof TABS)[number]["k"];

export const isFinanceTab = (value: string | null): value is FinanceTab =>
  TABS.some((tab) => tab.k === value);

/** Competência no formato AAAA-MM (mesmo formato do <input type="month">). */
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

// Só as telas que efetivamente consultam lançamentos por mês exibem o filtro.
const TABS_COM_COMPETENCIA: ReadonlySet<FinanceTab> = new Set([
  "visao",
  "despesas",
]);

export default function FinanceiroWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("tab");
  const tab: FinanceTab = isFinanceTab(raw) ? raw : "visao";
  const rawComp = searchParams.get("comp");
  const competencia = isCompetencia(rawComp) ? rawComp : competenciaAtual();
  const mostraCompetencia = TABS_COM_COMPETENCIA.has(tab);

  const setTab = (next: FinanceTab, extra?: Record<string, string>) =>
    setSearchParams(nextFinanceParams(searchParams, next, extra), {
      replace: true,
    });

  const setCompetencia = (value: string) => {
    const params = new URLSearchParams(searchParams);
    if (isCompetencia(value)) params.set("comp", value);
    else params.delete("comp");
    setSearchParams(params, { replace: true });
  };

  return (
    <div className="executive-workspace space-y-5">
      <PageHeader
        eyebrow="Gestão financeira"
        title="Financeiro"
        subtitle="Honorários, cobranças, despesas, contratos e administração da sociedade em uma visão operacional única."
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
      <div className="overflow-x-auto">
        <div className="flex w-fit gap-1 rounded-xl bg-slate-900/[0.05] p-1 dark:bg-white/[0.07]">
          {TABS.map(({ k, label, icon: Icon }) => (
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
      </div>
      <div className="min-w-0">
        <ErrorBoundary key={tab}>
          {tab === "visao" && (
            <FinanceiroDashboard
              competencia={competencia}
              onDrillDown={(destino, status) =>
                setTab(destino, status ? { status } : undefined)
              }
            />
          )}
          {tab === "honorarios" && <Honorarios />}
          {tab === "nfse" && <NotasFiscais />}
          {tab === "despesas" && <Despesas competencia={competencia} />}
          {tab === "recorrentes" && <DespesasRecorrentes />}
          {tab === "contratos" && <OfficeContracts />}
          {tab === "societaria" && <Sociedade />}
          {tab === "estimador" && <EstimadorHonorarios />}
        </ErrorBoundary>
      </div>
    </div>
  );
}
