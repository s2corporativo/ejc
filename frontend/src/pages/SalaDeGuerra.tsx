import { useEffect, useState } from "react";
import Markdown from "../components/Markdown";
import { useParams, useNavigate } from "react-router-dom";
import {
  Button,
  EmptyState,
  PageHeader,
  Spinner,
  fmtMoney,
} from "../components/UI";
import { toast } from "../components/Toast";
import {
  AlertTriangle,
  Clock,
  Users,
  FileText,
  BarChart2,
  CheckSquare,
  ArrowLeft,
  Edit2,
  Save,
  X,
  TrendingUp,
  Briefcase,
  Shield,
  BookOpen,
  Swords,
  Radar,
  FileDown,
  Handshake,
  Calculator,
} from "lucide-react";
import api from "../lib/api";

interface TimeEntry {
  usuario: string;
  horas: number;
  horas_faturavel: number;
  lancamentos: number;
}
interface Prazo {
  id: string;
  descricao: string;
  due_date: string | null;
  dias_restantes: number | null;
  urgente: boolean;
  tipo: string;
}
interface Checklist {
  id: string;
  nome: string;
  progresso: number;
  total_itens: number;
  itens_ok: number;
}
interface Doc {
  id: string;
  nome: string;
  tipo: string;
  created_at: string | null;
}
interface Movimento {
  id: string;
  tipo: string;
  descricao: string;
  data_movimento: string | null;
}
interface Tese {
  id: string;
  titulo: string;
  taxa_sucesso: number | null;
  resultado: string | null;
  observacoes: string | null;
}
interface TeamMember {
  id: string;
  nome: string;
  role: string;
  responsavel: boolean;
}

interface SalaData {
  caso: {
    id: string;
    numero_interno: string;
    titulo: string;
    area: string;
    status: string;
    fase: string;
    prioridade: string;
    numero_processo: string | null;
    tribunal: string | null;
    comarca: string | null;
    vara: string | null;
    parte_contraria: string | null;
    valor_causa: number | null;
    tese_principal: string | null;
    pontos_fortes: string | null;
    pontos_fracos: string | null;
    observacoes: string | null;
    resultado: string | null;
    licoes_aprendidas: string | null;
    created_at: string | null;
  };
  time: TeamMember[];
  prazos: Prazo[];
  horas: { por_pessoa: TimeEntry[]; total: number };
  checklists: Checklist[];
  documentos_recentes: Doc[];
  movimentos_recentes: Movimento[];
  teses_vinculadas: Tese[];
  risco: {
    indice: number | null;
    nivel: string | null;
    // jsonb no backend: pode vir string, lista, objeto {} ou null
    fatores: unknown;
  };
}

const PRIORIDADE_COLOR: Record<string, string> = {
  urgente: "bg-danger-100 text-danger-700 border border-danger-200",
  alta: "bg-orange-100 text-orange-700 border border-orange-200",
  media: "bg-yellow-100 text-yellow-700 border border-yellow-200",
  baixa: "bg-green-100 text-green-700 border border-green-200",
};

const RISCO_COLOR: Record<string, string> = {
  critico: "text-danger-600",
  alto: "text-orange-500",
  medio: "text-yellow-500",
  baixo: "text-green-500",
};

const SEM_FATORES = "Nenhum fator de risco cadastrado.";

/**
 * `cases.risco_fatores` é jsonb no backend: na prática costuma vir como objeto
 * vazio `{}`, mas também pode ser string, lista de strings ou lista de objetos.
 * Converte qualquer forma para texto Markdown, tratando vazio explicitamente
 * (evita renderizar "[object Object]" — BUG-02).
 */
