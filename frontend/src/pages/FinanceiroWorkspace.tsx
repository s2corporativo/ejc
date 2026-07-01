import { useState } from "react";
import {
  BarChart3,
  Wallet,
  TrendingDown,
  FileText,
  Building2,
  Repeat,
  Calculator,
} from "lucide-react";
import FinanceiroDashboard from "./FinanceiroDashboard";
import Honorarios from "./Honorarios";
import Despesas from "./Despesas";
import DespesasRecorrentes from "./DespesasRecorrentes";
import OfficeContracts from "./OfficeContracts";
import Sociedade from "./Sociedade";
import EstimadorHonorarios from "../components/EstimadorHonorarios";
import ErrorBoundary from "../components/ErrorBoundary";
import { PageHeader } from "../components/UI";

const TABS = [
  { k: "visao", label: "Visão", icon: BarChart3 },
  { k: "honorarios", label: "Honorários", icon: Wallet },
  { k: "despesas", label: "Despesas", icon: TrendingDown },
  { k: "recorrentes", label: "Recorrentes", icon: Repeat },
  { k: "contratos", label: "Contratos", icon: FileText },
  { k: "societaria", label: "Societária", icon: Building2 },
  { k: "estimador", label: "Estimador OAB", icon: Calculator },
] as const;

type Tab = (typeof TABS)[number]["k"];

export default function FinanceiroWorkspace() {
  const [tab, setTab] = useState<Tab>("visao");
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Gestao financeira"
        title="Financeiro"
        subtitle="Receitas, despesas, honorarios, contratos e distribuicao societaria em uma visao operacional unica."
      />
      <div className="overflow-x-auto">
        <div className="flex w-fit gap-1 rounded-xl border border-slate-200 bg-white/80 p-1 shadow-sm">
          {TABS.map(({ k, label, icon: Icon }) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`flex h-9 items-center gap-1.5 whitespace-nowrap rounded-lg px-4 text-sm font-medium transition-all ${
                tab === k
                  ? "bg-blue-600 text-white shadow-sm shadow-blue-600/20"
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
          {tab === "visao" && <FinanceiroDashboard />}
          {tab === "honorarios" && <Honorarios />}
          {tab === "despesas" && <Despesas />}
          {tab === "recorrentes" && <DespesasRecorrentes />}
          {tab === "contratos" && <OfficeContracts />}
          {tab === "societaria" && <Sociedade />}
          {tab === "estimador" && <EstimadorHonorarios />}
        </ErrorBoundary>
      </div>
    </div>
  );
}
