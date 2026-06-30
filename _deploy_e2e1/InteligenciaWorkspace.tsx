import { useState } from "react";
import { Sparkles, Bot, Library, Scale, BookOpen, Activity, Cpu } from "lucide-react";
import AgenteIA from "./AgenteIA";
import IA from "./IA";
import AssistenteIA from "./AssistenteIA";
import ConteudoJuridico from "./ConteudoJuridico";
import Jurimetria from "./Jurimetria";
import Conhecimento from "./Conhecimento";
import DashboardIA from "./DashboardIA";

const TABS = [
  { k: "agente", label: "Agente Pro", icon: Cpu },
  { k: "assistente", label: "Assistente", icon: Bot },
  { k: "ia", label: "IA Jurídica", icon: Sparkles },
  { k: "conteudo", label: "FAQ & Glossário", icon: Library },
  { k: "jurimetria", label: "Jurimetria", icon: Scale },
  { k: "conhecimento", label: "Conhecimento", icon: BookOpen },
  { k: "saude", label: "Saúde da IA", icon: Activity },
] as const;

type Tab = typeof TABS[number]["k"];

export default function InteligenciaWorkspace() {
  const [tab, setTab] = useState<Tab>("agente");
  return (
    <div>
      <div className="pt-1 pb-4">
        <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit overflow-x-auto">
          {TABS.map(({ k, label, icon: Icon }) => (
            <button key={k} onClick={() => setTab(k)}
              className={`flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium rounded-lg whitespace-nowrap transition-all ${
                tab === k ? "bg-white text-navy shadow-sm" : "text-slate-500 hover:text-slate-700"
              }`}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
      </div>
      <div>
        {tab === "agente" && <AgenteIA />}
        {tab === "assistente" && <AssistenteIA />}
        {tab === "ia" && <IA />}
        {tab === "conteudo" && <ConteudoJuridico />}
        {tab === "jurimetria" && <Jurimetria />}
        {tab === "conhecimento" && <Conhecimento />}
        {tab === "saude" && <DashboardIA />}
      </div>
    </div>
  );
}
