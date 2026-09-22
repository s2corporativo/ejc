import { useEffect, useRef, useState } from "react";
import { Database } from "lucide-react";
import JurimetriaTribunais from "../components/JurimetriaTribunais";
import api from "../lib/api";
import { ErrorState, PageHeader, Spinner } from "../components/UI";
import { toast } from "../components/Toast";
import { asList } from "../lib/list";
import { mensagemErroHttp } from "../lib/iaErro";
import { useCarregar } from "../lib/useCarregar";
import { useAuth } from "../stores/auth";

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

function fmtData(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}

export default function Jurimetria() {
  const user = useAuth((state) => state.user);
  const podeVerEstrategico = Boolean(
    user?.role && ["superadmin", "admin", "socio"].includes(user.role),
  );
  const [desfechos, setDesfechos] = useState<any>(null);
  const [ragCoverage, setRagCoverage] = useState<any>(null);
  const [mgCoverage, setMgCoverage] = useState<any>(null);

  // Análise prospectiva por histórico interno (heurística descritiva, não ML).
  const [predForm, setPredForm] = useState({
    classe: "",
    tribunal: "TJMG",
    dias: "365",
  });
  const [predicao, setPredicao] = useState<any>(null);
  const [loadingPred, setLoadingPred] = useState(false);

  const prever = async () => {
    if (!podeVerEstrategico) return;
    setLoadingPred(true);
    try {
      const r = await api.get(
        `/jurimetria/interno/analise-prospectiva?classe=${predForm.classe}&tribunal=${predForm.tribunal}&dias_estimados=${predForm.dias}`,
      );
      setPredicao(r.data);
    } catch (err) {
      setPredicao(null);
      toast.error(
        mensagemErroHttp(err, "Não foi possível calcular o histórico."),
      );
    } finally {
      setLoadingPred(false);
    }
  };

  // Métricas internas do escritório. DataJud externo não está habilitado aqui.
  const [internalStats, setInternalStats] = useState<any>(null);
  const [benchmarks, setBenchmarks] = useState<any>(null);
  const [selectedTribunal, setSelectedTribunal] = useState("TJMG");
  const [loadingExt, setLoadingExt] = useState(false);
  const benchmarkRequestRef = useRef(0);

  // Carga principal: os quatro painéis são independentes; a tela só "falha"
  // quando NENHUM deles responde (senão mostra o que chegou). Os blocos
  // secundários (desfechos, stats internos, cobertura) são decorativos e
  // seguem best-effort — ausência deles não é erro para o usuário.
  const carga = useCarregar(
    async () => {
      const [a, b, c, d] = await Promise.allSettled([
        podeVerEstrategico
          ? api.get("/jurimetria/overview")
          : Promise.resolve({ data: null }),
        api.get("/jurimetria/por-area"),
        api.get("/jurimetria/por-tribunal"),
        api.get("/jurimetria/por-tese"),
      ]);
      const todos = [a, b, c, d];
      if (todos.every((r) => r.status === "rejected")) {
        throw (a as PromiseRejectedResult).reason;
      }
      return {
        ov: a.status === "fulfilled" ? a.value.data : null,
        area: b.status === "fulfilled" ? asList(b.value.data) : [],
        trib: c.status === "fulfilled" ? asList(c.value.data) : [],
        tese: d.status === "fulfilled" ? asList(d.value.data) : [],
      };
    },
    [podeVerEstrategico],
    {
      vazio: () => false,
      fallbackErro: "Não foi possível carregar a jurimetria.",
    },
  );
  const loading = carga.carregando;
  const ov = carga.dados?.ov ?? null;
  const area = carga.dados?.area ?? [];
  const trib = carga.dados?.trib ?? [];
  const tese = carga.dados?.tese ?? [];

  useEffect(() => {
    if (podeVerEstrategico) {
      api
        .get("/jurimetria/desfechos")
        .then((r: any) => setDesfechos(r.data))
        .catch(() => setDesfechos(null));
    } else {
      setDesfechos(null);
    }
    api
      .get("/jurimetria/interno/stats")
      .then((r: any) => setInternalStats(r.data))
      .catch(() => setInternalStats(null));
    Promise.allSettled([
      api.get("/jurimetria/cobertura-rag"),
      api.get("/jurimetria/cobertura-mg-jec"),
    ]).then(([rag, mg]) => {
      if (rag.status === "fulfilled") setRagCoverage(rag.value.data);
      if (mg.status === "fulfilled") setMgCoverage(mg.value.data);
    });
  }, [podeVerEstrategico]);

  const carregarBenchmarks = async (tribunal: string) => {
    const requestId = ++benchmarkRequestRef.current;
    setLoadingExt(true);
    try {
      const r = await api.get(
        `/jurimetria/interno/benchmarks?tribunal=${tribunal}`,
      );
      if (requestId === benchmarkRequestRef.current) {
        setBenchmarks(r.data);
      }
    } catch {
      if (requestId === benchmarkRequestRef.current) {
        setBenchmarks(null);
      }
    } finally {
      if (requestId === benchmarkRequestRef.current) {
        setLoadingExt(false);
      }
    }
  };

  useEffect(() => {
    if (!podeVerEstrategico) {
      setBenchmarks(null);
      setLoadingExt(false);
      return;
    }
    void carregarBenchmarks(selectedTribunal);
  }, [selectedTribunal, podeVerEstrategico]);

  if (loading)
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  if (carga.estado === "falhou")
    return (
      <div>
        <PageHeader
          title="Jurimetria"
          subtitle="Histórico interno do escritório e benchmarks externos dos tribunais — exibidos separadamente quando disponíveis"
        />
        <ErrorState
          title="Não foi possível carregar a jurimetria"
          message={carga.erro ?? undefined}
          onRetry={carga.recarregar}
        />
      </div>
    );

  const taxa = ov?.taxa_sucesso_geral;
  const totalInterno =
    internalStats?.total_com_tribunal ??
    internalStats?.por_tribunal?.reduce(
      (s: number, t: any) => s + t.total,
      0,
    ) ??
    0;
  const taxaHistorica =
    predicao?.taxa_historica_favoravel ?? predicao?.probabilidade_provimento;

  return (
    <div>
      <PageHeader
        title="Jurimetria"
        subtitle="Histórico interno do escritório e benchmarks externos dos tribunais — exibidos separadamente quando disponíveis"
      />

      {/* Cards resumo escritório */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {podeVerEstrategico && (
          <StatCard
            label="Taxa de Teses Decididas"
            value={taxa != null ? `${(taxa * 100).toFixed(1)}%` : "—"}
            sub="procedentes ÷ decididas"
          />
        )}
        <StatCard
          label="Áreas"
          value={area.length}
          sub="com vínculos de tese"
        />
        <StatCard label="Tribunais" value={trib.length} sub="no escritório" />
        <StatCard
          label="Base Interna"
          value={totalInterno.toLocaleString("pt-BR")}
          sub="casos com tribunal informado"
        />
      </div>

      {/* Jurimetria dos TRIBUNAIS (Issue #1527) — DataJud/TJMG. Coexiste com os
          painéis do escritório acima; o componente rotula a diferença. */}
      <JurimetriaTribunais />

      {/* Cobertura real do conhecimento */}
      {(ragCoverage || mgCoverage) && (
        <div className="card p-5 mb-6">
          <div className="flex items-center gap-1.5 mb-1">
            <Database size={16} className="text-primary-500" />
            <h3 className="font-semibold text-sm text-gray-700 uppercase">
              Cobertura Real do Conhecimento da IA
            </h3>
          </div>
          <p className="text-xs text-gray-400 mb-4">
            Contagem do acervo RAG efetivamente armazenado. Ausência de metadado
            ou fonte validada permanece visível e não é inferida como cobertura.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
            <div className="text-center p-3 bg-gray-50 rounded-lg">
              <p className="text-xl font-bold text-gray-800">
                {ragCoverage?.documentos?.toLocaleString("pt-BR") ?? "—"}
              </p>
              <p className="text-xs text-gray-500">Docs RAG atuais</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded-lg">
              <p className="text-xl font-bold text-gray-800">
                {ragCoverage?.chunks?.toLocaleString("pt-BR") ?? "—"}
              </p>
              <p className="text-xs text-gray-500">Chunks atuais</p>
            </div>
            <div className="text-center p-3 bg-primary-50 rounded-lg">
              <p className="text-xl font-bold text-primary-700">
                {mgCoverage?.documentos?.toLocaleString("pt-BR") ?? "—"}
              </p>
              <p className="text-xs text-primary-600">Docs MG/JEC</p>
            </div>
            <div className="text-center p-3 bg-primary-50 rounded-lg">
              <p className="text-xl font-bold text-primary-700">
                {mgCoverage?.chunks?.toLocaleString("pt-BR") ?? "—"}
              </p>
              <p className="text-xs text-primary-600">Chunks MG/JEC</p>
            </div>
            <div className="text-center p-3 bg-green-50 rounded-lg">
              <p className="text-xl font-bold text-green-700">
                {mgCoverage?.pct_fonte_validada_explicita != null
                  ? `${mgCoverage.pct_fonte_validada_explicita}%`
                  : "—"}
              </p>
              <p className="text-xs text-green-600">Fonte validada explícita</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-500 mb-3">
            <span>
              MG/JEC indexados: {mgCoverage?.documentos_indexados ?? "—"}
            </span>
            <span>
              MG/JEC aprovados: {mgCoverage?.documentos_aprovados ?? "—"}
            </span>
            <span>
              Última atualização: {fmtData(mgCoverage?.ultima_atualizacao)}
            </span>
          </div>
          {mgCoverage?.colecoes?.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-400 border-b">
                    <th className="py-2 pr-3 font-medium">Coleção medida</th>
                    <th className="py-2 px-3 font-medium text-right">Docs</th>
                    <th className="py-2 px-3 font-medium text-right">Chunks</th>
                    <th className="py-2 px-3 font-medium text-right">
                      Indexados
                    </th>
                    <th className="py-2 pl-3 font-medium text-right">
                      Fonte validada
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {mgCoverage.colecoes.slice(0, 10).map((c: any) => (
                    <tr key={c.colecao} className="border-b border-gray-100">
                      <td className="py-2 pr-3 text-gray-700">{c.colecao}</td>
                      <td className="py-2 px-3 text-right text-gray-600">
                        {c.documentos}
                      </td>
                      <td className="py-2 px-3 text-right text-gray-600">
                        {c.chunks}
                      </td>
                      <td className="py-2 px-3 text-right text-gray-600">
                        {c.indexados}
                      </td>
                      <td className="py-2 pl-3 text-right text-gray-600">
                        {c.fonte_validada_explicita}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[11px] text-gray-400 mt-3">
            O crawler TJMG genérico é mapeado logicamente na cobertura, sem
            duplicar documentos. “Fonte validada” conta somente metadado
            explícito; ausência não é presumida como validação.
          </p>
        </div>
      )}

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

      {/* Histórico interno por tribunal — bloco estratégico (sócio+) */}
      {podeVerEstrategico && (
        <div className="card p-5 mb-6">
          <div className="flex flex-wrap items-center gap-3 mb-2">
            <div className="flex items-center gap-1.5">
              <Database size={16} className="text-primary-500" />
              <h3 className="font-semibold text-sm text-gray-700 uppercase">
                Histórico Interno por Tribunal
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
          <p className="text-xs text-gray-400 mb-4">
            Fonte: casos cadastrados no EJC. Estes números não são DataJud/STJ e
            não representam benchmark externo.
          </p>

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
                  Processos encerrados na base interna
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
      )}

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
                <span className="font-medium text-gray-700">
                  {l.titulo || "Caso"}
                </span>
                {l.licoes_aprendidas && <> — {l.licoes_aprendidas}</>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Análise prospectiva descritiva — bloco estratégico (sócio+) */}
      {podeVerEstrategico && (
        <div className="card p-5 mt-4">
          <h3 className="font-semibold text-sm text-gray-500 uppercase mb-1">
            Análise Prospectiva — Histórico Interno
          </h3>
          <p className="text-xs text-gray-400 mb-3">
            Indicador descritivo dos casos decididos do escritório. Não é modelo
            preditivo e não representa probabilidade de decisão futura.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">
                Classe TPU (somente referência)
              </label>
              <input
                type="number"
                placeholder="Opcional — não filtra a base atual"
                value={predForm.classe}
                onChange={(e) =>
                  setPredForm((p) => ({ ...p, classe: e.target.value }))
                }
                className="w-full text-sm border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-bronze"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">
                Tribunal
              </label>
              <select
                value={predForm.tribunal}
                onChange={(e) =>
                  setPredForm((p) => ({ ...p, tribunal: e.target.value }))
                }
                className="w-full text-sm border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-bronze"
              >
                {TRIBUNAIS.map((t) => (
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
              disabled={loadingPred}
              className="btn-primary"
            >
              {loadingPred ? "Calculando..." : "Calcular histórico"}
            </button>
          </div>

          {predicao && taxaHistorica == null && (
            <p className="text-sm text-warn-600 bg-warn-50 border border-warn-200 rounded px-3 py-2">
              {predicao.aviso ||
                `Amostra decidida insuficiente (${predicao.amostra ?? 0} casos).`}
            </p>
          )}

          {predicao != null && taxaHistorica != null && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="text-center p-3 bg-green-50 rounded-lg border border-green-100">
                  <p className="text-2xl font-bold text-green-700">
                    {taxaHistorica}%
                  </p>
                  <p className="text-xs text-green-600">
                    Taxa histórica favorável
                  </p>
                </div>
                <div className="text-center p-3 bg-danger-50 rounded-lg border border-danger-100">
                  <p className="text-2xl font-bold text-danger-700">
                    {predicao.desfavoraveis ?? "—"}
                  </p>
                  <p className="text-xs text-danger-600">
                    Desfechos desfavoráveis
                  </p>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg border border-black/[0.05]">
                  <p className="text-2xl font-bold text-gray-700">
                    {predicao.acordos ?? 0}
                  </p>
                  <p className="text-xs text-gray-500">
                    Acordos (fora da taxa)
                  </p>
                </div>
                <div className="text-center p-3 bg-primary-50 rounded-lg border border-primary-100">
                  <p className="text-2xl font-bold capitalize text-primary-700">
                    {predicao.confianca}
                  </p>
                  <p className="text-xs text-primary-600">
                    Amostra: {predicao.amostra} decididos
                  </p>
                </div>
              </div>
              {predicao.aviso && (
                <p className="text-xs text-gray-500 mt-3">{predicao.aviso}</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
