import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/UI";
import {
  Building2,
  Scale,
  Lock,
  HardHat,
  Landmark,
  Banknote,
  Receipt,
  Leaf,
  Heart,
  Home,
  Users,
  Globe,
  Shield,
  Baby,
  Database,
  Car,
} from "lucide-react";

const RAMOS = [
  {
    slug: "empresarial",
    label: "Direito Empresarial",
    icon: Building2,
    color: "bg-primary-50 text-primary-700 border-primary-200",
    desc: "Contratos, fusões, M&A, recuperação judicial",
  },
  {
    slug: "civel",
    label: "Direito Cível",
    icon: Scale,
    color: "bg-ai-50 text-ai-700 border-ai-200",
    desc: "Contratos, danos, família, sucessões",
  },
  {
    slug: "penal",
    label: "Direito Penal",
    icon: Lock,
    color: "bg-danger-50 text-danger-700 border-danger-200",
    desc: "Defesa criminal, inquéritos, habeas corpus",
  },
  {
    slug: "trabalhista",
    label: "Direito Trabalhista",
    icon: HardHat,
    color: "bg-yellow-50 text-yellow-700 border-yellow-200",
    desc: "Reclamações, TST, FGTS, demissões",
  },
  {
    slug: "administrativo",
    label: "Direito Administrativo",
    icon: Landmark,
    color: "bg-cyan-50 text-cyan-700 border-cyan-200",
    desc: "Licitações, concessões, atos administrativos",
  },
  {
    slug: "bancario",
    label: "Direito Bancário",
    icon: Banknote,
    color: "bg-success-50 text-success-700 border-success-200",
    desc: "Contratos bancários, superendividamento",
  },
  {
    slug: "tributario",
    label: "Direito Tributário",
    icon: Receipt,
    color: "bg-orange-50 text-orange-700 border-orange-200",
    desc: "Planejamento fiscal, defesas, CARF",
  },
  {
    slug: "ambiental",
    label: "Direito Ambiental",
    icon: Leaf,
    color: "bg-green-50 text-green-700 border-green-200",
    desc: "Licenciamento, AIA, responsabilidade ambiental",
  },
  {
    slug: "saude",
    label: "Direito da Saúde",
    icon: Heart,
    color: "bg-pink-50 text-pink-700 border-pink-200",
    desc: "Planos, SUS, responsabilidade médica",
  },
  {
    slug: "imobiliario",
    label: "Direito Imobiliário",
    icon: Home,
    color: "bg-stone-50 text-stone-700 border-stone-200",
    desc: "Compra e venda, locação, incorporação",
  },
  {
    slug: "consumidor",
    label: "Direito do Consumidor",
    icon: Users,
    color: "bg-teal-50 text-teal-700 border-teal-200",
    desc: "CDC, recalls, práticas abusivas",
  },
  {
    slug: "internacional",
    label: "Direito Internacional",
    icon: Globe,
    color: "bg-primary-50 text-primary-700 border-primary-200",
    desc: "Tratados, arbitragem, comércio exterior",
  },
  {
    slug: "previdenciario",
    label: "Direito Previdenciário",
    icon: Shield,
    color: "bg-slate-50 text-slate-700 border-slate-200",
    desc: "INSS, aposentadorias, benefícios",
  },
  {
    slug: "familia",
    label: "Direito de Família",
    icon: Baby,
    color: "bg-rose-50 text-rose-700 border-rose-200",
    desc: "Divórcio, guarda, alimentos, inventário",
  },
  {
    slug: "digital_lgpd",
    label: "Direito Digital e LGPD",
    icon: Database,
    color: "bg-primary-50 text-primary-700 border-primary-200",
    desc: "LGPD, DPO, contratos SaaS, startups, dados",
  },
  {
    slug: "transito",
    label: "Direito de Tr\u00e2nsito",
    icon: Car,
    color: "bg-primary-50 text-primary-700 border-primary-200",
    desc: "Multas, recursos JARI/CETRAN, CNH, pontos",
  },
];

export default function RamosHub() {
  const navigate = useNavigate();
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <PageHeader
        title="Ramos do Direito"
        subtitle="Selecione uma área para acessar ferramentas, cálculos e casos especializados"
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {RAMOS.map((r) => {
          const Icon = r.icon;
          return (
            <button
              key={r.slug}
              onClick={() => navigate(`/ramos/${r.slug}`)}
              className={`flex flex-col items-start gap-3 p-4 rounded-xl border-2 hover:shadow-md transition-all text-left ${r.color}`}
            >
              <div className="p-2 rounded-lg bg-white/60">
                <Icon className="w-5 h-5" />
              </div>
              <div>
                <div className="font-semibold text-sm">{r.label}</div>
                <div className="text-xs opacity-70 mt-0.5 leading-snug">
                  {r.desc}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
