import { useState } from "react";
import {
  UploadCloud,
  AlertTriangle,
  ShieldAlert,
  CheckCircle2,
  FileText,
  FileDown,
  Loader2,
} from "lucide-react";
import api from "../lib/api";
import { PageHeader } from "../components/UI";

interface Analise {
  status: string;
  aviso?: string;
  summary: string;
  potential_flaws: string[];
  equivalence_issues: string[];
  extracted_text_sample: string;
  ia_usada?: boolean;
  ia_indisponivel?: boolean;
  ai_flags?: string[];
  ai_equivalencia?: string[];
}

export default function LicitacaoAuditoria() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<Analise | null>(null);
  const [edital, setEdital] = useState("");
  const [concorrente, setConcorrente] = useState("");
  const [gerandoPdf, setGerandoPdf] = useState(false);
  const [comIa, setComIa] = useState(false);

  const analisar = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setRes(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.post(
        `/v1/licitacao-auditoria/analyze-competitor-proposal?com_ia=${comIa}`,
        form,
      );
      setRes(r.data);
    } catch (e: any) {
      setError(
        e?.response?.data?.detail ||
          "Falha ao analisar o PDF. Tente novamente.",
      );
    } finally {
      setLoading(false);
    }
  };

  const gerarPdf = async () => {
    if (!res) return;
    setGerandoPdf(true);
    setError(null);
    try {
      const r = await api.post("/v1/licitacao-auditoria/report-pdf", {
        analise: {
          summary: res.summary,
          potential_flaws: res.potential_flaws,
          equivalence_issues: res.equivalence_issues,
          aviso: res.aviso ?? null,
        },
        edital,
        concorrente,
      });
      const downloadUrl: string | undefined = r.data?.download_url;
      if (!downloadUrl) throw new Error("download_url ausente na resposta");
      const blob = await api.get(downloadUrl.replace(/^\/api/, ""), {
        responseType: "blob",
      });
      const url = URL.createObjectURL(blob.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "auditoria-proposta-concorrente.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(
        e?.response?.data?.detail || "Falha ao gerar o relatorio em PDF.",
      );
    } finally {
      setGerandoPdf(false);
    }
  };

  const semAchados =
    res &&
    res.potential_flaws.length === 0 &&
    res.equivalence_issues.length === 0;

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
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setRes(null);
                setError(null);
              }}
            />
          </label>
          <label className="flex items-start gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={comIa}
              onChange={(e) => setComIa(e.target.checked)}
            />
            <span>
              Enriquecer com IA (opt-in). O texto é sanitizado antes do modelo e
              a chamada é registrada (LGPD). Saída é minuta — revisão do advogado
              obrigatória.
            </span>
          </label>
          <button
            onClick={analisar}
            disabled={!file || loading}
            className="btn-primary w-full"
          >
            {loading ? "Analisando..." : "Analisar proposta"}
          </button>
          {error && (
            <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">
              {error}
            </div>
          )}
        </div>

        <div className="space-y-4">
          {!res ? (
            <div className="card flex h-full items-center justify-center p-8 text-center text-sm text-slate-400">
              Envie um PDF e clique em "Analisar" para ver os pontos de
              impugnacao.
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
                    <p className="text-sm font-medium text-slate-900">
                      {res.summary}
                    </p>
                    {res.aviso && (
                      <p className="mt-1 text-xs text-slate-400">{res.aviso}</p>
                    )}
                  </div>
                </div>
              </div>

              {res.potential_flaws.length > 0 && (
                <div className="card p-5">
                  <span className="eyebrow">
                    Pontos de impugnacao ({res.potential_flaws.length})
                  </span>
                  <ul className="mt-3 space-y-2">
                    {res.potential_flaws.map((f, i) => (
                      <li key={i} className="flex gap-2 text-sm text-slate-700">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn-500" />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {res.equivalence_issues.length > 0 && (
                <div className="card p-5">
                  <span className="eyebrow">
                    Questoes de equivalencia ({res.equivalence_issues.length})
                  </span>
                  <ul className="mt-3 space-y-2">
                    {res.equivalence_issues.map((f, i) => (
                      <li key={i} className="flex gap-2 text-sm text-slate-700">
                        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-primary-500" />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {res.ia_indisponivel && (
                <div className="rounded-lg border border-warn-200 bg-warn-50 p-3 text-xs text-warn-700">
                  A análise por IA está indisponível no momento — os achados
                  determinísticos acima permanecem válidos.
                </div>
              )}

              {res.ia_usada &&
                ((res.ai_flags?.length ?? 0) > 0 ||
                  (res.ai_equivalencia?.length ?? 0) > 0) && (
                  <div className="card border-primary-200 p-5">
                    <div className="mb-1 flex items-center gap-2">
                      <ShieldAlert className="h-4 w-4 text-primary-600" />
                      <span className="eyebrow">Achados adicionais por IA</span>
                    </div>
                    <p className="mb-3 text-[11px] text-slate-400">
                      Minuta gerada por IA (texto sanitizado, chamada registrada
                      — LGPD). Revisão do advogado obrigatória; a IA não cita lei
                      ou jurisprudência sem confirmação.
                    </p>
                    <ul className="space-y-2">
                      {(res.ai_flags ?? []).map((f, i) => (
                        <li
                          key={`f${i}`}
                          className="flex gap-2 text-sm text-slate-700"
                        >
                          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn-500" />
                          {f}
                        </li>
                      ))}
                      {(res.ai_equivalencia ?? []).map((f, i) => (
                        <li
                          key={`e${i}`}
                          className="flex gap-2 text-sm text-slate-700"
                        >
                          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-primary-500" />
                          {f}
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

              <div className="card space-y-3 p-5">
                <span className="eyebrow">Relatorio de auditoria (Visual Law)</span>
                <div className="grid gap-2 sm:grid-cols-2">
                  <input
                    className="input text-sm"
                    placeholder="Edital (ex.: Pregao 12/2026)"
                    value={edital}
                    onChange={(e) => setEdital(e.target.value)}
                  />
                  <input
                    className="input text-sm"
                    placeholder="Concorrente"
                    value={concorrente}
                    onChange={(e) => setConcorrente(e.target.value)}
                  />
                </div>
                <button
                  onClick={gerarPdf}
                  disabled={gerandoPdf}
                  className="btn-gold flex items-center gap-2 text-sm"
                >
                  {gerandoPdf ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" /> Gerando PDF...
                    </>
                  ) : (
                    <>
                      <FileDown className="h-4 w-4" /> Gerar relatorio em PDF
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
