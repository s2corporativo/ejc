import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  FileSearch,
  GitCompare,
  RefreshCw,
  Save,
  ShieldCheck,
  TestTube2,
  XCircle,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { Spinner, fmtDate } from "../components/UI";
import { asList } from "../lib/list";
import Conhecimento from "./Conhecimento";

type GovernanceTab = "saude" | "cobertura" | "laboratorio";

type HealthSummary = {
  total_docs: number;
  historical_versions: number;
  approved_docs: number;
  usable_docs: number;
  vectorized_docs: number;
  total_chunks: number;
  embedded_chunks: number;
  chunks_without_embedding: number;
  ocr_issues: number;
  duplicate_groups: number;
  conflict_groups: number;
  stale_sources: number;
  legal_status_unverified: number;
  usable_percent: number;
  vectorized_percent: number;
};

type HealthAlert = {
  severity: "critical" | "warning";
  code: string;
  doc_id: string;
  title: string;
  detail: string;
};

type HealthResponse = {
  generated_at: string;
  summary: HealthSummary;
  alerts: HealthAlert[];
};

type CoverageRow = {
  area: string;
  legislacao: number;
  sumulas: number;
  jurisprudencia: number;
  modelos: number;
  doutrina: number;
  score: number;
  status: "boa" | "atencao" | "critica";
  lacunas: string[];
};

type CoverageResponse = {
  generated_at: string;
  dimensions: string[];
  areas: CoverageRow[];
};

type KnowledgeDocListItem = {
  id: string;
  titulo: string;
  categoria: string;
  fonte?: string | null;
  tribunal?: string | null;
  status_indexacao?: string | null;
  created_at?: string | null;
};

type DocDetails = {
  id: string;
  titulo: string;
  categoria: string;
  fonte?: string | null;
  tribunal?: string | null;
  versao: number;
  vigente_no_ejc: boolean;
  status_indexacao: string;
  created_at?: string | null;
  atualizado_em?: string | null;
  extra: Record<string, any>;
  autoridade: { code: string; label: string; weight: number; official: boolean };
  situacao_juridica: {
    code: string;
    label: string;
    permite_fundamentacao_atual: boolean;
    requires_warning: boolean;
    blocks_current_law: boolean;
  };
  frescor: {
    status: string;
    days?: number | null;
    threshold_days?: number;
    reference_at?: string | null;
  };
  qualidade: { score: number; status: string; issues: string[] };
  metricas: { chunks: number; chars: number; embedded: number };
  versoes: Array<{
    id: string;
    versao: number;
    vigente: boolean;
    atualizado_em?: string | null;
  }>;
};

type TestResult = {
  recuperado: boolean;
  posicao?: number | null;
  top_score?: number | null;
  pergunta?: string | null;
  diagnostico?: string;
  detail?: string;
  resultados?: Array<Record<string, any>>;
};

type CompareResult = {
  available: boolean;
  detail?: string;
  current?: { id: string; titulo: string; versao: number };
  previous?: { id: string; titulo: string; versao: number } | null;
  summary?: {
    secoes_adicionadas: number;
    secoes_removidas: number;
    secoes_alteradas: number;
    similaridade_global: number;
  };
  added?: Array<{ secao: string; texto: string }>;
  removed?: Array<{ secao: string; texto: string }>;
  changed?: Array<{
    secao: string;
    similaridade: number;
    antes: string;
    depois: string;
  }>;
};

type SmokeResult = {
  approved: number;
  failed: number;
  score_percent: number;
  status: string;
  tests: Array<{
    id: string;
    pergunta: string;
    status: string;
    fontes_encontradas: number;
    termos_confirmados: string[];
  }>;
};

const AUTHORITY_OPTIONS = [
  ["oficial_normativa", "Oficial normativa"],
  ["precedente_vinculante", "Precedente vinculante/oficial"],
  ["jurisprudencia_oficial", "Jurisprudência oficial"],
  ["oficial_informativa", "Oficial informativa"],
  ["institucional_interna", "Institucional interna"],
  ["doutrinaria", "Doutrinária"],
  ["referencial", "Referencial"],
] as const;

const LEGAL_STATUS_OPTIONS = [
  ["vigente", "Vigente"],
  ["parcialmente_revogada", "Parcialmente revogada"],
  ["revogada", "Revogada"],
  ["suspensa", "Suspensa"],
  ["vigencia_nao_verificada", "Vigência não verificada"],
  ["nao_aplicavel", "Não aplicável"],
  ["historica", "Versão histórica"],
] as const;

