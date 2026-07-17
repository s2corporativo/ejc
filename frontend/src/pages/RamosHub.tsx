import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Baby,
  Banknote,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  Car,
  Database,
  FileCheck2,
  FileSignature,
  Globe,
  Handshake,
  HardHat,
  HeartPulse,
  Home,
  Landmark,
  Leaf,
  Network,
  Receipt,
  Scale,
  Shield,
  Sprout,
  Stethoscope,
  UploadCloud,
  Users,
  Vote,
} from "lucide-react";
import api from "../lib/api";
import { RAMOS } from "./ramos/ramosConfig";
import {
  Badge,
  Button,
  Card,
  Page,
  PageActions,
  PageDescription,
  PageGrid,
  PageHeader,
  PageTitle,
} from "../components/ui";

type Area = {
  slug: string;
  nome: string;
  ordem?: number;
  ativo?: boolean;
};

type AreaVisual = {
  icon: typeof Scale;
  description: string;
  tone: string;
};

const VISUAL: Record<string, AreaVisual> = {
  empresarial: {
    icon: Building2,
    description: "Sociedades, contratos empresariais, recuperação e governança",
    tone: "from-primary-900/10 to-primary-900/0 text-primary-800",
  },
  societario: {
    icon: Network,
    description: "Constituição, alterações, sócios, governança e reorganizações",
    tone: "from-indigo-500/10 to-indigo-500/0 text-indigo-700",
  },
  contratual: {
    icon: FileSignature,
    description: "Elaboração, revisão, obrigações, riscos e inadimplemento",
    tone: "from-slate-700/10 to-slate-700/0 text-slate-700",
  },
  civil: {
    icon: Scale,
    description: "Obrigações, responsabilidade civil, danos e procedimentos comuns",
    tone: "from-slate-900/10 to-slate-900/0 text-slate-800",
  },
  criminal: {
    icon: Shield,
    description: "Defesa criminal, inquéritos, cautelares e recursos",
    tone: "from-danger-500/10 to-danger-500/0 text-danger-700",
  },
  trabalhista: {
    icon: HardHat,
    description: "Vínculo, verbas, audiência, recursos, liquidação e execução",
    tone: "from-yellow-500/10 to-yellow-500/0 text-yellow-700",
  },
  administrativo: {
    icon: Landmark,
    description: "Atos administrativos, servidores, sanções e processos públicos",
    tone: "from-ouro/10 to-ouro/0 text-ouro-profundo",
  },
  licitacoes: {
    icon: FileCheck2,
    description: "Editais, propostas, contratos, sanções e reequilíbrio econômico",
    tone: "from-amber-500/10 to-amber-500/0 text-amber-700",
  },
  bancario: {
    icon: Banknote,
    description: "Contratos bancários, CET, juros, cobranças e superendividamento",
    tone: "from-success-500/10 to-success-500/0 text-success-700",
  },
  tributario: {
    icon: Receipt,
    description: "Autos, lançamentos, execução fiscal, defesas e planejamento",
    tone: "from-orange-500/10 to-orange-500/0 text-orange-700",
  },
  ambiental: {
    icon: Leaf,
    description: "Licenciamento, autos, embargos, laudos e responsabilidades conexas",
    tone: "from-green-500/10 to-green-500/0 text-green-700",
  },
  agrario: {
    icon: Sprout,
    description: "Posse rural, contratos agrários, regularização e conflitos fundiários",
    tone: "from-lime-600/10 to-lime-600/0 text-lime-700",
  },
  agronegocio: {
    icon: BriefcaseBusiness,
    description: "Operações rurais, cadeias produtivas, crédito e contratos do agro",
    tone: "from-emerald-600/10 to-emerald-600/0 text-emerald-700",
  },
  consumidor: {
    icon: Users,
    description: "Cobranças, vícios, serviços, negativação e responsabilidade do fornecedor",
    tone: "from-teal-500/10 to-teal-500/0 text-teal-700",
  },
  familia: {
    icon: Baby,
    description: "Divórcio, união estável, guarda, convivência e alimentos",
    tone: "from-rose-500/10 to-rose-500/0 text-rose-700",
  },
  sucessoes: {
    icon: BookOpenCheck,
    description: "Inventário, testamento, herdeiros, bens e partilha",
    tone: "from-violet-500/10 to-violet-500/0 text-violet-700",
  },
  imobiliario: {
    icon: Home,
    description: "Locação, compra e venda, posse, usucapião e incorporação",
    tone: "from-stone-500/10 to-stone-500/0 text-stone-700",
  },
  previdenciario: {
    icon: Shield,
    description: "INSS, benefícios, CNIS, PPP, perícias e revisões",
    tone: "from-slate-500/10 to-slate-500/0 text-slate-700",
  },
  saude: {
    icon: HeartPulse,
    description: "Planos de saúde, SUS, tratamentos, negativas e tutelas urgentes",
    tone: "from-pink-500/10 to-pink-500/0 text-pink-700",
  },
  medico: {
    icon: Stethoscope,
    description: "Responsabilidade médica, prontuários, consentimento e perícia",
    tone: "from-cyan-500/10 to-cyan-500/0 text-cyan-700",
  },
  digital_lgpd: {
    icon: Database,
    description: "LGPD, incidentes, contratos digitais, provas e governança de dados",
    tone: "from-sky-600/10 to-sky-600/0 text-sky-700",
  },
  transito: {
    icon: Car,
    description: "Multas, defesa prévia, JARI, CETRAN, suspensão e cassação",
    tone: "from-blue-600/10 to-blue-600/0 text-blue-700",
  },
  constitucional: {
    icon: Scale,
    description: "Questões constitucionais, controle, repercussão geral e STF",
    tone: "from-purple-600/10 to-purple-600/0 text-purple-700",
  },
  eleitoral: {
    icon: Vote,
    description: "Eleições, candidaturas, propaganda, contas e contencioso eleitoral",
    tone: "from-fuchsia-600/10 to-fuchsia-600/0 text-fuchsia-700",
  },
  internacional: {
    icon: Globe,
    description: "Contratos internacionais, cooperação, tratados e comércio exterior",
    tone: "from-primary-900/10 to-primary-900/0 text-primary-800",
  },
};

