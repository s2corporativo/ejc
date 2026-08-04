import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { addDays, addWeeks, format, isSameDay, startOfWeek } from "date-fns";
import { ptBR } from "date-fns/locale";
import { ChevronLeft, ChevronRight } from "lucide-react";
import api from "../lib/api";

type EventoAgenda = {
  id: string;
  titulo?: string;
  data_evento?: string | null;
  concluido?: boolean | null;
};

/** "2026-08-04" | "2026-08-04T10:00:00" → Date local (sem shift de fuso). */
function parseDataEvento(valor?: string | null): Date | null {
  if (!valor) return null;
  const [ano, mes, dia] = valor.slice(0, 10).split("-").map(Number);
  if (!ano || !mes || !dia) return null;
  return new Date(ano, mes - 1, dia);
}

const LETRAS_DIAS = ["D", "S", "T", "Q", "Q", "S", "S"];

/**
 * Calendário semanal da base da sidebar (conceito aprovado): semana atual,
 * navegação entre semanas, dia de hoje destacado e pontos nos dias com
 * compromissos vindos da agenda REAL (/agenda-eventos/, já filtrada por
 * permissão no backend). Clicar num dia abre a Central de Atividades.
 */
export default function SidebarAgendaSemana({
  className,
}: {
  className?: string;
}) {
  const nav = useNavigate();
  const hoje = new Date();
  const [inicioSemana, setInicioSemana] = useState(() =>
    startOfWeek(new Date(), { weekStartsOn: 0 }),
  );
  const [eventos, setEventos] = useState<EventoAgenda[]>([]);

  useEffect(() => {
    let ativo = true;
    api
      .get("/agenda-eventos/", { params: { page_size: 500 } })
      .then((response) => {
        if (ativo) setEventos(response.data?.data ?? []);
      })
      .catch(() => {
        // Sem agenda disponível o calendário continua navegável, só sem pontos.
      });
    return () => {
      ativo = false;
    };
  }, []);

  const diasComEvento = useMemo(() => {
    const conjunto = new Set<string>();
    for (const evento of eventos) {
      const data = parseDataEvento(evento.data_evento);
      if (data) conjunto.add(format(data, "yyyy-MM-dd"));
    }
    return conjunto;
  }, [eventos]);

  const dias = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(inicioSemana, i)),
    [inicioSemana],
  );

  const rotuloSemana = `Semana de ${format(dias[0], "d")} a ${format(
    dias[6],
    "d 'de' MMM",
    { locale: ptBR },
  )}`;

  return (
    <div
      className={`sidebar-surface rounded-xl p-3 ${className || ""}`}
      aria-label="Calendário da semana"
    >
      <div className="mb-2 flex items-center justify-between gap-1">
        <span className="min-w-0 truncate text-[11px] font-semibold text-shell-text">
          {rotuloSemana}
        </span>
        <span className="flex shrink-0 items-center">
          <button
            type="button"
            onClick={() => setInicioSemana((atual) => addWeeks(atual, -1))}
            className="rounded-md p-1 text-shell-muted transition-colors hover:bg-white/10 hover:text-shell-text"
            aria-label="Semana anterior"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setInicioSemana((atual) => addWeeks(atual, 1))}
            className="rounded-md p-1 text-shell-muted transition-colors hover:bg-white/10 hover:text-shell-text"
            aria-label="Próxima semana"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </span>
      </div>
      <div className="grid grid-cols-7 gap-0.5 text-center">
        {LETRAS_DIAS.map((letra, i) => (
          <span
            key={`${letra}-${i}`}
            aria-hidden="true"
            className="text-[10px] font-medium text-shell-muted"
          >
            {letra}
          </span>
        ))}
        {dias.map((dia) => {
          const chave = format(dia, "yyyy-MM-dd");
          const ehHoje = isSameDay(dia, hoje);
          const temEvento = diasComEvento.has(chave);
          return (
            <button
              key={chave}
              type="button"
              onClick={() => nav("/atividades")}
              aria-label={`${format(dia, "d 'de' MMMM", { locale: ptBR })}${
                temEvento ? " — há compromissos" : ""
              } — abrir agenda`}
              className={`relative mx-auto flex h-7 w-7 items-center justify-center rounded-full text-[11px] tabular-nums transition-colors ${
                ehHoje
                  ? "bg-gold font-semibold text-shell-950"
                  : "text-shell-text/85 hover:bg-white/10"
              }`}
            >
              {format(dia, "d")}
              {temEvento && !ehHoje && (
                <span
                  aria-hidden="true"
                  className="absolute bottom-0.5 h-1 w-1 rounded-full bg-gold"
                />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
