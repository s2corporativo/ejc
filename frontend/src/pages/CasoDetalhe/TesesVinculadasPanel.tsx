import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { AlertTriangle, BookOpenCheck, RefreshCw, Scale } from "lucide-react";

import api from "../../lib/api";
import { fmtTaxaSucesso } from "../../utils/formato";

interface TeseVinculada {
  id: string;
  titulo: string;
  descricao?: string | null;
  fundamentacao?: string | null;
  jurisprudencia?: string | null;
  contra_argumento?: string | null;
  area_juridica?: string | null;
  tribunal?: string | null;
  status: string;
  taxa_sucesso?: number | null;
  resultado?: string | null;
  observacao?: string | null;
}

export default function TesesVinculadasPanel({ caseId }: { caseId: string }) {
  const [teses, setTeses] = useState<TeseVinculada[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const requestSeqRef = useRef(0);

  const carregar = useCallback(async () => {
    const requestSeq = ++requestSeqRef.current;
    setCarregando(true);
    setErro(null);
    try {
      const { data } = await api.get<TeseVinculada[]>(`/teses/casos/${caseId}`);
      if (requestSeq !== requestSeqRef.current) return;
      setTeses(Array.isArray(data) ? data : []);
    } catch (e: any) {
      if (requestSeq !== requestSeqRef.current) return;
      setTeses([]);
      setErro(
        e?.response?.data?.detail ||
          "Não foi possível carregar as teses vinculadas a este caso.",
      );
    } finally {
      if (requestSeq === requestSeqRef.current) setCarregando(false);
    }
  }, [caseId]);

  useEffect(() => {
    void carregar();
    return () => {
      // Invalida a resposta em voo quando o componente desmonta ou o caseId muda.
      requestSeqRef.current += 1;
    };
  }, [carregar]);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
            <Scale className="h-4 w-4" /> Banco de Teses · contexto da peça
          </div>
          <h3 className="mt-2 text-base font-semibold text-slate-900">
            Teses já vinculadas ao caso
          </h3>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-500">
            Referência somente leitura para o advogado durante a produção. O EJC
            não injeta automaticamente estas teses na peça e não presume que a
            fundamentação ou jurisprudência estejam atuais.
          </p>
        </div>
        <Link
          to="/teses"
          className="btn-ghost inline-flex items-center gap-2 px-3 py-2 text-xs"
        >
          <BookOpenCheck className="h-4 w-4" /> Abrir Banco de Teses
        </Link>
      </div>

      <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-900">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>
          Antes de usar qualquer fundamento, confira vigência, inteiro teor e
          fonte oficial. A tela atual não possui o ciclo avançado de validação
          das fases futuras do Banco de Teses; a decisão jurídica continua humana.
        </span>
      </div>

      {carregando ? (
        <div className="mt-4 text-sm text-slate-500">Carregando teses do caso…</div>
      ) : erro ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-3">
          <span className="text-xs text-red-700">{String(erro)}</span>
          <button
            type="button"
            onClick={() => void carregar()}
            className="btn-ghost inline-flex items-center gap-1.5 px-3 py-1.5 text-xs"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Tentar novamente
          </button>
        </div>
      ) : teses.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
          Nenhuma tese está vinculada a este caso. Consulte o Banco de Teses para
          localizar conteúdo institucional. Esta tela não oferece ação de vínculo;
          o EJC não cria vínculo automático.
        </div>
      ) : (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {teses.map((tese) => {
            const ativa = tese.status === "ativa";
            return (
              <article
                key={tese.id}
                className={`rounded-xl border p-4 ${
                  ativa ? "border-slate-200" : "border-amber-200 bg-amber-50/30"
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">
                      {tese.titulo}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500">
                      {[tese.area_juridica, tese.tribunal].filter(Boolean).join(" · ") ||
                        "Sem área/tribunal informado"}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-1.5">
                    <span
                      className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-wide ${
                        ativa
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {tese.status}
                    </span>
                    {typeof tese.taxa_sucesso === "number" && (
                      <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-medium text-slate-600">
                        histórico {fmtTaxaSucesso(tese.taxa_sucesso)}
                      </span>
                    )}
                  </div>
                </div>

                {!ativa && (
                  <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-4 text-amber-800">
                    Tese não ativa. Não a trate como fundamento institucional aprovado
                    sem revisão e mudança deliberada de status.
                  </div>
                )}

                {tese.descricao && (
                  <p className="mt-3 whitespace-pre-line text-xs leading-5 text-slate-600">
                    {tese.descricao}
                  </p>
                )}

                {tese.fundamentacao && (
                  <div className="mt-3 rounded-lg bg-slate-50 p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                      Fundamentação cadastrada
                    </div>
                    <p className="mt-1 whitespace-pre-line text-xs leading-5 text-slate-600">
                      {tese.fundamentacao}
                    </p>
                  </div>
                )}

                {tese.jurisprudencia && (
                  <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                      Jurisprudência cadastrada
                    </div>
                    <p className="mt-1 whitespace-pre-line text-xs leading-5 text-slate-600">
                      {tese.jurisprudencia}
                    </p>
                  </div>
                )}

                {tese.contra_argumento && (
                  <div className="mt-3 rounded-lg border border-amber-100 bg-amber-50/60 p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                      Contrargumento previsível cadastrado
                    </div>
                    <p className="mt-1 whitespace-pre-line text-xs leading-5 text-amber-900">
                      {tese.contra_argumento}
                    </p>
                  </div>
                )}

                {tese.resultado && (
                  <div className="mt-3 text-[11px] text-slate-500">
                    Resultado do vínculo: <strong>{tese.resultado}</strong>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
