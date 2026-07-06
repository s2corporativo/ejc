import { exportCsv } from "../utils/exportCsv";
import { exportPdf } from "../utils/exportPdf";
import { useEffect, useState } from "react";
import {
  Download,
  FileType2,
  Clock,
  TrendingUp,
  Users,
  Briefcase,
} from "lucide-react";
import api from "../lib/api";
import { PageHeader } from "../components/UI";

const PERIODOS = [
  { label: "7 dias", value: "7d" },
  { label: "30 dias", value: "30d" },
  { label: "3 meses", value: "90d" },
  { label: "1 ano", value: "365d" },
];

interface AdvData {
  id: string;
  nome: string;
  horas: number;
  horas_faturavel: number;
  lancamentos: number;
  casos: number;
  pct_faturavel: number;
}
interface AreaData {
  area: string;
  horas: number;
  horas_faturavel: number;
  casos: number;
}
interface TrendData {
  dia: string;
  horas: number;
}
interface ProdData {
  periodo: string;
  desde: string;
  resumo: {
    total_horas: number;
    horas_faturavel: number;
    pct_faturavel: number;
    lancamentos: number;
  };
  por_advogado: AdvData[];
  por_area: AreaData[];
  trend: TrendData[];
}

function StatCard({
  label,
  value,
  sub,
  icon,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-zinc-100 shadow-sm px-5 py-4 flex items-start gap-4">
      <div className="p-2.5 bg-bronze/8 rounded-lg text-bronze">{icon}</div>
      <div>
        <p className="text-xs text-zinc-400 uppercase tracking-wider mb-0.5">
          {label}
        </p>
        <p className="text-2xl font-light text-zinc-800">{value}</p>
        {sub && <p className="text-xs text-zinc-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

function BarRow({
  label,
  value,
  max,
  sub,
  color = "bg-bronze/60",
}: {
  label: string;
  value: number;
  max: number;
  sub?: string;
  color?: string;
}) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-zinc-700 truncate mr-2">{label}</span>
        <span className="text-sm font-light text-zinc-600 shrink-0">
          {value}h
        </span>
      </div>
      <div className="h-2 bg-zinc-100 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {sub && <p className="text-xs text-zinc-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function Produtividade() {
  const [periodo, setPeriodo] = useState("30d");
  const [data, setData] = useState<ProdData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .get(`/analytics/produtividade?periodo=${periodo}`)
      .then((r: { data: ProdData }) => setData(r.data))
      .finally(() => setLoading(false));
  }, [periodo]);

  const maxAdv = data
    ? Math.max(...(Array.isArray(data.por_advogado) ? data.por_advogado : []).map((a) => a.horas), 1)
    : 1;
  const maxArea = data ? Math.max(...(Array.isArray(data.por_area) ? data.por_area : []).map((a) => a.horas), 1) : 1;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <PageHeader
        title="Dashboard de Produtividade"
        subtitle="Horas trabalhadas por advogado e por área jurídica"
        actions={
          <div className="flex items-center gap-2">
            <div className="flex gap-1 bg-zinc-100 rounded-lg p-1">
              {PERIODOS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPeriodo(p.value)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${periodo === p.value ? "bg-white shadow-sm text-zinc-800" : "text-zinc-500 hover:text-zinc-700"}`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <button
              onClick={() =>
                data &&
                exportCsv(
                  data.por_advogado.map((a) => ({
                    advogado: a.nome,
                    horas: a.horas,
                    horas_faturavel: a.horas_faturavel,
                    pct_faturavel: a.pct_faturavel,
                    lancamentos: a.lancamentos,
                    casos: a.casos,
                  })),
                  `produtividade-${periodo}`,
                )
              }
              className="btn-secondary text-xs px-3 py-1.5"
              title="Exportar CSV"
            >
              <Download className="w-3.5 h-3.5" /> CSV
            </button>
            <button
              onClick={() =>
                data &&
                exportPdf(
                  `Produtividade — ${periodo}`,
                  ["Advogado", "Horas", "HH Fat.", "%Fat.", "Casos"],
                  data.por_advogado.map((a) => [
                    a.nome,
                    `${a.horas}h`,
                    `${a.horas_faturavel}h`,
                    `${a.pct_faturavel}%`,
                    String(a.casos),
                  ]),
                )
              }
              className="btn-secondary text-xs px-3 py-1.5"
              title="Exportar PDF"
            >
              <FileType2 className="w-3.5 h-3.5" /> PDF
            </button>
          </div>
        }
      />

      {loading ? (
        <div className="flex items-center justify-center h-40 text-zinc-400 text-sm">
          Carregando…
        </div>
      ) : !data ? (
        <div className="text-zinc-400 text-sm">Erro ao carregar dados.</div>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              label="HH Total"
              value={`${data.resumo.total_horas}h`}
              icon={<Clock className="w-4 h-4" />}
            />
            <StatCard
              label="HH Faturável"
              value={`${data.resumo.horas_faturavel}h`}
              sub={`${data.resumo.pct_faturavel}% do total`}
              icon={<TrendingUp className="w-4 h-4" />}
            />
            <StatCard
              label="Lançamentos"
              value={data.resumo.lancamentos}
              icon={<Briefcase className="w-4 h-4" />}
            />
            <StatCard
              label="Profissionais"
              value={data.por_advogado.length}
              icon={<Users className="w-4 h-4" />}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Por advogado */}
            <div className="bg-white rounded-xl border border-zinc-100 shadow-sm p-5">
              <h3 className="text-sm font-medium text-zinc-600 mb-4 flex items-center gap-2">
                <Users className="w-4 h-4 text-bronze" /> Por Advogado
              </h3>
              {data.por_advogado.length === 0 ? (
                <p className="text-sm text-zinc-300 italic">
                  Nenhum lançamento no período.
                </p>
              ) : (
                <div className="space-y-4">
                  {data.por_advogado.map((a) => (
                    <div key={a.id}>
                      <BarRow
                        label={a.nome}
                        value={a.horas}
                        max={maxAdv}
                        sub={`${a.horas_faturavel}h faturável (${a.pct_faturavel}%) · ${a.casos} caso(s)`}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Por área */}
            <div className="bg-white rounded-xl border border-zinc-100 shadow-sm p-5">
              <h3 className="text-sm font-medium text-zinc-600 mb-4 flex items-center gap-2">
                <Briefcase className="w-4 h-4 text-bronze" /> Por Área Jurídica
              </h3>
              {data.por_area.length === 0 ? (
                <p className="text-sm text-zinc-300 italic">
                  Nenhum dado no período.
                </p>
              ) : (
                <div className="space-y-4">
                  {data.por_area.map((a, i) => (
                    <BarRow
                      key={i}
                      label={a.area}
                      value={a.horas}
                      max={maxArea}
                      sub={`${a.horas_faturavel}h fat. · ${a.casos} caso(s)`}
                      color="bg-success-400/70"
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Trend */}
          {data.trend.length > 1 && (
            <div className="bg-white rounded-xl border border-zinc-100 shadow-sm p-5">
              <h3 className="text-sm font-medium text-zinc-600 mb-4 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-bronze" /> Evolução Diária
              </h3>
              <div className="flex items-end gap-0.5 h-24 overflow-x-auto pb-2">
                {(() => {
                  const mx = Math.max(...(Array.isArray(data.trend) ? data.trend : []).map((t) => t.horas), 1);
                  return (Array.isArray(data.trend) ? data.trend : []).map((t, i) => (
                    <div
                      key={i}
                      className="flex flex-col items-center gap-1 shrink-0"
                      style={{ minWidth: "10px", flex: "1 0 10px" }}
                    >
                      <div
                        className="w-full bg-bronze/50 rounded-t"
                        style={{ height: `${(t.horas / mx) * 80}px` }}
                        title={`${t.dia}: ${t.horas}h`}
                      />
                    </div>
                  ));
                })()}
              </div>
              <div className="flex justify-between text-xs text-zinc-300 mt-1">
                <span>{data.trend[0]?.dia?.slice(5)}</span>
                <span>{data.trend[data.trend.length - 1]?.dia?.slice(5)}</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
