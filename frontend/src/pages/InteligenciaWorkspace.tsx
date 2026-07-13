import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Sparkles,
  Bot,
  Library,
  Scale,
  BookOpen,
  Activity,
  Cpu,
  Wrench,
} from "lucide-react";
import AgenteIA from "./AgenteIA";
import IA from "./IA";
import AssistenteIA from "./AssistenteIA";
import FerramentasIA from "./FerramentasIA";
import ConteudoJuridico from "./ConteudoJuridico";
import Jurimetria from "./Jurimetria";
import Conhecimento from "./Conhecimento";
import DashboardIA from "./DashboardIA";
import ErrorBoundary from "../components/ErrorBoundary";
import { IANotice, PageHeader } from "../components/UI";
import { useAuth } from "../stores/auth";

const GESTORES: readonly string[] = ["superadmin", "admin", "socio"];

const TABS = [
  { k: "agente", label: "Agente Pro", icon: Cpu },
  { k: "assistente", label: "Assistente", icon: Bot },
  { k: "ia", label: "Análise e Validação", icon: Sparkles },
  { k: "ferramentas", label: "Ferramentas", icon: Wrench },
  { k: "conteudo", label: "FAQ & Glossário", icon: Library },
  { k: "jurimetria", label: "Jurimetria", icon: Scale },
  {
    k: "conhecimento",
    label: "Curadoria RAG",
    icon: BookOpen,
    roles: GESTORES,
  },
  {
    k: "saude",
    label: "Saúde da IA",
    icon: Activity,
    roles: GESTORES,
  },
] as const;

type Tab = (typeof TABS)[number]["k"];

export default function InteligenciaWorkspace() {
  const user = useAuth((state) => state.user);
  const [searchParams, setSearchParams] = useSearchParams();

  const availableTabs = useMemo(
    () =>
      TABS.filter(
        (tab) =>
          !("roles" in tab) ||
          Boolean(
            user?.role && (tab.roles as readonly string[]).includes(user.role),
          ),
      ),
    [user?.role],
  );

  const rawTab = searchParams.get("tab") as Tab | null;
  const tab = availableTabs.some((item) => item.k === rawTab)
    ? (rawTab as Tab)
    : availableTabs[0].k;

  const selectTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Inteligência jurídica"
        title="Inteligência Jurídica"
        subtitle="Agentes, análise, validação, jurimetria e conhecimento com revisão humana e rastreabilidade."
      />
      <IANotice>
        Toda resposta de IA deve ser conferida quanto a fatos, documentos,
        valores, prazos, pedidos, citações e estratégia antes de qualquer uso
        jurídico.
      </IANotice>
      <div className="overflow-x-auto">
        <div className="flex w-fit gap-1 rounded-xl border border-ai-100 bg-white/80 p-1 shadow-sm">
          {availableTabs.map(({ k, label, icon: Icon }) => (
            <button
              key={k}
              onClick={() => selectTab(k)}
              className={`flex h-9 items-center gap-1.5 whitespace-nowrap rounded-lg px-4 text-sm font-medium transition-all ${
                tab === k
                  ? "bg-ai-600 text-white shadow-sm shadow-ai-600/20"
                  : "text-slate-500 hover:bg-ai-50 hover:text-ai-700"
              }`}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-w-0">
        <ErrorBoundary key={tab}>
          {tab === "agente" && <AgenteIA />}
          {tab === "assistente" && <AssistenteIA />}
          {tab === "ia" && <IA />}
          {tab === "ferramentas" && <FerramentasIA />}
          {tab === "conteudo" && <ConteudoJuridico />}
          {tab === "jurimetria" && <Jurimetria />}
          {tab === "conhecimento" && <Conhecimento />}
          {tab === "saude" && <DashboardIA />}
        </ErrorBoundary>
      </div>
    </div>
  );
}
