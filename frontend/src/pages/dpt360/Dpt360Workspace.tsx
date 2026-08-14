import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  ArrowRight,
  BookOpen,
  BrainCircuit,
  BriefcaseBusiness,
  Building2,
  CalendarClock,
  ChevronRight,
  ClipboardCheck,
  FileSearch,
  Gavel,
  Gauge,
  Radar,
  RefreshCcw,
  ShieldAlert,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { Link, NavLink, useLocation, useNavigate } from "react-router";
import { Empty, ErrorState, Spinner } from "../../components/UI";
import {
  getDptCompanyProfile,
  getDptDashboard,
  type DptCompany,
  type DptDashboard,
} from "./api";
import CompanyLegalTwin from "./CompanyLegalTwin";
import DptFeatureRouter from "./DptFeatureRouter";

// Fase 4 (QA / refinamento): navegação reduzida de 10 para 8 itens. "Ferramentas"
// deixa de ser item de topo — as ferramentas continuam na Visão Executiva e no
// mais-ferramentas do escritório. "Biblioteca" volta ao Conhecimento canônico
// (/inteligencia?tab=conhecimento), conforme a regra de governança do
// DptFeatureRouter. Os caminhos removidos continuam resolvendo para o destino
// canônico, para não quebrar deep-links antigos.
const NAV_ITEMS: Array<{ path: string; label: string; icon: LucideIcon }> = [
  { path: "/dpt360", label: "Visão Executiva", icon: Gauge },
  { path: "/dpt360/empresas", label: "Empresas", icon: Building2 },
  {
    path: "/dpt360/diagnostico",
    label: "Diagnóstico 360",
    icon: ClipboardCheck,
  },
  { path: "/dpt360/radar", label: "Radar Jurídico", icon: Radar },
  {
    path: "/dpt360/inteligencia",
    label: "Inteligência Jurídica",
    icon: BrainCircuit,
  },
  { path: "/dpt360/casos", label: "Casos", icon: Gavel },
  { path: "/dpt360/obrigacoes", label: "Obrigações", icon: CalendarClock },
  { path: "/dpt360/relatorios", label: "Relatórios", icon: BookOpen },
];

// Deep-links legados da navegação anterior do DPT 360 → destino canônico.
const LEGACY_DPT360_REDIRECTS: Record<string, string> = {
  ferramentas: "/dpt360",
  biblioteca: "/inteligencia?tab=conhecimento",
};

