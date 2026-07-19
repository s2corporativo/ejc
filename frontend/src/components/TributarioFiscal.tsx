// ── src/components/TributarioFiscal.tsx ──────────────────────────────────────
// Vertical tributário — Recuperação de Créditos Fiscais:
//   upload de XMLs de NF-e + diagnóstico determinístico por tese (ex.: Tema 69
//   STF — exclusão do ICMS da base de PIS/COFINS), com estimativa de valores,
//   memória de cálculo e relatório PDF Visual Law.
// Tudo é estimativa preliminar — HITL obrigatório (OAB).
import { useRef, useState } from "react";
import {
  AlertTriangle,
  Coins,
  FileDown,
  FileText,
  Loader2,
  Receipt,
  Trash2,
  UploadCloud,
  XCircle,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";

// ── helpers ──────────────────────────────────────────────────────────────────
function fmtBRL(v: number | null | undefined) {
  return Number(v ?? 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}
// "2024-03-01" → "01/03/2024" (sem Date para evitar drift de fuso)
function fmtDataISO(iso: string | null | undefined) {
  if (!iso) return "—";
  const [a, m, d] = String(iso).slice(0, 10).split("-");
  return d && m && a ? `${d}/${m}/${a}` : String(iso);
}
function apiDetail(e: any, fallback: string): string {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d
      .map((x: any) => (typeof x === "string" ? x : x?.msg || ""))
      .filter(Boolean)
      .join("; ");
  return fallback;
}

const MAX_ARQUIVOS = 50;

// ── Tipos (contrato de POST /tributario/fiscal/analisar-xml) ────────────────
type Regime = "simples" | "lucro_presumido" | "lucro_real";

const REGIME_LABELS: Record<Regime, string> = {
  simples: "Simples Nacional",
  lucro_presumido: "Lucro Presumido",
  lucro_real: "Lucro Real",
};

interface TeseFiscal {
  tese_id: string;
  titulo: string;
  base_legal: string;
  fundamento: string;
  aplicavel: boolean;
  motivo_inaplicavel: string | null;
  valor_estimado: number;
  memoria_calculo: string[];
  alertas: string[];
  nivel_confianca: string;
}
interface NotaAnalisada {
  chave: string;
  numero: string;
  data_emissao: string;
  emitente_nome: string;
  valor_total: number;
  icms_destacado: number;
  erro: string | null;
}
interface AnaliseFiscalRes {
  total_estimado: number;
  notas_analisadas: number;
  notas_com_erro: number;
  periodo: { inicio: string; fim: string };
  teses: TeseFiscal[];
  aviso_hitl: string;
  notas: NotaAnalisada[];
}

// ── Card de tese ─────────────────────────────────────────────────────────────
function TeseCard({ tese }: { tese: TeseFiscal }) {
  return (
    <div
      className={`rounded-xl border-2 p-4 ${
        tese.aplicavel
          ? "border-gold-light bg-white"
          : "border-transparent bg-slate-900/[0.04] opacity-60 dark:bg-white/[0.06]"
      }`}
    >
      <div className="flex flex-wrap items-start gap-2">
        <h3 className="font-serif font-semibold text-navy text-sm flex-1 min-w-[200px]">
          {tese.titulo}
        </h3>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-gold-50 border border-gold-light text-gold-700 leading-relaxed">
          {tese.base_legal}
        </span>
      </div>
      <p className="text-xs text-slate-600 leading-relaxed mt-1.5">
        {tese.fundamento}
      </p>

      {tese.aplicavel ? (
        <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-xl font-bold text-gold-700">
            {fmtBRL(tese.valor_estimado)}
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-900/[0.05] text-slate-500 dark:bg-white/[0.07] dark:text-slate-400 uppercase tracking-wide">
            {tese.nivel_confianca.replace(/_/g, " ")}
          </span>
        </div>
      ) : (
        <p className="mt-3 text-xs text-slate-500">
          <b>Não aplicável:</b>{" "}
          {tese.motivo_inaplicavel || "sem elementos nas notas enviadas."}
        </p>
      )}

      {tese.memoria_calculo?.length > 0 && (
        <details className="card mt-2 bg-slate-50/60 px-3 py-2">
          <summary className="text-xs font-medium text-slate-600 cursor-pointer select-none">
            Como chegamos neste número
          </summary>
          <ol className="mt-2 space-y-1">
            {tese.memoria_calculo.map((m, i) => (
              <li key={i} className="text-[11px] text-slate-600 font-mono">
                {m}
              </li>
            ))}
          </ol>
        </details>
      )}

      {tese.alertas?.length > 0 && (
        <ul className="mt-2 space-y-1">
          {tese.alertas.map((a, i) => (
            <li key={i} className="text-[11px] text-warn-700">
              ⚠ {a}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Componente principal ─────────────────────────────────────────────────────
export default function TributarioFiscal() {
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [regime, setRegime] = useState<Regime | "">("");
  const [analisando, setAnalisando] = useState(false);
  const [gerandoPdf, setGerandoPdf] = useState(false);
  const [erro, setErro] = useState("");
  const [res, setRes] = useState<AnaliseFiscalRes | null>(null);
  const [errosAbertos, setErrosAbertos] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const adicionarArquivos = (lista: FileList | null) => {
    if (!lista?.length) return;
    setArquivos((prev) => {
      const novos = Array.from(lista).filter(
        (f) => !prev.some((p) => p.name === f.name && p.size === f.size),
      );
      return [...prev, ...novos];
    });
    // permite re-selecionar o mesmo arquivo depois de removê-lo
    if (inputRef.current) inputRef.current.value = "";
  };
  const removerArquivo = (i: number) =>
    setArquivos((prev) => prev.filter((_, j) => j !== i));

  const excedeu = arquivos.length > MAX_ARQUIVOS;

  const analisar = async () => {
    if (!arquivos.length) {
      setErro("Selecione ao menos um arquivo XML de NF-e.");
      return;
    }
    if (excedeu) {
      setErro(`Máximo de ${MAX_ARQUIVOS} XMLs por análise — remova o excedente.`);
      return;
    }
    if (!regime) {
      setErro("Informe o regime tributário do cliente no período das notas.");
      return;
    }
    setAnalisando(true);
    setErro("");
    setRes(null);
    setErrosAbertos(false);
    try {
      const fd = new FormData();
      arquivos.forEach((f) => fd.append("arquivos", f));
      fd.append("regime", regime);
      const { data } = await api.post<AnaliseFiscalRes>(
        "/tributario/fiscal/analisar-xml",
        fd,
      );
      setRes(data);
    } catch (e: any) {
      setErro(apiDetail(e, "Falha ao analisar os XMLs de NF-e."));
    } finally {
      setAnalisando(false);
    }
  };

  // Mesmo padrão dos demais PDFs Visual Law (SalaDeGuerra.tsx): POST → download_url → blob
  const gerarPdf = async () => {
    if (!res) return;
    setGerandoPdf(true);
    try {
      const r = await api.post("/tributario/fiscal/relatorio-pdf", res);
      const downloadUrl: string | undefined = r.data?.download_url;
      if (!downloadUrl) throw new Error("download_url ausente na resposta");
      // baseURL do client é /api — remove o prefixo se o backend devolver a URL completa
      const blob = await api.get(downloadUrl.replace(/^\/api/, ""), {
        responseType: "blob",
      });
      const url = URL.createObjectURL(blob.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "diagnostico-creditos-fiscais.pdf";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Diagnóstico em PDF (Visual Law) gerado.");
    } catch (e: any) {
      toast.error(apiDetail(e, "Falha ao gerar o PDF do diagnóstico."));
    } finally {
      setGerandoPdf(false);
    }
  };

  const notasComErro = res?.notas.filter((n) => n.erro) ?? [];

  return (
    <div
      id="tributario-fiscal"
      className="card p-4 mb-4 border-l-4 border-gold scroll-mt-20"
    >
      <div className="flex items-center gap-2 mb-1">
        <Coins size={16} className="text-gold-600" />
        <h2 className="font-serif font-semibold text-navy">
          Recuperação de Créditos Fiscais — diagnóstico por XML de NF-e
        </h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Envie os XMLs de NF-e do cliente e o sistema estima créditos
        recuperáveis por tese consolidada (ex.: Tema 69 STF — exclusão do ICMS
        da base de PIS/COFINS). Estimativa preliminar — revisão do advogado
        obrigatória.
      </p>

      {/* ── Passo 1 — Upload ─────────────────────────────────────────────── */}
      <div className="space-y-3">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="w-full rounded-xl border-2 border-dashed border-gold-light bg-gold-50/40 hover:bg-gold-50 transition-colors p-6 flex flex-col items-center gap-1.5 text-center"
        >
          <UploadCloud size={22} className="text-gold-600" />
          <span className="text-sm font-medium text-navy">
            Clique para selecionar os XMLs de NF-e
          </span>
          <span className="text-[11px] text-slate-500">
            Somente .xml · até {MAX_ARQUIVOS} arquivos por análise
          </span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".xml,text/xml"
          multiple
          className="hidden"
          onChange={(e) => adicionarArquivos(e.target.files)}
        />

        {arquivos.length > 0 && (
          <div className="card bg-slate-50/60 p-3">
            <div className="flex items-center justify-between mb-2">
              <span
                className={`text-xs font-semibold ${excedeu ? "text-danger-600" : "text-slate-600"}`}
              >
                {arquivos.length} arquivo{arquivos.length > 1 ? "s" : ""}{" "}
                selecionado{arquivos.length > 1 ? "s" : ""}
              </span>
              <button
                className="text-[11px] text-slate-400 hover:text-danger-600 transition-colors"
                onClick={() => setArquivos([])}
              >
                Limpar tudo
              </button>
            </div>
            {excedeu && (
              <p className="text-[11px] text-danger-600 mb-2">
                ⚠ Máximo de {MAX_ARQUIVOS} XMLs por análise — remova{" "}
                {arquivos.length - MAX_ARQUIVOS} arquivo
                {arquivos.length - MAX_ARQUIVOS > 1 ? "s" : ""}.
              </p>
            )}
            <ul className="max-h-40 overflow-y-auto space-y-1">
              {arquivos.map((f, i) => (
                <li
                  key={`${f.name}-${f.size}`}
                  className="flex items-center gap-2 text-[11px] text-slate-600"
                >
                  <FileText size={12} className="text-slate-400 shrink-0" />
                  <span className="truncate flex-1" title={f.name}>
                    {f.name}
                  </span>
                  <button
                    className="text-slate-300 hover:text-danger-600 transition-colors shrink-0"
                    title="Remover"
                    onClick={() => removerArquivo(i)}
                  >
                    <Trash2 size={12} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 items-end">
          <div>
            <label className="label text-xs">Regime tributário *</label>
            <select
              className="input text-sm"
              value={regime}
              onChange={(e) => setRegime(e.target.value as Regime | "")}
            >
              <option value="">Selecione…</option>
              {(Object.keys(REGIME_LABELS) as Regime[]).map((r) => (
                <option key={r} value={r}>
                  {REGIME_LABELS[r]}
                </option>
              ))}
            </select>
            <p className="text-[10px] text-slate-400 mt-1">
              Regime do <b>cliente</b> no período das notas — as teses variam
              por regime.
            </p>
          </div>
          <button
            className="btn-gold text-sm justify-self-start"
            disabled={analisando}
            onClick={analisar}
          >
            {analisando ? (
              <>
                <Loader2 size={14} className="animate-spin" /> Analisando XMLs…
              </>
            ) : (
              <>
                <Receipt size={14} /> Analisar créditos
              </>
            )}
          </button>
        </div>
        {erro && <p className="text-xs text-danger-600">{erro}</p>}
      </div>

      {/* ── Passo 2 — Resultado ──────────────────────────────────────────── */}
      {res && (
        <div className="mt-5 space-y-3">
          {/* Hero — total estimado */}
          <div className="rounded-xl border border-gold bg-gold-50 p-4">
            <div className="text-xs font-bold text-gold-700 uppercase tracking-wide">
              Total estimado de créditos recuperáveis
            </div>
            <div className="text-xl font-bold text-navy mt-1">
              {fmtBRL(res.total_estimado)}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
              <span>
                Período: <b>{fmtDataISO(res.periodo.inicio)}</b> a{" "}
                <b>{fmtDataISO(res.periodo.fim)}</b>
              </span>
              <span>
                Notas analisadas: <b>{res.notas_analisadas}</b>
              </span>
              {res.notas_com_erro > 0 && (
                <button
                  onClick={() => setErrosAbertos((v) => !v)}
                  className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-danger-50 border border-danger-200 text-danger-700 hover:bg-danger-100 transition-colors"
                  title="Ver notas com erro de leitura"
                >
                  <XCircle size={11} /> {res.notas_com_erro} nota
                  {res.notas_com_erro > 1 ? "s" : ""} com erro{" "}
                  {errosAbertos ? "▴" : "▾"}
                </button>
              )}
            </div>
            {errosAbertos && notasComErro.length > 0 && (
              <ul className="mt-2 space-y-1 rounded-lg border border-danger-200 bg-white/70 p-2">
                {notasComErro.map((n, i) => (
                  <li key={i} className="text-[11px] text-danger-700">
                    <span className="font-mono" title={n.chave}>
                      {n.chave ? `${n.chave.slice(0, 10)}…` : "(sem chave)"}
                    </span>{" "}
                    — {n.erro}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Aviso HITL — sempre visível */}
          <div className="rounded-xl border-2 border-warn-200 bg-warn-50 p-3 flex items-start gap-2">
            <AlertTriangle size={15} className="text-warn-700 shrink-0 mt-0.5" />
            <p className="text-xs text-warn-700 leading-relaxed">
              {res.aviso_hitl}
            </p>
          </div>

          {/* Teses */}
          <div className="space-y-2">
            {res.teses.map((t) => (
              <TeseCard key={t.tese_id} tese={t} />
            ))}
          </div>

          {/* PDF Visual Law */}
          <button
            className="btn-gold text-sm"
            disabled={gerandoPdf}
            onClick={gerarPdf}
          >
            {gerandoPdf ? (
              <>
                <Loader2 size={14} className="animate-spin" /> Gerando PDF…
              </>
            ) : (
              <>
                <FileDown size={14} /> Gerar diagnóstico em PDF (Visual Law)
              </>
            )}
          </button>

          {/* Notas analisadas */}
          <details className="card bg-slate-50/60 px-3 py-2">
            <summary className="text-xs font-medium text-slate-600 cursor-pointer select-none">
              Notas analisadas ({res.notas.length})
            </summary>
            <div className="overflow-x-auto mt-2">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-left text-slate-400 border-b border-slate-200">
                    <th className="py-1 pr-3 font-semibold">Chave</th>
                    <th className="py-1 pr-3 font-semibold">Nº</th>
                    <th className="py-1 pr-3 font-semibold">Emissão</th>
                    <th className="py-1 pr-3 font-semibold">Emitente</th>
                    <th className="py-1 pr-3 font-semibold text-right">
                      Total
                    </th>
                    <th className="py-1 pr-3 font-semibold text-right">
                      ICMS destacado
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {res.notas.map((n, i) => (
                    <tr
                      key={n.chave || i}
                      className={`border-t border-slate-100 hover:bg-slate-50/60 ${n.erro ? "text-danger-600" : "text-slate-600"}`}
                    >
                      <td className="py-1.5 pr-3 font-mono" title={n.chave}>
                        {n.chave
                          ? `${n.chave.slice(0, 8)}…${n.chave.slice(-6)}`
                          : "—"}
                      </td>
                      <td className="py-1.5 pr-3">{n.numero || "—"}</td>
                      <td className="py-1.5 pr-3 whitespace-nowrap">
                        {fmtDataISO(n.data_emissao)}
                      </td>
                      <td className="py-1.5 pr-3">{n.emitente_nome || "—"}</td>
                      <td className="py-1.5 pr-3 text-right whitespace-nowrap">
                        {fmtBRL(n.valor_total)}
                      </td>
                      <td className="py-1.5 pr-3 text-right whitespace-nowrap">
                        {fmtBRL(n.icms_destacado)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
