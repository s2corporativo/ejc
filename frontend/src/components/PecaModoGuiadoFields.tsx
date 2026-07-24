import { FieldLabel, Textarea } from "./UI";

interface Props {
  campos: string[];
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
  disabled?: boolean;
}

function labelCampo(campo: string): string {
  const texto = campo.replace(/_/g, " ").trim();
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : "Campo";
}

export default function PecaModoGuiadoFields({
  campos,
  value,
  onChange,
  disabled = false,
}: Props) {
  const preenchidos = campos.filter((campo) => value[campo]?.trim()).length;

  if (!campos.length) {
    return (
      <div className="rounded-xl border border-warn-200 bg-warn-50 px-4 py-3 text-sm text-warn-800">
        O backend não informou campos guiados para este tipo de peça. A geração
        permanece bloqueada até o catálogo ser revisado.
      </div>
    );
  }

  return (
    <fieldset disabled={disabled} className="space-y-4">
      <legend className="text-sm font-semibold text-slate-800">
        Informações jurídicas estruturadas
      </legend>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs leading-5 text-slate-500">
          Preencha somente informações confirmadas. Lacunas devem permanecer
          explícitas para revisão do advogado.
        </p>
        <span className="shrink-0 text-xs text-slate-500">
          {preenchidos} de {campos.length} preenchidos
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {campos.map((campo) => {
          const label = labelCampo(campo);
          return (
            <div key={campo} className="min-w-0">
              <FieldLabel required>{label}</FieldLabel>
              <Textarea
                id={`peca-guiada-${campo}`}
                name={campo}
                value={value[campo] ?? ""}
                onChange={(event) =>
                  onChange({ ...value, [campo]: event.target.value })
                }
                maxLength={6000}
                aria-label={label}
                aria-required="true"
                placeholder={`Informe ${label.toLowerCase()}`}
                className="min-h-28"
              />
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
