import { AlertTriangle, CheckCircle2, LoaderCircle } from "lucide-react";
import {
  ATTENTION_LABEL,
  STATUS_LABEL,
  humanStatus,
  type DocumentItem,
} from "../../services/documents";

export default function DocumentStatusBadge({ document }: { document: DocumentItem }) {
  const status = humanStatus(document);
  const reasons = (document.attention_reasons || [])
    .map((reason) => ATTENTION_LABEL[reason] || reason)
    .join(" · ");

  if (status === "processing") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 ring-1 ring-blue-200 dark:bg-blue-950/30 dark:text-blue-300 dark:ring-blue-800"
        title="O EJC está processando o documento."
      >
        <LoaderCircle size={12} className="animate-spin" />
        {STATUS_LABEL.processing}
      </span>
    );
  }

  if (status === "attention") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:ring-amber-800"
        title={reasons || "Este documento precisa de atenção."}
      >
        <AlertTriangle size={12} />
        {STATUS_LABEL.attention}
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-800"
      title="Documento pronto para uso."
    >
      <CheckCircle2 size={12} />
      {STATUS_LABEL.ready}
    </span>
  );
}
