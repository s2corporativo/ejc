import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
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
  LibraryBig,
  Radar,
  RefreshCcw,
  ShieldAlert,
  Sparkles,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { Link, NavLink, useLocation } from "react-router";
import api from "../../lib/api";
import type { Case, Client, Deadline } from "../../types";
import { Empty, ErrorState, Spinner } from "../../components/UI";
import {
  HEALTH_AREAS,
  buildCompanySummaries,
  companyDisplayName,
  extractCollection,
  isBusinessCase,
  isCriticalCase,
  localIsoDate,
  nextCompanyDeadlines,
  type DptData,
} from "./model";

const NAV_ITEMS: Array<{ path: string; label: string; icon: LucideIcon }> = [
  { path: "/dpt360", label: "Visão Executiva", icon: Gauge },
  { path: "/dpt360/empresas", label: "Empresas", icon: Building2 },
  { path: "/dpt360/diagnostico", label: "Diagnóstico 360", icon: ClipboardCheck },
  { path: "/dpt360/radar", label: "Radar Jurídico", icon: Radar },
  { path: "/dpt360/inteligencia", label: "Inteligência Jurídica", icon: BrainCircuit },
  { path: "/dpt360/ferramentas", label: "Ferramentas", icon: Wrench },
  { path: "/dpt360/casos", label: "Casos", icon: Gavel },
  { path: "/dpt360/obrigacoes", label: "Obrigações", icon: CalendarClock },
  { path: "/dpt360/biblioteca", label: "Biblioteca", icon: LibraryBig },
  { path: "/dpt360/relatorios", label: "Relatórios", icon: BookOpen },
];

const EMPTY_DATA: DptData = {
  companies: [],
  cases: [],
  deadlines: [],
  degraded: [],
  truncated: [],
};

