import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import {
  Baby,
  Banknote,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  Car,
  ClipboardPen,
  Database,
  FileSignature,
  Globe,
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
  Wrench,
} from "lucide-react";
import api from "../lib/api";
import { ROLES } from "../config/moduleRegistry";
import { CANONICAL_ROUTES } from "../config/canonicalRoutes";
import { useAuth } from "../stores/auth";
import { RAMOS } from "./ramos/ramosConfig";
import { Badge, Button, Card, PageHeader } from "../components/UI";

// Área (taxonomia de casos) → slug do hub de ferramentas na rota canônica
// /areas-de-atuacao/<slug> (o alias legado /ramos/<slug> só redireciona).
// A maioria coincide; "civil" e "criminal" têm hubs com nome próprio.
const AREA_PARA_HUB: Record<string, string> = {
  civil: "civel",
  criminal: "penal",
};

/** Caminho do hub do ramo para uma área, ou null quando não há hub. */
export function hubDoRamo(areaSlug: string): string | null {
  const slug = AREA_PARA_HUB[areaSlug] ?? areaSlug;
  return RAMOS[slug] ? `${CANONICAL_ROUTES.areasAtuacao}/${slug}` : null;
}

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
    tone: "bg-primary-900 text-primary-800 dark:bg-primary-400",
  },
  societario: {
    icon: Network,
    description:
      "Constituição, alterações, sócios, governança e reorganizações",
    tone: "bg-indigo-500 text-indigo-700",
  },
  contratual: {
    icon: FileSignature,
    description: "Elaboração, revisão, obrigações, riscos e inadimplemento",
    tone: "bg-slate-700 text-slate-700 dark:bg-slate-400",
  },
  civil: {
    icon: Scale,
    description:
      "Obrigações, responsabilidade civil, danos e procedimentos comuns",
    tone: "bg-slate-900 text-slate-800 dark:bg-slate-400",
  },
  criminal: {
    icon: Shield,
    description: "Defesa criminal, inquéritos, cautelares e recursos",
    tone: "bg-danger-500 text-danger-700",
  },
  trabalhista: {
    icon: HardHat,
    description: "Vínculo, verbas, audiência, recursos, liquidação e execução",
    tone: "bg-yellow-500 text-yellow-700",
  },
  administrativo: {
    icon: Landmark,
    description:
      "Atos administrativos, servidores, sanções e processos públicos",
    tone: "bg-ouro text-ouro-profundo",
  },
  bancario: {
    icon: Banknote,
    description:
      "Contratos bancários, CET, juros, cobranças e superendividamento",
    tone: "bg-success-500 text-success-700",
  },
  tributario: {
    icon: Receipt,
    description: "Autos, lançamentos, execução fiscal, defesas e planejamento",
    tone: "bg-orange-500 text-orange-700",
  },
  ambiental: {
    icon: Leaf,
    description:
      "Licenciamento, autos, embargos, laudos e responsabilidades conexas",
    tone: "bg-green-500 text-green-700",
  },
  agrario: {
    icon: Sprout,
    description:
      "Posse rural, contratos agrários, regularização e conflitos fundiários",
    tone: "bg-lime-600 text-lime-700",
  },
  agronegocio: {
    icon: BriefcaseBusiness,
    description:
      "Operações rurais, cadeias produtivas, crédito e contratos do agro",
    tone: "bg-emerald-600 text-emerald-700",
  },
  consumidor: {
    icon: Users,
    description:
      "Cobranças, vícios, serviços, negativação e responsabilidade do fornecedor",
    tone: "bg-teal-500 text-teal-700",
  },
  familia: {
    icon: Baby,
    description: "Divórcio, união estável, guarda, convivência e alimentos",
    tone: "bg-rose-500 text-rose-700",
  },
  sucessoes: {
    icon: BookOpenCheck,
    description: "Inventário, testamento, herdeiros, bens e partilha",
    tone: "bg-violet-500 text-violet-700",
  },
  imobiliario: {
    icon: Home,
    description: "Locação, compra e venda, posse, usucapião e incorporação",
    tone: "bg-stone-500 text-stone-700",
  },
  previdenciario: {
    icon: Shield,
    description: "INSS, benefícios, CNIS, PPP, perícias e revisões",
    tone: "bg-slate-500 text-slate-700",
  },
  saude: {
    icon: HeartPulse,
    description:
      "Planos de saúde, SUS, tratamentos, negativas e tutelas urgentes",
    tone: "bg-pink-500 text-pink-700",
  },
  medico: {
    icon: Stethoscope,
    description:
      "Responsabilidade médica, prontuários, consentimento e perícia",
    tone: "bg-cyan-500 text-cyan-700",
  },
  digital_lgpd: {
    icon: Database,
    description:
      "LGPD, incidentes, contratos digitais, provas e governança de dados",
    tone: "bg-sky-600 text-sky-700",
  },
  transito: {
    icon: Car,
    description: "Multas, defesa prévia, JARI, CETRAN, suspensão e cassação",
    tone: "bg-indigo-600 text-indigo-700",
  },
  constitucional: {
    icon: Scale,
    description: "Questões constitucionais, controle, repercussão geral e STF",
    tone: "bg-purple-600 text-purple-700",
  },
  eleitoral: {
    icon: Vote,
    description:
      "Eleições, candidaturas, propaganda, contas e contencioso eleitoral",
    tone: "bg-fuchsia-600 text-fuchsia-700",
  },
  internacional: {
    icon: Globe,
    description:
      "Contratos internacionais, cooperação, tratados e comércio exterior",
    tone: "bg-primary-900 text-primary-800 dark:bg-primary-400",
  },
};

