import { useNavigate } from "react-router-dom";
import {
  Baby,
  Banknote,
  Building2,
  Car,
  Database,
  Globe,
  HardHat,
  Heart,
  Home,
  Landmark,
  Leaf,
  Lock,
  Receipt,
  Scale,
  Shield,
  Sparkles,
  Users,
} from "lucide-react";
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

const RAMOS = [
  {
    slug: "empresarial",
    label: "Direito Empresarial",
    icon: Building2,
    tone: "from-primary-900/10 to-primary-900/0 text-primary-800",
    desc: "Contratos, sociedades, M&A e recuperação judicial",
  },
  {
    slug: "civel",
    label: "Direito Cível",
    icon: Scale,
    tone: "from-slate-900/10 to-slate-900/0 text-slate-800",
    desc: "Contratos, danos, obrigações e responsabilidade civil",
  },
  {
    slug: "penal",
    label: "Direito Penal",
    icon: Lock,
    tone: "from-danger-500/10 to-danger-500/0 text-danger-700",
    desc: "Defesa criminal, inquéritos e medidas urgentes",
  },
  {
    slug: "trabalhista",
    label: "Direito Trabalhista",
    icon: HardHat,
    tone: "from-yellow-500/10 to-yellow-500/0 text-yellow-700",
    desc: "Reclamações, cálculos, FGTS, verbas e recursos",
  },
  {
    slug: "administrativo",
    label: "Direito Administrativo",
    icon: Landmark,
    tone: "from-ouro/10 to-ouro/0 text-ouro-profundo",
    desc: "Licitações, contratos públicos e atos administrativos",
  },
  {
    slug: "bancario",
    label: "Direito Bancário",
    icon: Banknote,
    tone: "from-success-500/10 to-success-500/0 text-success-700",
    desc: "Contratos bancários, juros e superendividamento",
  },
  {
    slug: "tributario",
    label: "Direito Tributário",
    icon: Receipt,
    tone: "from-orange-500/10 to-orange-500/0 text-orange-700",
    desc: "Planejamento, defesas, autos e contencioso fiscal",
  },
  {
    slug: "ambiental",
    label: "Direito Ambiental",
    icon: Leaf,
    tone: "from-green-500/10 to-green-500/0 text-green-700",
    desc: "Licenciamento, autos, AIA e responsabilidade ambiental",
  },
  {
    slug: "saude",
    label: "Direito da Saúde",
    icon: Heart,
    tone: "from-pink-500/10 to-pink-500/0 text-pink-700",
    desc: "Planos de saúde, SUS e responsabilidade médica",
  },
  {
    slug: "imobiliario",
    label: "Direito Imobiliário",
    icon: Home,
    tone: "from-stone-500/10 to-stone-500/0 text-stone-700",
    desc: "Compra e venda, locação, posse e incorporação",
  },
  {
    slug: "consumidor",
    label: "Direito do Consumidor",
    icon: Users,
    tone: "from-teal-500/10 to-teal-500/0 text-teal-700",
    desc: "CDC, práticas abusivas, cobranças e indenizações",
  },
  {
    slug: "internacional",
    label: "Direito Internacional",
    icon: Globe,
    tone: "from-primary-900/10 to-primary-900/0 text-primary-800",
    desc: "Tratados, arbitragem e comércio exterior",
  },
  {
    slug: "previdenciario",
    label: "Direito Previdenciário",
    icon: Shield,
    tone: "from-slate-500/10 to-slate-500/0 text-slate-700",
    desc: "INSS, aposentadorias, benefícios e revisões",
  },
  {
    slug: "familia",
    label: "Direito de Família",
    icon: Baby,
    tone: "from-rose-500/10 to-rose-500/0 text-rose-700",
    desc: "Divórcio, guarda, alimentos e inventário",
  },
  {
    slug: "digital_lgpd",
    label: "Direito Digital e LGPD",
    icon: Database,
    tone: "from-primary-900/10 to-primary-900/0 text-primary-800",
    desc: "LGPD, DPO, contratos SaaS, dados e tecnologia",
  },
  {
    slug: "transito",
    label: "Direito de Trânsito",
    icon: Car,
    tone: "from-primary-900/10 to-primary-900/0 text-primary-800",
    desc: "Multas, JARI/CETRAN, CNH e pontuação",
  },
];

export default function RamosHub() {
  const navigate = useNavigate();

  return (
    <Page className="surface-soft min-h-full px-6 py-8">
      <div className="mx-auto max-w-7xl space-y-8">
        <PageHeader className="rounded-[2rem] bg-white/70 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur dark:bg-white/[0.03]">
          <div>
            <Badge variant="gold" className="mb-3 gap-1">
              <Sparkles className="h-3 w-3" /> Áreas estratégicas
            </Badge>
            <PageTitle>Ramos do Direito</PageTitle>
            <PageDescription>
              Escolha uma área para acessar ferramentas especializadas, cálculos,
              guias, análises e fluxos jurídicos próprios do escritório.
            </PageDescription>
          </div>
          <PageActions>
            <Button variant="secondary" onClick={() => navigate("/casos")}>Casos</Button>
            <Button onClick={() => navigate("/ia")}>Abrir IA jurídica</Button>
          </PageActions>
        </PageHeader>

        <PageGrid className="grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {RAMOS.map((ramo) => {
            const Icon = ramo.icon;
            return (
              <button
                key={ramo.slug}
                onClick={() => navigate(`/ramos/${ramo.slug}`)}
                className="group text-left outline-none"
              >
                <Card className="relative h-full overflow-hidden p-5 transition duration-200 group-hover:-translate-y-1 group-hover:shadow-[0_26px_70px_rgba(15,23,42,0.14)]">
                  <div className={`absolute inset-x-0 top-0 h-24 bg-gradient-to-b ${ramo.tone}`} />
                  <div className="relative flex h-full flex-col gap-5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="grid h-11 w-11 place-items-center rounded-2xl bg-white/85 shadow-[0_10px_30px_rgba(15,23,42,0.08)] ring-1 ring-black/5 dark:bg-white/10">
                        <Icon className="h-5 w-5" />
                      </div>
                      <span className="rounded-full bg-slate-950/5 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:bg-white/10 dark:text-slate-300">
                        Núcleo
                      </span>
                    </div>

                    <div className="space-y-2">
                      <h2 className="text-base font-semibold text-slate-950 dark:text-slate-50">
                        {ramo.label}
                      </h2>
                      <p className="text-sm leading-6 text-slate-500 dark:text-slate-300">
                        {ramo.desc}
                      </p>
                    </div>

                    <div className="mt-auto flex items-center justify-between pt-2 text-xs font-medium text-primary-800 dark:text-primary-200">
                      <span>Acessar módulo</span>
                      <span className="transition-transform group-hover:translate-x-1">→</span>
                    </div>
                  </div>
                </Card>
              </button>
            );
          })}
        </PageGrid>
      </div>
    </Page>
  );
}