function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/40 ${className}`}
    >
      {children}
    </section>
  );
}

function Metric({ label, value, note }: { label: string; value: number | null; note?: string }) {
  return (
    <Card className="min-h-[132px]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">{label}</p>
      <div className="mt-4 text-3xl font-semibold tracking-tight text-slate-950 dark:text-white">
        {value === null ? "—" : value}
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
        {note || (value === null ? "Integração especializada ainda não ativada." : "Dados reais do EJC.")}
      </p>
    </Card>
  );
}

function companyMap(companies: Client[]) {
  return new Map(companies.map((company) => [company.id, company]));
}

function caseMap(cases: Case[]) {
  return new Map(cases.map((item) => [item.id, item]));
}

function formatDate(value?: string) {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-");
  if (!year || !month || !day) return value;
  return `${day}/${month}/${year}`;
}

function OperationalWarnings({ data }: { data: DptData }) {
  if (!data.degraded.length && !data.truncated.length) return null;
  return (
    <div className="mb-4 space-y-2">
      {data.degraded.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100">
          <strong>Visão parcialmente indisponível:</strong> {data.degraded.join(", ")}. Os demais blocos continuam usando somente dados confirmados.
        </div>
      )}
      {data.truncated.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300">
          <strong>Cobertura parcial:</strong> {data.truncated.join(", ")} possuem mais de 100 registros visíveis. Antes da produção definitiva, o dashboard deverá migrar para endpoint agregador paginado.
        </div>
      )}
    </div>
  );
}

function ExecutiveHome({ data }: { data: DptData }) {
  const companyById = useMemo(() => companyMap(data.companies), [data.companies]);
  const caseById = useMemo(() => caseMap(data.cases), [data.cases]);
  const upcoming = useMemo(() => nextCompanyDeadlines(data, 7), [data]);
  const businessCases = useMemo(
    () => data.cases.filter((item) => companyById.has(item.client_id) && isBusinessCase(item)),
    [data.cases, companyById],
  );
  const critical = businessCases.filter(isCriticalCase);

  const priorities = useMemo(() => {
    const today = localIsoDate();
    const deadlineItems = upcoming.map((deadline) => {
      const linkedCase = deadline.case_id ? caseById.get(deadline.case_id) : undefined;
      const company = linkedCase ? companyById.get(linkedCase.client_id) : undefined;
      const overdue = deadline.data_prazo < today || deadline.status === "vencido";
      const dueToday = !overdue && deadline.data_prazo === today;
      return {
        key: `deadline-${deadline.id}`,
        company: company ? companyDisplayName(company) : "Empresa da carteira",
        text: `${deadline.titulo} — ${formatDate(deadline.data_prazo)}`,
        tone: overdue ? "bg-red-600" : dueToday ? "bg-orange-500" : "bg-amber-400",
        href: linkedCase ? `/atividades?tipo=prazo&caso=${linkedCase.id}` : "/atividades?tipo=prazo",
      };
    });
    const caseItems = critical.map((item) => {
      const company = companyById.get(item.client_id);
      return {
        key: `case-${item.id}`,
        company: company ? companyDisplayName(company) : "Empresa da carteira",
        text: `${item.titulo} — sinal crítico em ${item.area}`,
        tone: item.prioridade === "critica" ? "bg-red-600" : "bg-orange-500",
        href: `/casos/${item.id}`,
      };
    });
    return [...deadlineItems, ...caseItems].slice(0, 7);
  }, [caseById, companyById, critical, upcoming]);

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-amber-700 dark:text-amber-300">Dashboard Executivo Empresarial</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">O que merece atenção jurídica hoje?</h2>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <Metric label="Empresas acompanhadas" value={data.companies.length} note="Clientes pessoa jurídica visíveis na sua carteira." />
        <Metric label="Riscos críticos" value={critical.length} note="Casos empresariais abertos com prioridade crítica ou risco alto registrado." />
        <Metric label="Providências próximas" value={upcoming.length} note="Prazos pendentes/vencidos ligados a casos empresariais até os próximos 7 dias." />
        <Metric label="Mudanças jurídicas hoje" value={null} note="Será conectado ao Radar DPT após a estabilização das fontes oficiais." />
        <Metric label="Empresas potencialmente impactadas" value={null} note="Depende do Motor de Impacto e do Perfil Jurídico Vivo." />
        <Metric label="Diagnósticos pendentes" value={null} note="Conceito ainda sem persistência própria confirmada; não é tratado como zero." />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_.85fr]">
        <Card>
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Prioridades</p>
              <h3 className="mt-1 font-semibold text-slate-950 dark:text-white">Sinais objetivos da carteira empresarial</h3>
            </div>
            <Link to="/atividades" className="text-xs font-semibold text-amber-700 hover:text-amber-800 dark:text-amber-300">Agenda completa</Link>
          </div>
          {priorities.length === 0 ? (
            <div className="mt-5 rounded-xl border border-dashed border-slate-200 px-4 py-7 text-sm text-slate-500 dark:border-white/10 dark:text-slate-400">
              Nenhum prazo próximo ou caso com sinal crítico foi encontrado nos dados disponíveis. Isso não equivale a regularidade jurídica.
            </div>
          ) : (
            <div className="mt-4 divide-y divide-slate-100 dark:divide-white/10">
              {priorities.map((item) => (
                <Link key={item.key} to={item.href} className="group flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                  <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${item.tone}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-slate-900 group-hover:text-amber-800 dark:text-slate-100 dark:group-hover:text-amber-300">{item.company}</span>
                    <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">{item.text}</span>
                  </span>
                  <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-slate-300 group-hover:text-amber-600" />
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
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Pergunta central à IA</p>
              <h3 className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">O que exige minha atenção hoje?</h3>
              <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
                O cruzamento DPT específico entre carteira, fontes, vigência, fatos e HITL será ligado somente após as frentes de RAG, fontes e crítica adversarial. Nesta onda, nenhuma análise autônoma é simulada.
              </p>
              <Link to="/inteligencia" className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-950">
                Abrir Pesquisa e IA <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Radar de Hoje</p>
            <h3 className="mt-1 font-semibold text-slate-950 dark:text-white">Inteligência regulatória por área</h3>
          </div>
          <Link to="/radar" className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700 dark:text-amber-300">Abrir radar atual <ChevronRight className="h-3.5 w-3.5" /></Link>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {["Tributário", "Ambiental", "Administrativo/Licitações", "Trabalhista", "LGPD/IA"].map((area) => (
            <div key={area} className="rounded-xl border border-slate-100 bg-slate-50/70 p-3 dark:border-white/10 dark:bg-white/[0.03]">
              <div className="text-sm font-medium text-slate-800 dark:text-slate-200">{area}</div>
              <div className="mt-2 text-xl font-semibold text-slate-400">—</div>
              <div className="mt-1 text-[11px] text-slate-400">Aguardando motor DPT de relevância e impacto.</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function CompaniesView({ data }: { data: DptData }) {
  const summaries = useMemo(() => buildCompanySummaries(data), [data]);
  if (!summaries.length) {
    return <Empty titulo="Nenhuma empresa na carteira visível" descricao="O DPT 360 utiliza Clientes pessoa jurídica já cadastrados no EJC. Nenhum cadastro paralelo será criado." />;
  }
  return (
    <Card>
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Empresas</p>
        <h2 className="mt-1 text-xl font-semibold text-slate-950 dark:text-white">Carteira empresarial</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400 dark:border-white/10">
            <tr><th className="px-3 py-3">Empresa</th><th className="px-3 py-3">Saúde jurídica</th><th className="px-3 py-3">Riscos</th><th className="px-3 py-3">Casos</th><th className="px-3 py-3">Pendências</th><th className="px-3 py-3" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-white/10">
            {summaries.map(({ company, cases, deadlines, criticalSignals }) => (
              <tr key={company.id}>
                <td className="px-3 py-4"><div className="font-semibold text-slate-900 dark:text-slate-100">{companyDisplayName(company)}</div><div className="mt-1 text-xs text-slate-400">{[company.cidade, company.estado].filter(Boolean).join(" / ") || "Localidade não informada"}</div></td>
                <td className="px-3 py-4"><span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300">Não avaliado</span></td>
                <td className="px-3 py-4 font-semibold text-slate-700 dark:text-slate-200">{criticalSignals}</td>
                <td className="px-3 py-4 text-slate-600 dark:text-slate-300">{cases.length}</td>
                <td className="px-3 py-4 text-slate-600 dark:text-slate-300">{deadlines.length}</td>
                <td className="px-3 py-4 text-right"><Link to={`/dpt360/empresas/${company.id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700 hover:text-amber-800 dark:text-amber-300">Empresa 360 <ChevronRight className="h-3.5 w-3.5" /></Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function CompanyDetail({ data, clientId }: { data: DptData; clientId: string }) {
  const summary = useMemo(() => buildCompanySummaries(data).find((item) => item.company.id === clientId), [clientId, data]);
  if (!summary) return <ErrorState message="Empresa não encontrada na carteira empresarial visível." />;
  const { company, cases, deadlines } = summary;
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">Empresa 360</p>
            <h2 className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">{companyDisplayName(company)}</h2>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{[company.cidade, company.estado].filter(Boolean).join(" / ") || "Localidade não informada"} · Perfil Jurídico Vivo será enriquecido progressivamente sem duplicar o cadastro de Cliente.</p>
          </div>
          <Link to={`/clientes/${company.id}`} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-amber-300 hover:text-amber-800 dark:border-white/10 dark:text-slate-200">Abrir cadastro canônico <ArrowRight className="h-3.5 w-3.5" /></Link>
        </div>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {HEALTH_AREAS.map((area) => (
          <Card key={area} className="p-4">
            <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{area}</div>
            <div className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Não avaliado</div>
            <div className="mt-2 text-xs leading-5 text-slate-400">Sem diagnóstico especializado aprovado e evidenciado.</div>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <div className="flex items-center justify-between"><h3 className="font-semibold text-slate-950 dark:text-white">Casos empresariais</h3><span className="text-xs text-slate-400">{cases.length}</span></div>
          {cases.length === 0 ? <p className="mt-4 text-sm text-slate-500">Nenhum caso empresarial relacionado foi encontrado.</p> : <div className="mt-3 divide-y divide-slate-100 dark:divide-white/10">{cases.slice(0, 8).map((item) => <Link key={item.id} to={`/casos/${item.id}`} className="flex items-center justify-between gap-3 py-3 text-sm"><span><span className="block font-medium text-slate-800 dark:text-slate-100">{item.titulo}</span><span className="mt-0.5 block text-xs text-slate-400">{item.area} · {item.status}</span></span><ChevronRight className="h-4 w-4 text-slate-300" /></Link>)}</div>}
        </Card>
        <Card>
          <div className="flex items-center justify-between"><h3 className="font-semibold text-slate-950 dark:text-white">Prazos e providências</h3><span className="text-xs text-slate-400">{deadlines.length}</span></div>
          {deadlines.length === 0 ? <p className="mt-4 text-sm text-slate-500">Nenhuma pendência temporal vinculada aos casos empresariais foi encontrada.</p> : <div className="mt-3 divide-y divide-slate-100 dark:divide-white/10">{deadlines.slice(0, 8).map((item) => <Link key={item.id} to={`/atividades?tipo=prazo&caso=${item.case_id || ""}`} className="flex items-center justify-between gap-3 py-3 text-sm"><span><span className="block font-medium text-slate-800 dark:text-slate-100">{item.titulo}</span><span className="mt-0.5 block text-xs text-slate-400">{formatDate(item.data_prazo)} · {item.status}</span></span><ChevronRight className="h-4 w-4 text-slate-300" /></Link>)}</div>}
        </Card>
      </div>
    </div>
  );
}

function CasesView({ data }: { data: DptData }) {
  const ids = useMemo(() => new Set(data.companies.map((company) => company.id)), [data.companies]);
  const names = useMemo(() => companyMap(data.companies), [data.companies]);
  const cases = data.cases.filter((item) => ids.has(item.client_id) && isBusinessCase(item));
  if (!cases.length) return <Empty titulo="Nenhum caso empresarial encontrado" descricao="A visão usa os Casos canônicos do EJC e filtra somente clientes pessoa jurídica e áreas empresariais relacionadas." />;
  return <Card><div className="mb-4"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Casos</p><h2 className="mt-1 text-xl font-semibold text-slate-950 dark:text-white">Visão empresarial dos Casos</h2></div><div className="space-y-2">{cases.map((item) => <Link key={item.id} to={`/casos/${item.id}`} className="flex flex-col gap-2 rounded-xl border border-slate-100 p-4 transition hover:border-amber-200 hover:bg-amber-50/30 dark:border-white/10 dark:hover:bg-white/[0.03] sm:flex-row sm:items-center sm:justify-between"><div><div className="font-semibold text-slate-900 dark:text-slate-100">{item.titulo}</div><div className="mt-1 text-xs text-slate-400">{names.get(item.client_id) ? companyDisplayName(names.get(item.client_id)!) : "Empresa"} · {item.area} · {item.status}</div></div><ChevronRight className="h-4 w-4 text-slate-300" /></Link>)}</div></Card>;
}

const PLANNED: Record<string, { title: string; text: string; href?: string; hrefLabel?: string; icon: LucideIcon }> = {
  diagnostico: { title: "Diagnóstico Jurídico Empresarial 360", text: "O fluxo fatos → evidências → questões → fontes → riscos → providências → HITL será persistido somente após auditoria do schema. Nesta onda não é criado diagnóstico fictício nem migration concorrente.", icon: ClipboardCheck },
  radar: { title: "Radar Jurídico DPT", text: "A camada de impacto por empresa dependerá das fontes oficiais, vigência e quarentena já em estabilização. O radar atual do EJC continua sendo a fonte operacional até esse acoplamento.", href: "/radar", hrefLabel: "Abrir Radar atual", icon: Radar },
  inteligencia: { title: "Inteligência Jurídica Empresarial", text: "O DPT reutilizará o núcleo central de IA. O Modo Conselho e a pergunta executiva serão adicionados como competências do orchestrator após HITL/citações/crítica adversarial estarem consolidados.", href: "/inteligencia", hrefLabel: "Abrir Pesquisa e IA", icon: BrainCircuit },
  ferramentas: { title: "Ferramentas Empresariais", text: "Os workspaces jurídicos continuam canônicos. O DPT 360 fará composição e atalhos, sem duplicar calculadoras ou analisadores já existentes.", href: "/areas-de-atuacao", hrefLabel: "Abrir Áreas de Atuação", icon: Wrench },
  obrigacoes: { title: "Agenda de Obrigações Empresariais", text: "Licenças, TACs, contratos, políticas e obrigações recorrentes podem exigir persistência própria. O modelo será criado somente se a auditoria confirmar que Prazos/Tarefas não atendem semanticamente ao conceito.", href: "/atividades", hrefLabel: "Abrir Agenda e Prazos", icon: CalendarClock },
  biblioteca: { title: "Biblioteca Empresarial", text: "Legislação, jurisprudência, teses internas, modelos e lições aprendidas continuarão no Conhecimento canônico, com segregação entre conteúdo público, escritório, cliente e caso.", href: "/inteligencia?tab=conhecimento", hrefLabel: "Abrir Conhecimento", icon: LibraryBig },
  relatorios: { title: "Relatórios Executivos", text: "O relatório mensal será gerado como rascunho com atividades, riscos, prazos, mudanças relevantes e recomendações. Nenhum envio automático ao cliente será permitido sem revisão e aprovação humana.", icon: BookOpen },
};

function PlannedView({ name }: { name: string }) {
  const item = PLANNED[name] || PLANNED.diagnostico;
  const Icon = item.icon;
  return <Card className="min-h-[360px]"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-slate-950 text-amber-300 dark:bg-white/10"><Icon className="h-6 w-6" /></span><h2 className="mt-5 text-2xl font-semibold text-slate-950 dark:text-white">{item.title}</h2><p className="mt-3 max-w-3xl text-sm leading-7 text-slate-500 dark:text-slate-400">{item.text}</p><div className="mt-6 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-sm text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400"><strong className="text-slate-700 dark:text-slate-200">Estado da Onda 1:</strong> arquitetura reservada, sem dados simulados e sem novo schema.</div>{item.href && <Link to={item.href} className="mt-5 inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:border-amber-300 hover:text-amber-800 dark:border-white/10 dark:text-slate-200">{item.hrefLabel}<ArrowRight className="h-4 w-4" /></Link>}</Card>;
}

export default function Dpt360Workspace() {
  const location = useLocation();
  const [data, setData] = useState<DptData>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [fatal, setFatal] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFatal(false);
    const requests = [
      api.get("/clients/", { params: { page_size: 100 } }),
      api.get("/cases/", { params: { page_size: 100 } }),
      api.get("/deadlines/", { params: { page_size: 100 } }),
    ] as const;
    const [clientsResult, casesResult, deadlinesResult] = await Promise.allSettled(requests);
    const degraded: string[] = [];
    const truncated: string[] = [];

    let companies: Client[] = [];
    let cases: Case[] = [];
    let deadlines: Deadline[] = [];

    if (clientsResult.status === "fulfilled") {
      const collection = extractCollection<Client>(clientsResult.value.data);
      companies = collection.items.filter((item) => item.tipo === "PJ");
      if (collection.total > collection.items.length) truncated.push("Clientes");
    } else degraded.push("Clientes");

    if (casesResult.status === "fulfilled") {
      const collection = extractCollection<Case>(casesResult.value.data);
      cases = collection.items;
      if (collection.total > collection.items.length) truncated.push("Casos");
    } else degraded.push("Casos");

    if (deadlinesResult.status === "fulfilled") {
      const collection = extractCollection<Deadline>(deadlinesResult.value.data);
      deadlines = collection.items;
      if (collection.total > collection.items.length) truncated.push("Prazos");
    } else degraded.push("Prazos");

    if (degraded.length === 3) setFatal(true);
    setData({ companies, cases, deadlines, degraded, truncated });
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const segments = location.pathname.replace(/^\/dpt360\/?/, "").split("/").filter(Boolean);
  const view = segments[0] || "home";
  const companyId = view === "empresas" && segments[1] ? segments[1] : null;

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-4 pb-8">
      <div className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm dark:border-white/10 dark:bg-slate-950/50">
        <div className="border-b border-slate-100 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-800 px-5 py-5 text-white dark:border-white/10 sm:px-7">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <span className="grid h-12 w-12 place-items-center rounded-2xl border border-amber-300/20 bg-white/5 text-amber-300"><BriefcaseBusiness className="h-6 w-6" /></span>
              <div><p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-300">Inteligência Jurídica Empresarial</p><h1 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">DPT Empresarial 360</h1><p className="mt-1 text-xs text-slate-300">De Paula Teixeira Advogados · subaplicativo do EJC</p></div>
            </div>
            <button type="button" onClick={() => void load()} className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:bg-white/10"><RefreshCcw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />Atualizar</button>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto border-b border-slate-100 px-3 py-2 dark:border-white/10" aria-label="Navegação DPT Empresarial 360">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isDashboard = item.path === "/dpt360";
            return <NavLink key={item.path} to={item.path} end={isDashboard} className={({ isActive }) => `inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition ${isActive ? "bg-slate-950 text-white dark:bg-white dark:text-slate-950" : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.06] dark:hover:text-white"}`}><Icon className="h-3.5 w-3.5" />{item.label}</NavLink>;
          })}
        </nav>
      </div>

      <OperationalWarnings data={data} />

      {fatal ? (
        <ErrorState message="Não foi possível carregar Clientes, Casos e Prazos do EJC para o DPT 360." onRetry={() => void load()} />
      ) : loading ? (
        <div className="grid min-h-[320px] place-items-center"><Spinner /></div>
      ) : companyId ? (
        <CompanyDetail data={data} clientId={companyId} />
      ) : view === "home" ? (
        <ExecutiveHome data={data} />
      ) : view === "empresas" ? (
        <CompaniesView data={data} />
      ) : view === "casos" ? (
        <CasesView data={data} />
      ) : (
        <PlannedView name={view} />
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 dark:border-white/10 dark:bg-slate-950/40"><div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100"><Building2 className="h-4 w-4 text-amber-600" />DPT Legal Twin</div><p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">Arquitetura prevista para representar empresa, contratos, obrigações, licenças, dados, riscos, eventos e fontes aplicáveis sem duplicar os registros canônicos.</p></div>
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 dark:border-white/10 dark:bg-slate-950/40"><div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100"><ShieldAlert className="h-4 w-4 text-amber-600" />Pré-flight jurídico</div><p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">Planejado para detectar fatos sem prova, citações não confirmadas, vigência duvidosa, datas conflitantes e divergências entre peça e cadastro.</p></div>
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 dark:border-white/10 dark:bg-slate-950/40"><div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100"><Sparkles className="h-4 w-4 text-amber-600" />Modo Conselho Jurídico</div><p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">Camada executiva futura para priorizar riscos e providências com base em evidências, fontes e decisão humana.</p></div>
        <div className="rounded-2xl border border-slate-200/80 bg-white p-4 dark:border-white/10 dark:bg-slate-950/40"><div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100"><FileSearch className="h-4 w-4 text-amber-600" />Memória do escritório</div><p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">Decisões profissionais aprovadas serão versionadas no conhecimento interno; nenhuma preferência será inferida como regra sem aprovação.</p></div>
      </div>
    </div>
  );
}
