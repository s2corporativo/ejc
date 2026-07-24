import {
  Bot,
  FileStack,
  ListChecks,
  PencilLine,
  ShieldCheck,
} from "lucide-react";

import type { ModoProducao, PecaModoMeta } from "../types/pecaWorkflow";

interface Props {
  modos: PecaModoMeta[];
  value: ModoProducao;
  onChange: (modo: ModoProducao) => void;
  caseId?: string | null;
  disabled?: boolean;
}

const ICONES: Record<ModoProducao, typeof PencilLine> = {
  livre: PencilLine,
  guiado: ListChecks,
  molde: FileStack,
  agente: Bot,
};

export default function PecaModoSelector({
  modos,
  value,
  onChange,
  caseId,
  disabled = false,
}: Props) {
  return (
    <fieldset disabled={disabled}>
      <legend className="mb-2 text-xs font-medium text-slate-600">
        Modo de produção
      </legend>

      <div className="grid gap-2 sm:grid-cols-2" role="group">
        {modos.map((modo) => {
          const Icone = ICONES[modo.value];
          const ativo = value === modo.value;
          const exigeCasoAusente = modo.exige_caso && !caseId;
          const indisponivel = disabled || exigeCasoAusente;

          return (
            <button
              key={modo.value}
              type="button"
              aria-label={`Modo ${modo.label}`}
              aria-pressed={ativo}
              disabled={indisponivel}
              onClick={() => onChange(modo.value)}
              className={`rounded-xl border p-3 text-left transition ${
                ativo
                  ? "border-primary-500 bg-primary-50 ring-1 ring-primary-200"
                  : "border-slate-200 bg-white hover:border-primary-300 hover:bg-slate-50"
              } disabled:cursor-not-allowed disabled:opacity-55`}
            >
              <div className="flex items-start gap-3">
                <span
                  className={`mt-0.5 rounded-lg p-2 ${
                    ativo
                      ? "bg-primary-100 text-primary-700"
                      : "bg-slate-100 text-slate-500"
                  }`}
                  aria-hidden="true"
                >
                  <Icone className="h-4 w-4" />
                </span>

                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-slate-800">
                    {modo.label}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">
                    {modo.descricao}
                  </span>

                  <span className="mt-2 flex flex-wrap gap-1.5">
                    {modo.exige_aprovacao && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                        <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                        Aprovação antes da redação
                      </span>
                    )}
                    {exigeCasoAusente && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                        Vincule um caso para usar
                      </span>
                    )}
                  </span>
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
