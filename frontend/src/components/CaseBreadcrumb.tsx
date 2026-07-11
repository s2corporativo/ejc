import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

/**
 * Breadcrumb padrão das telas internas do caso (/casos/:id/*):
 * "Casos → {título do caso} → {tela}".
 */
export default function CaseBreadcrumb({
  caseId,
  titulo,
  tela,
}: {
  caseId: string;
  titulo?: string | null;
  tela: string;
}) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="mb-3 flex flex-wrap items-center gap-1 text-xs text-slate-500"
    >
      <Link to="/casos" className="transition-colors hover:text-primary-700">
        Casos
      </Link>
      <ChevronRight className="h-3 w-3 text-slate-300" aria-hidden="true" />
      <Link
        to={`/casos/${caseId}`}
        className="max-w-[14rem] truncate transition-colors hover:text-primary-700"
        title={titulo || undefined}
      >
        {titulo || "Caso"}
      </Link>
      <ChevronRight className="h-3 w-3 text-slate-300" aria-hidden="true" />
      <span className="font-medium text-slate-700">{tela}</span>
    </nav>
  );
}
