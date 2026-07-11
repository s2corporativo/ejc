// ── Visual Law: Linha do tempo processual ────────────────────────────────────
// Stepper de fases + banner de estagnação + timeline vertical filtrável +
// próximos passos estimados. Consome GET /visual-law/casos/{id}/timeline.
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  Check,
  FileText,
  Gavel,
  Lightbulb,
  Timer,
  Wallet,
} from "lucide-react";
import api from "../../lib/api";
import { toast } from "../Toast";
import { Empty, Spinner, cn, fmtDate } from "../UI";
import type {
  CategoriaEvento,
  TimelineEvento,
  VisualLawTimeline,
} from "../../types/visualLaw";

const CATEGORIAS: Array<{
  key: CategoriaEvento;
  label: string;
  chip: string;
  chipAtivo: string;
  dot: string;
  icone: React.ReactNode;
}> = [
  {
    key: "movimento",
    label: "Movimentos",
    chip: "border-primary-200 text-primary-700 hover:bg-primary-50",
    chipAtivo: "bg-primary-600 border-primary-600 text-white",
    dot: "border-primary-400 bg-primary-50 text-primary-600",
    icone: <Gavel className="h-3 w-3" />,
  },
  {
    key: "prazo",
    label: "Prazos",
    chip: "border-danger-200 text-danger-700 hover:bg-danger-50",
    chipAtivo: "bg-danger-600 border-danger-600 text-white",
    dot: "border-danger-400 bg-danger-50 text-danger-600",
    icone: <Timer className="h-3 w-3" />,
  },
  {
    key: "documento",
    label: "Documentos",
    chip: "border-violet-200 text-violet-700 hover:bg-violet-50",
    chipAtivo: "bg-violet-600 border-violet-600 text-white",
    dot: "border-violet-400 bg-violet-50 text-violet-600",
    icone: <FileText className="h-3 w-3" />,
  },
  {
    key: "honorario",
    label: "Honorários",
    chip: "border-emerald-200 text-emerald-700 hover:bg-emerald-50",
    chipAtivo: "bg-emerald-600 border-emerald-600 text-white",
    dot: "border-emerald-400 bg-emerald-50 text-emerald-600",
    icone: <Wallet className="h-3 w-3" />,
  },
];

const LIMITE_INICIAL = 30;
const DESCRICAO_CURTA = 160;

function EventoItem({ evento }: { evento: TimelineEvento }) {
  const [expandido, setExpandido] = useState(false);
  const cat =
    CATEGORIAS.find((c) => c.key === evento.categoria) ?? CATEGORIAS[0];
  const longa = evento.descricao.length > DESCRICAO_CURTA;
  const texto =
    longa && !expandido
      ? `${evento.descricao.slice(0, DESCRICAO_CURTA)}…`
      : evento.descricao;
  return (
    <div className="flex gap-3">
      <div
        className={cn(
          "z-10 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2",
          cat.dot,
        )}
      >
        {cat.icone}
      </div>
      <div className="card min-w-0 flex-1 p-3">
        <div className="flex flex-wrap items-start justify-between gap-x-2 gap-y-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            {cat.label.replace(/s$/, "")}
            {evento.tipo ? ` · ${evento.tipo.replace(/_/g, " ")}` : ""}
          </span>
          <span className="shrink-0 text-xs text-slate-400">
            {fmtDate(evento.data)}
          </span>
        </div>
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">
          {texto}
        </p>
        {longa && (
          <button
            type="button"
            onClick={() => setExpandido((v) => !v)}
            className="mt-1 text-xs font-medium text-primary-600 hover:underline"
          >
            {expandido ? "Recolher" : "Ler descrição completa"}
          </button>
        )}
      </div>
    </div>
  );
}