// Redirect suave de deep-link legado: troca a URL para o destino canônico
// com um aviso discreto — mantém acessibilidade (o usuário vê para onde foi).
function DptLegacyRedirect({
  from,
  to,
}: {
  from: string;
  to: string;
  base?: string;
}) {
  const navigate = useNavigate();
  useEffect(() => {
    const handle = setTimeout(() => void navigate(to, { replace: true }), 600);
    return () => clearTimeout(handle);
  }, [to, navigate]);
  return (
    <div className="grid min-h-[240px] place-items-center rounded-2xl border border-dashed border-slate-300 p-8 text-center dark:border-white/15">
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Esta seção foi consolidada na nova navegação do DPT 360.
      </p>
      <p className="mt-2 text-xs text-slate-400">
        Abrindo <strong>“{from === "ferramentas" ? "Ferramentas → Visão Executiva" : "Biblioteca → Conhecimento"}“</strong>…
      </p>
      <Link
        to={to}
        className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white dark:bg-white dark:text-slate-950"
      >
        Abrir agora <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

const RADAR_AREAS = [
  { label: "Tributário", key: "tributario" },
  { label: "Ambiental", key: "ambiental" },
  { label: "Administrativo/Licitações", key: "administrativo" },
  { label: "Trabalhista", key: "trabalhista" },
  { label: "LGPD/IA", key: "lgpd_ia" },
] as const;

function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/40 ${className}`}
    >
      {children}
    </section>
  );
}

function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: number | null;
  note: string;
}) {
  return (
    <Card className="min-h-[132px]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
        {label}
      </p>
      <div className="mt-4 text-3xl font-semibold tracking-tight text-slate-950 dark:text-white">
        {value === null ? "—" : value}
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
        {note}
      </p>
    </Card>
  );
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-");
  return year && month && day ? `${day}/${month}/${year}` : value;
}

function ExecutiveHome({ data }: { data: DptDashboard }) {
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
          Dashboard Executivo Empresarial
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">
          O que merece atenção jurídica hoje?
        </h2>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <Metric
          label="Empresas acompanhadas"
          value={data.metrics.empresas_acompanhadas}
          note="Clientes pessoa jurídica dentro do seu escopo de acesso."
        />
        <Metric
          label="Riscos críticos"
          value={data.metrics.riscos_criticos}
          note="Sinais objetivos em casos abertos; não é score probabilístico."
        />
        <Metric
          label="Providências próximas"
          value={data.metrics.providencias_proximas}
          note="Prazos empresariais vencidos ou com vencimento em até sete dias."
        />
        <Metric
          label="Mudanças jurídicas hoje"
          value={data.metrics.mudancas_juridicas_hoje}
          note="Publicações reais coletadas nas últimas 24h; vigência requer confirmação."
        />
        <Metric
          label="Empresas potencialmente impactadas"
          value={data.metrics.empresas_potencialmente_impactadas}
          note="Possível impacto baseado em aderência objetiva; exige análise humana."
        />
        <Metric
          label="Diagnósticos pendentes"
          value={data.metrics.diagnosticos_pendentes}
          note="Permanece indisponível até existir persistência de diagnóstico compatível com a governança Alembic."
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_.85fr]">
        <Card>
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Prioridades
              </p>
              <h3 className="mt-1 font-semibold text-slate-950 dark:text-white">
                Sinais objetivos da carteira empresarial
              </h3>
            </div>
            <Link
              to="/atividades"
              className="text-xs font-semibold text-amber-700 dark:text-amber-300"
            >
              Agenda completa
            </Link>
          </div>
          {data.priorities.length === 0 ? (
            <div className="mt-5 rounded-xl border border-dashed border-slate-200 px-4 py-7 text-sm text-slate-500 dark:border-white/10 dark:text-slate-400">
              Nenhum sinal prioritário foi encontrado nos registros disponíveis.
              Isso não equivale a regularidade jurídica.
            </div>
          ) : (
            <div className="mt-4 divide-y divide-slate-100 dark:divide-white/10">
              {data.priorities.map((item) => (
                <Link
                  key={`${item.tipo}-${item.case_id}-${item.title}`}
                  to={item.canonical_path}
                  className="group flex items-start gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <span
                    className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${
                      item.nivel === "critico"
                        ? "bg-red-600"
                        : item.nivel === "alto"
                          ? "bg-orange-500"
                          : "bg-amber-400"
                    }`}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-slate-900 group-hover:text-amber-800 dark:text-slate-100 dark:group-hover:text-amber-300">
                      {item.company_name}
                    </span>
                    <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">
                      {item.title} — {item.detail}
                      {item.due_date ? ` · ${formatDate(item.due_date)}` : ""}
                    </span>
                  </span>
                  <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-slate-300" />
                </Link>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-slate-950 text-amber-300 dark:bg-white/10">
              <BrainCircuit className="h-5 w-5" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Pergunta central à IA
              </p>
              <h3 className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">
                O que exige minha atenção hoje?
              </h3>
              <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
                A resposta especializada usa o núcleo central de IA com RAG,
                citações e HITL. O dashboard não dispara comunicação nem altera
                casos automaticamente.
              </p>
              <Link
                to="/dpt360/inteligencia"
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white dark:bg-white dark:text-slate-950"
              >
                Abrir Modo Conselho <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
              Radar de Hoje
            </p>
            <h3 className="mt-1 font-semibold text-slate-950 dark:text-white">
              Inteligência regulatória por área
            </h3>
          </div>
          <Link
            to="/dpt360/radar"
            className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700 dark:text-amber-300"
          >
            Abrir Radar DPT <ChevronRight className="h-3.5 w-3.5" />
          </Link>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {RADAR_AREAS.map(({ label, key }) => {
            const hasRadar = data.radar_por_area != null;
            const value = hasRadar ? (data.radar_por_area?.[key] ?? 0) : null;
            return (
              <div
                key={key}
                className="rounded-xl border border-slate-100 bg-slate-50/70 p-3 dark:border-white/10 dark:bg-white/[0.03]"
              >
                <div className="text-sm font-medium text-slate-800 dark:text-slate-200">
                  {label}
                </div>
                <div className="mt-2 text-xl font-semibold text-slate-700 dark:text-slate-100">
                  {value === null ? "—" : value}
                </div>
                <div className="mt-1 text-[11px] text-slate-400">
                  Publicações classificadas nas últimas 24h; vigência requer
                  confirmação.
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

function CompaniesView({ data }: { data: DptDashboard }) {
  if (!data.companies.length) {
    return (
      <Empty
        titulo="Nenhuma empresa na carteira visível"
        descricao="O DPT 360 usa Clientes PJ canônicos do EJC; nenhum cadastro paralelo é criado."
      />
    );
  }
  return (
    <Card>
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
          Empresas
        </p>
        <h2 className="mt-1 text-xl font-semibold text-slate-950 dark:text-white">
          Carteira empresarial
        </h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-slate-100 text-[11px] uppercase tracking-wide text-slate-400 dark:border-white/10">
            <tr>
              <th className="px-3 py-3">Empresa</th>
              <th className="px-3 py-3">Saúde jurídica</th>
              <th className="px-3 py-3">Sinais</th>
              <th className="px-3 py-3">Casos</th>
              <th className="px-3 py-3">Providências</th>
              <th className="px-3 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-white/10">
            {data.companies.map((company) => (
              <tr key={company.id}>
                <td className="px-3 py-4">
                  <div className="font-semibold text-slate-900 dark:text-slate-100">
                    {company.nome}
                  </div>
                  <div className="mt-1 text-xs text-slate-400">
                    {[company.cidade, company.estado]
                      .filter(Boolean)
                      .join(" / ") || "Localidade não informada"}
                  </div>
                </td>
                <td className="px-3 py-4">
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300">
                    Não avaliado
                  </span>
                </td>
                <td className="px-3 py-4 font-semibold text-slate-700 dark:text-slate-200">
                  {company.sinais_criticos}
                </td>
                <td className="px-3 py-4 text-slate-600 dark:text-slate-300">
                  {company.casos}
                </td>
                <td className="px-3 py-4 text-slate-600 dark:text-slate-300">
                  {company.providencias_proximas}
                </td>
                <td className="px-3 py-4 text-right">
                  <Link
                    to={`/dpt360/empresas/${company.id}`}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700 dark:text-amber-300"
                  >
                    Empresa 360 <ChevronRight className="h-3.5 w-3.5" />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

type CompanyDetailHeader = Pick<DptCompany, "id" | "nome" | "cidade" | "estado">;

function CompanyDetail({
  data,
  company,
  possivelmenteFora,
}: {
  data: DptDashboard;
  company: CompanyDetailHeader;
  // true quando a empresa não estava no payload agregado do dashboard (veio
  // do fallback por ID): os casos/prazos abaixo, filtrados desse mesmo
  // payload, podem estar zerados só porque a empresa ficou fora do teto —
  // não porque ela realmente não tem casos/prazos.
  possivelmenteFora?: boolean;
}) {
  const cases = data.cases.filter((item) => item.client_id === company.id);
  const caseIds = new Set(cases.map((item) => item.id));
  const deadlines = data.deadlines.filter((item) => caseIds.has(item.case_id));
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">
              Empresa 360
            </p>
            <h2 className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">
              {company.nome}
            </h2>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              {[company.cidade, company.estado].filter(Boolean).join(" / ") ||
                "Localidade não informada"}{" "}
              · Perfil Jurídico Vivo derivado de registros canônicos.
            </p>
          </div>
          <Link
            to={`/clientes/${company.id}`}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 dark:border-white/10 dark:text-slate-200"
          >
            Abrir cadastro canônico <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </Card>
      {possivelmenteFora ? (
        <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs leading-5 text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-300">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Cobertura indisponível: esta empresa está fora do teto de itens do
          dashboard agregado. Casos e prazos abaixo podem aparecer zerados sem
          que isso signifique ausência real — confira pelo cadastro canônico.
        </div>
      ) : null}
      <CompanyLegalTwin clientId={company.id} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-950 dark:text-white">
              Casos empresariais
            </h3>
            <span className="text-xs text-slate-400">{cases.length}</span>
          </div>
          {cases.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">
              {possivelmenteFora
                ? "Cobertura indisponível: esta empresa está fora da amostra agregada do dashboard. Abra os casos pelo cadastro canônico."
                : "Nenhum caso empresarial relacionado foi encontrado."}
            </p>
          ) : (
            <div className="mt-3 divide-y divide-slate-100 dark:divide-white/10">
              {cases.slice(0, 8).map((item) => (
                <Link
                  key={item.id}
                  to={`/casos/${item.id}`}
                  className="flex items-center justify-between gap-3 py-3 text-sm"
                >
                  <span>
                    <span className="block font-medium text-slate-800 dark:text-slate-100">
                      {item.titulo}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-400">
                      {item.area} · {item.status}
                    </span>
                  </span>
                  <ChevronRight className="h-4 w-4 text-slate-300" />
                </Link>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-950 dark:text-white">
              Prazos e providências
            </h3>
            <span className="text-xs text-slate-400">{deadlines.length}</span>
          </div>
          {deadlines.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">
              {possivelmenteFora
                ? "Cobertura indisponível: esta empresa está fora da amostra agregada do dashboard. Abra os prazos pelo cadastro canônico."
                : "Nenhuma pendência temporal vinculada aos casos empresariais foi encontrada."}
            </p>
          ) : (
            <div className="mt-3 divide-y divide-slate-100 dark:divide-white/10">
              {deadlines.slice(0, 8).map((item) => (
                <Link
                  key={item.id}
                  to={`/atividades?tipo=prazo&caso=${item.case_id}`}
                  className="flex items-center justify-between gap-3 py-3 text-sm"
                >
                  <span>
                    <span className="block font-medium text-slate-800 dark:text-slate-100">
                      {item.titulo}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-400">
                      {formatDate(item.data_prazo)} · {item.status}
                    </span>
                  </span>
                  <ChevronRight className="h-4 w-4 text-slate-300" />
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

// A carteira do dashboard é limitada a um teto de empresas (payload agregado).
// Uma empresa fora desse teto ainda existe e responde em /companies/{id}; sem
// este fallback o deep link mentia "não encontrada" para qualquer empresa
// além do corte.
function CompanyDetailByIdFallback({
  data,
  clientId,
}: {
  data: DptDashboard;
  clientId: string;
}) {
  const [company, setCompany] = useState<CompanyDetailHeader | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setCompany(null);
    setNotFound(false);
    setLoadError(false);
    getDptCompanyProfile(clientId)
      .then((profile) => {
        if (!active) return;
        setCompany({
          id: profile.id,
          nome: profile.nome,
          cidade: profile.cidade,
          estado: profile.estado,
        });
      })
      .catch((err: unknown) => {
        if (!active) return;
        const status = (err as { response?: { status?: number } } | undefined)
          ?.response?.status;
        if (status === 404) {
          setNotFound(true);
        } else {
          setLoadError(true);
        }
      });
    return () => {
      active = false;
    };
  }, [clientId, attempt]);

  if (notFound) {
    return (
      <ErrorState message="Empresa não encontrada na carteira empresarial visível." />
    );
  }
  if (loadError) {
    return (
      <ErrorState
        message="Não foi possível consultar a empresa agora. Nenhuma conclusão foi presumida — tente novamente."
        onRetry={() => setAttempt((value) => value + 1)}
      />
    );
  }
  if (!company) {
    return (
      <div className="grid min-h-[240px] place-items-center">
        <Spinner />
      </div>
    );
  }
  return <CompanyDetail data={data} company={company} possivelmenteFora />;
}

function CasesView({ data }: { data: DptDashboard }) {
  const companies = useMemo(
    () => new Map(data.companies.map((item) => [item.id, item.nome])),
    [data.companies],
  );
  if (!data.cases.length) {
    return (
      <Empty
        titulo="Nenhum caso empresarial encontrado"
        descricao="A visão usa somente Casos canônicos e respeita o escopo de acesso do usuário."
      />
    );
  }
  return (
    <Card>
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
          Casos
        </p>
        <h2 className="mt-1 text-xl font-semibold text-slate-950 dark:text-white">
          Visão empresarial dos Casos
        </h2>
      </div>
      <div className="space-y-2">
        {data.cases.map((item) => (
          <Link
            key={item.id}
            to={`/casos/${item.id}`}
            className="flex flex-col gap-2 rounded-xl border border-slate-100 p-4 transition hover:border-amber-200 dark:border-white/10 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <div className="font-semibold text-slate-900 dark:text-slate-100">
                {item.titulo}
              </div>
              <div className="mt-1 text-xs text-slate-400">
                {companies.get(item.client_id) || "Empresa"} · {item.area} ·{" "}
                {item.status}
              </div>
            </div>
            <ChevronRight className="h-4 w-4 text-slate-300" />
          </Link>
        ))}
      </div>
    </Card>
  );
}

export default function Dpt360Workspace() {
  const location = useLocation();
  const [data, setData] = useState<DptDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setData(await getDptDashboard());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const relative = location.pathname.replace(/^\/dpt360\/?/, "");
  const segments = relative ? relative.split("/").filter(Boolean) : [];
  const company =
    segments[0] === "empresas" && segments[1] && data
      ? data.companies.find((item) => item.id === segments[1])
      : undefined;

  let content: ReactNode;
  if (loading) {
    content = (
      <div className="grid min-h-[360px] place-items-center">
        <Spinner />
      </div>
    );
  } else if (error || !data) {
    content = (
      <ErrorState message="Não foi possível carregar o DPT Empresarial 360. Nenhum dado foi inferido para substituir a fonte indisponível." />
    );
  } else if (segments.length === 0) {
    content = <ExecutiveHome data={data} />;
  } else if (segments[0] === "empresas" && segments.length === 1) {
    content = <CompaniesView data={data} />;
  } else if (segments[0] === "empresas" && segments[1]) {
    content = company ? (
      <CompanyDetail data={data} company={company} />
    ) : (
      <CompanyDetailByIdFallback data={data} clientId={segments[1]} />
    );
  } else if (segments[0] === "casos") {
    content = <CasesView data={data} />;
  } else if (segments[0] in LEGACY_DPT360_REDIRECTS) {
    // Deep-link legado da navegação antiga: retorna ao destino canônico em
    // vez de deixar a URL morta ou exibir página de erro.
    return (
      <div className="min-h-[360px]">
        <DptLegacyRedirect
          from={segments[0]}
          to={LEGACY_DPT360_REDIRECTS[segments[0]]}
          base="/dpt360"
        />
      </div>
    );
  } else {
    content = <DptFeatureRouter name={segments[0]} data={data} />;
  }

  return (
    <div className="min-h-full bg-slate-50/60 dark:bg-slate-950">
      <div className="border-b border-slate-200/80 bg-white/90 dark:border-white/10 dark:bg-slate-950/90">
        <div className="px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-2xl bg-slate-950 text-amber-300 dark:bg-white/10">
                <BriefcaseBusiness className="h-5 w-5" />
              </span>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-700 dark:text-amber-300">
                  De Paula Teixeira Advogados
                </p>
                <h1 className="text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
                  DPT Empresarial 360
                </h1>
                <p className="text-xs text-slate-400">
                  Inteligência Jurídica Empresarial
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {data?.coverage === "complete" && (
                <span className="hidden items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 sm:inline-flex">
                  <ShieldCheck className="h-3.5 w-3.5" /> Escopo completo
                </span>
              )}
              <button
                type="button"
                onClick={() => void load()}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-200"
              >
                <RefreshCcw className="h-3.5 w-3.5" /> Atualizar
              </button>
            </div>
          </div>
          <nav className="mt-4 flex gap-1 overflow-x-auto pb-1">
            {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
              <NavLink
                key={path}
                to={path}
                end={path === "/dpt360"}
                className={({ isActive }) =>
                  `inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition ${
                    isActive
                      ? "bg-slate-950 text-white dark:bg-white dark:text-slate-950"
                      : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-white"
                  }`
                }
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </div>
      <main className="px-4 py-5 sm:px-6 lg:px-8">
        {data?.notes?.length ? (
          <div className="mb-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs leading-5 text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400">
            {data.notes.join(" ")}
          </div>
        ) : null}
        {content}
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
              <Building2 className="h-4 w-4 text-amber-600" /> DPT Legal Twin
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
              Perfil Jurídico Vivo construído sobre dados canônicos, com
              histórico e evidências, sem segundo cadastro.
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
              <FileSearch className="h-4 w-4 text-amber-600" /> Pré-flight
              jurídico
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
              Fatos sem prova, vigência, citações e inconsistências são
              verificados antes de liberar entregáveis.
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
              <BrainCircuit className="h-4 w-4 text-amber-600" /> Modo Conselho
            </div>
            <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
              Perguntas executivas usam o contexto real da empresa e permanecem
              sob revisão humana.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
