import { useState } from "react";
import { FolderOpen, Lock } from "lucide-react";
import Documentos from "./Documentos";
import DataRoom from "./DataRoom";

const TABS = [
  { k: "docs", label: "Documentos", icon: FolderOpen },
  { k: "dataroom", label: "Data Room", icon: Lock },
] as const;

export default function GestaoDocumental() {
  const [tab, setTab] = useState<"docs" | "dataroom">("docs");
  return (
    <div>
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit mb-5">
        {TABS.map(({ k, label, icon: Icon }) => (
          <button
            key={k}
            onClick={() => setTab(k)}
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
      {tab === "docs" ? <Documentos /> : <DataRoom />}
    </div>
  );
}
