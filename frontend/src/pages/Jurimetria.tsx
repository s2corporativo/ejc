import { useEffect, useState } from "react";
import { RefreshCw, Database } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";

const TRIBUNAIS = ["TJMG", "STJ", "STF", "TRF1", "TRT3"];

function Bars({
  titulo,
  rows,
  label,
  val,
  cor = "bg-blue-500",
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

  // Predição ML
  const [predForm, setPredForm] = useState({
    classe: "",
    tribunal: "TJMG",
    dias: "365",
  });
  const [predicao, setPredicao] = useState<any>(null);
  const [loadingPred, setLoadingPred] = useState(false);
  const [treinando, setTreinando] = useState(false);

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

  const treinarModelo = async () => {
    setTreinando(true);
    try {
      await api.post(
        `/jurimetria/ext/predicao/treinar?tribunal=${predForm.tribunal}`,
      );
      alert(
        "Treinamento iniciado em background. Aguarde alguns minutos e tente a predição.",
      );
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Erro ao iniciar treinamento");
    } finally {
      setTreinando(false);
    }
  };

  // Dados externos (DataJud/STJ)
  const [extStats, setExtStats] = useState<any>(null);
  const [benchmarks, setBenchmarks] = useState<any>(null);
  const [selectedTribunal, setSelectedTribunal] = useState("TJMG");
  const [loadingExt, setLoadingExt] = useState(false);
  const [ingerindo, setIngerindo] = useState(false);
  const [msgIngestao, setMsgIngestao] = useState("");

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
          setArea(
            Array.isArray(b.value.data)
              ? b.value.data
              : (b.value.data?.items ?? []),
          );
        if (c.status === "fulfilled")
          setTrib(
            Array.isArray(c.value.data)
              ? c.value.data
              : (c.value.data?.items ?? []),
          );
        if (d.status === "fulfilled")
          setTese(
            Array.isArray(d.value.data)
              ? d.value.data
              : (d.value.data?.items ?? []),
          );
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

  const dispararIngestao = async () => {
    setIngerindo(true);
    setMsgIngestao("");
    try {
      await api.post(
        `/jurimetria/ext/ingerir/datajud?tribunal=${selectedTribunal}&data_inicio=2022-01-01&limite=500`,
      );
      setMsgIngestao(
        `Ingestão iniciada para ${selectedTribunal}. Aguarde alguns minutos e recarregue.`,
      );
    } catch (e: any) {
      setMsgIngestao(e?.response?.data?.detail || "Erro ao iniciar ingestão");
    } finally {
      setIngerindo(false);
    }
  };

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
                          : "h-full bg-red-400"
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
            <Database size={16} className="text-blue-500" />
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
                    ? "bg-blue-600 text-white border-blue-600"
                    : "text-gray-600 border-gray-300 hover:border-blue-400"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <button
            onClick={dispararIngestao}
            disabled={ingerindo}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 rounded-lg border transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={ingerindo ? "animate-spin" : ""} />
            {ingerindo ? "Coletando..." : "Coletar DataJud"}
          </button>
        </div>

        {msgIngestao && (
          <p className="text-xs text-blue-600 bg-blue-50 border border-blue-200 rounded px-3 py-2 mb-3">
            {msgIngestao}
          </p>
        )}

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
                        className="h-full bg-indigo-500"
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
            Sem dados para {selectedTribunal}. Clique em "Coletar DataJud" para
            iniciar a ingestão.
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
          cor="bg-indigo-500"
        />
      </div>

      <Bars
        titulo="Teses Mais Utilizadas"
        rows={tese}
        label={(r) => r.titulo || r.tese || "—"}
        val={(r) => r.total ?? r.count ?? r.uso ?? 0}
        cor="bg-emerald-500"
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
                className="text-sm text-gray-600 border-l-2 border-amber-400 pl-3 py-0.5"
              >
                <span className="font-medium text-gray-700">{l.nr_cnj}</span>
                {l.licoes_aprendidas && <> — {l.licoes_aprendidas}</>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Predição ML ─────────────────────────────────────────────── */}
      <div className="card p-5 mt-4">
        <h3 className="font-semibold text-sm text-gray-500 uppercase mb-3">
          Predição de Provimento (IA)
        </h3>
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
            className="px-4 py-1.5 text-sm bg-bronze text-white rounded-lg hover:bg-bronze-dark disabled:opacity-50 transition-colors"
          >
            {loadingPred ? "Calculando..." : "Calcular"}
          </button>
          <button
            onClick={treinarModelo}
            disabled={treinando}
            className="px-4 py-1.5 text-sm border rounded-lg text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {treinando ? "Iniciando..." : "Treinar modelo"}
          </button>
        </div>

        {predicao && !predicao.disponivel && (
          <p className="text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            {predicao.mensagem}
          </p>
        )}

        {predicao?.disponivel && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="text-center p-3 bg-green-50 rounded-lg border border-green-100">
              <p className="text-2xl font-bold text-green-700">
                {predicao.probabilidade_provimento}%
              </p>
              <p className="text-xs text-green-600">Prob. Provimento</p>
            </div>
            <div className="text-center p-3 bg-red-50 rounded-lg border border-red-100">
              <p className="text-2xl font-bold text-red-700">
                {predicao.probabilidade_negado}%
              </p>
              <p className="text-xs text-red-600">Prob. Negado</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded-lg border border-gray-200">
              <p className="text-2xl font-bold text-gray-700">
                {predicao.confianca}%
              </p>
              <p className="text-xs text-gray-500">Confiança</p>
            </div>
            <div className="text-center p-3 bg-blue-50 rounded-lg border border-blue-100 flex items-center justify-center">
              <p className="text-sm font-medium text-blue-700">
                {predicao.interpretacao}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
