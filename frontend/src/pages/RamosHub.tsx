import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import {
  Banknote,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  Car,
  Database,
  FileSignature,
  Globe,
  HardHat,
  HeartPulse,
  Home,
  Landmark,
  Leaf,
  Receipt,
  Scale,
  Search,
  Shield,
  Sprout,
  Star,
  Stethoscope,
  Users,
  Vote,
} from "lucide-react";
import api from "../lib/api";
import { CANONICAL_ROUTES } from "../config/canonicalRoutes";
import { ROLES } from "../config/moduleRegistry";
import { Badge, Button, Card, PageHeader } from "../components/UI";
import { useAuth } from "../stores/auth";
import {
  AREAS_PRINCIPAIS_PADRAO,
  GRUPOS_AREAS,
  areaCombinaBusca,
  casosGeraisPath,
  grupoDaArea,
  hubSlugDaArea,
  novoCasoPath,
  type AreaResumo,
} from "./ramos/areasWorkspace";

const FAVORITOS_KEY = "ejc:areas-favoritas:v1";

export function hubDoRamo(areaSlug: string): string | null {
  const slug = hubSlugDaArea(areaSlug);
  return slug ? `${CANONICAL_ROUTES.areasAtuacao}/${slug}` : null;
}

export function podeCriarCasoNoHub(role?: string | null): boolean {
  return Boolean(role && (ROLES.clientes as readonly string[]).includes(role));
}

type Area = AreaResumo;
type IconeArea = typeof Scale;

type AreaVisual = {
  icon: IconeArea;
  descricao: string;
};

const VISUAL: Record<string, AreaVisual> = {
  empresarial: {
    icon: Building2,
    descricao: "Sociedades, contratos empresariais, recuperação e governança.",
  },
  societario: {
    icon: BriefcaseBusiness,
    descricao: "Constituição, alterações, sócios, governança e reorganizações.",
  },
  contratual: {
    icon: FileSignature,
    descricao: "Elaboração, revisão, riscos, obrigações e inadimplemento.",
  },
  civil: {
    icon: Scale,
    descricao:
      "Responsabilidade civil, obrigações, cobrança, indenizações e JEC.",
  },
  criminal: {
    icon: Shield,
    descricao: "Defesa criminal, inquéritos, cautelares, instrução e recursos.",
  },
  trabalhista: {
    icon: HardHat,
    descricao: "Consultivo, contencioso, vínculo, verbas, recursos e execução.",
  },
  administrativo: {
    icon: Landmark,
    descricao: "Atos, sanções, servidores, contratos públicos e regulação.",
  },
  licitacoes: {
    icon: Landmark,
    descricao:
      "Licitações, compras públicas e execução de contratos administrativos.",
  },
  bancario: {
    icon: Banknote,
    descricao:
      "Contratos bancários, CET, juros, cobranças e superendividamento.",
  },
  tributario: {
    icon: Receipt,
    descricao: "Autos, lançamentos, execução fiscal, defesas e planejamento.",
  },
  ambiental: {
    icon: Leaf,
    descricao:
      "Licenciamento, autos, embargos, laudos e responsabilidades conexas.",
  },
  agrario: {
    icon: Sprout,
    descricao:
      "Posse rural, contratos agrários, regularização e conflitos fundiários.",
  },
  agronegocio: {
    icon: BriefcaseBusiness,
    descricao:
      "Operações rurais, cadeias produtivas, crédito e contratos do agro.",
  },
  consumidor: {
    icon: Users,
    descricao:
      "Cobranças, vícios, serviços, negativação e responsabilidade do fornecedor.",
  },
  familia: {
    icon: Users,
    descricao:
      "Família, guarda, convivência, alimentos, divórcio e planejamento.",
  },
  sucessoes: {
    icon: BookOpenCheck,
    descricao: "Inventário, testamento, herdeiros, bens e partilha.",
  },
  imobiliario: {
    icon: Home,
    descricao: "Locação, compra e venda, posse, usucapião e incorporação.",
  },
  previdenciario: {
    icon: Shield,
    descricao: "Benefícios, CNIS, PPP, perícias, revisões e planejamento.",
  },
  saude: {
    icon: HeartPulse,
    descricao:
      "Planos de saúde, SUS, tratamentos, negativas e tutelas urgentes.",
  },
  medico: {
    icon: Stethoscope,
    descricao: "Responsabilidade médica, prontuários, consentimento e perícia.",
  },
  digital_lgpd: {
    icon: Database,
    descricao:
      "LGPD, incidentes, contratos digitais, provas e governança de dados.",
  },
  transito: {
    icon: Car,
    descricao: "Multas, recursos, suspensão, cassação e questões de trânsito.",
  },
  constitucional: {
    icon: Scale,
    descricao: "Questões constitucionais, controle, repercussão geral e STF.",
  },
  eleitoral: {
    icon: Vote,
    descricao:
      "Eleições, candidaturas, propaganda, contas e contencioso eleitoral.",
  },
  internacional: {
    icon: Globe,
    descricao:
      "Contratos internacionais, cooperação, tratados e comércio exterior.",
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
    const salvo = JSON.parse(
      window.localStorage.getItem(FAVORITOS_KEY) || "null",
    );
    if (
      Array.isArray(salvo) &&
      salvo.every((item) => typeof item === "string")
    ) {
      return salvo;
    }
  } catch {
    // Preferência local inválida não bloqueia o módulo.
  }
  return [...AREAS_PRINCIPAIS_PADRAO];
}

