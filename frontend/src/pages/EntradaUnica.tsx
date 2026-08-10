// Entrada Única (/entrada) — gateway canônico para iniciar trabalho jurídico.
//
// O RBAC desta rota é definido uma única vez em moduleRegistry/RoleOnly e
// confirmado pelo backend em /api/entrada. Este componente não replica a
// matriz de papéis: ele apenas roteia intenções e preserva query/contexto.
// Sala Jurídica e Raio-X continuam como superfícies canônicas independentes,
// mantendo lifecycle, ajuda contextual, ErrorBoundary e manifests próprios.
import { FileText, ScanSearch, Sparkles } from "lucide-react";
import { Link, Navigate, useSearchParams } from "react-router";
import EntradaRelato from "./EntradaRelato";

export type ModoEntrada = "relato" | "raio-x" | "sala";

const MODO_PADRAO: ModoEntrada = "relato";

const MODOS = [
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
] as const satisfies ReadonlyArray<{
  id: ModoEntrada;
  label: string;
  descricao: string;
  icon: typeof FileText;
}>;

export function ehModoEntrada(value: string | null): value is ModoEntrada {
  return value === "relato" || value === "raio-x" || value === "sala";
}

export function normalizarModoEntrada(value: string | null): ModoEntrada {
  return ehModoEntrada(value) ? value : MODO_PADRAO;
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
  return `/entrada?${proximos.toString()}`;
}

export default function EntradaUnica() {
  const [searchParams] = useSearchParams();
  const modoBruto = searchParams.get("modo");
  const modo = normalizarModoEntrada(modoBruto);

  // URLs com modo desconhecido são normalizadas para uma forma canônica. Isso
  // evita estado ambíguo em analytics, histórico, testes e links compartilhados.
  if (modoBruto !== null && !ehModoEntrada(modoBruto)) {
    return <Navigate replace to={hrefModo(MODO_PADRAO, searchParams)} />;
  }

  if (modo === "sala" || modo === "raio-x") {
    return <Navigate replace to={destinoModo(modo, searchParams)} />;
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
