import { lazy, Suspense, useMemo } from "react";
import { useSearchParams } from "react-router";
import {
  Sparkles,
  Bot,
  Library,
  Scale,
  BookOpen,
  Activity,
  SearchCheck,
  Wrench,
  AlertTriangle,
  Calculator,
  ShieldCheck,
} from "lucide-react";
import ErrorBoundary from "../components/ErrorBoundary";
import {
  AIFactualityLegend,
  IANotice,
  PageHeader,
  Spinner,
} from "../components/UI";
import { useAuth } from "../stores/auth";
import { MENSAGEM_IA_NAO_ATIVADA, useIaStatus } from "../lib/iaStatus";

// Code-splitting por aba (auditoria §2.6 #4): importar as páginas inteiras
// estaticamente anulava o lazy() do registry — tudo caía num chunk só.
// Uma aba renderiza por vez; cada página vira um chunk carregado sob demanda.
const AgenteIA = lazy(() => import("./AgenteIA"));
const IA = lazy(() => import("./IA"));
const AssistenteIA = lazy(() => import("./AssistenteIA"));
const FerramentasIA = lazy(() => import("./FerramentasIA"));
const PesquisaJuridica = lazy(() => import("./PesquisaJuridica"));
const Jurimetria = lazy(() => import("./Jurimetria"));
const ConhecimentoGovernado = lazy(() => import("./ConhecimentoGovernado"));
const DashboardIA = lazy(() => import("./DashboardIA"));
const GovernancaIA = lazy(() => import("./GovernancaIA"));
const EstimadorHonorarios = lazy(
  () => import("../components/EstimadorHonorarios"),
);

const GESTORES: readonly string[] = ["superadmin", "admin", "socio"];
const ADVOGADOS: readonly string[] = ["superadmin", "admin", "socio", "advogado"];

const TABS = [
  {
    k: "assistente",
    label: "Consultar a IA",
    icon: Bot,
    subs: [
      { k: "agente", label: "Análise aprofundada", icon: SearchCheck },
      { k: "rapido", label: "Pergunta rápida", icon: Bot },
    ],
  },
  {
    k: "producao",
    label: "Analisar e produzir",
    icon: Sparkles,
    subs: [
      { k: "analise", label: "Analisar ou revisar", icon: Sparkles },
      { k: "ferramentas", label: "Ferramentas especializadas", icon: Wrench },
    ],
  },
  {
    k: "honorarios",
    label: "Precificar honorários",
    icon: Calculator,
    roles: ADVOGADOS,
  },
  {
    k: "jurimetria",
    label: "Analisar dados e resultados",
    icon: Scale,
    roles: GESTORES,
  },
  {
    k: "conhecimento",
    label: "Conhecimento jurídico",
    icon: BookOpen,
    subs: [
      { k: "pesquisa", label: "Pesquisar e validar fontes", icon: Library },
      {
        k: "curadoria",
        label: "Administrar base de conhecimento",
        icon: BookOpen,
        roles: GESTORES,
      },
    ],
  },
  {
    k: "saude",
    label: "Estado da inteligência artificial",
    icon: Activity,
    roles: GESTORES,
    subs: [
      { k: "saude", label: "Saúde", icon: Activity },
      { k: "governanca", label: "Governança", icon: ShieldCheck },
    ],
  },
] as const;

type Tab = (typeof TABS)[number]["k"];

const LEGACY_TABS: Record<string, { tab: Tab; sub?: string }> = {
  agente: { tab: "assistente", sub: "agente" },
  ia: { tab: "producao", sub: "analise" },
  ferramentas: { tab: "producao", sub: "ferramentas" },
  conteudo: { tab: "conhecimento", sub: "pesquisa" },
  pesquisa: { tab: "conhecimento", sub: "pesquisa" },
  estimador: { tab: "honorarios" },
};

export function isInteligenciaTab(value: string | null): boolean {
  if (!value) return false;
  return (
    TABS.some((item) => item.k === value) ||
    Object.prototype.hasOwnProperty.call(LEGACY_TABS, value)
  );
}

