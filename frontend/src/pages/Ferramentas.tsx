import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ChevronDown,
  ChevronUp,
  LayoutGrid,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
} from "lucide-react";
import {
  Badge,
  Button,
  Card,
  Page,
  PageDescription,
  PageGrid,
  PageHeader,
  PageTitle,
} from "../components/ui";
import { EmptyState } from "../components/UI";
import { cn } from "../lib/cn";
import DefesasRevisoesPanel from "../components/DefesasRevisoesPanel";
import RevisaoBancariaDeterministica from "../components/RevisaoBancariaDeterministica";
import {
  canRoleAccessPath,
  STAFF_ROUTES,
  type ModuleRoute,
} from "../config/moduleRegistry";
import { useAuth } from "../stores/auth";

const CATEGORIES: { title: string; description: string; keys: string[] }[] = [
  {
    title: "Inteligência e conhecimento",
    description: "Bases de conteúdo e apoio à produção jurídica.",
    keys: ["biblioteca", "memoria", "wiki", "prompts"],
  },
  {
    title: "Compliance e governança",
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
    description: "Dados públicos e publicações acompanhados pelo escritório.",
    keys: ["datajud", "diario-oficial", "noticias"],
  },
  {
    title: "Produtividade e operações",
    description: "Fluxos, indicadores e apoio operacional do dia a dia.",
    keys: ["produtividade", "workflow", "checklists", "assinaturas", "crm"],
  },
];

const FAVORITOS_KEY = "ejc_ferramentas_favoritas";

function carregarFavoritos(): Set<string> {
  try {
    const valor = JSON.parse(localStorage.getItem(FAVORITOS_KEY) || "[]");
    return new Set(
      Array.isArray(valor)
        ? valor.filter((item) => typeof item === "string")
        : [],
    );
  } catch {
    return new Set();
  }
}

