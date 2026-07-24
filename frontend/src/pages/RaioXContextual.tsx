import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  FileText,
  Gavel,
  Loader2,
  RefreshCw,
  Scale,
} from "lucide-react";
import Markdown from "../components/Markdown";
import api, {
  analiseAdvogadoContextual,
  type AnaliseAdvogadoResult,
} from "../lib/api";

type ContextualReport = {
  aviso?: string;
  identificacao?: Record<string, unknown>;
  sintese_executiva?: string;
  pontos_fortes?: unknown[];
  pontos_fracos?: unknown[];
  tese_principal?: string | null;
  documentos?: Array<Record<string, unknown>>;
  prazos?: Array<Record<string, unknown>>;
  tarefas?: Array<Record<string, unknown>>;
  proximos_passos?: unknown[];
};

const asText = (value: unknown): string => {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const item = value as Record<string, unknown>;
    const preferred =
      item.titulo ?? item.texto ?? item.descricao ?? item.nome ?? item.status;
    return preferred ? String(preferred) : JSON.stringify(item);
  }
  return String(value ?? "");
};

function ListCard({
  title,
  items,
  empty,
}: {
  title: string;
  items?: unknown[];
  empty: string;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-xs font-bold uppercase tracking-[0.12em] text-slate-600">
        {title}
      </h3>
      {!items?.length ? (
        <p className="mt-3 text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((item, index) => (
            <li
              key={`${title}-${index}`}
              className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-sm leading-relaxed text-slate-700"
            >
              {asText(item)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function RaioXContextual({ caseId }: { caseId: string }) {
  const [report, setReport] = useState<ContextualReport | null>(null);
  const [analysis, setAnalysis] = useState<AnaliseAdvogadoResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get<ContextualReport>(
        `/raio-x/contextual/${caseId}`,
      );
      setReport(data);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          "Não foi possível carregar o Raio-X contextual do caso.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [caseId]);

  const runSeniorAnalysis = async () => {
    setAnalyzing(true);
    setError(null);
    try {
      setAnalysis(await analiseAdvogadoContextual(caseId));
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          "A análise como advogado sênior não pôde ser concluída.",
      );
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) {
    return (
      <div className="grid min-h-[65vh] place-items-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
      </div>
    );
  }

  const identification = report?.identificacao || {};
  const title = String(identification.titulo || "Caso em análise");

  return (
    <div className="space-y-5">
      <header className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start gap-4">
          <div className="rounded-2xl bg-slate-950 p-3 text-white">
            <Scale className="h-6 w-6" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary-600">
              Raio-X contextual
            </p>
            <h1 className="mt-1 truncate text-xl font-bold text-slate-950">
              {title}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Leitura do caso oficial existente. Este fluxo não cria nem converte cadastros.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => window.location.assign(`/casos/${caseId}`)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              <ArrowLeft className="h-4 w-4" /> Voltar ao caso
            </button>
            <button
              onClick={() => void load()}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw className="h-4 w-4" /> Atualizar
            </button>
            <button
              onClick={() => void runSeniorAnalysis()}
              disabled={analyzing}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
            >
              {analyzing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Gavel className="h-4 w-4" />
              )}
              Analisar como advogado
            </button>
          </div>
        </div>
      </header>

      {error && (
        <div className="flex gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </div>
      )}

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-primary-600" />
          <h2 className="font-bold text-slate-950">Síntese registrada</h2>
        </div>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
          {report?.sintese_executiva || "Síntese ainda não registrada no caso."}
        </p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Área", identification.area],
            ["Fase", identification.fase],
            ["Tribunal", identification.tribunal],
            ["Parte contrária", identification.parte_contraria],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-xl bg-slate-50 p-3">
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                {String(label)}
              </p>
              <p className="mt-1 truncate text-sm font-semibold text-slate-700">
                {value ? String(value) : "Não informado"}
              </p>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <ListCard
          title="Pontos fortes"
          items={report?.pontos_fortes}
          empty="Nenhum ponto forte registrado."
        />
        <ListCard
          title="Pontos fracos"
          items={report?.pontos_fracos}
          empty="Nenhuma fragilidade registrada."
        />
        <ListCard
          title="Próximos passos"
          items={report?.proximos_passos}
          empty="Nenhum próximo passo cadastrado."
        />
        <ListCard
          title="Prazos e tarefas"
          items={[...(report?.prazos || []), ...(report?.tarefas || [])]}
          empty="Nenhum prazo ou tarefa vinculado."
        />
      </div>

      {report?.tese_principal && (
        <section className="rounded-2xl border border-blue-200 bg-blue-50 p-4">
          <div className="flex items-center gap-2 text-blue-800">
            <CheckCircle2 className="h-4 w-4" />
            <h2 className="text-sm font-bold">Tese principal registrada</h2>
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-blue-950">
            {report.tese_principal}
          </p>
        </section>
      )}

      {analysis && (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary-600" />
            <h2 className="font-bold text-slate-950">
              Análise como advogado sênior
            </h2>
          </div>
          {analysis.status === "ok" && analysis.analise ? (
            <>
              <Markdown source={analysis.analise} className="mt-4 text-sm text-slate-700" />
              {analysis.critica_adversarial?.relatorio && (
                <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4">
                  <h3 className="text-sm font-bold text-amber-900">
                    Crítica adversarial
                    {analysis.critica_adversarial.nota_robustez !== undefined
                      ? ` · robustez ${analysis.critica_adversarial.nota_robustez}`
                      : ""}
                  </h3>
                  <Markdown
                    source={analysis.critica_adversarial.relatorio}
                    className="mt-2 text-sm text-amber-950"
                  />
                </div>
              )}
            </>
          ) : (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              {analysis.detalhe ||
                "A análise agêntica está indisponível na configuração atual."}
            </div>
          )}
          <p className="mt-4 text-xs text-slate-400">
            Rascunho de apoio sujeito à revisão humana obrigatória.
          </p>
        </section>
      )}
    </div>
  );
}