const FALLBACK_AREAS: Area[] = [
  ["empresarial", "Direito Empresarial"],
  ["civil", "Direito Cível"],
  ["criminal", "Direito Penal"],
  ["trabalhista", "Direito Trabalhista"],
  ["administrativo", "Direito Administrativo"],
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
  // O RamosHub é visível para ROLES.juridico (inclui estagiário/auxiliar),
  // mas /cadastro-manual exige ROLES.clientes — só mostra o atalho para quem
  // de fato passa no guard da rota (evita botão que leva a "acesso negado").
  const role = useAuth((s) => s.user?.role);
  const podeCadastroManual =
    !!role && (ROLES.clientes as readonly string[]).includes(role);

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
    <div className="min-h-full px-6 py-6">
      <div className="mx-auto max-w-7xl space-y-4">
        <PageHeader
          title="Áreas de Atuação"
          subtitle="As áreas funcionam como filtros e perfis de jornada. Selecione uma área para consultar os casos correspondentes ou iniciar uma importação inteligente."
          eyebrow="Especializações da Central de Casos"
          actions={
            <>
              {podeCadastroManual && (
                <Button
                  variant="secondary"
                  onClick={() => navigate("/cadastro-manual")}
                >
                  <ClipboardPen className="h-4 w-4" /> Cadastro manual
                </Button>
              )}
              <Button variant="secondary" onClick={() => navigate("/casos")}>
                Todos os casos
              </Button>
              <Button onClick={() => navigate("/casos/novo?modo=documento")}>
                <UploadCloud className="h-4 w-4" /> Importar documento
              </Button>
            </>
          }
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {ordered.map((area) => {
            const visual = VISUAL[area.slug] || {
              icon: Scale,
              description:
                "Casos, documentos, jornadas e ferramentas pertinentes à área",
              tone: "bg-slate-500 text-slate-700",
            };
            const Icon = visual.icon;
            const hub = hubDoRamo(area.slug);
            const toneText =
              visual.tone.split(" ").find((c) => c.startsWith("text-")) || "";
            return (
              <Card
                key={area.slug}
                className="group relative h-full overflow-hidden rounded-[10px] p-4"
              >
                <div
                  className={`absolute inset-x-0 top-0 h-[3px] ${visual.tone}`}
                  aria-hidden="true"
                />
                <div className="relative flex h-full flex-col gap-3">
                  <div className="flex items-start justify-between gap-3">
                    <div
                      className={`grid h-10 w-10 place-items-center rounded-lg border border-slate-200 bg-slate-50 dark:border-white/10 dark:bg-white/10 ${toneText} dark:text-slate-200`}
                    >
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <span className="rounded-full bg-slate-950/5 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:bg-white/10 dark:text-slate-300">
                      Área
                    </span>
                  </div>
                  <div className="space-y-1">
                    <h2 className="text-[15px] font-bold text-slate-950 dark:text-slate-50">
                      {area.nome}
                    </h2>
                    <p className="text-[13px] leading-5 text-slate-500 dark:text-slate-300">
                      {visual.description}
                    </p>
                  </div>
                  <div className="mt-auto space-y-2 pt-2">
                    {/* Ação primária: abre o hub do ramo (calculadoras, guias
                        e súmulas) — antes só alcançável digitando a URL. */}
                    {hub && (
                      <Button
                        size="sm"
                        className="w-full"
                        onClick={() => navigate(hub)}
                      >
                        <Wrench className="h-3.5 w-3.5" /> Abrir ferramentas do
                        ramo
                      </Button>
                    )}
                    <div className="grid grid-cols-2 gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() =>
                          navigate(
                            `/casos?area=${encodeURIComponent(area.slug)}`,
                          )
                        }
                      >
                        Ver casos
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() =>
                          navigate(
                            `/casos/novo?modo=documento&area=${encodeURIComponent(area.slug)}`,
                          )
                        }
                      >
                        <UploadCloud className="h-3.5 w-3.5" /> Importar
                      </Button>
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}
