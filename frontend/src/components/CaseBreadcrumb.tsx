import { Link } from "react-router";
import { ChevronRight } from "lucide-react";
import { areaLabel } from "../lib/areas";

/**
 * Breadcrumb padrão das telas internas do caso (/casos/:id/*):
 * "Casos → {título do caso} → {tela}".
 */
export default function CaseBreadcrumb({
  caseId,
  titulo,
  tela,
  area,
}: {
  caseId: string;
  titulo?: string | null;
  tela: string;
  area?: string | null;
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
      {area && (
        <>
          <span className="font-medium text-slate-500">{areaLabel(area)}</span>
          <ChevronRight className="h-3 w-3 text-slate-300" aria-hidden="true" />
        </>
      )}
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
