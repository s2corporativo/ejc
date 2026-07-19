import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Download,
  FileText,
  RefreshCw,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Badge, Button, EmptyState, Modal, Spinner } from "./UI";

type Severity = "P0" | "P1" | "P2" | "P3" | "INFO";

type Finding = {
  tipo: string;
  severidade: Severity;
  titulo: string;
  detalhe: string;
  sugestao: string;
  alvo?: string | null;
  evidencias: string[];
  aplicado: boolean;
  requer_revisao_humana: boolean;
};

type AutoFixReport = {
  modo: "diagnostico";
  dry_run: boolean;
  aplicou_correcoes: boolean;
  requer_revisao_humana: boolean;
  resumo: string;
  metricas: {
    modulos_esperados: number;
    topicos_help_ativos: number;
    rotas_api_detectadas: number;
    modulos_com_backend: number;
    colisoes_metodo_rota: number;
    achados: number;
    por_severidade: Partial<Record<Severity, number>>;
  };
  achados: Finding[];
  proximos_passos: string[];
};

const ORDER: Record<Severity, number> = {
  P0: 0,
  P1: 1,
  P2: 2,
  P3: 3,
  INFO: 4,
};

const TONE: Record<Severity, "red" | "amber" | "blue" | "slate"> = {
  P0: "red",
  P1: "red",
  P2: "amber",
  P3: "blue",
  INFO: "slate",
};

export function ordenarAchados(items: Finding[]): Finding[] {
  return [...items].sort(
    (a, b) =>
      ORDER[a.severidade] - ORDER[b.severidade] ||
      a.titulo.localeCompare(b.titulo, "pt-BR"),
  );
}

function detalheErro(error: unknown): string {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } }
  )?.response?.data?.detail;
  return typeof detail === "string" && detail
    ? detail
    : "Não foi possível executar o diagnóstico AutoFix.";
}

export default function AutoFixPanel() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [report, setReport] = useState<AutoFixReport | null>(null);

  const findings = useMemo(
    () => ordenarAchados(report?.achados || []),
    [report],
  );

  const carregar = async () => {
    setLoading(true);
    try {
      const response = await api.get<AutoFixReport>(
        "/module-help/diagnostico-sistema",
      );
      setReport(response.data);
    } catch (error) {
      toast.error(detalheErro(error));
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  const preencherManuais = async () => {
    setSeeding(true);
    try {
      await api.post("/module-help/preencher-minimo");
      toast.success("Manuais mínimos preenchidos de forma idempotente.");
      await carregar();
    } catch (error) {
      toast.error(detalheErro(error));
    } finally {
      setSeeding(false);
    }
  };

  const exportar = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `ejc-autofix-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    if (open) void carregar();
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 shadow-md transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2"
        aria-label="Abrir AutoFix em modo diagnóstico"
      >
        <Bot className="h-4 w-4 text-primary-700" />
        AutoFix
      </button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="IA AutoFix — diagnóstico assistido"
        size="xl"
      >
        {loading ? (
          <div className="grid min-h-64 place-items-center">
            <Spinner />
          </div>
        ) : !report ? (
          <EmptyState
            icon={AlertTriangle}
            title="Diagnóstico indisponível"
            message="Nenhuma alteração foi aplicada. Execute novamente para obter o relatório."
            action={
              <Button
                variant="secondary"
                onClick={() => void carregar()}
                icon={<RefreshCw className="h-4 w-4" />}
              >
                Executar diagnóstico
              </Button>
            }
          />
        ) : (
          <div className="space-y-6">
            <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-5 w-5 text-primary-700" />
                    <h3 className="font-semibold text-slate-950">
                      Modo somente leitura
                    </h3>
                  </div>
                  <p className="mt-1 max-w-2xl text-sm text-slate-600">
                    {report.resumo} Patches, migrations e deploy exigem branch,
                    revisão humana e CI verde.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={exportar}
                    icon={<Download className="h-4 w-4" />}
                  >
                    Exportar JSON
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void carregar()}
                    icon={<RefreshCw className="h-4 w-4" />}
                  >
                    Reexecutar
                  </Button>
                </div>
              </div>
            </section>

            <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <Metric label="Rotas" value={report.metricas.rotas_api_detectadas} />
              <Metric label="Módulos" value={report.metricas.modulos_esperados} />
              <Metric
                label="Cobertos"
                value={report.metricas.modulos_com_backend}
              />
              <Metric label="Achados" value={report.metricas.achados} />
              <Metric
                label="Colisões"
                value={report.metricas.colisoes_metodo_rota}
              />
            </section>

            <section>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-slate-950">
                    Achados priorizados
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">
                    P0 e P1 devem bloquear release até correção ou aceite formal de risco.
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  loading={seeding}
                  onClick={() => void preencherManuais()}
                  icon={<FileText className="h-4 w-4" />}
                >
                  Preencher manuais mínimos
                </Button>
              </div>

              {!findings.length ? (
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-600">
                  Nenhuma lacuna foi identificada pelos scanners atuais.
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  {findings.map((finding, index) => (
                    <article
                      key={`${finding.tipo}-${finding.alvo || index}`}
                      className="rounded-xl border border-slate-200 p-4"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={TONE[finding.severidade]}>
                          {finding.severidade}
                        </Badge>
                        <span className="text-xs text-slate-500">
                          {finding.tipo}
                        </span>
                      </div>
                      <h4 className="mt-2 font-semibold text-slate-950">
                        {finding.titulo}
                      </h4>
                      <p className="mt-1 text-sm text-slate-600">
                        {finding.detalhe}
                      </p>
                      <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
                        <span className="font-semibold">Correção recomendada: </span>
                        {finding.sugestao}
                      </div>
                      {!!finding.evidencias?.length && (
                        <ul className="mt-3 space-y-1 font-mono text-xs text-slate-500">
                          {finding.evidencias.slice(0, 8).map((evidence) => (
                            <li key={evidence}>• {evidence}</li>
                          ))}
                        </ul>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-xl border border-slate-200 p-4">
              <div className="flex items-center gap-2">
                <Wrench className="h-4 w-4 text-slate-600" />
                <h3 className="font-semibold text-slate-950">Próximos passos</h3>
              </div>
              <ol className="mt-3 space-y-2 text-sm text-slate-600">
                {report.proximos_passos.map((step, index) => (
                  <li key={step}>
                    {index + 1}. {step}
                  </li>
                ))}
              </ol>
            </section>
          </div>
        )}
      </Modal>
    </>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 p-4 text-center">
      <div className="text-2xl font-bold tabular-nums text-slate-950">{value}</div>
      <div className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
    </div>
  );
}
