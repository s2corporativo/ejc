// ── src/components/AnaliseExtratos.tsx ───────────────────────────────────────
// Módulo de Análise Bancária (EXTRATOS): upload PDF/OFX/CSV → detecta cobranças
// abusivas (base legal) → Excel + minutas (notificação/petição/BACEN).
// Determinístico. Tudo é minuta — revisão obrigatória (OAB).
import { useState, useRef } from "react";
import {
  Landmark,
  UploadCloud,
  FileSpreadsheet,
  FileText,
  AlertTriangle,
} from "lucide-react";
import api from "../lib/api";

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
      className={`rounded-lg p-2 border ${alerta ? "border-red-200 bg-red-50/40" : "border-bronze-pale bg-bronze-50/10"}`}
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
      const { data } = await api.post("/v1/bank-analysis/upload", fd, {
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
    const r = await api.get(`/v1/bank-analysis/${res.analise.id}/excel`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "analise_bancaria.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  };

  const gerarDoc = async (tipo: string) => {
    if (!res?.analise?.id) return;
    const { data } = await api.post(
      `/v1/bank-analysis/${res.analise.id}/documento`,
      { tipo },
    );
    const w = window.open("", "_blank");
    if (w) {
      w.document.write(data.html);
      w.document.close();
    }
  };

  const a = res?.analise;
  const cobr: any[] = res?.cobrancas || [];
  const prioCor = (p: string) =>
    p === "URGENTE" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700";
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
      {erro && <p className="text-xs text-red-600">{erro}</p>}

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
            <p className="text-xs text-emerald-700 flex items-center gap-1">
              <AlertTriangle size={12} /> Nenhuma cobrança abusiva detectada
              automaticamente neste extrato.
            </p>
          )}
          <p className="text-[10px] text-amber-700">
            ⚠ Indícios automáticos — não afirmam ilegalidade. Revisão
            obrigatória do advogado (OAB).
          </p>
        </div>
      )}
    </div>
  );
}
