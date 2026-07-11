import { FolderOpen, X } from "lucide-react";

/**
 * Chip removível "Filtrando por: {caso}" usado pelos módulos globais
 * (Documentos, Peças, Prazos) quando a listagem está filtrada por um caso —
 * seja via `?caso=` na URL, seja pelo caso ativo do Modo Caso.
 */
export default function CaseFilterChip({
  nome,
  onRemove,
}: {
  nome?: string | null;
  onRemove: () => void;
}) {
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-primary-200 bg-primary-50 px-3 py-1 text-xs font-medium text-primary-800">
      <FolderOpen className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="truncate">
        Filtrando por: {nome || "caso selecionado"}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="shrink-0 rounded-full p-0.5 text-primary-600 transition-colors hover:bg-primary-100 hover:text-primary-900"
        title="Remover filtro de caso"
        aria-label="Remover filtro de caso"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}
