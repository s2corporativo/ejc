import { useEffect, useRef, useState } from "react";
import { BrainCircuit, ClipboardCheck, ShieldAlert } from "lucide-react";
import {
  runDptAction,
  type DptAction,
  type DptActionResponse,
  type DptCompany,
} from "./api";

const ACTIONS: Array<{ value: DptAction; label: string; description: string }> =
  [
    {
      value: "conselho",
      label: "Modo Conselho",
      description:
        "Prioridades executivas e redução de risco com base na realidade registrada.",
    },
    {
      value: "diagnostico",
      label: "Diagnóstico",
      description:
        "Fatos, provas, questões, teses, riscos, lacunas e providências.",
    },
    {
      value: "preflight",
      label: "Pré-flight",
      description:
        "Consistência de fatos, fontes, vigência, datas, provas e contradições.",
    },
  ];

function traceText(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function DptIntelligence({
  companies,
  initialAction = "conselho",
  initialClientId,
  initialArea,
}: {
  companies: DptCompany[];
  initialAction?: DptAction;
  initialClientId?: string;
  initialArea?: string;
}) {
  const fallbackClientId = companies[0]?.id || "";
  const [action, setAction] = useState<DptAction>(initialAction);
  const [clientId, setClientId] = useState(initialClientId || fallbackClientId);
  const [question, setQuestion] = useState("");
  const [area, setArea] = useState(initialArea || "empresarial");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DptActionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Invalida qualquer análise em voo quando a área muda no meio do caminho —
  // sem isso, uma resposta tardia poderia sobrescrever a tela com o rascunho
  // de um domínio que o usuário já não está mais analisando.
  const requestToken = useRef(0);

  // Sincroniza o pai quando o diagnóstico troca de empresa. A seleção manual
  // feita dentro do Motor não participa deste efeito e não é revertida.
  useEffect(() => {
    if (
      initialClientId &&
      companies.some((company) => company.id === initialClientId)
    ) {
      setClientId(initialClientId);
    }
  }, [companies, initialClientId]);

  // Mesmo princípio para a área: quando o pai (Diagnóstico) troca o tipo
  // selecionado, a análise de IA deve incidir sobre essa mesma área — nunca
  // sobre "empresarial" por omissão enquanto o usuário pediu outra coisa.
  // O rascunho anterior é descartado junto: sem isso, um resultado tributário
  // continuaria na tela rotulado como se fosse a análise da área nova.
  useEffect(() => {
    if (initialArea) {
      requestToken.current += 1;
      setArea(initialArea);
      setResult(null);
      setError(null);
    }
  }, [initialArea]);

  useEffect(() => {
    if (!companies.some((company) => company.id === clientId)) {
      setClientId(fallbackClientId);
    }
  }, [companies, clientId, fallbackClientId]);

  async function submit() {
    if (!clientId || question.trim().length < 3) return;
    const token = ++requestToken.current;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await runDptAction({
        action,
        client_id: clientId,
        question,
        area,
      });
      if (requestToken.current === token) setResult(response);
    } catch {
      if (requestToken.current === token) {
        setError(
          "Não foi possível executar a análise. Nenhuma conclusão foi presumida.",
        );
      }
    } finally {
      if (requestToken.current === token) setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex items-start gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-slate-950 text-amber-300 dark:bg-white/10">
            <BrainCircuit className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              Motor Jurídico DPT
            </h2>
            <p className="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-400">
              Executa pelo núcleo único do EJC, com RAG, validação de citações e
              HITL. Não altera caso nem comunica cliente.
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-3 lg:grid-cols-3">
          {ACTIONS.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setAction(item.value)}
              className={`rounded-xl border p-4 text-left transition ${action === item.value ? "border-amber-300 bg-amber-50/60 dark:border-amber-400/30 dark:bg-amber-400/10" : "border-slate-200 dark:border-white/10"}`}
            >
              <div className="text-sm font-semibold text-slate-900 dark:text-white">
                {item.label}
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
                {item.description}
              </p>
            </button>
          ))}
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Empresa
            <select
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm dark:border-white/10 dark:bg-slate-950"
            >
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.nome}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Área de foco
            <select
              value={area}
              onChange={(e) => setArea(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm dark:border-white/10 dark:bg-slate-950"
            >
              {[
                "empresarial",
                "tributario",
                "ambiental",
                "administrativo",
                "trabalhista",
                "contratual",
                "societario",
                "digital_lgpd",
              ].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="mt-4 block text-xs font-semibold text-slate-600 dark:text-slate-300">
          Pergunta ou material para análise
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={7}
            maxLength={12000}
            className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 dark:border-white/10 dark:bg-slate-950"
            placeholder="Ex.: Quais são os cinco maiores riscos jurídicos desta empresa e quais providências devem ser priorizadas nos próximos 30 dias?"
          />
        </label>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={loading || !clientId || question.trim().length < 3}
          className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-white dark:text-slate-950"
        >
          <ClipboardCheck className="h-4 w-4" />
          {loading ? "Analisando…" : "Gerar rascunho para revisão"}
        </button>
      </section>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-300">
          {error}
        </div>
      ) : null}

      {result ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
              <ShieldAlert className="h-4 w-4 text-amber-600" /> Rascunho
              jurídico — revisão humana obrigatória
            </div>
            <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700 dark:bg-amber-400/10 dark:text-amber-300">
              {result.status_hitl}
            </span>
          </div>
          {result.alertas.length ? (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/60 p-3 text-xs leading-5 text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-200">
              {result.alertas.join(" ")}
            </div>
          ) : null}
          <pre className="mt-4 whitespace-pre-wrap break-words rounded-xl bg-slate-50 p-4 text-xs leading-6 text-slate-700 dark:bg-black/20 dark:text-slate-200">
            {result.estruturado
              ? JSON.stringify(result.estruturado, null, 2)
              : result.conteudo}
          </pre>

          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 p-3 dark:border-white/10">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Fontes recuperadas
              </h3>
              {result.fontes.length ? (
                <div className="mt-2 space-y-2">
                  {result.fontes.map((fonte, index) => (
                    <pre
                      key={`fonte-${index}`}
                      className="whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 text-[11px] leading-5 text-slate-600 dark:bg-black/20 dark:text-slate-300"
                    >
                      {traceText(fonte)}
                    </pre>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-400">
                  Nenhuma fonte retornada pelo núcleo central.
                </p>
              )}
            </div>
            <div className="rounded-xl border border-slate-200 p-3 dark:border-white/10">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Citações / rastreabilidade
              </h3>
              {result.citacoes.length ? (
                <div className="mt-2 space-y-2">
                  {result.citacoes.map((citation, index) => (
                    <pre
                      key={`citacao-${index}`}
                      className="whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 text-[11px] leading-5 text-slate-600 dark:bg-black/20 dark:text-slate-300"
                    >
                      {traceText(citation)}
                    </pre>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-400">
                  Nenhuma citação verificável retornada; não trate o rascunho
                  como fundamentado sem conferência.
                </p>
              )}
            </div>
          </div>

          <p className="mt-3 text-xs text-slate-400">{result.aviso_hitl}</p>
        </section>
      ) : null}
    </div>
  );
}
