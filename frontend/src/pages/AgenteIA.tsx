import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Cpu,
  Loader2,
  Send,
  ShieldAlert,
  ShieldQuestion,
  Wrench,
} from "lucide-react";
import Markdown from "../components/Markdown";
import api from "../lib/api";
import { asList } from "../lib/list";
import { streamSSE, SSEHttpError, type SSEEvent } from "../lib/stream";
import { toast } from "../components/Toast";
import { Badge, Button, PageHeader, SectionCard } from "../components/UI";

// ── Contrato de eventos (POST /ia/agente/stream → loop de tool-use) ──────────
// Emitidos por app/services/ai/agent/loop.py. A escrita PAUSA em
// `confirmacao_requerida` (HITL vinculado aos args); o cliente retoma com
// `retomar_token` + `decisao` (ou, sem Redis, reenvia a mensagem + o
// `aprovacoes_hash` da tool aprovada).
interface PassoEvent {
  passo: number;
  provider?: string;
  model?: string;
  stop_reason?: string;
  tokens?: number;
  ferramentas?: string[];
}
interface FerramentaEvent {
  ferramenta: string;
  args?: Record<string, unknown>;
}
interface ResultadoEvent {
  ferramenta: string;
  resultado?: unknown;
}
interface ConfirmacaoEvent {
  token: string | null;
  args_hash: string;
  ferramenta: string;
  args: Record<string, unknown>;
  tool_use_id?: string;
}
/** Confirmação pendente + a mensagem CONGELADA da execução que pausou: o
 *  textarea é reabilitado no `finally` do stream, então o fallback sem Redis
 *  (reenvio de `mensagem` + `aprovacoes_hash`) não pode ler o estado atual —
 *  usa o valor capturado no momento da pausa. */
interface PendingConfirmacao extends ConfirmacaoEvent {
  mensagemOriginal: string;
}
interface FinalEvent {
  status: string;
  resposta: string;
  is_rascunho?: boolean;
  custo_estimado_brl?: number;
  alertas?: string[];
  revisao_obrigatoria?: boolean;
}

type TimelineItem =
  | { id: number; kind: "passo"; data: PassoEvent }
  | { id: number; kind: "ferramenta"; data: FerramentaEvent }
  | { id: number; kind: "resultado"; data: ResultadoEvent }
  | { id: number; kind: "degradacao"; motivo?: string }
  | { id: number; kind: "recusado"; ferramenta?: string }
  | { id: number; kind: "decisao"; texto: string };

const pretty = (v: unknown) => {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
};

