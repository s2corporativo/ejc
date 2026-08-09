// Entrada Única (/entrada) — gateway canônico para iniciar trabalho jurídico.
// O fluxo de relato/documentos permanece em EntradaRelato. Sala Jurídica e
// Raio-X continuam como superfícies registradas e protegidas, mas deixam de
// disputar espaço no menu: o gateway encaminha para as rotas canônicas sem
// apagar lifecycle, ajuda contextual, ErrorBoundary ou identidade do caso.
import { FileText, ScanSearch, Sparkles } from "lucide-react";
import { Link, Navigate, useSearchParams } from "react-router";
import { useAuth } from "../stores/auth";
import EntradaRelato from "./EntradaRelato";

type ModoEntrada = "relato" | "raio-x" | "sala";

const ROLES_RELATO = new Set(["superadmin", "admin", "socio", "advogado"]);

const MODOS: Array<{
  id: ModoEntrada;
  label: string;
  descricao: string;
  icon: typeof FileText;
}> = [
  {
    id: "relato",
    label: "Relato ou documentos",
    descricao: "Criar um novo caso a partir do relato, documentos ou ambos.",
    icon: FileText,
  },
  {
    id: "raio-x",
    label: "Raio-X de documentos",
    descricao: "Analisar documentos antes de decidir pela abertura do caso.",
    icon: ScanSearch,
  },
  {
    id: "sala",
    label: "Conversa jurídica",
    descricao: "Estruturar fatos, provas e estratégia em conversa assistida.",
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

export function destinoModo(
  modo: Exclude<ModoEntrada, "relato">,
  params: URLSearchParams,
): string {
  const proximos = new URLSearchParams(params);
  proximos.delete("modo");
  const query = proximos.toString();
  const path = modo === "sala" ? "/sala-juridica" : "/raio-x";
  return query ? `${path}?${query}` : path;
}

function hrefModo(modo: ModoEntrada, params: URLSearchParams): string {
  const proximos = new URLSearchParams(params);
  proximos.set("modo", modo);
  const query = proximos.toString();
  return query ? `/entrada?${query}` : "/entrada";
}

export default function EntradaUnica() {
  const user = useAuth((state) => state.user);
  const [searchParams] = useSearchParams();
  const bruto = searchParams.get("modo");
  const modo = ehModoEntrada(bruto) ? bruto : modoPadraoParaRole(user?.role);

  if (modo === "sala" || modo === "raio-x") {
    return <Navigate replace to={destinoModo(modo, searchParams)} />;
  }

  if (!podeUsarRelato(user?.role)) {
    return (
      <section className="mx-auto max-w-3xl space-y-4 py-6">
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 dark:border-amber-400/20 dark:bg-amber-400/10">
          <h1 className="text-lg font-semibold text-slate-950 dark:text-white">
            Entrada Única
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
            A criação de caso por relato exige perfil de advogado. Seu perfil
            continua com acesso às superfícies jurídicas já permitidas; escolha
            Sala Jurídica ou Raio-X de documentos.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              to={hrefModo("sala", searchParams)}
              className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white dark:bg-white dark:text-slate-950"
            >
              Abrir Sala Jurídica
            </Link>
            <Link
              to={hrefModo("raio-x", searchParams)}
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 dark:border-white/15 dark:text-slate-200"
            >
              Abrir Raio-X
            </Link>
          </div>
        </div>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <nav
        aria-label="Modos da Entrada Única"
        className="flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-white/10 dark:bg-white/[0.03]"
      >
        {MODOS.map((item) => {
          const Icone = item.icon;
          const ativo = item.id === modo;
          return (
            <Link
              key={item.id}
              to={hrefModo(item.id, searchParams)}
              aria-current={ativo ? "page" : undefined}
              title={item.descricao}
              className={`inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition ${
                ativo
                  ? "bg-slate-950 text-white dark:bg-white dark:text-slate-950"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/10"
              }`}
            >
              <Icone className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <EntradaRelato />
    </div>
  );
}
