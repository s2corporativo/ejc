import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Clock3,
  ShieldAlert,
} from "lucide-react";
import { Link } from "react-router";
import api from "../lib/api";
import { useAuth } from "../stores/auth";

type PrazoRadar = {
  id: string;
  data_prazo: string;
  data_intimacao?: string | null;
  dias_restantes?: number;
  confirmado?: boolean;
  ciencia_confirmada?: boolean;
};

type DiagnosticoSub = { nome: string; status: string; detalhe?: string };

const GESTORES = new Set(["superadmin", "admin", "socio"]);

export default function DeadlineRiskStrip() {
  const role = useAuth((state) => state.user?.role);
  const [prazos, setPrazos] = useState<PrazoRadar[]>([]);
  const [calendario, setCalendario] = useState<DiagnosticoSub | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    const carregar = async () => {
      try {
        const res = await api.get("/deadlines/", {
          params: { status: "pendente", page_size: 100 },
        });
        if (!ativo) return;
        setPrazos(Array.isArray(res.data?.data) ? res.data.data : []);
        setErro(false);
      } catch {
        if (ativo) setErro(true);
      }

      if (role && GESTORES.has(role)) {
        try {
          const diag = await api.get("/diagnostico/central");
          const subs = Array.isArray(diag.data?.subsistemas)
            ? (diag.data.subsistemas as DiagnosticoSub[])
            : [];
          const item = subs.find((s) => s.nome === "Calendário jurídico de prazos");
          if (ativo) setCalendario(item ?? null);
        } catch {
          // O radar de prazos não depende da Central de Diagnóstico. Falha/flag
          // desabilitada apenas omite o sinal administrativo do calendário.
        }
      }
    };
    void carregar();
    return () => {
      ativo = false;
    };
  }, [role]);

  const risco = useMemo(() => {
    let vencidos = 0;
    let ate48h = 0;
    let preliminares = 0;
    let cienciaPendente = 0;
    let revisados = 0;

    for (const p of prazos) {
      const dias = Number(p.dias_restantes);
      if (Number.isFinite(dias)) {
        if (dias < 0) vencidos += 1;
        else if (dias <= 2) ate48h += 1;
      }
      if (p.confirmado === false) preliminares += 1;
      if (p.data_intimacao && !p.ciencia_confirmada) cienciaPendente += 1;
      if (p.confirmado && (!p.data_intimacao || p.ciencia_confirmada)) revisados += 1;
    }

    return { vencidos, ate48h, preliminares, cienciaPendente, revisados };
  }, [prazos]);

  if (erro) {
    return (
      <div className="mb-3 flex items-center justify-between rounded-2xl border border-amber-200 bg-amber-50/70 px-4 py-3 text-xs text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100">
        <span className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          Radar de prazos temporariamente indisponível.
        </span>
        <Link to="/prazos" className="font-semibold underline underline-offset-2">
          Abrir prazos
        </Link>
      </div>
    );
  }

  const calendarioAlerta = calendario && calendario.status !== "ok";

  return (
    <section className="mb-3 rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-3 shadow-sm backdrop-blur dark:border-white/10 dark:bg-slate-950/55">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-slate-950 text-[#e5ce7f] dark:bg-white/10">
            <ShieldAlert className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <strong className="text-xs font-semibold text-slate-900 dark:text-white">
              Radar de risco de prazos
            </strong>
            <p className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400">
              Contagens operacionais; confirmação jurídica continua humana.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[10px] font-semibold">
          <RiskChip
            icon={AlertTriangle}
            label={`${risco.vencidos} vencido(s)`}
            danger={risco.vencidos > 0}
          />
          <RiskChip
            icon={Clock3}
            label={`${risco.ate48h} até 48h`}
            warning={risco.ate48h > 0}
          />
          <RiskChip
            icon={CalendarClock}
            label={`${risco.preliminares} preliminar(es)`}
            warning={risco.preliminares > 0}
          />
          <RiskChip
            icon={AlertTriangle}
            label={`${risco.cienciaPendente} ciência pendente`}
            warning={risco.cienciaPendente > 0}
          />
          <RiskChip
            icon={CheckCircle2}
            label={`${risco.revisados} revisado(s)`}
            ok
          />
          {calendarioAlerta && (
            <RiskChip
              icon={ShieldAlert}
              label="calendário não validado"
              danger={calendario.status === "erro"}
              warning={calendario.status !== "erro"}
            />
          )}
        </div>

        <Link
          to="/prazos"
          className="inline-flex shrink-0 items-center gap-1 text-[10px] font-semibold text-slate-700 hover:text-amber-800 dark:text-slate-200 dark:hover:text-amber-200"
        >
          Abrir prazos <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </section>
  );
}

function RiskChip({
  icon: Icon,
  label,
  danger = false,
  warning = false,
  ok = false,
}: {
  icon: typeof AlertTriangle;
  label: string;
  danger?: boolean;
  warning?: boolean;
  ok?: boolean;
}) {
  const cls = danger
    ? "border-red-200 bg-red-50 text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200"
    : warning
      ? "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-200"
      : ok
        ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200"
        : "border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300";

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 ${cls}`}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label}
    </span>
  );
}
