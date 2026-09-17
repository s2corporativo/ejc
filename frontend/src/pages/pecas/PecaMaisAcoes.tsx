// Menu "Mais ações" da linha de peça (auditoria §2.6 #10).
//
// Extraído do monólito Pecas.tsx: menu contextual com exportações (PDF/DOCX/
// Visual Law), impressão e as ferramentas de inteligência (validação,
// jurisprudência, crítica da IA).
import {
  MoreHorizontal,
  FileDown,
  Printer,
  ShieldCheck,
  SearchCheck,
  Sparkles,
} from "lucide-react";
import type { ReactNode } from "react";
import type { LegalDoc } from "../../types";

export default function MaisAcoes({
  doc,
  gerandoVL,
  onPdf,
  onDocx,
  onVisualLaw,
  onPrint,
  onJuris,
  onValidar,
  onAuditar,
}: {
  doc: LegalDoc;
  gerandoVL: boolean;
  onPdf: (doc: LegalDoc) => void;
  onDocx: (doc: LegalDoc) => void;
  onVisualLaw: (doc: LegalDoc) => void;
  onPrint: (doc: LegalDoc) => void;
  onJuris: (doc: LegalDoc) => void;
  onValidar: (doc: LegalDoc) => void;
  onAuditar: (doc: LegalDoc) => void;
}) {
  return (
    <details className="relative">
      <summary className="btn-ghost list-none cursor-pointer px-2.5 py-1.5 text-xs [&::-webkit-details-marker]:hidden">
        <MoreHorizontal size={16} />
        <span className="sr-only">Mais ações</span>
      </summary>
      <div className="absolute right-0 z-30 mt-1 w-52 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg">
        <MenuAction
          label="PDF"
          icon={<FileDown size={14} />}
          onClick={() => onPdf(doc)}
        />
        <MenuAction
          label="DOCX"
          icon={<FileDown size={14} />}
          onClick={() => onDocx(doc)}
        />
        <MenuAction
          label={
            gerandoVL ? "Gerando Visual Law..." : "Documento único / Visual Law"
          }
          icon={<FileDown size={14} />}
          disabled={gerandoVL}
          onClick={() => onVisualLaw(doc)}
        />
        <MenuAction
          label="Imprimir"
          icon={<Printer size={14} />}
          onClick={() => onPrint(doc)}
        />
        <div className="my-1 border-t border-slate-100" />
        <MenuAction
          label="Revisão jurídica"
          icon={<ShieldCheck size={14} />}
          onClick={() => onValidar(doc)}
        />
        <MenuAction
          label="Jurisprudência e citações"
          icon={<SearchCheck size={14} />}
          onClick={() => onJuris(doc)}
        />
        <MenuAction
          label="Crítica da peça"
          icon={<Sparkles size={14} />}
          onClick={() => onAuditar(doc)}
        />
      </div>
    </details>
  );
}

function MenuAction({
  label,
  icon,
  onClick,
  disabled = false,
}: {
  label: string;
  icon: ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
    >
      {icon}
      {label}
    </button>
  );
}