function fatoresRiscoToText(fatores: unknown): string {
  if (fatores == null) return SEM_FATORES;

  if (typeof fatores === "string") {
    const t = fatores.trim();
    return t.length ? t : SEM_FATORES;
  }

  if (Array.isArray(fatores)) {
    if (fatores.length === 0) return SEM_FATORES;
    const linhas = fatores
      .map((item) => {
        if (item == null) return "";
        if (typeof item === "string") return item.trim();
        if (typeof item === "object") {
          const obj = item as Record<string, unknown>;
          const desc =
            typeof obj.descricao === "string"
              ? obj.descricao
              : typeof obj.fator === "string"
                ? obj.fator
                : JSON.stringify(obj);
          const nivel = typeof obj.nivel === "string" ? ` (${obj.nivel})` : "";
          return `${desc}${nivel}`.trim();
        }
        return String(item);
      })
      .filter((l) => l.length > 0)
      .map((l) => `- ${l}`);
    return linhas.length ? linhas.join("\n") : SEM_FATORES;
  }

  if (typeof fatores === "object") {
    // Objeto genérico (incluindo `{}`, que é truthy). Se vazio → sem fatores.
    const entries = Object.entries(fatores as Record<string, unknown>);
    if (entries.length === 0) return SEM_FATORES;
    return entries
      .map(
        ([k, v]) =>
          `- **${k}:** ${typeof v === "object" ? JSON.stringify(v) : String(v)}`,
      )
      .join("\n");
  }

  return String(fatores);
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-zinc-400 uppercase tracking-wider font-medium">
        {label}
      </span>
      <span className="text-xl font-light text-zinc-800">{value}</span>
      {sub && <span className="text-xs text-zinc-400">{sub}</span>}
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-zinc-100 shadow-sm overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3.5 border-b border-zinc-50">
        <span className="text-bronze">{icon}</span>
        <h3 className="font-medium text-zinc-700 text-sm tracking-wide">
          {title}
        </h3>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

/** Aviso HITL padrão: toda saída de IA é rascunho com revisão obrigatória. */
function AvisoHitl() {
  return (
    <p className="text-[11px] text-warn-700 bg-warn-50 border border-warn-200 rounded-lg px-3 py-2">
      ⚠ Conteúdo gerado por IA — rascunho de apoio. Revisão obrigatória pelo
      advogado responsável antes de qualquer uso.
    </p>
  );
}

// ── War Room — Simulação Adversarial + Sentinela + Visual Law ───────────────
interface SentinelaAlertaProcesso {
  id: string;
  titulo: string;
  numero_interno: string | null;
  ultima_movimentacao: string | null;
}
interface SentinelaAlertaCliente {
  id: string;
  full_name: string;
  ultimo_contato: string | null;
}
interface SentinelaData {
  alertas_processuais: SentinelaAlertaProcesso[];
  alertas_clientes: SentinelaAlertaCliente[];
}

function WarRoomTab({
  caseId,
  tesePadrao,
}: {
  caseId: string;
  tesePadrao: string;
}) {
  const [peticao, setPeticao] = useState(tesePadrao);
  const [simulando, setSimulando] = useState(false);
  const [resultado, setResultado] = useState("");

  const [sentinela, setSentinela] = useState<SentinelaData | null>(null);
  const [sentinelaErro, setSentinelaErro] = useState(false);

  const [gerandoPdf, setGerandoPdf] = useState(false);
  const [pdfUrl, setPdfUrl] = useState("");

  useEffect(() => {
    api
      .get("/sala-de-guerra-v3/sentinela/auditoria")
      .then((r: { data: SentinelaData }) => setSentinela(r.data))
      .catch(() => setSentinelaErro(true));
  }, []);

  const simular = async () => {
    if (!peticao.trim()) {
      toast.error("Descreva a tese/estratégia a ser testada.");
      return;
    }
    setSimulando(true);
    setResultado("");
    try {
      const r = await api.post("/sala-de-guerra-v3/war-room/simular", {
        peticao,
      });
      setResultado(
        typeof r.data === "string"
          ? r.data
          : (r.data?.texto ?? JSON.stringify(r.data, null, 2)),
      );
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Falha na simulação adversarial.",
      );
    } finally {
      setSimulando(false);
    }
  };

  const gerarVisualLaw = async () => {
    setGerandoPdf(true);
    try {
      const r = await api.post(`/sala-de-guerra-v3/visual-law/${caseId}`, {});
      const downloadUrl: string | undefined = r.data?.download_url;
      if (!downloadUrl) throw new Error("download_url ausente na resposta");
      // baseURL do client é /api — remove o prefixo se o backend devolver a URL completa
      const blob = await api.get(downloadUrl.replace(/^\/api/, ""), {
        responseType: "blob",
      });
      const url = URL.createObjectURL(blob.data as Blob);
      setPdfUrl(url);
      const a = document.createElement("a");
      a.href = url;
      a.download = `visual-law-cronologia-${caseId}.pdf`;
      a.click();
      toast.success("PDF Visual Law gerado.");
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Falha ao gerar o PDF Visual Law.",
      );
    } finally {
      setGerandoPdf(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        <Section
          title="War Room — Simulação Adversarial"
          icon={<Swords className="w-4 h-4" />}
        >
          <p className="text-xs text-zinc-400 mb-3">
            A IA assume o papel do advogado da parte contrária e ataca a sua
            tese: nulidades, contradições, jurisprudência defensiva e falta de
            provas.
          </p>
          <textarea
            className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-2 resize-y focus:outline-none focus:ring-1 focus:ring-bronze/40 text-zinc-700"
            rows={6}
            placeholder="Cole aqui a tese, estratégia ou petição inicial a ser blindada…"
            value={peticao}
            onChange={(e) => setPeticao(e.target.value)}
          />
          <div className="mt-3">
            <button
              className="btn-gold text-sm"
              disabled={simulando}
              onClick={simular}
            >
              {simulando
                ? "Simulando parte contrária…"
                : "Simular parte contrária"}
            </button>
          </div>
          {resultado && (
            <div className="mt-4 space-y-3">
              <AvisoHitl />
              <div className="p-4 rounded-lg bg-zinc-50 border border-zinc-100">
                <p className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                  Relatório de vulnerabilidades (visão adversarial)
                </p>
                <Markdown
                  source={resultado}
                  className="text-sm text-zinc-700 leading-relaxed"
                />
              </div>
            </div>
          )}
        </Section>

        <Section
          title="Visual Law — Cronologia em PDF"
          icon={<FileDown className="w-4 h-4" />}
        >
          <p className="text-xs text-zinc-400 mb-3">
            Gera um PDF visual com a cronologia processual do caso, pronto para
            audiências e negociações.
          </p>
          <div className="flex items-center gap-3 flex-wrap">
            <button
              className="btn-gold text-sm"
              disabled={gerandoPdf}
              onClick={gerarVisualLaw}
            >
              {gerandoPdf
                ? "Gerando PDF…"
                : "Gerar Visual Law PDF (cronologia)"}
            </button>
            {pdfUrl && (
              <a
                href={pdfUrl}
                download={`visual-law-cronologia-${caseId}.pdf`}
                className="text-sm text-bronze hover:underline flex items-center gap-1"
              >
                <FileDown className="w-4 h-4" /> Baixar novamente
              </a>
            )}
          </div>
        </Section>
      </div>

      <div className="space-y-6">
        <Section
          title="Sentinela — Auditoria de Inércia"
          icon={<Radar className="w-4 h-4" />}
        >
          {sentinelaErro ? (
            <p className="text-sm text-danger-500">
              Falha ao consultar a Sentinela.
            </p>
          ) : !sentinela ? (
            <p className="text-sm text-zinc-300 italic">
              Auditando inércia processual…
            </p>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-100 bg-zinc-50 px-3 py-2.5 text-center">
                  <div className="text-xl font-light text-zinc-800">
                    {sentinela.alertas_processuais.length}
                  </div>
                  <div className="text-[10px] text-zinc-400 uppercase tracking-wider">
                    Processos parados &gt;60d
                  </div>
                </div>
                <div className="rounded-lg border border-zinc-100 bg-zinc-50 px-3 py-2.5 text-center">
                  <div className="text-xl font-light text-zinc-800">
                    {sentinela.alertas_clientes.length}
                  </div>
                  <div className="text-[10px] text-zinc-400 uppercase tracking-wider">
                    Clientes sem reporte &gt;30d
                  </div>
                </div>
              </div>

              {sentinela.alertas_processuais.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                    Processos sem movimentação
                  </p>
                  <div className="space-y-1.5 max-h-44 overflow-y-auto">
                    {sentinela.alertas_processuais.map((p) => (
                      <div
                        key={p.id}
                        className="flex items-center justify-between text-xs py-1 border-b border-zinc-50 last:border-0"
                      >
                        <span className="text-zinc-600 line-clamp-1 mr-2">
                          {p.numero_interno ? `${p.numero_interno} — ` : ""}
                          {p.titulo}
                        </span>
                        <span className="text-orange-500 shrink-0">
                          {p.ultima_movimentacao
                            ? new Date(
                                p.ultima_movimentacao,
                              ).toLocaleDateString("pt-BR")
                            : "sem registro"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {sentinela.alertas_clientes.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                    Clientes sem contato
                  </p>
                  <div className="space-y-1.5 max-h-44 overflow-y-auto">
                    {sentinela.alertas_clientes.map((c) => (
                      <div
                        key={c.id}
                        className="flex items-center justify-between text-xs py-1 border-b border-zinc-50 last:border-0"
                      >
                        <span className="text-zinc-600 line-clamp-1 mr-2">
                          {c.full_name}
                        </span>
                        <span className="text-orange-500 shrink-0">
                          {c.ultimo_contato
                            ? new Date(c.ultimo_contato).toLocaleDateString(
                                "pt-BR",
                              )
                            : "nunca"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {sentinela.alertas_processuais.length === 0 &&
                sentinela.alertas_clientes.length === 0 && (
                  <p className="text-sm text-success-600">
                    ✓ Nenhum alerta de inércia — carteira em dia.
                  </p>
                )}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}

// ── Acordo & Liquidez — Diplomacia Digital ───────────────────────────────────
interface AcordoResultado {
  valor_causa: number;
  probabilidade_exito: number;
  tempo_estimado_anos: number;
  valor_presente_liquido: number;
  sugestao_acordo_ideal: number;
  custo_oportunidade_perda: number;
  custos_estimados?: number;
  selic_anual?: number;
  selic_fonte?: string; // "bcb" | "fallback" | "informada" (aditivo no backend)
}

function AcordoTab({
  caseId,
  caso,
}: {
  caseId: string;
  caso: SalaData["caso"];
}) {
  const [form, setForm] = useState({
    valor_causa: caso.valor_causa != null ? String(caso.valor_causa) : "",
    prob_exito_pct: "",
    tempo_anos: "",
    custas_pct: "",
    honorarios_sucumbencia_pct: "",
  });
  const [res, setRes] = useState<AcordoResultado | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [preenchendo, setPreenchendo] = useState(false);
  const [dossie, setDossie] = useState("");
  const [gerandoDossie, setGerandoDossie] = useState(false);

  const set = (k: keyof typeof form) => (e: any) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const preencherJurimetria = async () => {
    setPreenchendo(true);
    try {
      const r = await api.get("/jurimetria/ext/benchmarks", {
        params: caso.tribunal ? { tribunal: caso.tribunal } : {},
      });
      const porResultado: { resultado_raw: string; total: number }[] =
        r.data?.por_resultado ?? [];
      const total = porResultado.reduce((s, x) => s + x.total, 0);
      const favoraveis = porResultado
        .filter((x) =>
          ["exito_total", "exito_parcial", "acordo"].includes(x.resultado_raw),
        )
        .reduce((s, x) => s + x.total, 0);
      const diasMedio: number = r.data?.tempo_tramitacao?.dias_medio ?? 0;

      let aplicou = false;
      const next = { ...form };
      if (total > 0) {
        next.prob_exito_pct = String(
          Math.round((favoraveis / total) * 1000) / 10,
        );
        aplicou = true;
      }
      if (diasMedio > 0) {
        next.tempo_anos = String(Math.round((diasMedio / 365) * 10) / 10);
        aplicou = true;
      }
      if (aplicou) {
        setForm(next);
        toast.success(
          `Jurimetria aplicada — base interna${caso.tribunal ? ` (${caso.tribunal})` : ""}.`,
        );
      } else {
        toast.info(
          "Sem dados históricos suficientes na jurimetria para pré-preencher.",
        );
      }
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao consultar jurimetria.");
    } finally {
      setPreenchendo(false);
    }
  };

  const calcular = async () => {
    const valor = parseFloat(form.valor_causa);
    const prob = parseFloat(form.prob_exito_pct);
    const tempo = parseFloat(form.tempo_anos);
    if (!valor || !prob || !tempo) {
      toast.error(
        "Preencha valor da causa, probabilidade de êxito e tempo estimado.",
      );
      return;
    }
    setCalculando(true);
    setRes(null);
    setDossie("");
    try {
      const r = await api.post("/diplomacia-v3/calcular-acordo", {
        valor_causa: valor,
        prob_exito: prob / 100,
        tempo_anos: tempo,
        custas_pct: (parseFloat(form.custas_pct) || 0) / 100,
        honorarios_sucumbencia_pct:
          (parseFloat(form.honorarios_sucumbencia_pct) || 0) / 100,
      });
      setRes(r.data);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha no cálculo do acordo.");
    } finally {
      setCalculando(false);
    }
  };

  const gerarDossie = async () => {
    if (!res) {
      toast.error("Calcule o acordo antes de gerar o dossiê.");
      return;
    }
    setGerandoDossie(true);
    setDossie("");
    try {
      // Contrato real: POST /diplomacia-v3/dossie-pressao
      // body {case_id?, valor_causa, prob_exito, tempo_anos} → {argumentacao,…}
      const r = await api.post("/diplomacia-v3/dossie-pressao", {
        case_id: caseId,
        valor_causa: res.valor_causa,
        prob_exito: res.probabilidade_exito,
        tempo_anos: res.tempo_estimado_anos,
      });
      const d = r.data;
      setDossie(
        typeof d === "string"
          ? d
          : (d?.argumentacao ?? d?.dossie ?? d?.texto ?? ""),
      );
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Falha ao gerar o dossiê de pressão.",
      );
    } finally {
      setGerandoDossie(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        <Section
          title="Calculadora de Acordo Racional (VPL)"
          icon={<Calculator className="w-4 h-4" />}
        >
          <p className="text-xs text-zinc-400 mb-4">
            Valor presente líquido do processo descontado pela Selic — quanto
            vale um acordo hoje versus litigar até o fim.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-zinc-400 uppercase tracking-wider block mb-1">
                Valor da causa (R$)
              </label>
              <input
                type="number"
                step="0.01"
                className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-bronze/40 text-zinc-700"
                value={form.valor_causa}
                onChange={set("valor_causa")}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400 uppercase tracking-wider block mb-1">
                Prob. de êxito (%)
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="100"
                className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-bronze/40 text-zinc-700"
                value={form.prob_exito_pct}
                onChange={set("prob_exito_pct")}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400 uppercase tracking-wider block mb-1">
                Tempo estimado (anos)
              </label>
              <input
                type="number"
                step="0.1"
                className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-bronze/40 text-zinc-700"
                value={form.tempo_anos}
                onChange={set("tempo_anos")}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400 uppercase tracking-wider block mb-1">
                Custas (% da causa)
              </label>
              <input
                type="number"
                step="0.1"
                className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-bronze/40 text-zinc-700"
                placeholder="0"
                value={form.custas_pct}
                onChange={set("custas_pct")}
              />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-zinc-400 uppercase tracking-wider block mb-1">
                Honorários sucumbência (%)
              </label>
              <input
                type="number"
                step="0.1"
                className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-bronze/40 text-zinc-700"
                placeholder="0"
                value={form.honorarios_sucumbencia_pct}
                onChange={set("honorarios_sucumbencia_pct")}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-4">
            <button
              className="btn-secondary text-sm"
              disabled={preenchendo}
              onClick={preencherJurimetria}
            >
              {preenchendo ? "Consultando…" : "Pré-preencher da jurimetria"}
            </button>
            <button
              className="btn-gold text-sm"
              disabled={calculando}
              onClick={calcular}
            >
              {calculando ? "Calculando…" : "Calcular acordo racional"}
            </button>
          </div>

          {res && (
            <div className="mt-5 space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="rounded-lg border border-zinc-100 bg-zinc-50 px-4 py-3">
                  <div className="text-[10px] text-zinc-400 uppercase tracking-wider">
                    VPL do processo
                  </div>
                  <div className="text-lg font-light text-zinc-800">
                    {fmtMoney(res.valor_presente_liquido)}
                  </div>
                </div>
                <div className="rounded-lg border border-bronze/30 bg-bronze/5 px-4 py-3">
                  <div className="text-[10px] text-bronze uppercase tracking-wider">
                    Acordo racional sugerido
                  </div>
                  <div className="text-lg font-medium text-bronze">
                    {fmtMoney(res.sugestao_acordo_ideal)}
                  </div>
                </div>
                <div className="rounded-lg border border-zinc-100 bg-zinc-50 px-4 py-3">
                  <div className="text-[10px] text-zinc-400 uppercase tracking-wider">
                    Custo de oportunidade
                  </div>
                  <div className="text-lg font-light text-zinc-800">
                    {fmtMoney(res.custo_oportunidade_perda)}
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-400">
                {res.selic_anual != null && (
                  <span>
                    Selic usada no desconto:{" "}
                    <b className="text-zinc-600">
                      {(res.selic_anual * 100).toFixed(2)}% a.a.
                    </b>
                    {res.selic_fonte ? ` (fonte: ${res.selic_fonte})` : ""}
                  </span>
                )}
                {res.custos_estimados != null && (
                  <span>
                    Custos estimados:{" "}
                    <b className="text-zinc-600">
                      {fmtMoney(res.custos_estimados)}
                    </b>
                  </span>
                )}
              </div>
              <div className="pt-3 border-t border-zinc-100">
                <button
                  className="btn-secondary text-sm"
                  disabled={gerandoDossie}
                  onClick={gerarDossie}
                >
                  {gerandoDossie
                    ? "Gerando dossiê…"
                    : "Gerar dossiê de pressão"}
                </button>
              </div>
            </div>
          )}
        </Section>

        {dossie && (
          <Section
            title="Dossiê de Pressão"
            icon={<Handshake className="w-4 h-4" />}
          >
            <div className="space-y-3">
              <AvisoHitl />
              <Markdown
                source={dossie}
                className="text-sm text-zinc-700 leading-relaxed"
              />
            </div>
          </Section>
        )}
      </div>

      <div className="space-y-6">
        <Section title="Como funciona" icon={<Shield className="w-4 h-4" />}>
          <ul className="text-xs text-zinc-500 space-y-2 list-disc list-inside">
            <li>
              <b>VPL</b> = (valor × probabilidade − custos) ÷ (1 + Selic)^anos.
            </li>
            <li>
              A Selic anual usada é a retornada pelo backend (Banco Central).
            </li>
            <li>
              O pré-preenchimento usa a taxa histórica de êxito e o tempo médio
              de tramitação da base interna (jurimetria).
            </li>
            <li>
              O acordo sugerido inclui margem de conveniência de 5% sobre o VPL.
            </li>
          </ul>
        </Section>
      </div>
    </div>
  );
}

export default function SalaDeGuerra() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<SalaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [editando, setEditando] = useState(false);
  const [notas, setNotas] = useState({
    tese_principal: "",
    pontos_fortes: "",
    pontos_fracos: "",
    observacoes: "",
  });
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<"visao" | "warroom" | "acordo">("visao");

  useEffect(() => {
    if (!caseId) return;
    api
      .get(`/cases/${caseId}/sala-de-guerra`)
      .then((r: { data: SalaData }) => {
        setData(r.data);
        const c = r.data.caso;
        setNotas({
          tese_principal: c.tese_principal ?? "",
          pontos_fortes: c.pontos_fortes ?? "",
          pontos_fracos: c.pontos_fracos ?? "",
          observacoes: c.observacoes ?? "",
        });
      })
      // 403/erro (sem acesso ao caso): degrada para o EmptyState, sem crash.
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [caseId]);

  const salvarNotas = async () => {
    if (!caseId) return;
    setSaving(true);
    await api.patch(`/cases/${caseId}/sala-de-guerra/notas`, notas);
    setSaving(false);
    setEditando(false);
    // refresh
    const r = (await api.get(`/cases/${caseId}/sala-de-guerra`)) as {
      data: SalaData;
    };
    setData(r.data);
  };

  if (loading) return <Spinner />;
  if (!data) return <EmptyState title="Caso não encontrado." />;

  const {
    caso,
    time,
    prazos,
    horas,
    checklists,
    documentos_recentes,
    movimentos_recentes,
    teses_vinculadas,
    risco,
  } = data;
  const prazosUrgentes = prazos.filter(
    (p) => p.urgente || (p.dias_restantes !== null && p.dias_restantes <= 7),
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="mt-1 h-auto w-auto p-1.5 text-zinc-400"
          aria-label="Voltar"
          onClick={() => navigate(-1)}
          icon={<ArrowLeft className="w-4 h-4" />}
        />
        <div className="flex-1 min-w-0">
          <PageHeader
            eyebrow={`Sala de Guerra · ${caso.numero_interno}`}
            title={caso.titulo}
            subtitle={`${
              caso.parte_contraria ? `vs. ${caso.parte_contraria} · ` : ""
            }${caso.tribunal ?? caso.comarca ?? ""}`}
            actions={
              <>
                {caso.prioridade && (
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${PRIORIDADE_COLOR[caso.prioridade] ?? "bg-zinc-100 text-zinc-500"}`}
                  >
                    {caso.prioridade.toUpperCase()}
                  </span>
                )}
                {risco.nivel && (
                  <span
                    className={`text-sm font-medium ${RISCO_COLOR[risco.nivel] ?? "text-zinc-500"}`}
                  >
                    Risco {risco.nivel}{" "}
                    {risco.indice !== null ? `(${risco.indice})` : ""}
                  </span>
                )}
              </>
            }
          />
        </div>
      </div>

      {/* Alertas urgentes */}
      {prazosUrgentes.length > 0 && (
        <div className="bg-danger-50 border border-danger-200 rounded-xl px-5 py-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-danger-500" />
            <span className="text-sm font-medium text-danger-700">
              Atenção — {prazosUrgentes.length} prazo(s) crítico(s)
            </span>
          </div>
          <div className="space-y-1.5">
            {prazosUrgentes.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-danger-700">{p.descricao}</span>
                <span
                  className={`text-xs font-medium ${p.urgente ? "text-danger-600" : "text-orange-500"}`}
                >
                  {p.urgente ? "VENCIDO" : `${p.dias_restantes}d`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-zinc-100 shadow-sm px-5 py-4">
          <Stat
            label="HH Total"
            value={`${horas.total}h`}
            sub={`${horas.por_pessoa.length} profissional(is)`}
          />
        </div>
        <div className="bg-white rounded-xl border border-zinc-100 shadow-sm px-5 py-4">
          <Stat
            label="Prazos abertos"
            value={prazos.length}
            sub={`${prazosUrgentes.length} urgentes`}
          />
        </div>
        <div className="bg-white rounded-xl border border-zinc-100 shadow-sm px-5 py-4">
          <Stat
            label="Valor da causa"
            value={
              caso.valor_causa
                ? `R$ ${caso.valor_causa.toLocaleString("pt-BR", { minimumFractionDigits: 0 })}`
                : "—"
            }
          />
        </div>
        <div className="bg-white rounded-xl border border-zinc-100 shadow-sm px-5 py-4">
          <Stat label="Fase" value={caso.fase ?? "—"} sub={caso.status} />
        </div>
      </div>

      {/* Abas */}
      <div className="flex gap-1 border-b border-zinc-200">
        {(
          [
            { id: "visao", label: "Visão Geral", icon: Shield },
            { id: "warroom", label: "War Room", icon: Swords },
            { id: "acordo", label: "Acordo & Liquidez", icon: Handshake },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
              tab === t.id
                ? "border-bronze text-bronze"
                : "border-transparent text-zinc-400 hover:text-zinc-600"
            }`}
          >
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "warroom" && caseId && (
        <WarRoomTab caseId={caseId} tesePadrao={caso.tese_principal ?? ""} />
      )}
      {tab === "acordo" && caseId && <AcordoTab caseId={caseId} caso={caso} />}

      <div
        className={
          tab === "visao" ? "grid grid-cols-1 lg:grid-cols-3 gap-6" : "hidden"
        }
      >
        {/* Left column (2/3) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Notas estratégicas */}
          <Section
            title="Análise Estratégica"
            icon={<Shield className="w-4 h-4" />}
          >
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs text-zinc-400">
                Tese, pontos fortes/fracos e observações
              </span>
              {!editando ? (
                <button
                  onClick={() => setEditando(true)}
                  className="flex items-center gap-1 text-xs text-bronze hover:underline"
                >
                  <Edit2 className="w-3 h-3" /> Editar
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => setEditando(false)}
                    className="flex items-center gap-1 text-xs text-zinc-400 hover:underline"
                  >
                    <X className="w-3 h-3" /> Cancelar
                  </button>
                  <button
                    onClick={salvarNotas}
                    disabled={saving}
                    className="flex items-center gap-1 text-xs text-bronze hover:underline"
                  >
                    <Save className="w-3 h-3" />{" "}
                    {saving ? "Salvando…" : "Salvar"}
                  </button>
                </div>
              )}
            </div>
            <div className="space-y-4">
              {(
                [
                  "tese_principal",
                  "pontos_fortes",
                  "pontos_fracos",
                  "observacoes",
                ] as const
              ).map((field) => (
                <div key={field}>
                  <label className="text-xs text-zinc-400 uppercase tracking-wider block mb-1.5">
                    {field === "tese_principal"
                      ? "Tese Principal"
                      : field === "pontos_fortes"
                        ? "Pontos Fortes"
                        : field === "pontos_fracos"
                          ? "Pontos Fracos"
                          : "Observações"}
                  </label>
                  {editando ? (
                    <textarea
                      className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-bronze/40 text-zinc-700"
                      rows={3}
                      value={notas[field]}
                      onChange={(e) =>
                        setNotas((n) => ({ ...n, [field]: e.target.value }))
                      }
                    />
                  ) : (
                    <p className="text-sm text-zinc-600 whitespace-pre-wrap">
                      {notas[field] || (
                        <span className="text-zinc-300 italic">
                          Não preenchido
                        </span>
                      )}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </Section>

          {/* Prazos */}
          <Section title="Prazos" icon={<Clock className="w-4 h-4" />}>
            {prazos.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Nenhum prazo nos próximos 30 dias.
              </p>
            ) : (
              <div className="space-y-2">
                {prazos.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center justify-between py-2 border-b border-zinc-50 last:border-0"
                  >
                    <div>
                      <p className="text-sm text-zinc-700">{p.descricao}</p>
                      <p className="text-xs text-zinc-400 mt-0.5">
                        {p.tipo} ·{" "}
                        {p.due_date
                          ? new Date(p.due_date).toLocaleDateString("pt-BR")
                          : "—"}
                      </p>
                    </div>
                    <span
                      className={`text-xs font-medium shrink-0 ml-4 ${p.urgente ? "text-danger-600" : p.dias_restantes !== null && p.dias_restantes <= 7 ? "text-orange-500" : "text-zinc-400"}`}
                    >
                      {p.urgente
                        ? "VENCIDO"
                        : p.dias_restantes !== null
                          ? `${p.dias_restantes}d`
                          : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Horas */}
          <Section
            title="Horas Trabalhadas"
            icon={<BarChart2 className="w-4 h-4" />}
          >
            {horas.por_pessoa.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Nenhum lançamento de horas.
              </p>
            ) : (
              <div className="space-y-3">
                {horas.por_pessoa.map((p, i) => (
                  <div key={i}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-zinc-700">{p.usuario}</span>
                      <span className="text-sm font-light text-zinc-700">
                        {p.horas}h{" "}
                        <span className="text-xs text-zinc-400">
                          ({p.horas_faturavel}h fat.)
                        </span>
                      </span>
                    </div>
                    <div className="h-1.5 bg-zinc-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-bronze/60 rounded-full"
                        style={{
                          width: `${horas.total > 0 ? (p.horas / horas.total) * 100 : 0}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
                <div className="pt-2 border-t border-zinc-50 flex justify-between text-xs text-zinc-400">
                  <span>Total</span>
                  <span className="font-medium text-zinc-600">
                    {horas.total}h
                  </span>
                </div>
              </div>
            )}
          </Section>

          {/* Movimentos */}
          <Section
            title="Movimentos Recentes"
            icon={<Briefcase className="w-4 h-4" />}
          >
            {movimentos_recentes.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Nenhum movimento registrado.
              </p>
            ) : (
              <div className="space-y-2">
                {movimentos_recentes.map((m) => (
                  <div
                    key={m.id}
                    className="py-2 border-b border-zinc-50 last:border-0"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-zinc-400 uppercase tracking-wide">
                        {m.tipo}
                      </span>
                      <span className="text-xs text-zinc-300">
                        {m.data_movimento
                          ? new Date(m.data_movimento).toLocaleDateString(
                              "pt-BR",
                            )
                          : ""}
                      </span>
                    </div>
                    <p className="text-sm text-zinc-600 mt-0.5 line-clamp-2">
                      {m.descricao}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>

        {/* Right column (1/3) */}
        <div className="space-y-6">
          {/* Time */}
          <Section title="Time" icon={<Users className="w-4 h-4" />}>
            {time.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Sem advogados vinculados.
              </p>
            ) : (
              <div className="space-y-3">
                {time.map((m) => (
                  <div key={m.id} className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-bronze/10 flex items-center justify-center text-bronze text-sm font-medium shrink-0">
                      {m.nome[0]?.toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm text-zinc-700">{m.nome}</p>
                      <p className="text-xs text-zinc-400">
                        {m.responsavel ? "Responsável" : "Auxiliar"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Checklists */}
          <Section
            title="Checklists"
            icon={<CheckSquare className="w-4 h-4" />}
          >
            {checklists.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">Nenhum checklist.</p>
            ) : (
              <div className="space-y-3">
                {checklists.map((ck) => (
                  <div key={ck.id}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-zinc-700 truncate mr-2">
                        {ck.nome}
                      </span>
                      <span className="text-xs text-zinc-400 shrink-0">
                        {ck.itens_ok}/{ck.total_itens}
                      </span>
                    </div>
                    <div className="h-1.5 bg-zinc-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-success-400 rounded-full transition-all"
                        style={{
                          width: `${ck.total_itens > 0 ? (ck.itens_ok / ck.total_itens) * 100 : 0}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Teses */}
          <Section
            title="Teses Vinculadas"
            icon={<BookOpen className="w-4 h-4" />}
          >
            {teses_vinculadas.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">
                Nenhuma tese vinculada.
              </p>
            ) : (
              <div className="space-y-3">
                {teses_vinculadas.map((t) => (
                  <div
                    key={t.id}
                    className="py-2 border-b border-zinc-50 last:border-0"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-zinc-700 line-clamp-2">
                        {t.titulo}
                      </p>
                      {t.taxa_sucesso !== null && (
                        <span className="text-xs font-medium text-success-600 shrink-0">
                          {t.taxa_sucesso}%
                        </span>
                      )}
                    </div>
                    {t.resultado && (
                      <p className="text-xs text-zinc-400 mt-0.5">
                        {t.resultado}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Documentos */}
          <Section
            title="Documentos Recentes"
            icon={<FileText className="w-4 h-4" />}
          >
            {documentos_recentes.length === 0 ? (
              <p className="text-sm text-zinc-300 italic">Nenhum documento.</p>
            ) : (
              <div className="space-y-2">
                {documentos_recentes.map((d) => (
                  <div
                    key={d.id}
                    className="flex items-center justify-between py-1.5 border-b border-zinc-50 last:border-0"
                  >
                    <div>
                      <p className="text-sm text-zinc-700 line-clamp-1">
                        {d.nome}
                      </p>
                      <p className="text-xs text-zinc-400">{d.tipo}</p>
                    </div>
                    <span className="text-xs text-zinc-300 shrink-0 ml-2">
                      {d.created_at
                        ? new Date(d.created_at).toLocaleDateString("pt-BR")
                        : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Risco */}
          <Section
            title="Fatores de Risco"
            icon={<TrendingUp className="w-4 h-4" />}
          >
            <Markdown
              source={fatoresRiscoToText(risco.fatores)}
              className="text-sm text-zinc-600"
            />
          </Section>
        </div>
      </div>
    </div>
  );
}
