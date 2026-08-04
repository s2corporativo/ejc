import { useMemo } from "react";
import { Quote } from "lucide-react";
import { mensagemDoDia } from "../../content/mensagensDoDia";

/**
 * Versículo/mensagem do dia no cabeçalho — base local auditável
 * (src/content/mensagensDoDia.ts), rotação determinística por dia, sem
 * API externa. Fallback seguro embutido no próprio `mensagemDoDia()`.
 */
export default function MensagemDia({ className }: { className?: string }) {
  // Recalcula só quando o dia muda (chave = data corrente do render).
  const hojeChave = new Date().toDateString();
  const mensagem = useMemo(
    () => mensagemDoDia(new Date()),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hojeChave],
  );

  return (
    <div
      className={`flex min-w-0 items-center gap-2 ${className || ""}`}
      title={
        mensagem.referencia
          ? `${mensagem.texto} — ${mensagem.referencia}`
          : mensagem.texto
      }
    >
      <Quote
        className="h-3.5 w-3.5 shrink-0 -scale-x-100 text-gold"
        aria-hidden="true"
      />
      <p className="min-w-0 truncate text-[13px] italic leading-tight text-shell-text/90">
        {mensagem.texto}
        {mensagem.referencia && (
          <span className="ml-2 not-italic text-[11px] font-semibold text-gold-light">
            {mensagem.referencia}
          </span>
        )}
      </p>
    </div>
  );
}
