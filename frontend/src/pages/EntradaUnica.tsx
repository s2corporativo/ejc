// Entrada Única (/entrada) — superfície canônica para iniciar trabalho jurídico.
//
// Simplificação deliberada: Relato/Documentos, Raio-X e Sala Jurídica deixam de
// competir como três portas de navegação. Os motores e contratos de backend são
// preservados, mas a experiência passa a ser uma única tela com modos. Isso
// reduz regressão: nenhuma persistência é fundida nesta etapa e os RBACs de cada
// ação continuam sendo validados pelo backend.
import { lazy, Suspense, type MouseEvent as ReactMouseEvent } from "react";
import { FileText, ScanSearch, Sparkles } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Spinner } from "../components/UI";
import { useAuth } from "../stores/auth";
import {
  useModuleLifecycleStore,
  type ModuleLifecycleOverride,
} from "../stores/moduleLifecycle";

const EntradaRelato = lazy(() => import("./EntradaRelato"));
const RaioXProcesso = lazy(() => import("./RaioXProcesso"));
const SalaJuridica = lazy(() => import("./SalaJuridica"));

type ModoEntrada = "relato" | "raio-x" | "sala";

const ROLES_RELATO = new Set(["superadmin", "admin", "socio", "advogado"]);

const MODULO_POR_MODO: Partial<Record<ModoEntrada, string>> = {
  "raio-x": "raio-x-processo",
  sala: "sala-juridica",
};

const MODOS: Array<{
  id: ModoEntrada;
  label: string;
  descricao: string;
  icon: typeof FileText;
}> = [
  {
    id: "relato",
    label: "Novo caso",
    descricao: "Criar caso a partir de relato, documentos ou ambos.",
    icon: FileText,
  },
  {
    id: "raio-x",
    label: "Raio-X",
    descricao:
      "Examinar documentos e evidências antes de abrir ou vincular o caso.",
    icon: ScanSearch,
  },
  {
    id: "sala",
    label: "Sala Jurídica",
    descricao:
      "Conversar, estruturar fatos, provas, teses e estratégia jurídica.",
    icon: Sparkles,
  },
];

function roleValue(role: unknown): string {
  if (role && typeof role === "object" && "value" in role) {
    return String((role as { value?: unknown }).value ?? "");
  }
  return String(role ?? "");
}

export function podeUsarRelato(role: unknown): boolean {
  return ROLES_RELATO.has(roleValue(role));
}

export function modoPadraoParaRole(role: unknown): ModoEntrada {
  return podeUsarRelato(role) ? "relato" : "sala";
}

export function ehModoEntrada(value: string | null): value is ModoEntrada {
  return value === "relato" || value === "raio-x" || value === "sala";
}

export function modoPermitidoParaRole(
  modo: ModoEntrada,
  role: unknown,
): boolean {
  return modo !== "relato" || podeUsarRelato(role);
}

export function modoDisponivelPorLifecycle(
  modo: ModoEntrada,
  settings: Record<string, ModuleLifecycleOverride>,
): boolean {
  const moduleKey = MODULO_POR_MODO[modo];
  if (!moduleKey) return true;
  const lifecycle = settings[moduleKey];
  return Boolean(
    !lifecycle || (lifecycle.enabled && lifecycle.status !== "disabled"),
  );
}

function hrefModo(modo: ModoEntrada, params: URLSearchParams): string {
  const proximos = new URLSearchParams(params);
  proximos.set("modo", modo);
  const query = proximos.toString();
  return query ? `/entrada?${query}` : "/entrada";
}

export default function EntradaUnica() {
  const { user } = useAuth();
  const settings = useModuleLifecycleStore((state) => state.settings);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const bruto = searchParams.get("modo");
  const candidato = ehModoEntrada(bruto)
    ? bruto
    : modoPadraoParaRole(user?.role);
  const modosVisiveis = MODOS.filter(
    (item) =>
      modoPermitidoParaRole(item.id, user?.role) &&
      modoDisponivelPorLifecycle(item.id, settings),
  );
  const modo =
    modoPermitidoParaRole(candidato, user?.role) &&
    modoDisponivelPorLifecycle(candidato, settings)
      ? candidato
      : (modosVisiveis[0]?.id ?? modoPadraoParaRole(user?.role));
  const ativo = MODOS.find((item) => item.id === modo) ?? modosVisiveis[0];

  const interceptarNavegacaoInterna = (
    evento: ReactMouseEvent<HTMLDivElement>,
  ) => {
    if (
      evento.defaultPrevented ||
      evento.button !== 0 ||
      evento.metaKey ||
      evento.ctrlKey ||
      evento.shiftKey ||
      evento.altKey
    ) {
      return;
    }
    const alvo = evento.target as HTMLElement | null;
    const link = alvo?.closest("a");
    if (!(link instanceof HTMLAnchorElement)) return;

    const url = new URL(link.href, window.location.origin);
    const modoDestino: ModoEntrada | null =
      url.pathname === "/sala-juridica"
        ? "sala"
        : url.pathname === "/raio-x"
          ? "raio-x"
          : null;
    if (
      !modoDestino ||
      !modoPermitidoParaRole(modoDestino, user?.role) ||
      !modoDisponivelPorLifecycle(modoDestino, settings)
    ) {
      return;
    }

    evento.preventDefault();
    const proximos = new URLSearchParams(searchParams);
    url.searchParams.forEach((valor, chave) => proximos.set(chave, valor));
    navigate(hrefModo(modoDestino, proximos));
  };

  return (
    <div className="space-y-4" onClickCapture={interceptarNavegacaoInterna}>
      <section className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-white/10 dark:bg-white/[0.03]">
        <div className="mb-3 px-1">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
            Entrada Jurídica
          </p>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Uma única porta para começar, analisar e estruturar o trabalho
            jurídico.
          </p>
        </div>
        <nav
          aria-label="Modos da Entrada Jurídica"
          className="flex flex-wrap gap-2"
        >
          {modosVisiveis.map((item) => {
            const Icone = item.icon;
            const selecionado = item.id === modo;
            return (
              <Link
                key={item.id}
                to={hrefModo(item.id, searchParams)}
                aria-current={selecionado ? "page" : undefined}
                title={item.descricao}
                className={`inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition ${
                  selecionado
                    ? "bg-slate-950 text-white dark:bg-white dark:text-slate-950"
                    : "border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/10"
                }`}
              >
                <Icone className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        {ativo && (
          <p className="mt-3 px-1 text-xs text-slate-500 dark:text-slate-400">
            {ativo.descricao}
          </p>
        )}
      </section>

      <Suspense
        fallback={
          <div className="grid min-h-[30vh] place-items-center">
            <Spinner />
          </div>
        }
      >
        {modo === "relato" && <EntradaRelato key="relato" />}
        {modo === "raio-x" && <RaioXProcesso key="raio-x" />}
        {modo === "sala" && <SalaJuridica key="sala" />}
      </Suspense>
    </div>
  );
}
