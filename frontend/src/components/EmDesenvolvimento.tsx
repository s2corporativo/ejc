import { Wrench } from "lucide-react";
import { PageHeader } from "./UI";

/**
 * Aviso padrão para telas cujo backend ainda não foi construído.
 * Evita que a página quebre/mostre dados vazios quando a API responde 404.
 */
export default function EmDesenvolvimento({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="space-y-5">
      <PageHeader eyebrow={eyebrow} title={title} subtitle={subtitle || "Módulo em construção."} />
      <div className="card p-10 text-center">
        <div className="flex justify-center mb-4 text-bronze-600">
          <Wrench size={36} />
        </div>
        <h3 className="text-lg font-serif text-navy mb-2">Módulo em desenvolvimento</h3>
        <p className="text-sm text-slate-500 max-w-md mx-auto">
          Esta funcionalidade está em construção e ainda não está disponível.
          Em breve estará ativa por aqui.
        </p>
      </div>
    </div>
  );
}
