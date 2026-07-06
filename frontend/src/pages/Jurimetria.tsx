import { useEffect, useState } from "react";
import { Database } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";
import { asList } from "../lib/list";

const TRIBUNAIS = ["TJMG", "STJ", "STF", "TRF1", "TRT3"];

function Bars({
  titulo,
  rows,
  label,
  val,
  cor = "bg-primary-500",
}: {
  titulo: string;
  rows: any[];
  label: (r: any) => string;
  val: (r: any) => number;
  cor?: string;
}) {
  const max = Math.max(1, ...rows.map(val));
  return (
    <div className="card p-5">
      <h3 className="font-semibold text-sm text-gray-500 uppercase mb-3">
        {titulo}
      </h3>
      {rows.length === 0 ? (
        <p className="text-gray-400 text-sm text-center py-4">
          Sem dados ainda
        </p>
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 12).map((r, i) => (
            <div key={i}>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-gray-600">{label(r)}</span>
                <span className="text-gray-400">{val(r)}</span>
              </div>
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full ${cor}`}
                  style={{ width: `${(val(r) / max) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="card p-4 text-center">
      <p className="text-xs text-gray-500 uppercase mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-800">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function Jurimetria() {
  const [ov, setOv] = useState<any>(null);
  const [area, setArea] = useState<any[]>([]);
  const [trib, setTrib] = useState<any[]>([]);
  const [tese, setTese] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [desfechos, setDesfechos] = useState<any>(null);

  // Predição por taxa histórica (heurística estatística, não ML)
  const [predForm, setPredForm] = useState({
    classe: "",
    tribunal: "TJMG",
    dias: "365",
  });
  const [predicao, setPredicao] = useState<any>(null);
  const [loadingPred, setLoadingPred] = useState(false);

  const prever = async () => {
    if (!predForm.classe) return;
    setLoadingPred(true);
    try {
      const r = await api.get(
        `/jurimetria/ext/predicao/provimento?classe=${predForm.classe}&tribunal=${predForm.tribunal}&dias_estimados=${predForm.dias}`,
      );
      setPredicao(r.data);
    } catch {
      setPredicao(null);
    } finally {
      setLoadingPred(false);
    }
  };

  // Dados externos (DataJud/STJ)
  const [extStats, setExtStats] = useState<any>(null);
  const [benchmarks, setBenchmarks] = useState<any>(null);
  const [selectedTribunal, setSelectedTribunal] = useState("TJMG");
  const [loadingExt, setLoadingExt] = useState(false);

  useEffect(() => {
    api
      .get("/jurimetria/desfechos")
      .then((r: any) => setDesfechos(r.data))
      .catch(() => {});
    Promise.allSettled([
      api.get("/jurimetria/overview"),
      api.get("/jurimetria/por-area"),
      api.get("/jurimetria/por-tribunal"),
      api.get("/jurimetria/por-tese"),
    ])
      .then(([a, b, c, d]) => {
        if (a.status === "fulfilled") setOv(a.value.data);
        if (b.status === "fulfilled")
          setArea(asList(b.value.data));
        if (c.status === "fulfilled")
          setTrib(asList(c.value.data));
        if (d.status === "fulfilled")
          setTese(asList(d.value.data));
      })
      .finally(() => setLoading(false));

    // Estatisticas da base externa
    api
      .get("/jurimetria/ext/stats")
      .then((r: any) => setExtStats(r.data))
      .catch(() => {});
  }, []);

  const carregarBenchmarks = async () => {
    setLoadingExt(true);
    try {
      const r = await api.get(
        `/jurimetria/ext/benchmarks?tribunal=${selectedTribunal}`,
      );
      setBenchmarks(r.data);
    } catch {
      setBenchmarks(null);
    } finally {
      setLoadingExt(false);
    }
  };

  useEffect(() => {
    carregarBenchmarks();
  }, [selectedTribunal]);

  if (loading)
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );

  const taxa = ov?.taxa_sucesso_geral;
  const totalExt =
    extStats?.por_tribunal?.reduce((s: number, t: any) => s + t.total, 0) ?? 0;

  return (
    <div>
      <PageHeader
        title="Jurimetria"
        subtitle="Desempenho do escritório + benchmarks externos DataJud/STJ"
      />

      {/* Cards resumo escritório */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Taxa de Sucesso"
          value={taxa != null ? `${(taxa * 100).toFixed(1)}%` : "—"}
          sub="casos encerrados"
        />
        <StatCard label="Áreas" value={area.length} sub="com processos" />
        <StatCard label="Tribunais" value={trib.length} sub="no escritório" />
        <StatCard
          label="Base Externa"
          value={totalExt.toLocaleString("pt-BR")}
          sub="processos DataJud"
        />
      </div>

      {/* Desfechos reais */}
      {desfechos?.por_resultado?.length > 0 && (
        <div className="card p-5 mb-6">
          <h3 className="font-semibold text-sm text-gray-500 uppercase mb-3">
            Desfechos Reais — {desfechos.total_encerrados} casos encerrados
          </h3>
          <div className="space-y-2">
            {desfechos.por_resultado.map((r: any, i: number) => (
              <div key={i}>
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-600 capitalize">
                    {r.resultado?.replace("_", " ") || "—"}
                  </span>
                  <span className="text-gray-500">
                    {r.total} ({r.pct?.toFixed(1)}%)
                  </span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={
                      r.pct > 50
                        ? "h-full bg-green-500"
                        : r.pct > 25
                          ? "h-full bg-yellow-400"
                          : "h-full bg-danger-400"
                    }
                    style={{ width: `${r.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Seção benchmarks externos */}
      <div className="card p-5 mb-6">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="flex items-center gap-1.5">
            <Database size={16} className="text-primary-500" />
            <h3 className="font-semibold text-sm text-gray-700 uppercase">
              Benchmarks DataJud
            </h3>
          </div>
          <div className="flex gap-2 flex-wrap">
            {TRIBUNAIS.map((t) => (
              <button
                key={t}
                onClick={() => setSelectedTribunal(t)}
                className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                  selectedTribunal === t
                    ? "bg-primary-600 text-white border-primary-600"
                    : "text-gray-600 border-gray-300 hover:border-primary-400"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {loadingExt ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : benchmarks ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-800">
                {benchmarks.tempo_tramitacao?.media_dias != null
                  ? `${Math.round(benchmarks.tempo_tramitacao.media_dias)}d`
                  : "—"}
              </p>
              <p className="text-xs text-gray-500">Duração média</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-800">
                {benchmarks.tempo_tramitacao?.mediana_dias != null
                  ? `${Math.round(benchmarks.tempo_tramitacao.mediana_dias)}d`
                  : "—"}
              </p>
              <p className="text-xs text-gray-500">Mediana duração</p>
            </div>
            <div className="text-center col-span-2">
              <p className="text-2xl font-bold text-gray-800">
                {benchmarks.tempo_tramitacao?.total_processos?.toLocaleString(
                  "pt-BR",
                ) ?? "0"}
              </p>
              <p className="text-xs text-gray-500">
                Processos encerrados na base
              </p>
            </div>
            {benchmarks.por_resultado?.length > 0 && (
              <div className="col-span-4 mt-3 space-y-2">
                <p className="text-xs text-gray-500 font-medium uppercase">
                  Distribuição de Resultados
                </p>
                {benchmarks.por_resultado.map((r: any, i: number) => (
                  <div key={i}>
                    <div className="flex justify-between text-xs mb-0.5">
                      <span className="capitalize text-gray-600">
                        {(r.resultado || "outro").replace("_", " ")}
                      </span>
                      <span className="text-gray-400">
                        {r.pct?.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary-500"
                        style={{ width: `${r.pct ?? 0}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <p className="text-gray-400 text-sm text-center py-6">
            Sem dados para {selectedTribunal} na base interna do escritório.
          </p>
        )}
      </div>

      {/* Gráficos internos do escritório */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <Bars
          titulo="Por Área"
          rows={area}
          label={(r) => r.area || r.area_direito || "—"}
          val={(r) => r.total ?? r.count ?? 0}
        />
        <Bars
          titulo="Por Tribunal"
          rows={trib}
          label={(r) => r.tribunal || "—"}
          val={(r) => r.total ?? r.count ?? 0}
          cor="bg-primary-500"
        />
      </div>

      <Bars
        titulo="Teses Mais Utilizadas"
        rows={tese}
        label={(r) => r.titulo || r.tese || "—"}
        val={(r) => r.total ?? r.count ?? r.uso ?? 0}
        cor="bg-success-500"
      />

      {/* Lições aprendidas */}
      {desfechos?.licoes_aprendidas?.length > 0 && (
        <div className="card p-5 mt-4">
          <h3 className="font-semibold text-sm text-gray-500 uppercase mb-3">
            Últimas Lições Aprendidas
          </h3>
          <ul className="space-y-2">
            {desfechos.licoes_aprendidas.map((l: any, i: number) => (
              <li
                key={i}
                className="text-sm text-gray-600 border-l-2 border-warn-400 pl-3 py-0.5"
              >
                <span className="font-medium text-gray-700">{l.nr_cnj}</span>
                {l.licoes_aprendidas && <> — {l.licoes_aprendidas}</>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Predição por taxa histórica ─────────────────────────────── */}
      <div className="card p-5 mt-4">
        <h3 className="font-semibold text-sm text-gray-500 uppercase mb-1">
          Predição de Provimento
        </h3>
        <p className="text-xs text-gray-400 mb-3">
          Baseada na taxa histórica dos casos do escritório (heurística
          estatística, não ML).
        </p>
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div>
            <label className="text-xs text-gray-500 block mb-1">
              Classe TPU
            </label>
            <input
              type="number"
              placeholder="Ex: 1116"
              value={predForm.classe}
              onChange={(e) =>
                setPredForm((p) => ({ ...p, classe: e.target.value }))
              }
              className="w-full text-sm border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-bronze"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Tribunal</label>
            <select
              value={predForm.tribunal}
              onChange={(e) =>
                setPredForm((p) => ({ ...p, tribunal: e.target.value }))
              }
              className="w-full text-sm border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-bronze"
            >
              {["TJMG", "STJ", "STF", "TRF1", "TRT3"].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">
              Duração estimada (dias)
            </label>
            <input
              type="number"
              value={predForm.dias}
              onChange={(e) =>
                setPredForm((p) => ({ ...p, dias: e.target.value }))
              }
              className="w-full text-sm border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-bronze"
            />
          </div>
        </div>
        <div className="flex gap-2 mb-4">
          <button
            onClick={prever}
            disabled={loadingPred || !predForm.classe}
            className="btn-primary"
          >
            {loadingPred ? "Calculando..." : "Calcular"}
          </button>
        </div>

        {/* Shape real do backend (/jurimetria/ext/predicao/provimento):
            probabilidade_provimento (null = amostra insuficiente), amostra,
            metodo, confianca textual (baixa/média/alta). */}
        {predicao && predicao.probabilidade_provimento == null && (
          <p className="text-sm text-warn-600 bg-warn-50 border border-warn-200 rounded px-3 py-2">
            Amostra histórica insuficiente para estimar ({predicao.metodo}).
            Encerre mais casos desta classe/tribunal para habilitar a taxa.
          </p>
        )}

        {predicao != null && predicao.probabilidade_provimento != null && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="text-center p-3 bg-green-50 rounded-lg border border-green-100">
              <p className="text-2xl font-bold text-green-700">
                {predicao.probabilidade_provimento}%
              </p>
              <p className="text-xs text-green-600">Taxa hist. favorável</p>
            </div>
            <div className="text-center p-3 bg-danger-50 rounded-lg border border-danger-100">
              <p className="text-2xl font-bold text-danger-700">
                {Math.round((100 - predicao.probabilidade_provimento) * 10) / 10}%
              </p>
              <p className="text-xs text-danger-600">Taxa hist. desfavorável</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded-lg border border-gray-200">
              <p className="text-2xl font-bold capitalize text-gray-700">
                {predicao.confianca}
              </p>
              <p className="text-xs text-gray-500">
                Confiança ({predicao.amostra} casos)
              </p>
            </div>
            <div className="text-center p-3 bg-primary-50 rounded-lg border border-primary-100 flex items-center justify-center">
              <p className="text-sm font-medium text-primary-700">
                {predicao.metodo}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
