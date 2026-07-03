import { useState } from "react";
import { UploadCloud, AlertTriangle, ShieldAlert, CheckCircle2, FileText } from "lucide-react";
import api from "../lib/api";
import { PageHeader } from "../components/UI";

interface Analise {
  status: string;
  aviso?: string;
  summary: string;
  potential_flaws: string[];
  equivalence_issues: string[];
  extracted_text_sample: string;
}

export default function LicitacaoAuditoria() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<Analise | null>(null);

  const analisar = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setRes(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.post("/v1/licitacao-auditoria/analyze-competitor-proposal", form);
      setRes(r.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Falha ao analisar o PDF. Tente novamente.");
    } finally {
      setLoading(false);
    }
  };

  const semAchados = res && res.potential_flaws.length === 0 && res.equivalence_issues.length === 0;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-primary-100 bg-white p-5 shadow-sm md:p-6">
        <PageHeader
          eyebrow="Licitacoes"
          title="Auditoria de proposta"
          subtitle="Envie o PDF da proposta de um concorrente. O sistema extrai o texto e sinaliza pontos preliminares de impugnacao (Lei 14.133/21). Revisao do advogado obrigatoria."
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card space-y-4 p-5">
          <span className="eyebrow">Proposta do concorrente (PDF)</span>
          <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/60 px-4 py-8 text-center transition-colors hover:border-primary-300">
            <UploadCloud className="h-7 w-7 text-slate-400" />
            <span className="text-sm text-slate-600">
              {file ? file.name : "Clique para selecionar um arquivo PDF"}
            </span>
            <input
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              onChange={(e) => { setFile(e.target.files?.[0] || null); setRes(null); setError(null); }}
            />
          </label>
          <button onClick={analisar} disabled={!file || loading} className="btn-primary w-full">
            {loading ? "Analisando..." : "Analisar proposta"}
          </button>
          {error && (
            <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">{error}</div>
          )}
        </div>

        <div className="space-y-4">
          {!res ? (
            <div className="card flex h-full items-center justify-center p-8 text-center text-sm text-slate-400">
              Envie um PDF e clique em "Analisar" para ver os pontos de impugnacao.
            </div>
          ) : (
            <>
              <div className={`card p-5 ${semAchados ? "" : ""}`}>
                <div className="flex items-start gap-3">
                  {semAchados ? (
                    <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success-600" />
                  ) : (
                    <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warn-600" />
                  )}
                  <div>
                    <p className="text-sm font-medium text-slate-900">{res.summary}</p>
                    {res.aviso && <p className="mt-1 text-xs text-slate-400">{res.aviso}</p>}
                  </div>
                </div>
              </div>

              {res.potential_flaws.length > 0 && (
                <div className="card p-5">
                  <span className="eyebrow">Pontos de impugnacao ({res.potential_flaws.length})</span>
                  <ul className="mt-3 space-y-2">
                    {res.potential_flaws.map((f, i) => (
                      <li key={i} className="flex gap-2 text-sm text-slate-700">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn-500" />{f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {res.equivalence_issues.length > 0 && (
                <div className="card p-5">
                  <span className="eyebrow">Questoes de equivalencia ({res.equivalence_issues.length})</span>
                  <ul className="mt-3 space-y-2">
                    {res.equivalence_issues.map((f, i) => (
                      <li key={i} className="flex gap-2 text-sm text-slate-700">
                        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-primary-500" />{f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {res.extracted_text_sample && (
                <div className="card p-5">
                  <div className="mb-2 flex items-center gap-2">
                    <FileText className="h-4 w-4 text-slate-400" />
                    <span className="eyebrow">Trecho extraido</span>
                  </div>
                  <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-100 bg-slate-50/60 p-3 text-xs text-slate-600">
                    {res.extracted_text_sample}
                  </pre>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