export default function Ferramentas() {
  const navigate = useNavigate();
  const user = useAuth((state) => state.user);
  const [busca, setBusca] = useState("");
  const [defesasOpen, setDefesasOpen] = useState(false);
  const [favoritos, setFavoritos] = useState<Set<string>>(carregarFavoritos);

  const modulesByKey = useMemo(
    () => new Map(STAFF_ROUTES.map((module) => [module.key, module])),
    [],
  );

  const termo = busca.trim().toLowerCase();
  const groups = useMemo(
    () =>
      CATEGORIES.map((category) => ({
        ...category,
        modules: category.keys
          .map((key) => modulesByKey.get(key))
          .filter((module): module is ModuleRoute => Boolean(module))
          .filter((module) => canRoleAccessPath(user?.role, module.path))
          .filter(
            (module) =>
              !termo ||
              `${module.label} ${module.description} ${category.title}`
                .toLowerCase()
                .includes(termo),
          )
          .sort(
            (a, b) =>
              Number(favoritos.has(b.key)) - Number(favoritos.has(a.key)),
          ),
      })).filter((category) => category.modules.length > 0),
    [favoritos, modulesByKey, termo, user?.role],
  );

  const podeUsarDefesas = [
    "superadmin",
    "admin",
    "socio",
    "advogado",
    "advogado_auxiliar",
    "estagiario",
  ].includes(user?.role || "");

  const alternarFavorito = (key: string) => {
    setFavoritos((atual) => {
      const proximo = new Set(atual);
      if (proximo.has(key)) proximo.delete(key);
      else proximo.add(key);
      localStorage.setItem(FAVORITOS_KEY, JSON.stringify([...proximo]));
      return proximo;
    });
  };

  return (
    <Page className="surface-soft min-h-full px-6 py-8">
      <div className="mx-auto max-w-7xl space-y-8">
        <PageHeader className="rounded-[2rem] bg-white/70 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur dark:bg-white/[0.03]">
          <div>
            <Badge variant="gold" className="mb-3 gap-1">
              <Sparkles className="h-3 w-3" /> Catálogo de ferramentas
            </Badge>
            <PageTitle>Mais Ferramentas</PageTitle>
            <PageDescription>
              Recursos complementares organizados por finalidade. A rotina
              principal continua dentro do caso e da Jornada.
            </PageDescription>
          </div>
        </PageHeader>

        <div className="relative max-w-xl">
          <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
          <input
            className="input w-full pl-10"
            placeholder="Buscar ferramenta por nome ou finalidade..."
            value={busca}
            onChange={(event) => setBusca(event.target.value)}
            aria-label="Buscar em Mais Ferramentas"
          />
        </div>

        {podeUsarDefesas &&
          (!termo ||
            "defesas revisões multas contratos bancária".includes(termo)) && (
            <section className="space-y-4">
              <button
                type="button"
                onClick={() => setDefesasOpen((aberto) => !aberto)}
                className="group w-full text-left"
                aria-expanded={defesasOpen}
              >
                <Card className="flex items-start gap-4 p-5 transition duration-200 group-hover:-translate-y-0.5 group-hover:shadow-[0_20px_55px_rgba(15,23,42,0.12)]">
                  <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-primary-50 text-primary-700 ring-1 ring-black/5 dark:bg-white/10 dark:text-primary-200">
                    <ShieldCheck className="h-6 w-6" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h2 className="font-semibold text-slate-950 dark:text-slate-50">
                          Defesas e Revisões
                        </h2>
                        <p className="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-300">
                          Multas de trânsito, ambientais e administrativas,
                          revisão de contratos e análise bancária com cálculos
                          rastreáveis.
                        </p>
                      </div>
                      <span className="rounded-lg p-2 text-slate-400">
                        {defesasOpen ? (
                          <ChevronUp className="h-5 w-5" />
                        ) : (
                          <ChevronDown className="h-5 w-5" />
                        )}
                      </span>
                    </div>
                  </div>
                </Card>
              </button>

              {defesasOpen && (
                <div className="space-y-6 rounded-2xl border border-slate-200 bg-white/60 p-4 dark:border-white/10 dark:bg-white/[0.02]">
                  <DefesasRevisoesPanel />
                  <RevisaoBancariaDeterministica />
                </div>
              )}
            </section>
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
                const favorito = favoritos.has(module.key);
                return (
                  <div key={module.key} className="group relative">
                    <button
                      onClick={() => navigate(module.path)}
                      className="h-full w-full text-left outline-none"
                    >
                      <Card className="flex h-full items-start gap-3 p-5 transition duration-200 group-hover:-translate-y-1 group-hover:shadow-[0_26px_70px_rgba(15,23,42,0.14)]">
                        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-primary-50 text-primary-700 ring-1 ring-black/5 dark:bg-white/10 dark:text-primary-200">
                          <Icon className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1 pr-7">
                          <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                            {module.label}
                          </h3>
                          <p className="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-300">
                            {module.description}
                          </p>
                        </div>
                      </Card>
                    </button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => alternarFavorito(module.key)}
                      className="absolute right-3 top-3 h-8 w-8 p-0"
                      aria-label={
                        favorito
                          ? `Remover ${module.label} dos favoritos`
                          : `Favoritar ${module.label}`
                      }
                      title={
                        favorito
                          ? "Remover dos favoritos"
                          : "Adicionar aos favoritos"
                      }
                    >
                      <Star
                        className={cn(
                          "h-4 w-4",
                          favorito
                            ? "fill-warn-400 text-warn-500"
                            : "text-slate-400",
                        )}
                      />
                    </Button>
                  </div>
                );
              })}
            </PageGrid>
          </section>
        ))}

        {groups.length === 0 && !podeUsarDefesas && (
          <EmptyState
            icon={LayoutGrid}
            title="Nenhuma ferramenta adicional disponível"
            message="O seu perfil não possui ferramentas complementares habilitadas."
          />
        )}

        {groups.length === 0 && termo && (
          <EmptyState
            icon={Search}
            title={`Nenhum resultado para “${busca.trim()}”`}
            message="Tente buscar pelo nome da tarefa, área jurídica ou finalidade."
          />
        )}
      </div>
    </Page>
  );
}
