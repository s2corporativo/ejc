import { useEffect, useMemo, useState } from "react";
import { Clock } from "lucide-react";
import { EJC_TIMEZONE } from "../../config/office";

/**
 * Hora e data do cabeçalho — formato brasileiro, fuso configurável
 * (VITE_EJC_TIMEZONE). Componente isolado: o tick de minuto re-renderiza
 * SÓ este nó, nunca o Layout inteiro.
 */
export default function RelogioAgora({ className }: { className?: string }) {
  const [agora, setAgora] = useState(() => new Date());

  useEffect(() => {
    // Alinha o próximo tick à virada do minuto e segue de minuto em minuto —
    // hora sem segundos não precisa de intervalo mais fino.
    let intervalo: ReturnType<typeof setInterval> | undefined;
    const atraso = 60_000 - (Date.now() % 60_000);
    const alinhamento = setTimeout(() => {
      setAgora(new Date());
      intervalo = setInterval(() => setAgora(new Date()), 60_000);
    }, atraso);
    return () => {
      clearTimeout(alinhamento);
      if (intervalo) clearInterval(intervalo);
    };
  }, []);

  const { hora, data } = useMemo(() => {
    try {
      return {
        hora: new Intl.DateTimeFormat("pt-BR", {
          timeZone: EJC_TIMEZONE,
          hour: "2-digit",
          minute: "2-digit",
        }).format(agora),
        data: new Intl.DateTimeFormat("pt-BR", {
          timeZone: EJC_TIMEZONE,
          weekday: "long",
          day: "numeric",
          month: "long",
        }).format(agora),
      };
    } catch {
      // Fuso inválido configurado não pode derrubar o cabeçalho.
      return {
        hora: new Intl.DateTimeFormat("pt-BR", {
          hour: "2-digit",
          minute: "2-digit",
        }).format(agora),
        data: new Intl.DateTimeFormat("pt-BR", {
          weekday: "long",
          day: "numeric",
          month: "long",
        }).format(agora),
      };
    }
  }, [agora]);

  return (
    <div
      className={`flex items-center gap-2.5 ${className || ""}`}
      aria-label={`Agora: ${hora}, ${data}`}
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-gold/40 text-gold">
        <Clock className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 leading-tight">
        <span className="block text-lg font-semibold tabular-nums text-shell-text">
          {hora}
        </span>
        <span className="block truncate text-[11px] text-shell-muted first-letter:uppercase">
          {data}
        </span>
      </span>
    </div>
  );
}