const FALLBACK_AREAS: Area[] = [
  ["empresarial", "Direito Empresarial"],
  ["civil", "Direito Cível"],
  ["criminal", "Direito Penal"],
  ["trabalhista", "Direito Trabalhista"],
  ["administrativo", "Direito Administrativo"],
  ["licitacoes", "Licitações e Contratos Administrativos"],
  ["bancario", "Direito Bancário"],
  ["tributario", "Direito Tributário"],
  ["ambiental", "Direito Ambiental"],
  ["consumidor", "Direito do Consumidor"],
  ["familia", "Direito de Família"],
  ["sucessoes", "Direito das Sucessões"],
  ["imobiliario", "Direito Imobiliário"],
  ["previdenciario", "Direito Previdenciário"],
  ["saude", "Direito da Saúde"],
  ["medico", "Direito Médico"],
  ["digital_lgpd", "Direito Digital e LGPD"],
  ["transito", "Direito de Trânsito"],
  ["constitucional", "Direito Constitucional"],
  ["agrario", "Direito Agrário"],
  ["agronegocio", "Direito do Agronegócio"],
  ["eleitoral", "Direito Eleitoral"],
  ["internacional", "Direito Internacional"],
  ["contratual", "Direito Contratual"],
  ["societario", "Direito Societário"],
].map(([slug, nome], index) => ({ slug, nome, ordem: (index + 1) * 10 }));

export default function RamosHub() {
  const navigate = useNavigate();
  const [areas, setAreas] = useState<Area[]>(FALLBACK_AREAS);

  useEffect(() => {
    api
      .get("/areas")
      .then(({ data }) => {
        const list = Array.isArray(data) ? data : data?.areas;
        if (Array.isArray(list) && list.length) {
          setAreas(list.filter((area: Area) => area.ativo !== false));
        }
      })
      .catch(() => undefined);
  }, []);

  const ordered = useMemo(
    () => [...areas].sort((a, b) => (a.ordem || 999) - (b.ordem || 999)),
    [areas],
  );

  return (
    <Page className="surface-soft min-h-full px-6 py-8">
      <div className="mx-auto max-w-7xl space-y-8">
        <PageHeader className="rounded-[2rem] bg-white/70 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur dark:bg-white/[0.03]">
          <div>
            <Badge variant="gold" className="mb-3 gap-1">
              <Handshake className="h-3 w-3" /> Especializações da Central de Casos
            </Badge>
            <PageTitle>Áreas de Atuação</PageTitle>
            <PageDescription>
              As áreas funcionam como filtros e perfis de jornada. Selecione uma área para consultar os casos correspondentes ou iniciar uma importação inteligente.
            </PageDescription>
          </div>
          <PageActions>
            <Button variant="secondary" onClick={() => navigate("/casos")}>Todos os casos</Button>
            <Button onClick={() => navigate("/casos/novo?modo=documento")}>
              <UploadCloud className="h-4 w-4" /> Importar documento
            </Button>
          </PageActions>
        </PageHeader>

        <PageGrid className="grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {ordered.map((area) => {
            const visual = VISUAL[area.slug] || {
              icon: Scale,
              description: "Casos, documentos, jornadas e ferramentas pertinentes à área",
              tone: "from-slate-500/10 to-slate-500/0 text-slate-700",
            };
            const Icon = visual.icon;
            return (
              <Card key={area.slug} className="group relative h-full overflow-hidden p-5 transition duration-200 hover:-translate-y-1 hover:shadow-[0_26px_70px_rgba(15,23,42,0.14)]">
                <div className={`absolute inset-x-0 top-0 h-24 bg-gradient-to-b ${visual.tone}`} />
                <div className="relative flex h-full flex-col gap-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="grid h-11 w-11 place-items-center rounded-2xl bg-white/85 shadow-[0_10px_30px_rgba(15,23,42,0.08)] ring-1 ring-black/5 dark:bg-white/10">
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <span className="rounded-full bg-slate-950/5 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:bg-white/10 dark:text-slate-300">Área</span>
                  </div>
                  <div className="space-y-2">
                    <h2 className="text-base font-semibold text-slate-950 dark:text-slate-50">{area.nome}</h2>
                    <p className="text-sm leading-6 text-slate-500 dark:text-slate-300">{visual.description}</p>
                  </div>
                  <div className="mt-auto grid grid-cols-2 gap-2 pt-2">
                    <Button variant="secondary" size="sm" onClick={() => navigate(`/casos?area=${encodeURIComponent(area.slug)}`)}>Ver casos</Button>
                    <Button size="sm" onClick={() => navigate(`/casos/novo?modo=documento&area=${encodeURIComponent(area.slug)}`)}>
                      <UploadCloud className="h-3.5 w-3.5" /> Importar
                    </Button>
                    {RAMOS[area.slug] && (
                      <Button variant="secondary" size="sm" className="col-span-2" onClick={() => navigate(`/ramos/${area.slug}`)}>
                        <BookOpenCheck className="h-3.5 w-3.5" /> Abrir núcleo
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </PageGrid>
      </div>
    </Page>
  );
}