export default function AgenteIA() {
  const [caseId, setCaseId] = useState("");
  const [casos, setCasos] = useState<any[]>([]);
  const [casosLoading, setCasosLoading] = useState(true);
  const [casosErro, setCasosErro] = useState(false);
  const [mensagem, setMensagem] = useState("");
  const [running, setRunning] = useState(false);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [pending, setPending] = useState<PendingConfirmacao | null>(null);
  const [final, setFinal] = useState<FinalEvent | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);
  // Mensagem enviada na execução em curso — congelada para a retomada HITL.
  const mensagemRunRef = useRef("");

  // Seletor de casos (mesmo padrão de IA.tsx): o advogado escolhe pelo
  // número interno/título em vez de digitar o UUID do caso à mão.
  // page_size=500 é o teto do backend (GET /cases/, Query le=500).
  useEffect(() => {
    api
      .get("/cases/", { params: { page_size: 500 } })
      .then((r) => setCasos(asList(r.data)))
      .catch(() => setCasosErro(true))
      .finally(() => setCasosLoading(false));
  }, []);

  const push = <T extends Omit<TimelineItem, "id">>(item: T) =>
    setTimeline((prev) => [
      ...prev,
      { ...item, id: ++seqRef.current } as TimelineItem,
    ]);

  const onEvent = useCallback((evt: SSEEvent) => {
    switch (evt.event) {
      case "passo":
        push({ kind: "passo", data: evt.data as PassoEvent });
        break;
      case "ferramenta":
        push({ kind: "ferramenta", data: evt.data as FerramentaEvent });
        break;
      case "resultado":
        push({ kind: "resultado", data: evt.data as ResultadoEvent });
        break;
      case "degradacao":
        push({
          kind: "degradacao",
          motivo: (evt.data as { motivo?: string }).motivo,
        });
        break;
      case "recusado":
        push({
          kind: "recusado",
          ferramenta: (evt.data as { ferramenta?: string }).ferramenta,
        });
        break;
      case "confirmacao_requerida":
        setPending({
          ...(evt.data as ConfirmacaoEvent),
          mensagemOriginal: mensagemRunRef.current,
        });
        break;
      case "final":
        setFinal(evt.data as FinalEvent);
        break;
      case "erro":
        setErro(
          (evt.data as { detalhe?: string }).detalhe || "Falha no agente.",
        );
        break;
      default:
        break;
    }
  }, []);

  // Dispara (ou retoma) o stream. `reset` limpa a timeline num começo novo;
  // numa retomada (aprovar/recusar) preservamos o histórico já exibido.
  const run = useCallback(
    async (body: Record<string, unknown>, reset: boolean) => {
      abortRef.current?.abort();
      abortRef.current = new AbortController();
      setRunning(true);
      setErro(null);
      setPending(null);
      if (reset) {
        setFinal(null);
        setTimeline([]);
        seqRef.current = 0;
      }
      try {
        await streamSSE("/api/ia/agente/stream", body, {
          onEvent,
          signal: abortRef.current.signal,
        });
      } catch (e: any) {
        if (e?.name === "AbortError") return;
        if (e instanceof SSEHttpError && e.status === 404) {
          setErro(
            "O modo agente está desativado neste ambiente — " +
              "fale com o administrador do sistema para ativá-lo.",
          );
        } else if (e instanceof SSEHttpError && e.status === 403) {
          setErro("Seu perfil não tem acesso ao agente neste caso.");
        } else {
          setErro(e?.message || "Falha ao conectar ao agente.");
        }
      } finally {
        setRunning(false);
      }
    },
    [onEvent],
  );

  const iniciar = () => {
    if (!caseId.trim()) {
      toast.error(
        "Selecione o caso (o agente opera sempre no contexto de um caso).",
      );
      return;
    }
    if (mensagem.trim().length < 5) {
      toast.error("Descreva a solicitação ao agente (mín. 5 caracteres).");
      return;
    }
    mensagemRunRef.current = mensagem.trim();
    void run(
      { case_id: caseId.trim(), mensagem: mensagemRunRef.current },
      true,
    );
  };

  const decidir = (decisao: "aprovar" | "recusar") => {
    const p = pending;
    setPending(null);
    if (!p) return;
    push({
      kind: "decisao",
      texto:
        decisao === "aprovar"
          ? `Você APROVOU a execução de ${p.ferramenta}.`
          : `Você RECUSOU a execução de ${p.ferramenta}.`,
    });
    if (p.token) {
      // Caminho normal: retoma o estado no Redis pelo token.
      void run(
        { case_id: caseId.trim(), retomar_token: p.token, decisao },
        false,
      );
    } else if (decisao === "aprovar") {
      // Fallback sem Redis (token=null): reexecuta aprovando pelo hash dos
      // args. Usa a mensagem CONGELADA da execução que pausou — o textarea
      // pode ter sido editado para a PRÓXIMA solicitação.
      void run(
        {
          case_id: caseId.trim(),
          mensagem: p.mensagemOriginal,
          aprovacoes_hash: [p.args_hash],
        },
        false,
      );
    } else {
      setErro(
        "Sem sessão retomável (Redis indisponível); a operação foi recusada. " +
          "Reenvie a solicitação para continuar.",
      );
    }
  };

  const cancelar = () => {
    abortRef.current?.abort();
    setRunning(false);
    setPending(null);
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Agente Jurídico (tool-use / HITL)"
        subtitle="O agente decide, consulta o dossiê e precedentes e propõe ações — pausando para sua aprovação antes de qualquer escrita. Resultado é rascunho: revisão humana obrigatória (OAB)."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Entrada */}
        <SectionCard title="Solicitação ao agente">
          <div className="space-y-3">
            <div>
              <label className="label">Caso (obrigatório)</label>
              <select
                value={caseId}
                onChange={(e) => setCaseId(e.target.value)}
                className="input w-full"
                disabled={running}
              >
                <option value="">
                  Selecione o caso em que o agente vai operar
                </option>
                {casos.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.numero_interno} — {c.titulo}
                  </option>
                ))}
              </select>
              {casosLoading && (
                <p className="mt-1 text-xs text-slate-400">Carregando casos…</p>
              )}
              {!casosLoading && casosErro && (
                <p className="mt-1 text-xs font-medium text-danger-600">
                  Não foi possível carregar a lista de casos — recarregue a
                  página ou tente novamente mais tarde.
                </p>
              )}
              {!casosLoading && !casosErro && casos.length === 0 && (
                <p className="mt-1 text-xs text-slate-400">
                  Nenhum caso disponível — cadastre um caso primeiro em Casos.
                </p>
              )}
            </div>
            <div>
              <label className="label">O que o agente deve fazer?</label>
              <textarea
                value={mensagem}
                onChange={(e) => setMensagem(e.target.value)}
                rows={8}
                className="input w-full"
                placeholder="Ex.: analise o dossiê, levante os precedentes da tese principal e proponha os próximos passos processuais."
                disabled={running}
              />
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ai"
                onClick={iniciar}
                disabled={running}
                icon={
                  running ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <Send size={15} />
                  )
                }
              >
                {running ? "Agente trabalhando…" : "Executar agente"}
              </Button>
              {running && (
                <button
                  onClick={cancelar}
                  className="px-3 py-2 text-sm text-danger-500 transition-colors hover:text-danger-700"
                >
                  Cancelar
                </button>
              )}
            </div>
          </div>
        </SectionCard>

        {/* Timeline + resultado */}
        <SectionCard
          title="Trabalho do agente"
          subtitle="Cada passo, ferramenta e resultado em tempo real."
        >
          {timeline.length === 0 && !running && !final && !erro && !pending && (
            <p className="py-10 text-center text-sm text-slate-400">
              A execução do agente aparecerá aqui, passo a passo.
            </p>
          )}

          <ol className="space-y-2">
            {timeline.map((item) => (
              <li
                key={item.id}
                className="rounded-xl border border-slate-100 bg-white"
              >
                {item.kind === "passo" && (
                  <div className="flex items-start gap-3 px-3 py-2.5">
                    <Cpu size={15} className="mt-0.5 shrink-0 text-ai-600" />
                    <div className="min-w-0 text-sm">
                      <div className="font-medium text-slate-800">
                        Passo {item.data.passo}
                      </div>
                      <div className="text-xs text-slate-400">
                        {item.data.provider}/{item.data.model}
                        {item.data.ferramentas?.length
                          ? ` · pediu: ${item.data.ferramentas.join(", ")}`
                          : " · raciocínio"}
                      </div>
                    </div>
                  </div>
                )}
                {item.kind === "ferramenta" && (
                  <details className="group px-3 py-2.5">
                    <summary className="flex cursor-pointer items-center gap-3 text-sm">
                      <Wrench size={15} className="shrink-0 text-slate-500" />
                      <span className="font-medium text-slate-800">
                        Ferramenta: {item.data.ferramenta}
                      </span>
                    </summary>
                    <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-50 p-2 text-[11px] text-slate-600">
                      {pretty(item.data.args ?? {})}
                    </pre>
                  </details>
                )}
                {item.kind === "resultado" && (
                  <details className="group px-3 py-2.5">
                    <summary className="flex cursor-pointer items-center gap-3 text-sm">
                      <CheckCircle2
                        size={15}
                        className="shrink-0 text-green-500"
                      />
                      <span className="font-medium text-slate-700">
                        Resultado de {item.data.ferramenta}
                      </span>
                    </summary>
                    <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-slate-50 p-2 text-[11px] text-slate-600">
                      {pretty(item.data.resultado ?? {})}
                    </pre>
                  </details>
                )}
                {item.kind === "degradacao" && (
                  <div className="flex items-start gap-3 px-3 py-2.5 text-sm text-warn-700">
                    <ShieldAlert size={15} className="mt-0.5 shrink-0" />
                    <span>
                      Trecho interno com dado pessoal residual foi redigido
                      (LGPD); a análise seguiu.
                    </span>
                  </div>
                )}
                {item.kind === "recusado" && (
                  <div className="flex items-start gap-3 px-3 py-2.5 text-sm text-slate-600">
                    <Ban
                      size={15}
                      className="mt-0.5 shrink-0 text-danger-500"
                    />
                    <span>
                      Ferramenta {item.ferramenta} não executada (recusa
                      humana).
                    </span>
                  </div>
                )}
                {item.kind === "decisao" && (
                  <div className="px-3 py-2.5 text-xs font-medium text-slate-500">
                    {item.texto}
                  </div>
                )}
              </li>
            ))}
          </ol>

          {running && !pending && (
            <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
              <Loader2 size={13} className="animate-spin" /> Agente processando…
            </div>
          )}

          {/* HITL — confirmação de escrita */}
          {pending && (
            <div className="mt-3 rounded-xl border border-ai-200 bg-ai-50 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-ai-800">
                <ShieldQuestion size={16} /> Confirmação necessária
              </div>
              <p className="mt-1 text-xs text-ai-700">
                O agente quer executar a ferramenta de escrita{" "}
                <code className="font-mono">{pending.ferramenta}</code>. Revise
                os argumentos exatos antes de aprovar — nada é gravado sem sua
                autorização.
              </p>
              <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-white p-2 text-[11px] text-slate-700 ring-1 ring-ai-100">
                {pretty(pending.args ?? {})}
              </pre>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="ai"
                  onClick={() => decidir("aprovar")}
                  icon={<CheckCircle2 size={15} />}
                >
                  Aprovar
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => decidir("recusar")}
                  icon={<Ban size={15} />}
                >
                  Recusar
                </Button>
              </div>
            </div>
          )}

          {/* Erro / desconexão */}
          {erro && (
            <div className="mt-3 flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <span>{erro}</span>
            </div>
          )}

          {/* Resposta final */}
          {final && (
            <div className="mt-3 space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <Badge tone="amber">RASCUNHO</Badge>
                {typeof final.custo_estimado_brl === "number" &&
                  final.custo_estimado_brl > 0 && (
                    <Badge tone="slate">
                      R$ {final.custo_estimado_brl.toFixed(4)}
                    </Badge>
                  )}
                {final.revisao_obrigatoria && (
                  <Badge tone="orange">Revisão humana obrigatória</Badge>
                )}
              </div>
              <Markdown
                source={final.resposta}
                className="max-h-[28rem] overflow-auto rounded-lg bg-slate-50 p-3 text-sm text-navy-900"
              />
              {!!final.alertas?.length && (
                <ul className="space-y-1 text-[11px] text-warn-700">
                  {final.alertas.map((a, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <AlertTriangle size={12} className="mt-0.5 shrink-0" />{" "}
                      {a}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
