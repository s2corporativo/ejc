// Badges e elementos de linha da lista de peças (auditoria §2.6 #10).
//
// Extraído do monólito Pecas.tsx: pequenos renderizadores compartilhados
// entre os cartões mobile e a tabela desktop.
import { Link } from "react-router";
import { FolderOpen } from "lucide-react";
import { Badge } from "../../components/UI";
import type { LegalDoc } from "../../types";

export function origemBadge(doc: LegalDoc) {
  return doc.ai_generated ? (
    doc.human_reviewed ? (
      <Badge tone="green">IA revisada</Badge>
    ) : (
      <Badge tone="amber">IA · revisar</Badge>
    )
  ) : (
    <Badge tone="slate">Manual</Badge>
  );
}

export function casoLink(doc: LegalDoc) {
  return doc.case_id ? (
    <Link
      to={`/casos/${doc.case_id}`}
      className="inline-flex items-center gap-1 text-xs text-primary-700 hover:underline"
    >
      <FolderOpen size={13} /> Ver caso
    </Link>
  ) : (
    <span className="text-xs text-slate-400">sem caso</span>
  );
}

export function ResumoItem({
  label,
  valor,
}: {
  label: string;
  valor?: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs uppercase tracking-wide text-slate-400">
        {label}
      </span>
      <span className="text-sm font-medium text-navy">{valor || "—"}</span>
    </div>
  );
}
