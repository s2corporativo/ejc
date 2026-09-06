// ── src/components/AnaliseExtratos.tsx ───────────────────────────────────────
// Módulo de Análise Bancária (EXTRATOS): upload PDF/OFX/CSV → detecta cobranças
// abusivas (base legal) → Excel + minutas (notificação/petição/BACEN).
// Determinístico. Tudo é minuta — revisão obrigatória (OAB).
import { useEffect, useState, useRef } from "react";
import {
  Landmark,
  UploadCloud,
  FileSpreadsheet,
  FileText,
  AlertTriangle,
  Sparkles,
  Loader2,
  CheckCircle2,
  Copy,
} from "lucide-react";
import api from "../lib/api";
import { authFetch } from "../lib/stream";
import { Modal, Button } from "./UI";
import { toast } from "./Toast";
import { mensagemErroHttp } from "../lib/iaErro";

// Etapas do pipeline de peças (mesma esteira 7 etapas reutilizada pelo backend).
const ETAPAS_MINUTA: { num: number; titulo: string }[] = [
  { num: 1, titulo: "Identificando tipo de peça" },
  { num: 2, titulo: "Estruturando enquadramento" },
  { num: 3, titulo: "Buscando fundamentos legais" },
  { num: 4, titulo: "Analisando jurisprudência" },
  { num: 5, titulo: "Organizando argumentos" },
  { num: 6, titulo: "Identificando riscos" },
  { num: 7, titulo: "Montando documento completo" },
];

type StatusEtapa = "aguardando" | "em_andamento" | "concluido";
type FaseMinuta = "gerando" | "concluido" | "erro";

/**
 * FE-01: abre o HTML gerado pelo backend numa aba nova via Blob/objectURL —
 * sem `document.write` numa janela `about:blank` (que herdava a origem da SPA
 * e podia executar script contra a sessão). `noopener` corta a referência
 * à janela de origem. O backend escapa os campos interpolados
 * (bank_report.py) e o CSP `script-src 'self'` vale para o documento blob.
 */
export function abrirHtmlEmNovaAba(html: string): boolean {
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const aberta = window.open(url, "_blank", "noopener,noreferrer");
  // Revoga depois que a aba já carregou o documento (o objeto vive na aba).
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  if (!aberta) {
    toast.info("Permita pop-ups para visualizar o documento gerado.");
    return false;
  }
  return true;
}

