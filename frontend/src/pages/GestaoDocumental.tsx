import { useSearchParams } from "react-router-dom";
import { FolderOpen, Lock } from "lucide-react";
import Documentos from "./Documentos";
import DataRoom from "./DataRoom";
import ErrorBoundary from "../components/ErrorBoundary";
import { PageHeader } from "../components/UI";

const TABS = [
  { k: "docs", label: "Documentos", icon: FolderOpen },
  { k: "dataroom", label: "Data Room", icon: Lock },
] as const;

type Tab = (typeof TABS)[number]["k"];

export default function GestaoDocumental() {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("tab");
  const tab: Tab = raw === "dataroom" ? "dataroom" : "docs";

  const selectTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  return (
    <div>
      <PageHeader
        title="Gestão Documental"
        subtitle="Documentos internos e Data Room com segregação de acesso."
      />
      <div className="flex w-fit gap-1 rounded-xl bg-slate-100 p-1 mb-5">
        {TABS.map(({ k, label, icon: Icon }) => (
          <button
            key={k}
            onClick={() => selectTab(k)}
            className={`flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium rounded-lg transition-all ${
              tab === k
                ? "bg-white text-navy shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>
      <ErrorBoundary key={tab}>
        {tab === "docs" ? <Documentos /> : <DataRoom />}
      </ErrorBoundary>
    </div>
  );
}