function mesclarAreas(remotas: Area[]): Area[] {
  const porSlug = new Map(FALLBACK_AREAS.map((area) => [area.slug, area]));
  for (const area of remotas) {
    if (!area?.slug || !area?.nome || area.ativo === false) continue;
    porSlug.set(area.slug, { ...porSlug.get(area.slug), ...area });
  }
  return [...porSlug.values()]
    .filter((area) => area.ativo !== false)
    .sort(
      (a, b) =>
        (a.ordem ?? Number.MAX_SAFE_INTEGER) -
          (b.ordem ?? Number.MAX_SAFE_INTEGER) ||
        a.nome.localeCompare(b.nome, "pt-BR"),
    );
}

function AreaCard({
  area,
  favorito,
  onFavorito,
  podeCriarCaso,
}: {
  area: Area;
  favorito: boolean;
  onFavorito: (slug: string) => void;
  podeCriarCaso: boolean;
}) {
  const navigate = useNavigate();
  const visual = VISUAL[area.slug] ?? {
    icon: Scale,
    descricao: "Casos e recursos relacionados a esta especialidade jurídica.",
  };
  const Icon = visual.icon;
  const hub = hubDoRamo(area.slug);

  return (
    <Card className="flex h-full flex-col rounded-xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-slate-200 bg-slate-50 text-slate-700 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-200">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
        <button
          type="button"
          onClick={() => onFavorito(area.slug)}
          className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition hover:bg-black/[0.04] hover:text-ouro dark:hover:bg-white/[0.06]"
          aria-label={
            favorito ? "Remover dos favoritos" : "Adicionar aos favoritos"
          }
          title={favorito ? "Remover dos favoritos" : "Adicionar aos favoritos"}
        >
          <Star
            className={`h-4 w-4 ${favorito ? "fill-current text-ouro" : ""}`}
          />
        </button>
      </div>

      <div className="mt-3 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-bold text-slate-950 dark:text-white">
            {area.nome}
          </h2>
          {!hub && <Badge>Sem workspace dedicado</Badge>}
        </div>
        <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-300">
          {visual.descricao}
        </p>
      </div>

      <div className="mt-4 grid gap-2">
        {hub ? (
          <Button size="sm" className="w-full" onClick={() => navigate(hub)}>
            Abrir workspace
          </Button>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            className="w-full"
            onClick={() => navigate(casosGeraisPath())}
          >
            Ver todos os casos
          </Button>
        )}
        {podeCriarCaso && (
          <Button
            size="sm"
            variant="secondary"
            className="w-full"
            onClick={() => navigate(novoCasoPath())}
          >
            Novo caso
          </Button>
        )}
      </div>
    </Card>
  );
}