function fmt(v: any) {
  return Number(v || 0).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function Kpi({
  label,
  val,
  alerta,
}: {
  label: string;
  val: any;
  alerta?: boolean;
}) {
  return (
    <div
      className={`rounded-lg p-2 border ${alerta ? "border-danger-200 bg-danger-50/40" : "border-bronze-pale bg-bronze-50/10"}`}
    >
      <div className="text-[15px] font-bold text-navy">{val}</div>
      <div className="text-[10px] text-slate-500 uppercase tracking-wide">
        {label}
      </div>
    </div>
  );
}

export default function AnaliseExtratos() {
  const ref = useRef<HTMLInputElement>(null);
  const [banco, setBanco] = useState("");
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const [res, setRes] = useState<any>(null);

  const enviar = async (file: File) => {
    setLoading(true);
    setErro("");
    setRes(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (banco) fd.append("banco", banco);
      const { data } = await api.post("/bank-analysis/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setRes(data);
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha ao analisar o extrato.");
    } finally {
      setLoading(false);
    }
  };

  const baixarExcel = async () => {
    if (!res?.analise?.id) return;
    try {
      const r = await api.get(`/bank-analysis/${res.analise.id}/excel`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "analise_bancaria.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(mensagemErroHttp(e, "Não foi possível baixar a planilha."));
    }
  };

  const gerarDoc = async (tipo: string) => {
    if (!res?.analise?.id) return;
    try {
      const { data } = await api.post(
        `/bank-analysis/${res.analise.id}/documento`,
        { tipo },
      );
      abrirHtmlEmNovaAba(String(data?.html ?? ""));
    } catch (e) {
      toast.error(mensagemErroHttp(e, "Não foi possível gerar o documento."));
    }
  };

  // ── Minuta revisional (IA) — consome o mesmo SSE do gerador de peças ─────────
  // Espelha o padrão de leitura de stream de PecaGeneratorModal.tsx:174-231
  // (fetch direto + reader + parse event:/data:). O endpoint reusa a esteira de
  // peças (gerar_peca_pipeline), então os eventos são idênticos: step/concluido/erro.
  const [minutaOpen, setMinutaOpen] = useState(false);
  const [minutaFase, setMinutaFase] = useState<FaseMinuta>("gerando");
  const [minutaEtapas, setMinutaEtapas] = useState<Record<number, StatusEtapa>>(
    {},
  );
  const [minutaDoc, setMinutaDoc] = useState("");
  const [minutaLegalDocId, setMinutaLegalDocId] = useState("");
  const [minutaErro, setMinutaErro] = useState("");
  const [minutaCopiado, setMinutaCopiado] = useState(false);
  const minutaAbort = useRef<AbortController | null>(null);

  // Aborta o stream SSE em voo ao desmontar — evita setState após unmount e
  // vazamento da conexão quando o usuário sai da tela durante a geração.
  useEffect(() => () => minutaAbort.current?.abort(), []);

  const fecharMinuta = () => {
    minutaAbort.current?.abort();
    setMinutaOpen(false);
  };

  const gerarMinuta = async () => {
    if (!res?.analise?.id) return;
    setMinutaOpen(true);
    setMinutaFase("gerando");
    setMinutaEtapas({});
    setMinutaDoc("");
    setMinutaLegalDocId("");
    setMinutaErro("");
    setMinutaCopiado(false);
    minutaAbort.current = new AbortController();

    try {
      const r = await authFetch(
        `/api/bank-analysis/${res.analise.id}/gerar-peca`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: minutaAbort.current.signal,
        },
      );

      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: "" }));
        if (r.status === 422) {
          throw new Error(
            err.detail ||
              "Nenhuma cobrança abusiva para peticionar nesta análise.",
          );
        }
        if (r.status === 503) {
          throw new Error(
            err.detail ||
              "Serviço de IA indisponível para geração de peças no momento.",
          );
        }
        throw new Error(err.detail || "Falha ao gerar a minuta revisional.");
      }

      const reader = r.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";

        for (const part of parts) {
          const eventLine = part.match(/^event:\s*(.+)$/m)?.[1]?.trim();
          const dataLine = part.match(/^data:\s*(.+)$/ms)?.[1]?.trim();
          if (!dataLine) continue;

          let payload: Record<string, any> = {};
          try {
            payload = JSON.parse(dataLine);
          } catch {
            continue;
          }

          if (eventLine === "step") {
            const num = Number(payload.etapa);
            const st: StatusEtapa =
              payload.status === "em_andamento" ? "em_andamento" : "concluido";
            setMinutaEtapas((prev) => ({ ...prev, [num]: st }));
          } else if (eventLine === "concluido") {
            setMinutaDoc(payload.documento ?? "");
            setMinutaLegalDocId(payload.legal_doc_id ?? "");
            setMinutaFase("concluido");
            toast.success("Minuta revisional gerada (rascunho — revise, OAB).");
          } else if (eventLine === "erro") {
            throw new Error(payload.detail ?? "Erro na geração da minuta.");
          }
        }
      }
    } catch (e: any) {
      if (e.name === "AbortError") return;
      setMinutaErro(e.message ?? "Erro desconhecido");
      setMinutaFase("erro");
      toast.error(e.message ?? "Falha ao gerar a minuta revisional.");
    }
  };

  const copiarMinuta = () => {
    navigator.clipboard.writeText(minutaDoc);
    setMinutaCopiado(true);
    setTimeout(() => setMinutaCopiado(false), 2000);
  };

  const a = res?.analise;
  const cobr: any[] = res?.cobrancas || [];
  const prioCor = (p: string) =>
    p === "URGENTE"
      ? "bg-danger-100 text-danger-700"
      : "bg-warn-100 text-warn-700";
  const btn =
    "text-xs px-2.5 py-1.5 rounded-lg border border-bronze text-bronze hover:bg-bronze-50/40 flex items-center gap-1 transition-colors";

  return (
    <div className="card p-4 mb-5 border-l-4 border-bronze">
      <div className="flex items-center gap-2 mb-1">
        <Landmark size={16} className="text-bronze" />
        <h3 className="font-serif font-semibold text-navy text-sm">
          Análise de Extrato Bancário — cobranças abusivas
        </h3>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Envie o extrato em <b>PDF, OFX ou CSV</b> (qualquer banco). O sistema lê
        as transações, aponta cobranças potencialmente indevidas com base legal
        e gera planilha Excel + minutas (Notificação, Petição, Reclamação
        BACEN). Tudo é minuta — revise (OAB).
      </p>

      <div className="flex flex-wrap gap-2 items-center mb-2">
        <input
          className="input max-w-[200px]"
          placeholder="Banco (opcional)"
          value={banco}
          onChange={(e) => setBanco(e.target.value)}
        />
        <input
          ref={ref}
          type="file"
          accept=".pdf,.ofx,.csv,.txt"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) enviar(f);
          }}
        />
        <button
          onClick={() => ref.current?.click()}
          disabled={loading}
          className="btn-gold text-sm"
        >
          <UploadCloud size={15} /> {loading ? "Analisando…" : "Enviar extrato"}
        </button>
      </div>
      {erro && <p className="text-xs text-danger-600">{erro}</p>}

      {a && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            <Kpi label="Transações" val={a.total_transacoes} />
            <Kpi label="Total débitos" val={`R$ ${fmt(a.total_debitos)}`} />
            <Kpi
              label="Cobranças abusivas"
              val={a.qtd_abusivas}
              alerta={a.qtd_abusivas > 0}
            />
            <Kpi
              label="Pot. indevido"
              val={`R$ ${fmt(a.total_abusivo)}`}
              alerta={a.total_abusivo > 0}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <button onClick={baixarExcel} className={btn}>
              <FileSpreadsheet size={13} /> Baixar Excel
            </button>
            <button onClick={() => gerarDoc("notificacao")} className={btn}>
              <FileText size={13} /> Notificação
            </button>
            <button onClick={() => gerarDoc("peticao")} className={btn}>
              <FileText size={13} /> Petição
            </button>
            <button onClick={() => gerarDoc("bacen")} className={btn}>
              <FileText size={13} /> Reclamação BACEN
            </button>
            {a.qtd_abusivas > 0 && (
              <button
                onClick={gerarMinuta}
                className="text-xs px-2.5 py-1.5 rounded-lg bg-navy text-white hover:bg-navy/90 flex items-center gap-1 transition-colors"
              >
                <Sparkles size={13} /> Gerar minuta revisional (IA)
              </button>
            )}
          </div>

          {cobr.length > 0 ? (
            <div className="border border-bronze-pale rounded-lg overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-navy text-white">
                  <tr>
                    <th className="p-2 text-left">Cobrança</th>
                    <th className="p-2 text-left">Base legal</th>
                    <th className="p-2">Prioridade</th>
                    <th className="p-2 text-right">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {cobr.map((c, i) => (
                    <tr key={i} className="border-t border-bronze-pale/40">
                      <td className="p-2 text-slate-700">{c.titulo}</td>
                      <td className="p-2 text-slate-500">{c.base_legal}</td>
                      <td className="p-2 text-center">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${prioCor(c.prioridade)}`}
                        >
                          {c.prioridade}
                        </span>
                      </td>
                      <td className="p-2 text-right text-slate-700">
                        R$ {fmt(c.valor)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-success-700 flex items-center gap-1">
              <AlertTriangle size={12} /> Nenhuma cobrança abusiva detectada
              automaticamente neste extrato.
            </p>
          )}
          <p className="text-[10px] text-warn-700">
            ⚠ Indícios automáticos — não afirmam ilegalidade. Revisão
            obrigatória do advogado (OAB).
          </p>
        </div>
      )}

      {/* ── Minuta revisional (IA) ── */}
      <Modal
        open={minutaOpen}
        onClose={fecharMinuta}
        title="Minuta revisional (IA)"
        wide
      >
        <div className="flex flex-col">
          <div className="-mt-5 -mx-5 mb-4 px-5 pb-3 border-b border-slate-100">
            <p className="text-xs text-slate-400">
              Ação revisional c/c repetição de indébito · pipeline 7 etapas ·
              HITL obrigatório
            </p>
          </div>

          {(minutaFase === "gerando" || minutaFase === "erro") && (
            <div className="flex flex-col gap-2">
              {ETAPAS_MINUTA.map((e) => {
                const st = minutaEtapas[e.num] ?? "aguardando";
                return (
                  <div
                    key={e.num}
                    className={`flex items-center gap-3 px-4 py-2.5 rounded-xl border transition-colors ${
                      st === "concluido"
                        ? "bg-success-50 border-success-200"
                        : st === "em_andamento"
                          ? "bg-bronze-50/40 border-bronze-pale"
                          : "bg-white border-slate-100"
                    }`}
                  >
                    <div
                      className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-[11px] font-medium ${
                        st === "concluido"
                          ? "bg-success-600 text-white"
                          : st === "em_andamento"
                            ? "bg-bronze text-white"
                            : "bg-slate-100 text-slate-400"
                      }`}
                    >
                      {st === "em_andamento" ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : st === "concluido" ? (
                        <CheckCircle2 size={12} />
                      ) : (
                        e.num
                      )}
                    </div>
                    <span
                      className={`text-sm ${
                        st === "aguardando" ? "text-slate-400" : "text-navy"
                      }`}
                    >
                      {e.titulo}
                    </span>
                  </div>
                );
              })}

              {minutaFase === "erro" && (
                <div className="mt-3 bg-danger-50 border border-danger-200 rounded-lg px-4 py-3 text-sm text-danger-700">
                  {minutaErro}
                </div>
              )}
            </div>
          )}

          {minutaFase === "concluido" && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-2 bg-success-50 border border-success-200 rounded-xl px-4 py-3">
                <CheckCircle2
                  size={18}
                  className="text-success-600 flex-shrink-0"
                />
                <div className="flex-1">
                  <div className="text-sm font-medium text-success-800">
                    Minuta gerada com sucesso
                  </div>
                  <div className="text-xs text-success-700">
                    {minutaLegalDocId ? `Peça: ${minutaLegalDocId} · ` : ""}
                    Rascunho (HITL) — aguarda revisão humana.
                  </div>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-slate-600">
                    Documento gerado
                  </label>
                  <button
                    onClick={copiarMinuta}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-bronze transition-colors"
                  >
                    <Copy size={13} />
                    {minutaCopiado ? "Copiado!" : "Copiar"}
                  </button>
                </div>
                <textarea
                  readOnly
                  value={minutaDoc}
                  rows={14}
                  className="input bg-slate-50 font-mono resize-none"
                />
              </div>

              <div className="bg-warn-50 border border-warn-200 rounded-lg px-4 py-3 text-xs text-warn-800">
                <strong>⚠ RASCUNHO:</strong> minuta gerada por IA. Revise,
                complemente com os dados reais do caso e assine (advogado
                habilitado, OAB) antes de protocolar.
              </div>
            </div>
          )}

          <div className="-mx-5 -mb-5 px-6 py-4 mt-4 border-t border-slate-100 flex items-center justify-between gap-3 bg-white rounded-b-2xl">
            {minutaFase === "gerando" && (
              <>
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Loader2 size={13} className="animate-spin" />
                  Processando pipeline...
                </div>
                <button
                  onClick={fecharMinuta}
                  className="px-4 py-2 text-sm text-danger-500 hover:text-danger-700 transition-colors"
                >
                  Cancelar
                </button>
              </>
            )}
            {minutaFase === "erro" && (
              <>
                <Button variant="ghost" onClick={fecharMinuta}>
                  Fechar
                </Button>
                <Button
                  variant="ai"
                  onClick={gerarMinuta}
                  icon={<Sparkles size={15} />}
                >
                  Tentar novamente
                </Button>
              </>
            )}
            {minutaFase === "concluido" && (
              <Button variant="ai" onClick={fecharMinuta} className="ml-auto">
                Fechar
              </Button>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
}
