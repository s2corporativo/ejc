import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { FolderOpen, Route, X } from "lucide-react";
import { useCaseContext } from "../stores/caseContext";

// Rotas /casos/:id/* ativam o modo caso; /casos/novo é o wizard (não é caso).
const CASE_ROUTE = /^\/casos\/([^/]+)/;

/**
 * Faixa fina de "Modo Caso" exibida logo abaixo do header quando há um caso
 * ativo. Também é o ponto único que OBSERVA a rota e ativa o caso ao entrar
 * em /casos/:id/* (persistindo até o usuário sair pelo ✕).
 */
export default function CaseContextBar() {
  const { pathname } = useLocation();
  const caso = useCaseContext((state) => state.caso);
  const ativar = useCaseContext((state) => state.ativar);
  const sair = useCaseContext((state) => state.sair);

  useEffect(() => {
    const match = CASE_ROUTE.exec(pathname);
    const id = match?.[1];
    if (id && id !== "novo") void ativar(id);
  }, [pathname, ativar]);

  if (!caso) return null;

  return (
    <div className="border-b border-primary-200/60 bg-primary-50/95">
      <div className="flex h-9 items-center gap-2 px-4 text-xs md:px-7">
        <FolderOpen
          className="h-3.5 w-3.5 shrink-0 text-primary-700"
          aria-hidden="true"
        />
        <Link
          to={`/casos/${caso.id}`}
          className="min-w-0 truncate font-medium text-primary-900 hover:underline"
          title={
            caso.numero_processo
              ? `${caso.titulo} · Processo ${caso.numero_processo}`
              : caso.titulo
          }
        >
          {caso.titulo}
          {caso.cliente && (
            <span className="font-normal text-primary-700/80">
              {" — "}
              {caso.cliente}
            </span>
          )}
        </Link>
        <span className="ml-auto flex shrink-0 items-center gap-1">
          <Link
            to={`/casos/${caso.id}/jornada`}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 font-medium text-primary-700 transition-colors hover:bg-primary-100"
          >
            <Route className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Jornada</span>
          </Link>
          <button
            type="button"
            onClick={sair}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-primary-600 transition-colors hover:bg-primary-100 hover:text-primary-900"
            title="Sair do modo caso"
            aria-label="Sair do modo caso"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </span>
      </div>
    </div>
  );
}
