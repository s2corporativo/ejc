import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import {
  Baby,
  Banknote,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  Car,
  ChevronRight,
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
  Search,
  Shield,
  Sparkles,
  Sprout,
  Star,
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
import { Badge, Button, Card, PageHeader } from "../components/UI";
import {
  AREAS_PRINCIPAIS_PADRAO,
  ESPECIALIDADES_SUBORDINADAS,
  GRUPOS_AREAS,
  areaCombinaBusca,
  buscarFerramentas,
  casosDaAreaPath,
  grupoDaArea,
  hubSlugDaArea,
  importacaoDaAreaPath,
  type AreaResumo,
} from "./ramos/areasWorkspace";

const FAVORITOS_KEY = "ejc:areas-favoritas:v1";

export function hubDoRamo(areaSlug: string): string | null {
  const slug = hubSlugDaArea(areaSlug);
  return slug ? `${CANONICAL_ROUTES.areasAtuacao}/${slug}` : null;
}

type Area = AreaResumo;

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
    description: "Constituição, alterações, sócios, governança e reorganizações",
    tone: "bg-indigo-500 text-indigo-700",
  },
  contratual: {
    icon: FileSignature,
    description: "Especialidade transversal para elaboração, revisão e inadimplemento",
    tone: "bg-slate-700 text-slate-700 dark:bg-slate-400",
  },
  civil: {
    icon: Scale,
    description: "Responsabilidade civil, obrigações, cobrança, indenizações e JEC",
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
    description: "Atos, servidores, sanções, contratos públicos e licitações",
    tone: "bg-ouro text-ouro-profundo",
  },
  licitacoes: {
    icon: ClipboardPen,
    description: "Especialidade de Direito Administrativo para compras e contratos públicos",
    tone: "bg-ouro text-ouro-profundo",
  },
  bancario: {
    icon: Banknote,
    description: "Contratos bancários, CET, juros, cobranças e superendividamento",
    tone: "bg-success-500 text-success-700",
  },
  tributario: {
    icon: Receipt,
    description: "Autos, lançamentos, execução fiscal, defesas e planejamento",
    tone: "bg-orange-500 text-orange-700",
  },
  ambiental: {
    icon: Leaf,
    description: "Licenciamento, autos, embargos, laudos e responsabilidades conexas",
    tone: "bg-green-500 text-green-700",
  },
  agrario: {
    icon: Sprout,
    description: "Posse rural, contratos agrários, regularização e conflitos fundiários",
    tone: "bg-lime-600 text-lime-700",
  },
  agronegocio: {
    icon: BriefcaseBusiness,
    description: "Operações rurais, cadeias produtivas, crédito e contratos do agro",
    tone: "bg-emerald-600 text-emerald-700",
  },
  consumidor: {
    icon: Users,
    description: "Cobranças, vícios, serviços, negativação e responsabilidade do fornecedor",
    tone: "bg-teal-500 text-teal-700",
  },
  familia: {
    icon: Baby,
    description: "Família, inventário, sucessões, guarda, convivência e alimentos",
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
    description: "Planos de saúde, SUS, tratamentos, negativas e tutelas urgentes",
    tone: "bg-pink-500 text-pink-700",
  },
  medico: {
    icon: Stethoscope,
    description: "Responsabilidade médica, prontuários, consentimento e perícia",
    tone: "bg-cyan-500 text-cyan-700",
  },
  digital_lgpd: {
    icon: Database,
    description: "LGPD, incidentes, contratos digitais, provas e governança de dados",
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
    description: "Eleições, candidaturas, propaganda, contas e contencioso eleitoral",
    tone: "bg-fuchsia-600 text-fuchsia-700",
  },
  internacional: {
    icon: Globe,
    description: "Contratos internacionais, cooperação, tratados e comércio exterior",
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
  ["licitacoes", "Licitações"],
].map(([slug, nome], index) => ({ slug, nome, ordem: (index + 1) * 10 }));

function lerFavoritos(): string[] {
  if (typeof window === "undefined") return [...AREAS_PRINCIPAIS_PADRAO];
  try {
    const salvo = JSON.parse(window.localStorage.getItem(FAVORITOS_KEY) || "null");
    if (Array.isArray(salvo) && salvo.every((item) => typeof item === "string")) {
      return salvo;
    }
  } catch {
    // Preferência local inválida não pode bloquear o módulo.
  }
  return [...AREAS_PRINCIPAIS_PADRAO];
}