export default function InteligenciaWorkspace() {
  const user = useAuth((state) => state.user);
  const { disponivel: iaDisponivel, mensagem: iaMensagem } = useIaStatus();
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

  const rawTab = searchParams.get("tab");
  const legacy = rawTab ? LEGACY_TABS[rawTab] : undefined;
  const resolvedTab = legacy?.tab ?? rawTab;
  const tab = availableTabs.some((item) => item.k === resolvedTab)
    ? (resolvedTab as Tab)
    : availableTabs[0].k;

  const tabDef = TABS.find((item) => item.k === tab);
  const allSubs = tabDef && "subs" in tabDef ? tabDef.subs : undefined;
  const subs = allSubs?.filter((item) => {
    const roles = (item as { roles?: readonly string[] }).roles;
    return !roles || Boolean(user?.role && roles.includes(user.role));
  });
  const rawSub = legacy?.sub ?? searchParams.get("sub");
  const sub =
    subs && subs.length > 0
      ? subs.some((item) => item.k === rawSub)
        ? (rawSub as string)
        : subs[0].k
      : null;

  const selectTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    params.delete("sub");
    setSearchParams(params, { replace: true });
  };

  const selectSub = (next: string) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", tab);
    params.set("sub", next);
    setSearchParams(params, { replace: true });
  };

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Inteligência jurídica"
        title="Inteligência Jurídica"
        subtitle="Pesquisa, análise, produção e precificação jurídica com fontes e revisão profissional."
      />

      {!iaDisponivel && (
        <div className="flex items-start gap-3 rounded-xl border border-warn-200 bg-warn-50 p-4 text-warn-900 dark:border-warn-500/30 dark:bg-warn-500/10 dark:text-warn-100">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <p className="font-semibold">Inteligência artificial não ativada</p>
            <p className="mt-1 text-sm">
              {iaMensagem || MENSAGEM_IA_NAO_ATIVADA} As calculadoras e
              validações determinísticas continuam disponíveis.
            </p>
          </div>
        </div>
      )}

      <IANotice>
        Toda resposta deve ser conferida quanto a fatos, documentos, valores,
        prazos, pedidos, citações e estratégia antes de qualquer uso jurídico.
      </IANotice>
      <AIFactualityLegend />

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

      {subs && subs.length > 0 && (
        <div className="overflow-x-auto">
          <div className="flex w-fit gap-1 rounded-lg border border-slate-200 bg-slate-50/80 p-1">
            {subs.map(({ k, label, icon: Icon }) => (
              <button
                key={k}
                onClick={() => selectSub(k)}
                className={`flex h-8 items-center gap-1.5 whitespace-nowrap rounded-md px-3 text-xs font-medium transition-all ${
                  sub === k
                    ? "bg-white text-ai-700 shadow-sm"
                    : "text-slate-500 hover:text-ai-700"
                }`}
              >
                <Icon size={13} /> {label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="min-w-0">
        <ErrorBoundary key={`${tab}-${sub ?? ""}`}>
          <Suspense
            fallback={
              <div className="flex justify-center py-16">
                <Spinner />
              </div>
            }
          >
            {tab === "assistente" && sub === "agente" && <AgenteIA />}
            {tab === "assistente" && sub === "rapido" && <AssistenteIA />}
            {tab === "producao" && sub === "analise" && <IA />}
            {tab === "producao" && sub === "ferramentas" && <FerramentasIA />}
            {tab === "honorarios" && <EstimadorHonorarios />}
            {tab === "jurimetria" && <Jurimetria />}
            {tab === "conhecimento" && sub === "pesquisa" && (
              <Conhecimento />
            )}
            {tab === "conhecimento" && sub === "curadoria" && (
              <ConhecimentoGovernado />
            )}
            {tab === "saude" && sub === "saude" && <DashboardIA />}
            {tab === "saude" && sub === "governanca" && <GovernancaIA />}
          </Suspense>
        </ErrorBoundary>
      </div>
    </div>
  );
}
