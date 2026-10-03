import {
  useId,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

type FieldProps = { label: string; containerClassName?: string };

export function FormInput({
  label,
  containerClassName,
  className = "input w-full",
  id,
  ...props
}: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  return (
    <div className={containerClassName}>
      <label className="label" htmlFor={fieldId}>
        {label}
      </label>
      <input {...props} id={fieldId} className={className} />
    </div>
  );
}

export function FormSelect({
  label,
  containerClassName,
  className = "input w-full",
  id,
  options,
  ...props
}: FieldProps &
  SelectHTMLAttributes<HTMLSelectElement> & {
    options: Record<string, string>;
  }) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  return (
    <div className={containerClassName}>
      <label className="label" htmlFor={fieldId}>
        {label}
      </label>
      <select {...props} id={fieldId} className={className}>
        {Object.entries(options).map(([key, value]) => (
          <option key={key} value={key}>
            {value}
          </option>
        ))}
      </select>
    </div>
  );
}

export function FormTextarea({
  label,
  containerClassName,
  className = "input w-full",
  id,
  ...props
}: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  return (
    <div className={containerClassName}>
      <label className="label" htmlFor={fieldId}>
        {label}
      </label>
      <textarea {...props} id={fieldId} className={className} />
    </div>
  );
}

type TemplateFields = {
  nome: string;
  area_juridica: string;
  descricao: string;
};

export function TemplateFormFields({
  value,
  onChange,
  namePlaceholder,
}: {
  value: TemplateFields;
  onChange: (patch: Partial<TemplateFields>) => void;
  namePlaceholder: string;
}) {
  return (
    <>
      <div className="grid md:grid-cols-2 gap-3">
        <FormInput
          label="Nome *"
          value={value.nome}
          onChange={(e) => onChange({ nome: e.target.value })}
          placeholder={namePlaceholder}
        />
        <FormInput
          label="Área jurídica"
          value={value.area_juridica}
          onChange={(e) => onChange({ area_juridica: e.target.value })}
          placeholder="trabalhista, cível…"
        />
      </div>
      <FormInput
        label="Descrição"
        value={value.descricao}
        onChange={(e) => onChange({ descricao: e.target.value })}
      />
    </>
  );
}