function MetricCard({
  label,
  value,
  detail,
  danger = false,
}: {
  label: string;
  value: string | number;
  detail?: string;
  danger?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {label}
      </p>
      <p
        className={`mt-1 text-2xl font-bold ${danger ? "text-danger-600" : "text-navy"}`}
      >
        {value}
      </p>
      {detail && <p className="mt-1 text-xs text-slate-500">{detail}</p>}
    </div>
  );
}

function StatusPill({ status }: { status: CoverageRow["status"] }) {
  const meta =
    status === "boa"
      ? "bg-success-50 text-success-700"
      : status === "atencao"
        ? "bg-warn-50 text-warn-700"
        : "bg-danger-50 text-danger-600";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${meta}`}>
      {status === "boa" ? "Boa" : status === "atencao" ? "Atenção" : "Crítica"}
    </span>
  );
}

export default function ConhecimentoGovernado() {
  const [tab, setTab] = useState<GovernanceTab>("saude");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [docs, setDocs] = useState<KnowledgeDocListItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [details, setDetails] = useState<DocDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [runningSmoke, setRunningSmoke] = useState(false);
  const [question, setQuestion] = useState("");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null);
  const [smokeResult, setSmokeResult] = useState<SmokeResult | null>(null);
  const [form, setForm] = useState({
    authority_level: "referencial",
    legal_status: "nao_aplicavel",
    area_juridica: "",
    diploma: "",
    numero: "",
    ano: "",
    source_official: false,
  });

  const loadOverview = async () => {
    setLoading(true);
    try {
      const [healthRes, coverageRes, docsRes] = await Promise.all([
        api.get("/rag/governanca/saude"),
        api.get("/rag/governanca/cobertura"),
        api.get("/rag/docs", { params: { page: 1, page_size: 100 } }),
      ]);
      setHealth(healthRes.data);
      setCoverage(coverageRes.data);
      const list = asList(docsRes.data) as KnowledgeDocListItem[];
      setDocs(list);
      setSelectedId((current) => current || list[0]?.id || "");
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          "Não foi possível carregar a governança da base de conhecimento.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetails(null);
      return;
    }
    setLoadingDoc(true);
    setTestResult(null);
    setCompareResult(null);
    api
      .get(`/rag/governanca/docs/${selectedId}`)
      .then(({ data }) => {
        const doc = data as DocDetails;
        setDetails(doc);
        setForm({
          authority_level: doc.autoridade.code || "referencial",
          legal_status: doc.situacao_juridica.code || "nao_aplicavel",
          area_juridica: doc.extra?.area_juridica || doc.extra?.area || "",
          diploma: doc.extra?.diploma || "",
          numero: doc.extra?.numero || "",
          ano: doc.extra?.ano ? String(doc.extra.ano) : "",
          source_official: Boolean(doc.extra?.source_official ?? doc.autoridade.official),
        });
      })
      .catch(() => {
        setDetails(null);
        toast.error("Não foi possível carregar os metadados do documento.");
      })
      .finally(() => setLoadingDoc(false));
  }, [selectedId]);

  const criticalAlerts = useMemo(
    () => health?.alerts.filter((alert) => alert.severity === "critical").length ?? 0,
    [health],
  );

  const saveGovernance = async (confirmSource = false) => {
    if (!selectedId) return;
    setSaving(true);
    try {
      const payload: Record<string, any> = {
        authority_level: form.authority_level,
        legal_status: form.legal_status,
        area_juridica: form.area_juridica.trim() || undefined,
        diploma: form.diploma.trim() || undefined,
        numero: form.numero.trim() || undefined,
        ano: form.ano ? Number(form.ano) : undefined,
        source_official: form.source_official,
        confirmar_fonte_agora: confirmSource,
      };
      const { data } = await api.patch(
        `/rag/governanca/docs/${selectedId}`,
        payload,
      );
      setDetails(data.documento);
      toast.success(
        confirmSource
          ? "Fonte conferida e metadados atualizados."
          : "Governança do documento atualizada.",
      );
      void loadOverview();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "Erro ao salvar a governança.");
    } finally {
      setSaving(false);
    }
  };

  const testKnowledge = async () => {
    if (!selectedId) return;
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await api.post(
        `/rag/governanca/docs/${selectedId}/testar`,
        { pergunta: question.trim() || null, limite: 8 },
      );
      setTestResult(data);
      if (data.recuperado) toast.success("Documento recuperado pelo pipeline da IA.");
      else toast.error("Documento não foi recuperado. Consulte o diagnóstico.");
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "Falha no teste do conhecimento.");
    } finally {
      setTesting(false);
    }
  };

  const compareVersions = async () => {
    if (!selectedId) return;
    setComparing(true);
    setCompareResult(null);
    try {
      const { data } = await api.get(
        `/rag/governanca/docs/${selectedId}/comparar`,
      );
      setCompareResult(data);
      if (!data.available) toast.error(data.detail || "Não há versão anterior.");
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "Falha ao comparar versões.");
    } finally {
      setComparing(false);
    }
  };

  const runSmokeTests = async () => {
    setRunningSmoke(true);
    try {
      const { data } = await api.post("/rag/governanca/testes-juridicos");
      setSmokeResult(data);
      setTab("laboratorio");
      if (data.failed === 0) toast.success("Todos os testes jurídicos foram aprovados.");
      else toast.error(`${data.failed} teste(s) jurídico(s) exigem atenção.`);
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "Falha nos testes jurídicos.");
    } finally {
      setRunningSmoke(false);
    }
  };

  const summary = health?.summary;

  return (
    <div className="space-y-6">
      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-ai-600" />
              <h2 className="font-serif text-lg font-bold text-navy">
                Governança da Base de Conhecimento
              </h2>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              Distingue aprovação interna, autoridade jurídica, qualidade técnica e
              vigência normativa.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="btn btn-ghost gap-2"
              onClick={() => void loadOverview()}
              disabled={loading}
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              Atualizar
            </button>
            <button
              className="btn btn-primary gap-2"
              onClick={() => void runSmokeTests()}
              disabled={runningSmoke}
            >
              {runningSmoke ? <Spinner /> : <TestTube2 className="h-4 w-4" />}
              Testes jurídicos
            </button>
          </div>
        </div>

        {loading && !health ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 bg-slate-50/60 p-4 md:grid-cols-3 xl:grid-cols-6">
              <MetricCard
                label="Utilizáveis pela IA"
                value={`${summary?.usable_percent ?? 0}%`}
                detail={`${summary?.usable_docs ?? 0} de ${summary?.total_docs ?? 0} documentos`}
              />
              <MetricCard
                label="Vetorizados"
                value={`${summary?.vectorized_percent ?? 0}%`}
                detail={`${summary?.vectorized_docs ?? 0} documentos`}
              />
              <MetricCard
                label="Trechos sem vetor"
                value={summary?.chunks_without_embedding ?? 0}
                danger={(summary?.chunks_without_embedding ?? 0) > 0}
              />
              <MetricCard
                label="Fontes desatualizadas"
                value={summary?.stale_sources ?? 0}
                danger={(summary?.stale_sources ?? 0) > 0}
              />
              <MetricCard
                label="Vigência não conferida"
                value={summary?.legal_status_unverified ?? 0}
                danger={(summary?.legal_status_unverified ?? 0) > 0}
              />
              <MetricCard
                label="Conflitos críticos"
                value={criticalAlerts}
                detail={`${summary?.duplicate_groups ?? 0} grupo(s) duplicado(s)`}
                danger={criticalAlerts > 0}
              />
            </div>

            <div className="border-t border-slate-100 px-4 pt-3">
              <div className="flex flex-wrap gap-1">
                {[
                  ["saude", "Saúde e alertas", Activity],
                  ["cobertura", "Cobertura jurídica", Database],
                  ["laboratorio", "Laboratório da IA", FileSearch],
                ].map(([key, label, Icon]) => (
                  <button
                    key={String(key)}
                    onClick={() => setTab(key as GovernanceTab)}
                    className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${
                      tab === key
                        ? "bg-navy text-white"
                        : "text-slate-500 hover:bg-slate-100 hover:text-navy"
                    }`}
                  >
                    <Icon className="h-4 w-4" /> {String(label)}
                  </button>
                ))}
              </div>
            </div>

            <div className="p-4">
              {tab === "saude" && (
                <div className="space-y-3">
                  {(health?.alerts?.length ?? 0) === 0 ? (
                    <div className="flex items-center gap-3 rounded-xl border border-success-200 bg-success-50 p-4 text-success-700">
                      <CheckCircle2 className="h-5 w-5" />
                      <div>
                        <p className="font-semibold">Base sem alertas técnicos relevantes</p>
                        <p className="text-xs">
                          Última verificação: {health?.generated_at ? fmtDate(health.generated_at) : "—"}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="grid gap-2 lg:grid-cols-2">
                      {health?.alerts.slice(0, 20).map((alert, index) => (
                        <button
                          key={`${alert.doc_id}-${alert.code}-${index}`}
                          type="button"
                          onClick={() => {
                            setSelectedId(alert.doc_id);
                            setTab("laboratorio");
                          }}
                          className={`flex items-start gap-3 rounded-xl border p-3 text-left transition-colors hover:bg-slate-50 ${
                            alert.severity === "critical"
                              ? "border-danger-200"
                              : "border-warn-200"
                          }`}
                        >
                          {alert.severity === "critical" ? (
                            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger-500" />
                          ) : (
                            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn-600" />
                          )}
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold text-navy">
                              {alert.title}
                            </span>
                            <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">
                              {alert.detail}
                            </span>
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {tab === "cobertura" && (
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="w-full min-w-[850px] text-sm">
                    <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400">
                      <tr>
                        <th className="px-4 py-3 text-left">Área</th>
                        <th className="px-3 py-3 text-center">Legislação</th>
                        <th className="px-3 py-3 text-center">Súmulas</th>
                        <th className="px-3 py-3 text-center">Jurisprudência</th>
                        <th className="px-3 py-3 text-center">Modelos</th>
                        <th className="px-3 py-3 text-center">Doutrina</th>
                        <th className="px-3 py-3 text-center">Cobertura</th>
                        <th className="px-3 py-3 text-center">Situação</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {coverage?.areas.map((row) => (
                        <tr key={row.area} className="hover:bg-slate-50/70">
                          <td className="px-4 py-3 font-medium text-navy">{row.area}</td>
                          {[row.legislacao, row.sumulas, row.jurisprudencia, row.modelos, row.doutrina].map(
                            (value, index) => (
                              <td key={index} className="px-3 py-3 text-center text-slate-600">
                                {value || "—"}
                              </td>
                            ),
                          )}
                          <td className="px-3 py-3 text-center font-semibold text-navy">
                            {row.score}%
                          </td>
                          <td className="px-3 py-3 text-center">
                            <StatusPill status={row.status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {tab === "laboratorio" && (
                <div className="space-y-4">
                  {smokeResult && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="font-semibold text-navy">Testes jurídicos permanentes</p>
                          <p className="text-xs text-slate-500">
                            {smokeResult.approved} aprovados · {smokeResult.failed} falharam
                          </p>
                        </div>
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-bold ${
                            smokeResult.failed === 0
                              ? "bg-success-50 text-success-700"
                              : "bg-danger-50 text-danger-600"
                          }`}
                        >
                          {smokeResult.score_percent}%
                        </span>
                      </div>
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {smokeResult.tests.map((test) => (
                          <div
                            key={test.id}
                            className="flex items-start gap-2 rounded-lg bg-white p-3"
                          >
                            {test.status === "aprovado" ? (
                              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success-600" />
                            ) : (
                              <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger-500" />
                            )}
                            <div>
                              <p className="text-xs font-medium text-navy">{test.pergunta}</p>
                              <p className="mt-1 text-[11px] text-slate-400">
                                {test.fontes_encontradas} fonte(s) · termos: {test.termos_confirmados.join(", ") || "não confirmados"}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
                    <div className="space-y-4 rounded-xl border border-slate-200 p-4">
                      <div>
                        <label className="label">Documento a auditar</label>
                        <select
                          className="input"
                          value={selectedId}
                          onChange={(event) => setSelectedId(event.target.value)}
                        >
                          {docs.map((doc) => (
                            <option key={doc.id} value={doc.id}>
                              {doc.titulo} · {doc.categoria}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="label">Pergunta de teste</label>
                        <textarea
                          className="input min-h-[90px] resize-y"
                          value={question}
                          onChange={(event) => setQuestion(event.target.value)}
                          placeholder="Deixe em branco para o EJC montar uma consulta pelo título ou informe uma pergunta jurídica específica."
                        />
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <button
                          className="btn btn-primary gap-2"
                          onClick={() => void testKnowledge()}
                          disabled={!selectedId || testing}
                        >
                          {testing ? <Spinner /> : <FileSearch className="h-4 w-4" />}
                          Testar conhecimento da IA
                        </button>
                        <button
                          className="btn btn-ghost gap-2"
                          onClick={() => void compareVersions()}
                          disabled={!selectedId || comparing}
                        >
                          {comparing ? <Spinner /> : <GitCompare className="h-4 w-4" />}
                          Comparar versões
                        </button>
                      </div>

                      {testResult && (
                        <div
                          className={`rounded-xl border p-4 ${
                            testResult.recuperado
                              ? "border-success-200 bg-success-50"
                              : "border-danger-200 bg-danger-50"
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            {testResult.recuperado ? (
                              <CheckCircle2 className="h-5 w-5 text-success-600" />
                            ) : (
                              <XCircle className="h-5 w-5 text-danger-500" />
                            )}
                            <p className="font-semibold text-navy">
                              {testResult.recuperado
                                ? `Recuperado na posição ${testResult.posicao ?? "—"}`
                                : "Documento não recuperado"}
                            </p>
                          </div>
                          <p className="mt-2 text-sm text-slate-600">
                            {testResult.diagnostico || testResult.detail}
                          </p>
                          {testResult.top_score != null && (
                            <p className="mt-1 text-xs text-slate-500">
                              Score máximo: {Math.round(testResult.top_score * 100)}%
                            </p>
                          )}
                          {(testResult.resultados?.length ?? 0) > 0 && (
                            <div className="mt-3 space-y-2">
                              {testResult.resultados?.slice(0, 3).map((result, index) => (
                                <div key={result.chunk_id ?? index} className="rounded-lg bg-white/80 p-3">
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                    <p className="text-xs font-semibold text-navy">
                                      {result.titulo || "Resultado"}
                                    </p>
                                    <span className="text-[10px] font-semibold text-slate-500">
                                      {result.autoridade?.label || result.citacao?.autoridade?.label || "Autoridade não classificada"}
                                    </span>
                                  </div>
                                  <p className="mt-1 line-clamp-3 text-xs text-slate-500">
                                    {result.conteudo}
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {compareResult && (
                        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                          {!compareResult.available ? (
                            <p className="text-sm text-slate-600">{compareResult.detail}</p>
                          ) : (
                            <div className="space-y-3">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <p className="font-semibold text-navy">
                                  Versão {compareResult.previous?.versao} → {compareResult.current?.versao}
                                </p>
                                <span className="text-xs text-slate-500">
                                  Similaridade global: {Math.round((compareResult.summary?.similaridade_global ?? 0) * 100)}%
                                </span>
                              </div>
                              <div className="grid grid-cols-3 gap-2 text-center">
                                <MetricCard label="Incluídas" value={compareResult.summary?.secoes_adicionadas ?? 0} />
                                <MetricCard label="Removidas" value={compareResult.summary?.secoes_removidas ?? 0} />
                                <MetricCard label="Alteradas" value={compareResult.summary?.secoes_alteradas ?? 0} />
                              </div>
                              {(compareResult.changed?.length ?? 0) > 0 && (
                                <div className="space-y-2">
                                  {compareResult.changed?.slice(0, 5).map((change) => (
                                    <details key={change.secao} className="rounded-lg border border-slate-200 bg-white p-3">
                                      <summary className="cursor-pointer text-xs font-semibold text-navy">
                                        {change.secao} · {Math.round(change.similaridade * 100)}% semelhante
                                      </summary>
                                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                                        <div>
                                          <p className="text-[10px] font-bold uppercase text-danger-500">Antes</p>
                                          <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600">{change.antes}</p>
                                        </div>
                                        <div>
                                          <p className="text-[10px] font-bold uppercase text-success-600">Depois</p>
                                          <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600">{change.depois}</p>
                                        </div>
                                      </div>
                                    </details>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="rounded-xl border border-slate-200 p-4">
                      {loadingDoc ? (
                        <div className="flex justify-center py-12"><Spinner /></div>
                      ) : !details ? (
                        <p className="py-8 text-center text-sm text-slate-400">
                          Selecione um documento para editar a governança.
                        </p>
                      ) : (
                        <div className="space-y-4">
                          <div>
                            <p className="font-semibold text-navy">{details.titulo}</p>
                            <p className="mt-1 text-xs text-slate-400">
                              Versão {details.versao} · {details.metricas.chunks} trecho(s) · {details.metricas.embedded} vetorizado(s)
                            </p>
                          </div>

                          <div className="grid grid-cols-2 gap-2">
                            <div className="rounded-lg bg-slate-50 p-3">
                              <p className="text-[10px] font-bold uppercase text-slate-400">Qualidade</p>
                              <p className="mt-1 text-sm font-semibold text-navy">{details.qualidade.score}/100</p>
                              <p className="text-[11px] text-slate-500">{details.qualidade.status}</p>
                            </div>
                            <div className="rounded-lg bg-slate-50 p-3">
                              <p className="text-[10px] font-bold uppercase text-slate-400">Frescor</p>
                              <p className="mt-1 text-sm font-semibold text-navy">{details.frescor.status}</p>
                              <p className="text-[11px] text-slate-500">
                                {details.frescor.days != null ? `${details.frescor.days} dia(s)` : "sem data"}
                              </p>
                            </div>
                          </div>

                          {details.qualidade.issues.length > 0 && (
                            <div className="rounded-lg border border-warn-200 bg-warn-50 p-3">
                              {details.qualidade.issues.map((issue) => (
                                <p key={issue} className="text-xs text-warn-800">• {issue}</p>
                              ))}
                            </div>
                          )}

                          <div>
                            <label className="label">Autoridade da fonte</label>
                            <select
                              className="input"
                              value={form.authority_level}
                              onChange={(event) =>
                                setForm((current) => ({ ...current, authority_level: event.target.value }))
                              }
                            >
                              {AUTHORITY_OPTIONS.map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                              ))}
                            </select>
                          </div>

                          <div>
                            <label className="label">Situação jurídica</label>
                            <select
                              className="input"
                              value={form.legal_status}
                              onChange={(event) =>
                                setForm((current) => ({ ...current, legal_status: event.target.value }))
                              }
                            >
                              {LEGAL_STATUS_OPTIONS.map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                              ))}
                            </select>
                          </div>

                          <div>
                            <label className="label">Área jurídica</label>
                            <input
                              className="input"
                              value={form.area_juridica}
                              onChange={(event) =>
                                setForm((current) => ({ ...current, area_juridica: event.target.value }))
                              }
                              placeholder="Ex.: Consumidor, Ambiental, Trabalhista"
                            />
                          </div>

                          <div className="grid grid-cols-3 gap-2">
                            <div className="col-span-2">
                              <label className="label">Diploma</label>
                              <input
                                className="input"
                                value={form.diploma}
                                onChange={(event) =>
                                  setForm((current) => ({ ...current, diploma: event.target.value }))
                                }
                                placeholder="Lei, decreto, resolução..."
                              />
                            </div>
                            <div>
                              <label className="label">Ano</label>
                              <input
                                className="input"
                                type="number"
                                value={form.ano}
                                onChange={(event) =>
                                  setForm((current) => ({ ...current, ano: event.target.value }))
                                }
                              />
                            </div>
                          </div>

                          <div>
                            <label className="label">Número</label>
                            <input
                              className="input"
                              value={form.numero}
                              onChange={(event) =>
                                setForm((current) => ({ ...current, numero: event.target.value }))
                              }
                            />
                          </div>

                          <label className="flex items-center gap-2 text-sm text-slate-600">
                            <input
                              type="checkbox"
                              checked={form.source_official}
                              onChange={(event) =>
                                setForm((current) => ({ ...current, source_official: event.target.checked }))
                              }
                            />
                            Fonte oficial conferida
                          </label>

                          <div className="flex flex-wrap gap-2">
                            <button
                              className="btn btn-primary gap-2"
                              disabled={saving}
                              onClick={() => void saveGovernance(false)}
                            >
                              {saving ? <Spinner /> : <Save className="h-4 w-4" />}
                              Salvar
                            </button>
                            <button
                              className="btn btn-ghost"
                              disabled={saving}
                              onClick={() => void saveGovernance(true)}
                            >
                              Conferir fonte agora
                            </button>
                          </div>

                          <p className="text-[11px] leading-relaxed text-slate-400">
                            “Aprovado” significa autorizado para consulta pela IA. A autoridade e a vigência acima permanecem controles independentes.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </section>

      <Conhecimento />
    </div>
  );
}