export default function LinhaDoTempoProcessual({ caseId }: { caseId: string }) {
  const [data, setData] = useState<VisualLawTimeline | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(false);
  const [filtros, setFiltros] = useState<CategoriaEvento[]>([]);
  const [limite, setLimite] = useState(LIMITE_INICIAL);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    setErro(false);
    api
      .get<VisualLawTimeline>(`/visual-law/casos/${caseId}/timeline`)
      .then((r) => {
        if (ativo) setData(r.data);
      })
      .catch(() => {
        if (!ativo) return;
        setErro(true);
        toast.error("Falha ao carregar a linha do tempo do processo");
      })
      .finally(() => {
        if (ativo) setCarregando(false);
      });
    return () => {
      ativo = false;
    };
  }, [caseId]);

  if (carregando) return <Spinner />;
  if (erro || !data) {
    return <Empty message="Não foi possível carregar a linha do tempo" />;
  }

  const alternarFiltro = (cat: CategoriaEvento) => {
    setLimite(LIMITE_INICIAL);
    setFiltros((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat],
    );
  };

  const eventosFiltrados =
    filtros.length === 0
      ? data.eventos
      : data.eventos.filter((e) => filtros.includes(e.categoria));
  const eventosVisiveis = eventosFiltrados.slice(0, limite);
  const estagnacao = data.estagnacao;

  return (
    <div className="space-y-6">
      {/* Stepper horizontal das fases */}
      {data.fases.length > 0 && (
        <div className="card overflow-x-auto p-4 scrollbar-thin">
          <ol className="flex min-w-max items-start">
            {data.fases.map((fase, i) => (
              <li key={fase.fase} className="flex items-start">
                {i > 0 && (
                  <div
                    className={cn(
                      "mt-4 h-0.5 w-8 sm:w-14",
                      fase.status === "futura"
                        ? "bg-slate-200"
                        : "bg-primary-500",
                    )}
                  />
                )}
                <div className="flex w-24 flex-col items-center gap-1.5 text-center sm:w-28">
                  <div
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-full border-2 text-xs font-semibold transition-all",
                      fase.status === "concluida" &&
                        "border-primary-600 bg-primary-600 text-white",
                      fase.status === "atual" &&
                        "border-primary-600 bg-white text-primary-700 ring-4 ring-primary-200",
                      fase.status === "futura" &&
                        "border-slate-200 bg-slate-50 text-slate-400",
                    )}
                  >
                    {fase.status === "concluida" ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      i + 1
                    )}
                  </div>
                  <span
                    className={cn(
                      "text-[11px] leading-tight",
                      fase.status === "atual"
                        ? "font-semibold text-slate-900"
                        : fase.status === "concluida"
                          ? "font-medium text-slate-600"
                          : "text-slate-400",
                    )}
                  >
                    {fase.label}
                  </span>
                  {fase.status === "atual" && (
                    <span className="rounded-full bg-primary-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary-700 ring-1 ring-inset ring-primary-200">
                      fase atual
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Banner de estagnação */}
      {estagnacao.nivel !== "ok" && (
        <div
          role="alert"
          className={cn(
            "flex items-start gap-3 rounded-xl border px-4 py-3 text-sm",
            estagnacao.nivel === "critico"
              ? "animate-pulse border-danger-300 bg-danger-50 text-danger-800"
              : "border-amber-300 bg-amber-50 text-amber-800",
          )}
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">
              {estagnacao.nivel === "critico"
                ? "Estagnação crítica"
                : "Atenção: processo parado"}
            </p>
            <p className="mt-0.5">
              Sem movimentação há {estagnacao.dias_parado}{" "}
              {estagnacao.dias_parado === 1 ? "dia" : "dias"}. Avalie
              diligências para impulsionar o processo.
            </p>
          </div>
        </div>
      )}

      {/* Linha do tempo vertical de eventos */}
      <div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold uppercase text-slate-500">
            Eventos do processo
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {CATEGORIAS.map((cat) => {
              const ativo = filtros.includes(cat.key);
              return (
                <button
                  key={cat.key}
                  type="button"
                  onClick={() => alternarFiltro(cat.key)}
                  aria-pressed={ativo}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                    ativo ? cat.chipAtivo : cn("bg-white", cat.chip),
                  )}
                >
                  {cat.icone}
                  {cat.label}
                </button>
              );
            })}
          </div>
        </div>
        {eventosFiltrados.length === 0 ? (
          <Empty
            message={
              filtros.length > 0
                ? "Nenhum evento nas categorias selecionadas"
                : "Nenhum evento registrado neste processo"
            }
          />
        ) : (
          <div className="relative">
            <div className="absolute bottom-0 left-3 top-0 w-0.5 bg-slate-200" />
            <div className="space-y-3">
              {eventosVisiveis.map((evento, i) => (
                <EventoItem
                  key={`${evento.data}-${evento.categoria}-${i}`}
                  evento={evento}
                />
              ))}
            </div>
            {eventosFiltrados.length > limite && (
              <div className="mt-3 flex justify-center">
                <button
                  type="button"
                  onClick={() => setLimite((l) => l + LIMITE_INICIAL)}
                  className="btn-secondary text-xs"
                >
                  Mostrar mais ({eventosFiltrados.length - limite} restantes)
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Próximos passos estimados */}
      {data.proximos_passos.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase text-slate-500">
            Próximos passos estimados
          </h3>
          <div className="space-y-2">
            {data.proximos_passos.map((passo, i) => (
              <div
                key={`${passo.titulo}-${i}`}
                className="card flex items-start gap-3 p-3"
              >
                <div
                  className={cn(
                    "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset",
                    passo.origem === "prazo"
                      ? "bg-danger-50 text-danger-600 ring-danger-200"
                      : "bg-amber-50 text-amber-600 ring-amber-200",
                  )}
                >
                  {passo.origem === "prazo" ? (
                    <CalendarClock className="h-4 w-4" />
                  ) : (
                    <Lightbulb className="h-4 w-4" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-slate-800">
                      {passo.titulo}
                    </span>
                    {passo.origem === "estimativa" ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                        estimativa
                      </span>
                    ) : (
                      <span className="rounded-full bg-danger-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger-700">
                        prazo
                      </span>
                    )}
                  </div>
                  {passo.detalhe && (
                    <p className="mt-0.5 text-xs text-slate-500">
                      {passo.detalhe}
                    </p>
                  )}
                  <p className="mt-0.5 text-xs text-slate-400">
                    {passo.origem === "prazo"
                      ? `Data do prazo: ${fmtDate(passo.data_estimada)}`
                      : passo.data_estimada
                        ? `Data estimada (não é dado do processo): ${fmtDate(passo.data_estimada)}`
                        : "Sem data estimada — projeção, não é dado do processo"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
