import { Link2, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";

const DIAS = [
  "Domingo",
  "Segunda",
  "Terça",
  "Quarta",
  "Quinta",
  "Sexta",
  "Sábado",
];
const MES = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];

export default function Agenda() {
  const [icsUrl, setIcsUrl] = useState<string | null>(null);
  const [prazos, setPrazos] = useState<any[]>([]);
  const [tarefas, setTarefas] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/users/me/calendar-url")
      .then((r: any) => setIcsUrl(r.data?.url ?? null))
      .catch(() => {});
    Promise.allSettled([
      api.get("/deadlines/?status=pendente&page_size=200"),
      api.get("/tasks/"),
    ])
      .then(([a, b]) => {
        if (a.status === "fulfilled")
          setPrazos(a.value.data?.data ?? a.value.data?.items ?? []);
        if (b.status === "fulfilled")
          setTarefas(
            (
              b.value.data?.data ??
              b.value.data?.items ??
              b.value.data ??
              []
            ).filter(
              (t: any) =>
                (t.status ?? t.situacao) !== "concluida" &&
                !t.concluida &&
                !t.done,
            ),
          );
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );

  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  const dias = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(hoje);
    d.setDate(hoje.getDate() + i);
    return d;
  });
  const chave = (d: Date) => d.toISOString().slice(0, 10);
  const doDia = (d: Date) =>
    prazos.filter((p) => (p.data_prazo || "").slice(0, 10) === chave(d));
  const atrasados = prazos.filter((p) => (p.dias_restantes ?? 0) < 0);

  const cor = (tipo: string) =>
    tipo === "audiencia"
      ? "bg-purple-100 text-purple-700"
      : tipo === "prescricao"
        ? "bg-red-100 text-red-700"
        : "bg-sky-100 text-sky-700";

  return (
    <div>
      <PageHeader
        eyebrow="Agenda & prazos"
        title="Agenda da semana"
        subtitle="Prazos, audiências e tarefas dos próximos 7 dias"
      />

      {atrasados.length > 0 && (
        <div className="mb-5 card border-l-4 border-red-600 p-4">
          <p className="text-sm font-semibold text-red-700 mb-2">
            {atrasados.length} prazo(s) vencido(s)
          </p>
          <div className="space-y-1">
            {atrasados.slice(0, 5).map((p, i) => (
              <Link
                key={i}
                to="/prazos"
                className="block text-sm text-red-700 hover:underline"
              >
                • {p.titulo}
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-[1fr_18rem] gap-5">
        {/* Coluna dos 7 dias */}
        <div className="space-y-3">
          {dias.map((d, i) => {
            const itens = doDia(d);
            const ehHoje = i === 0;
            return (
              <div
                key={i}
                className={`card p-4 ${ehHoje ? "ring-1 ring-bronze" : ""}`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-serif font-semibold text-ink">
                    {ehHoje ? "Hoje" : DIAS[d.getDay()]}
                  </span>
                  <span className="text-xs text-slate-400">
                    {d.getDate()} {MES[d.getMonth()]}
                  </span>
                  {itens.length > 0 && (
                    <span className="ml-auto text-xs font-semibold text-bronze-deep">
                      {itens.length}
                    </span>
                  )}
                </div>
                {itens.length === 0 ? (
                  <p className="text-xs text-slate-300">Sem compromissos</p>
                ) : (
                  <div className="space-y-1.5">
                    {itens.map((p, j) => (
                      <Link
                        key={j}
                        to="/prazos"
                        className="flex items-center gap-2 text-sm hover:bg-bronze-50/50 -mx-1 px-1 rounded"
                      >
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${cor(p.tipo)}`}
                        >
                          {p.tipo}
                        </span>
                        <span className="text-slate-700 truncate">
                          {p.titulo}
                        </span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Pendências */}
        <div>
          <div className="card p-4 sticky top-20">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-semibold text-ink">Pendências</h3>
              <Link to="/tarefas" className="text-xs text-bronze font-semibold">
                Ver todas
              </Link>
            </div>
            {tarefas.length === 0 ? (
              <p className="text-sm text-slate-400 py-4 text-center">
                Nenhuma pendência ✓
              </p>
            ) : (
              <div className="space-y-2">
                {tarefas.slice(0, 12).map((t, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <span className="w-1.5 h-1.5 rounded-full bg-bronze shrink-0" />
                    <span className="text-slate-700 truncate">
                      {t.titulo || t.descricao}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Calendário ICS ─────────────────────────────── */}
      {icsUrl && (
        <div className="card p-4 mt-4">
          <p className="text-xs font-semibold text-gray-500 uppercase mb-2 flex items-center gap-1.5">
            <Link2 size={13} /> Feed de Calendário (ICS)
          </p>
          <p className="text-xs text-gray-500 mb-2">
            Assine este link no Google Calendar, Apple Calendar ou Outlook para
            sincronizar prazos automaticamente.
          </p>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={icsUrl}
              className="flex-1 text-xs border rounded px-2 py-1.5 bg-gray-50 text-gray-600 truncate"
            />
            <button
              onClick={() => {
                navigator.clipboard.writeText(icsUrl);
              }}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs border rounded bg-white hover:bg-gray-50 transition-colors text-gray-600"
            >
              <Copy size={12} /> Copiar
            </button>
            <a
              href={icsUrl}
              download="ejc-agenda.ics"
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs border rounded bg-white hover:bg-gray-50 transition-colors text-gray-600"
            >
              Download
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