function AreaCard({
  area,
  favorito,
  onFavorito,
  compacta = false,
}: {
  area: Area;
  favorito: boolean;
  onFavorito: (slug: string) => void;
  compacta?: boolean;
}) {
  const navigate = useNavigate();
  const visual = VISUAL[area.slug] || {
    icon: Scale,
    description: "Casos e recursos relacionados a esta especialidade jurídica",
    tone: "bg-slate-500 text-slate-700",
  };
  const Icon = visual.icon;
  const hub = hubDoRamo(area.slug);
  const subordinada = ESPECIALIDADES_SUBORDINADAS[area.slug];
  const toneText =
    visual.tone.split(" ").find((classe) => classe.startsWith("text-")) || "";

  if (compacta) {
    return (
      <div className="flex flex-col gap-3 rounded-xl border border-black/[0.06] bg-white/70 p-3 dark:border-white/10 dark:bg-white/[0.03] sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div
            className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-50 ${toneText} dark:bg-white/10 dark:text-slate-200`}
          >
            <Icon className="h-4.5 w-4.5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                {area.nome}
              </h3>
              {subordinada && (
                <Badge>{`Especialidade de ${subordinada.pai}`}</Badge>
              )}
            </div>
            <p className="mt-0.5 text-xs leading-5 text-slate-500 dark:text-slate-300">
              {visual.description}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 sm:justify-end">
          <button
            type="button"
            onClick={() => onFavorito(area.slug)}
            className="grid h-9 w-9 place-items-center rounded-lg border border-black/[0.06] text-slate-400 transition hover:text-ouro dark:border-white/10"
            title={favorito ? "Remover dos favoritos" : "Adicionar aos favoritos"}
            aria-label={favorito ? "Remover dos favoritos" : "Adicionar aos favoritos"}
          >
            <Star className={`h-4 w-4 ${favorito ? "fill-current text-ouro" : ""}`} />
          </button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(casosDaAreaPath(area.slug))}
          >
            Casos
          </Button>
          {hub && (
            <Button size="sm" onClick={() => navigate(hub)}>
              Workspace <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <Card className="group relative h-full overflow-hidden rounded-xl p-4">
      <div className={`absolute inset-x-0 top-0 h-[3px] ${visual.tone}`} aria-hidden="true" />
      <div className="relative flex h-full flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div
            className={`grid h-10 w-10 place-items-center rounded-lg border border-slate-200 bg-slate-50 ${toneText} dark:border-white/10 dark:bg-white/10 dark:text-slate-200`}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
          </div>
          <button
            type="button"
            onClick={() => onFavorito(area.slug)}
            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition hover:bg-black/[0.04] hover:text-ouro dark:hover:bg-white/[0.06]"
            title={favorito ? "Remover dos favoritos" : "Adicionar aos favoritos"}
            aria-label={favorito ? "Remover dos favoritos" : "Adicionar aos favoritos"}
          >
            <Star className={`h-4 w-4 ${favorito ? "fill-current text-ouro" : ""}`} />
          </button>
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
          {hub ? (
            <Button size="sm" className="w-full" onClick={() => navigate(hub)}>
              <Wrench className="h-3.5 w-3.5" /> Abrir workspace
            </Button>
          ) : (
            <Button
              size="sm"
              className="w-full"
              variant="secondary"
              onClick={() => navigate(casosDaAreaPath(area.slug))}
            >
              Ver casos da área
            </Button>
          )}
          <div className="grid grid-cols-2 gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(casosDaAreaPath(area.slug))}
            >
              Ver casos
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(importacaoDaAreaPath(area.slug))}
            >
              <UploadCloud className="h-3.5 w-3.5" /> Importar
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

export default function RamosHub() {
  const navigate = useNavigate();
  const [areas, setAreas] = useState<Area[]>(FALLBACK_AREAS);
  const [busca, setBusca] = useState("");
  const [favoritos, setFavoritos] = useState<string[]>(lerFavoritos);
  const role = useAuth((state) => state.user?.role);
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

  const porSlug = useMemo(
    () => new Map(ordered.map((area) => [area.slug, area])),
    [ordered],
  );

  const areasFavoritas = useMemo(
    () => favoritos.map((slug) => porSlug.get(slug)).filter(Boolean) as Area[],
    [favoritos, porSlug],
  );

  const resultadosArea = useMemo(
    () => (busca.trim() ? ordered.filter((area) => areaCombinaBusca(area, busca)) : []),
    [busca, ordered],
  );

  const resultadosFerramenta = useMemo(() => buscarFerramentas(busca), [busca]);

  const alternarFavorito = (slug: string) => {
    setFavoritos((atuais) => {
      const proximo = atuais.includes(slug)
        ? atuais.filter((item) => item !== slug)
        : [...atuais, slug];
      try {
        window.localStorage.setItem(FAVORITOS_KEY, JSON.stringify(proximo));
      } catch {
        // Preferência é conveniência; falha de storage não afeta a operação.
      }
      return proximo;
    });
  };

  return (
    <div className="min-h-full px-6 py-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <PageHeader
          title="Áreas de Atuação"
          subtitle="Entre pela matéria jurídica e encontre casos, ferramentas, análise e referências sem duplicar caminhos."
          eyebrow="Centro de Especialidades Jurídicas"
          actions={
            <>
              {podeCadastroManual && (
                <Button variant="secondary" onClick={() => navigate("/cadastro-manual")}>
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

        <Card className="overflow-hidden rounded-2xl p-5">
          <div className="grid gap-5 lg:grid-cols-[1fr_auto] lg:items-end">
            <div>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-ouro-profundo">
                <Sparkles className="h-4 w-4" /> Acesso direto
              </div>
              <h2 className="text-xl font-bold text-slate-950 dark:text-white">
                O que você precisa trabalhar agora?
              </h2>
              <p className="mt-1 max-w-3xl text-sm text-slate-500 dark:text-slate-300">
                Pesquise por área, assunto ou ferramenta — por exemplo: ANPP, usucapião, BACEN, alimentos, LGPD ou licitações.
              </p>
            </div>
            <Badge>{`${ordered.length} classificações preservadas`}</Badge>
          </div>
          <div className="relative mt-4">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={busca}
              onChange={(event) => setBusca(event.target.value)}
              className="input w-full pl-10"
              placeholder="Buscar área, assunto, cálculo ou ferramenta…"
              aria-label="Buscar área, assunto ou ferramenta"
            />
          </div>
        </Card>

        {busca.trim() ? (
          <div className="space-y-6">
            <section className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-bold text-slate-950 dark:text-white">
                    Áreas encontradas
                  </h2>
                  <p className="text-xs text-slate-500">
                    A busca considera especialidades, subáreas e o conteúdo das ferramentas.
                  </p>
                </div>
                <Badge>{resultadosArea.length}</Badge>
              </div>
              {resultadosArea.length ? (
                <div className="space-y-2">
                  {resultadosArea.map((area) => (
                    <AreaCard
                      key={area.slug}
                      area={area}
                      favorito={favoritos.includes(area.slug)}
                      onFavorito={alternarFavorito}
                      compacta
                    />
                  ))}
                </div>
              ) : (
                <Card className="p-5 text-sm text-slate-500">
                  Nenhuma área corresponde diretamente à pesquisa.
                </Card>
              )}
            </section>

            {resultadosFerramenta.length > 0 && (
              <section className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-base font-bold text-slate-950 dark:text-white">
                      Ferramentas encontradas
                    </h2>
                    <p className="text-xs text-slate-500">
                      Abra diretamente o workspace e a aba de ferramentas.
                    </p>
                  </div>
                  <Badge>{resultadosFerramenta.length}</Badge>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {resultadosFerramenta.map(({ areaSlug, areaTitulo, ferramenta }) => {
                    const hub = hubDoRamo(areaSlug);
                    return (
                      <button
                        key={`${areaSlug}:${ferramenta.id}`}
                        type="button"
                        disabled={!hub}
                        onClick={() =>
                          hub &&
                          navigate(
                            `${hub}?tab=ferramentas&ferramenta=${encodeURIComponent(ferramenta.id)}`,
                          )
                        }
                        className="rounded-xl border border-black/[0.06] bg-white p-4 text-left transition hover:-translate-y-0.5 hover:border-ouro/40 hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-60 dark:border-white/10 dark:bg-white/[0.03]"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-ouro-profundo">
                              {areaTitulo}
                            </p>
                            <h3 className="mt-1 text-sm font-bold text-slate-950 dark:text-white">
                              {ferramenta.titulo}
                            </h3>
                            <p className="mt-1 text-xs leading-5 text-slate-500">
                              {ferramenta.descricao}
                            </p>
                          </div>
                          <Wrench className="h-4 w-4 shrink-0 text-slate-400" />
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>
            )}
          </div>
        ) : (
          <>
            <section className="space-y-3">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 className="text-base font-bold text-slate-950 dark:text-white">
                    Minhas áreas
                  </h2>
                  <p className="text-xs text-slate-500">
                    Fixe somente o que você usa no dia a dia. A preferência fica neste navegador.
                  </p>
                </div>
                <Badge>{`${areasFavoritas.length} favoritas`}</Badge>
              </div>
              {areasFavoritas.length ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {areasFavoritas.map((area) => (
                    <AreaCard
                      key={area.slug}
                      area={area}
                      favorito
                      onFavorito={alternarFavorito}
                    />
                  ))}
                </div>
              ) : (
                <Card className="p-5 text-sm text-slate-500">
                  Nenhuma área fixada. Use a estrela em “Todas as áreas” para montar seu acesso rápido.
                </Card>
              )}
            </section>

            <section className="space-y-4">
              <div>
                <h2 className="text-base font-bold text-slate-950 dark:text-white">
                  Todas as áreas
                </h2>
                <p className="text-xs text-slate-500">
                  A taxonomia completa continua disponível, agora organizada por finalidade jurídica em vez de uma grade única.
                </p>
              </div>

              {GRUPOS_AREAS.map((grupo) => {
                const areasGrupo = grupo.slugs
                  .map((slug) => porSlug.get(slug))
                  .filter(Boolean) as Area[];
                const primarias = areasGrupo.filter(
                  (area) => !ESPECIALIDADES_SUBORDINADAS[area.slug],
                );
                const subordinadas = areasGrupo.filter(
                  (area) => ESPECIALIDADES_SUBORDINADAS[area.slug],
                );
                if (!areasGrupo.length) return null;

                return (
                  <Card key={grupo.id} className="rounded-2xl p-4 sm:p-5">
                    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-bold text-slate-950 dark:text-white">
                          {grupo.titulo}
                        </h3>
                        <p className="mt-1 text-xs text-slate-500">{grupo.descricao}</p>
                      </div>
                      <Badge>{`${areasGrupo.length} matérias`}</Badge>
                    </div>
                    <div className="space-y-2">
                      {primarias.map((area) => (
                        <AreaCard
                          key={area.slug}
                          area={area}
                          favorito={favoritos.includes(area.slug)}
                          onFavorito={alternarFavorito}
                          compacta
                        />
                      ))}
                    </div>
                    {subordinadas.length > 0 && (
                      <div className="mt-4 border-t border-black/[0.05] pt-3 dark:border-white/10">
                        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                          Especialidades vinculadas
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {subordinadas.map((area) => {
                            const pai = ESPECIALIDADES_SUBORDINADAS[area.slug];
                            return (
                              <button
                                key={area.slug}
                                type="button"
                                onClick={() => {
                                  const hub = hubDoRamo(area.slug);
                                  if (hub) navigate(hub);
                                  else navigate(casosDaAreaPath(area.slug));
                                }}
                                className="rounded-full border border-black/[0.06] bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-ouro/40 hover:text-ouro-profundo dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300"
                                title={`Integrada ao núcleo ${pai?.pai || grupo.titulo}`}
                              >
                                {area.nome}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </Card>
                );
              })}

              {ordered
                .filter((area) => !grupoDaArea(area.slug))
                .map((area) => (
                  <AreaCard
                    key={area.slug}
                    area={area}
                    favorito={favoritos.includes(area.slug)}
                    onFavorito={alternarFavorito}
                    compacta
                  />
                ))}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
