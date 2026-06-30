import { useState } from "react";
import {
  Sparkles,
  Bot,
  Library,
  Scale,
  BookOpen,
  Activity,
  Cpu,
} from "lucide-react";
import AgenteIA from "./AgenteIA";
import IA from "./IA";
import AssistenteIA from "./AssistenteIA";
import ConteudoJuridico from "./ConteudoJuridico";
import Jurimetria from "./Jurimetria";
import Conhecimento from "./Conhecimento";
import DashboardIA from "./DashboardIA";
import { IANotice, PageHeader } from "../components/UI";

const TABS = [
  { k: "agente", label: "Agente Pro", icon: Cpu },
  { k: "assistente", label: "Assistente", icon: Bot },
  { k: "ia", label: "IA Jurídica", icon: Sparkles },
  { k: "conteudo", label: "FAQ & Glossário", icon: Library },
  { k: "jurimetria", label: "Jurimetria", icon: Scale },
  { k: "conhecimento", label: "Conhecimento", icon: BookOpen },
  { k: "saude", label: "Saúde da IA", icon: Activity },
] as const;

type Tab = (typeof TABS)[number]["k"];

export default function InteligenciaWorkspace() {
  const [tab, setTab] = useState<Tab>("agente");
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Inteligencia juridica"
        title="IA Juridica"
        subtitle="Agentes, assistente, jurimetria e base de conhecimento com foco em revisao humana e rastreabilidade."
      />
      <IANotice>
        Toda resposta de IA deve ser tratada como rascunho sujeito a revisao
        humana, conferencia de fontes e validacao juridica.
      </IANotice>
      <div className="overflow-x-auto">
        <div className="flex w-fit gap-1 rounded-xl border border-violet-100 bg-white/80 p-1 shadow-sm">
          {TABS.map(({ k, label, icon: Icon }) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`flex h-9 items-center gap-1.5 whitespace-nowrap rounded-lg px-4 text-sm font-medium transition-all ${
                tab === k
                  ? "bg-violet-600 text-white shadow-sm shadow-violet-600/20"
                  : "text-slate-500 hover:bg-violet-50 hover:text-violet-700"
              }`}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-w-0">
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
