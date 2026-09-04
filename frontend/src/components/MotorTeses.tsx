// ── src/components/MotorTeses.tsx ────────────────────────────────────────────
// P2.2 — Motor de Teses (IA). Usa os fatos do caso para gerar teses estruturadas
// com viabilidade Alta/Média/Baixa, ancoradas em jurisprudência/súmulas/precedentes
// internos/doutrina (RAG). Tudo é RASCUNHO — revisão obrigatória do advogado.
import { useEffect, useRef, useState } from "react";
import {
  Sparkles,
  Scale,
  ShieldAlert,
  BookMarked,
  Loader2,
} from "lucide-react";
import api from "../lib/api";
import { mensagemErroIA } from "../lib/iaErro";

const VIAB: Record<string, { label: string; cls: string; dot: string }> = {
  alta: {
    label: "Alta viabilidade",
    cls: "border-success-300 bg-success-50/40",
    dot: "bg-success-500",
  },
  media: {
    label: "Média viabilidade",
    cls: "border-warn-300 bg-warn-50/40",
    dot: "bg-warn-500",
  },
  baixa: {
    label: "Baixa viabilidade",
    cls: "border-slate-300 bg-slate-50",
    dot: "bg-slate-400",
  },
};

export default function MotorTeses({ caso }: { caso: any }) {
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const [polo, setPolo] = useState("autor");
  const [r, setR] = useState<any>(null);
  const [progresso, setProgresso] = useState("");
  // E8: o polling (até 180 s) precisa parar quando a aba é desmontada —
  // AbortController cancela a requisição em voo e `montado` impede setState
  // em componente morto (e a próxima iteração do loop).
  const abortRef = useRef<AbortController | null>(null);
  const montadoRef = useRef(true);
  useEffect(() => {
    montadoRef.current = true;
    return () => {
      montadoRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const gerar = async () => {
    if (!caso?.descricao_fatos || caso.descricao_fatos.length < 20) {
      setErro(
        "O caso precisa ter uma descrição dos fatos (mín. 20 caracteres) para gerar teses.",
      );
      return;
    }
    // E04 (auditoria funcional): geração assíncrona com polling — o backend
    // devolve task_id imediatamente e a geração roda em background (tipicamente
    // 30-60s em modelo local). O frontend consulta o status a cada 2s até
    // "concluido"/"erro", com janela total de 3 minutos. Nunca mais "30s e
    // interrompida" para uma geração que terminou com 200 OK no servidor.
    setLoading(true);
    setErro("");
    setR(null);
    setProgresso("Solicitando a geração…");
    const JANELA_MS = 180_000;
    const POLL_MS = 2_000;
    const started = Date.now();
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;
    try {
      const { data: task } = await api.post(
        "/teses/motor/async",
        {
          area: caso.area,
          descricao_fatos: caso.descricao_fatos,
          case_id: caso.id,
          polo,
        },
        { signal },
      );
      const task_id: string = task.task_id;
      const aguardar = (ms: number) =>
        new Promise((res) => setTimeout(res, ms));
      let status = "pendente";
      while (status === "pendente" || status === "em_andamento") {
        if (signal.aborted || !montadoRef.current) return;
        if (Date.now() - started > JANELA_MS) {
          throw Object.assign(new Error("tempo_excedido"), {
            nome: "tempo_excedido",
          });
        }
        setProgresso(
          status === "pendente"
            ? "Fila de processamento…"
            : "Consultando jurisprudência, súmulas e doutrina…",
        );
        await aguardar(POLL_MS);
        if (signal.aborted || !montadoRef.current) return;
        const { data } = await api.get(`/teses/motor/async/${task_id}`, {
          signal,
        });
        status = data.status;
        if (status === "concluido") {
          setR(data.resultado);
          setProgresso("");
          setLoading(false);
          return;
        }
      }
      throw Object.assign(new Error("falha_geracao"), {
        nome: "falha_geracao",
      });
    } catch (e: any) {
      if (signal.aborted || !montadoRef.current) return;
      if (e?.nome === "tempo_excedido") {
        setErro(
          "A geração de teses ultrapassou 3 minutos. A tarefa pode ainda estar em andamento no servidor — tente novamente em alguns instantes.",
        );
      } else if (e?.nome === "falha_geracao") {
        setErro(
          "A geração de teses terminou sem resultado. Verifique se a IA está configurada e tente novamente.",
        );
      } else {
        const isTimeout =
          e?.code === "ERR_CANCELED" ||
          e?.name === "CanceledError" ||
          e?.name === "TimeoutError";
        setErro(
          isTimeout
            ? "A conexão com o servidor foi interrompida. Tente novamente."
            : mensagemErroIA(
                e,
                "Falha ao gerar teses (a IA pode estar indisponível).",
              ),
        );
      }
    } finally {
      if (montadoRef.current && abortRef.current === controller) {
        setProgresso("");
        setLoading(false);
      }
    }
  };

  const fc = r?.fontes_consultadas || {};
  const teses = r?.teses || [];

  return (
    <div className="card p-4 border-l-4 border-bronze bg-bronze-50/20">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles size={16} className="text-bronze" />
        <h3 className="font-serif font-semibold text-navy text-sm">
          Motor de Teses (IA)
        </h3>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Busca jurisprudência, súmulas, precedentes internos e doutrina e propõe
        teses classificadas por viabilidade. Rascunho — verifique cada julgado e
        revise (OAB).
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <select
          className="input text-sm w-auto"
          value={polo}
          onChange={(e) => setPolo(e.target.value)}
        >
          <option value="autor">Polo: Autor</option>
          <option value="reu">Polo: Réu</option>
        </select>
        <button className="btn-gold text-sm" disabled={loading} onClick={gerar}>
          {loading ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Sparkles size={14} />
          )}
          {loading ? "Gerando teses…" : "Gerar teses"}
        </button>
        {loading && progresso && (
          <span className="text-[11px] text-slate-500">{progresso}</span>
        )}
      </div>
      {erro && <p className="text-xs text-danger-600 mt-2">{erro}</p>}

      {r && (
        <div className="mt-4 space-y-3">
          {r.sintese && (
            <p className="text-sm text-slate-700 bg-white rounded-lg p-3 border border-bronze-pale">
              {r.sintese}
            </p>
          )}

          <div className="flex flex-wrap gap-2 text-[11px] text-slate-500">
            <span className="px-2 py-0.5 rounded-full bg-bronze-50">
              Jurisprudência: {fc.jurisprudencia ?? 0}
            </span>
            <span className="px-2 py-0.5 rounded-full bg-bronze-50">
              Precedentes internos: {fc.precedentes_internos ?? 0}
            </span>
            <span className="px-2 py-0.5 rounded-full bg-bronze-50">
              Doutrina: {fc.doutrina ?? 0}
            </span>
            <span className="px-2 py-0.5 rounded-full bg-bronze-50">
              Teses do escritório: {fc.teses_escritorio ?? 0}
            </span>
          </div>

          {teses.length === 0 ? (
            <p className="text-sm text-slate-400 py-3 text-center">
              Nenhuma tese gerada — base escassa para estes fatos.
            </p>
          ) : (
            teses.map((t: any, i: number) => {
              const v =
                VIAB[(t.viabilidade || "baixa").toLowerCase()] || VIAB.baixa;
              return (
                <div key={i} className={`rounded-lg border p-3 ${v.cls}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`w-2 h-2 rounded-full ${v.dot}`} />
                    <span className="font-medium text-navy-900 text-sm flex-1">
                      {t.titulo}
                    </span>
                    <span className="text-[10px] uppercase tracking-wide font-semibold text-slate-500">
                      {v.label}
                    </span>
                  </div>
                  {t.justificativa_viabilidade && (
                    <p className="text-xs text-slate-600 mb-1.5">
                      {t.justificativa_viabilidade}
                    </p>
                  )}
                  <div className="space-y-1 text-xs">
                    {t.base_legal && (
                      <p className="flex items-start gap-1">
                        <Scale
                          size={12}
                          className="text-bronze mt-0.5 shrink-0"
                        />
                        <span>
                          <b className="text-slate-600">Base legal:</b>{" "}
                          {t.base_legal}
                        </span>
                      </p>
                    )}
                    {t.fundamentacao && (
                      <p className="flex items-start gap-1">
                        <BookMarked
                          size={12}
                          className="text-bronze mt-0.5 shrink-0"
                        />
                        <span>
                          <b className="text-slate-600">Fundamentação:</b>{" "}
                          {t.fundamentacao}
                        </span>
                      </p>
                    )}
                    {t.aplicacao && (
                      <p>
                        <b className="text-slate-600">Aplicação:</b>{" "}
                        {t.aplicacao}
                      </p>
                    )}
                    {t.contra_argumento && (
                      <p className="flex items-start gap-1 text-warn-700">
                        <ShieldAlert size={12} className="mt-0.5 shrink-0" />
                        <span>
                          <b>Contra-argumento:</b> {t.contra_argumento}
                        </span>
                      </p>
                    )}
                  </div>
                </div>
              );
            })
          )}

          {r._aviso && (
            <p className="text-[11px] text-warn-700 border-t border-warn-100 pt-2">
              ⚠ {r._aviso}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
