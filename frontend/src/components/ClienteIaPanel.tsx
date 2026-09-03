import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, RefreshCw } from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";

interface ClienteIaPanelProps {
  clientId: string;
  compacto?: boolean;
}

interface IaResposta {
  status?: string;
  resposta?: string;
  modelo_utilizado?: string;
  revisao_obrigatoria?: boolean;
  sem_base_verificavel?: boolean;
  alertas?: string[];
  log_id?: string;
  [key: string]: unknown;
}

interface ApiErro {
  code?: string;
  response?: {
    data?: {
      detail?: unknown;
    };
  };
}

export default function ClienteIaPanel({
  clientId,
  compacto = false,
}: ClienteIaPanelProps) {
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<IaResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    requestRef.current?.abort();
    requestRef.current = null;
    setLoading(false);
    setResultado(null);
    setErro(null);

    return () => {
      requestRef.current?.abort();
    };
  }, [clientId]);

  const analisar = async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;

    setLoading(true);
    setErro(null);
    setResultado(null);

    try {
      const { data } = await api.post<IaResposta>(
        `/clients/${clientId}/ia-analise`,
        undefined,
        { signal: controller.signal },
      );
      if (controller.signal.aborted || requestRef.current !== controller) {
        return;
      }
      if (data?.status && data.status !== "sucesso") {
        const mensagem =
          typeof data.resposta === "string" && data.resposta.trim()
            ? data.resposta
            : "A análise de IA não foi concluída.";
        setErro(mensagem);
        setResultado(null);
        return;
      }
      setResultado(data);
    } catch (e: unknown) {
      const err = e as ApiErro;
      if (controller.signal.aborted || err.code === "ERR_CANCELED") {
        return;
      }
      const detalhe = err.response?.data?.detail;
      const mensagem =
        typeof detalhe === "string"
          ? detalhe
          : "Não foi possível executar a análise estratégica do cliente.";
      setErro(mensagem);
      setResultado(null);
      toast.error(mensagem);
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  };

  return (
    <div className={compacto ? "space-y-4" : "card p-5 space-y-4"}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow flex items-center gap-2">
            <Bot className="w-3.5 h-3.5" /> IA do Cliente — análise 360º
          </p>
          <p className="text-sm text-slate-500 mt-1">
            Consolida indicadores autorizados do cliente e produz apoio
            estratégico interno. O resultado não substitui revisão jurídica.
          </p>
        </div>
        <button
          type="button"
          onClick={analisar}
          disabled={loading}
          className="btn-primary text-xs whitespace-nowrap"
        >
          {loading ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Analisando…
            </>
          ) : resultado ? (
            <>
              <RefreshCw className="w-3.5 h-3.5" /> Reanalisar
            </>
          ) : (
            <>
              <Bot className="w-3.5 h-3.5" /> Gerar análise
            </>
          )}
        </button>
      </div>

      <div className="rounded-lg border border-warn-200 bg-warn-50 p-3 text-xs text-warn-800 flex gap-2">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
        <span>
          Uso profissional interno. Confirme fatos, fontes, riscos, estratégia e
          qualquer conclusão antes de utilizar o conteúdo em orientação ao
          cliente, peça ou decisão processual.
        </span>
      </div>

      {!resultado && !erro && !loading && (
        <div className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-sm text-slate-400">
          A análise só é executada quando você solicitar. Nenhum dado é enviado à
          IA apenas por abrir esta tela.
        </div>
      )}

      {erro && (
        <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">
          {erro}
        </div>
      )}

      {resultado && (
        <div className="space-y-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-sm text-slate-700 whitespace-pre-wrap leading-6">
              {resultado.resposta || "A IA concluiu sem retornar texto."}
            </p>
          </div>
          {(resultado.revisao_obrigatoria || resultado.sem_base_verificavel) && (
            <div className="rounded-lg border border-warn-200 bg-warn-50 p-3 text-xs text-warn-800">
              {resultado.sem_base_verificavel
                ? "A resposta foi marcada sem base verificável suficiente. Revise os autos e fontes antes de qualquer uso."
                : "Revisão humana obrigatória antes de qualquer uso jurídico."}
            </div>
          )}
          {Array.isArray(resultado.alertas) && resultado.alertas.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-slate-500 space-y-1">
              {resultado.alertas.map((alerta, index) => (
                <li key={`${index}-${alerta}`}>{alerta}</li>
              ))}
            </ul>
          )}
          {resultado.modelo_utilizado && (
            <p className="text-[11px] text-slate-400">
              Modelo registrado: {resultado.modelo_utilizado}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
