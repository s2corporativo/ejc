import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { LayoutGrid, Sparkles } from "lucide-react";
import {
  Badge,
  Card,
  Page,
  PageDescription,
  PageGrid,
  PageHeader,
  PageTitle,
} from "../components/ui";
import DefesasRevisoesPanel from "../components/DefesasRevisoesPanel";
import RevisaoBancariaDeterministica from "../components/RevisaoBancariaDeterministica";
import {
  canRoleAccessPath,
  STAFF_ROUTES,
  type ModuleRoute,
} from "../config/moduleRegistry";
import { useAuth } from "../stores/auth";

// Hub de descoberta: reúne os módulos reais que ficaram fora do menu
// principal (status:"hidden") em cartões organizados por tema, em vez de
// reabrir 18 itens na barra lateral. Os dados (path/label/ícone/papéis) vêm
// direto do STAFF_ROUTES — nenhuma rota ou permissão é duplicada aqui.
const CATEGORIES: { title: string; description: string; keys: string[] }[] = [
  {
    title: "Inteligência & Conhecimento",
    description: "Bases de conteúdo e apoio à produção jurídica com IA.",
    keys: ["biblioteca", "memoria", "wiki", "prompts"],
  },
  {
    title: "Compliance & Governança",
    description: "Governança institucional, trilhas e avaliação de risco.",
    keys: [
      "governanca-ia",
      "auditoria",
      "radar-compliance",
      "radar-regulatorio",
      "mapa-modulos",
      "lixeira",
    ],
  },
  {
    title: "Monitoramento",
    description: "Dados públicos e publicações acompanhados automaticamente.",
    keys: ["datajud", "diario-oficial", "noticias"],
  },
  {
    title: "Produtividade & Operações",
    description: "Fluxos, indicadores e apoio operacional do dia a dia.",
    keys: ["produtividade", "workflow", "checklists", "assinaturas", "crm"],
  },
];

export default function Ferramentas() {
  const navigate = useNavigate();
  const user = useAuth((state) => state.user);

  const modulesByKey = useMemo(
    () => new Map(STAFF_ROUTES.map((module) => [module.key, module])),
    [],
  );

  const groups = useMemo(
    () =>
      CATEGORIES.map((category) => ({
        ...category,
        modules: category.keys
          .map((key) => modulesByKey.get(key))
          .filter((module): module is ModuleRoute => Boolean(module))
          .filter((module) => canRoleAccessPath(user?.role, module.path)),
      })).filter((category) => category.modules.length > 0),
    [modulesByKey, user?.role],
  );

  const podeUsarDefesas = [
    "superadmin",
    "admin",
    "socio",
    "advogado",
    "advogado_auxiliar",
    "estagiario",
  ].includes(user?.role || "");

  return (
    <Page className="surface-soft min-h-full px-6 py-8">
      <div className="mx-auto max-w-7xl space-y-8">
        <PageHeader className="rounded-[2rem] bg-white/70 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur dark:bg-white/[0.03]">
          <div>
            <Badge variant="gold" className="mb-3 gap-1">
              <Sparkles className="h-3 w-3" /> Catálogo de módulos
            </Badge>
            <PageTitle>Mais Ferramentas</PageTitle>
            <PageDescription>
              Módulos avançados e complementares do EJC, organizados por tema.
              Eles não ficam na barra lateral para manter o menu enxuto, mas
              continuam totalmente funcionais.
            </PageDescription>
          </div>
        </PageHeader>

        {podeUsarDefesas && (
          <>
            <DefesasRevisoesPanel />
            <RevisaoBancariaDeterministica />
          </>
        )}

        {groups.map((group) => (
          <section key={group.title} className="space-y-3">
            <div>
              <h2 className="text-base font-semibold text-slate-950 dark:text-slate-50">
                {group.title}
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-300">
                {group.description}
              </p>
            </div>

            <PageGrid className="grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
              {group.modules.map((module) => {
                const Icon = module.icon;
                return (
                  <button
                    key={module.key}
                    onClick={() => navigate(module.path)}
                    className="group text-left outline-none"
                  >
                    <Card className="flex h-full items-start gap-3 p-5 transition duration-200 group-hover:-translate-y-1 group-hover:shadow-[0_26px_70px_rgba(15,23,42,0.14)]">
                      <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-primary-50 text-primary-700 ring-1 ring-black/5 dark:bg-white/10 dark:text-primary-200">
                        <Icon className="h-5 w-5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                            {module.label}
                          </h3>
                        </div>
                        <p className="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-300">
                          {module.description}
                        </p>
                      </div>
                    </Card>
                  </button>
                );
              })}
            </PageGrid>
          </section>
        ))}

        {groups.length === 0 && !podeUsarDefesas && (
          <Card className="flex flex-col items-center gap-3 p-10 text-center text-slate-500">
            <LayoutGrid className="h-8 w-8" />
            <p>Nenhuma ferramenta adicional disponível para o seu perfil.</p>
          </Card>
        )}
      </div>
    </Page>
  );
}