export default function RamosHub() {
  const role = useAuth((state) => state.user?.role);
  const podeCriarCaso = podeCriarCasoNoHub(role);
  const [areas, setAreas] = useState<Area[]>(FALLBACK_AREAS);
  const [busca, setBusca] = useState("");
  const [favoritos, setFavoritos] = useState<string[]>(lerFavoritos);

  useEffect(() => {
    let ativo = true;
    api
      .get("/areas")
      .then((resposta) => {
        if (!ativo) return;
        const remotas = Array.isArray(resposta.data?.areas)
          ? (resposta.data.areas as Area[])
          : [];
        setAreas(mesclarAreas(remotas));
      })
      .catch(() => {
        if (ativo) setAreas(FALLBACK_AREAS);
      });
    return () => {
      ativo = false;
    };
  }, []);

  const alternarFavorito = (slug: string) => {
    setFavoritos((atuais) => {
      const proximos = atuais.includes(slug)
        ? atuais.filter((item) => item !== slug)
        : [...atuais, slug];
      window.localStorage.setItem(FAVORITOS_KEY, JSON.stringify(proximos));
      return proximos;
    });
  };

  const filtradas = useMemo(
    () => areas.filter((area) => areaCombinaBusca(area, busca)),
    [areas, busca],
  );

  const favoritas = useMemo(
    () => filtradas.filter((area) => favoritos.includes(area.slug)),
    [filtradas, favoritos],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Organização jurídica"
        title="Áreas de Atuação"
        subtitle="Encontre a especialidade, abra o workspace existente e preserve a classificação jurídica canônica de cada caso."
      />

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/[0.03]">
        <label className="relative block">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
            aria-hidden="true"
          />
          <input
            type="search"
            className="input w-full pl-9"
            value={busca}
            onChange={(event) => setBusca(event.target.value)}
            placeholder="Buscar área, assunto, ferramenta ou base legal…"
            aria-label="Buscar áreas de atuação"
          />
        </label>
        <p className="mt-2 text-xs text-slate-500">
          {filtradas.length} de {areas.length} áreas visíveis. Workspaces só são
          oferecidos quando existe implementação correspondente no EJC.
        </p>
      </div>

      {favoritas.length > 0 && (
        <section className="space-y-3" aria-labelledby="areas-favoritas">
          <div>
            <h2
              id="areas-favoritas"
              className="text-sm font-bold text-slate-900 dark:text-white"
            >
              Favoritas
            </h2>
            <p className="text-xs text-slate-500">
              Preferência local deste navegador; não altera cadastro, caso ou
              permissão.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {favoritas.map((area) => (
              <AreaCard
                key={`fav-${area.slug}`}
                area={area}
                favorito
                onFavorito={alternarFavorito}
                podeCriarCaso={podeCriarCaso}
              />
            ))}
          </div>
        </section>
      )}

      {GRUPOS_AREAS.map((grupo) => {
        const doGrupo = filtradas.filter(
          (area) => grupoDaArea(area.slug)?.id === grupo.id,
        );
        if (doGrupo.length === 0) return null;
        return (
          <section key={grupo.id} className="space-y-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                {grupo.titulo}
              </h2>
              <p className="text-xs text-slate-500">{grupo.descricao}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {doGrupo.map((area) => (
                <AreaCard
                  key={area.slug}
                  area={area}
                  favorito={favoritos.includes(area.slug)}
                  onFavorito={alternarFavorito}
                  podeCriarCaso={podeCriarCaso}
                />
              ))}
            </div>
          </section>
        );
      })}

      {filtradas.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-white/15">
          Nenhuma área corresponde à busca. Tente outro termo jurídico ou nome
          de ferramenta.
        </div>
      )}
    </div>
  );
}
