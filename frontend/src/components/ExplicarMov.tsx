// ── src/components/ExplicarMov.tsx ───────────────────────────────────────────
// P2.3 — Resumo/explicação em linguagem simples de cada movimentação processual.
// Reusa POST /api/ai/traduzir-andamento (já existente). Toggle por movimentação.
// Texto gerado por IA — revisar antes de repassar ao cliente.
import { useState } from "react";
import Markdown from "./Markdown";
import { Sparkles } from "lucide-react";
import api from "../lib/api";

export default function ExplicarMov({
  texto,
  caseId,
}: {
  texto?: string;
  caseId?: string;
}) {
  const [r, setR] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const explicar = async () => {
    if (r) {
      setR("");
      return;
    } // toggle: oculta
    if (!texto || texto.trim().length < 5) {
      setR("Movimentação curta demais para explicar.");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/ai/traduzir-andamento", {
        texto,
        case_id: caseId,
      });
      setR(data.resposta || "—");
    } catch (e: any) {
      setR(
        e.response?.status === 503
          ? "IA desabilitada."
          : "Falha ao explicar (IA indisponível).",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-1.5">
      <button
        onClick={explicar}
        disabled={loading}
        className="text-[11px] text-bronze hover:underline flex items-center gap-1"
      >
        <Sparkles size={11} />{" "}
        {loading ? "Explicando…" : r ? "Ocultar explicação" : "Explicar (IA)"}
      </button>
      {r && (
        <div className="text-xs text-slate-600 bg-bronze-50/40 rounded-lg p-2 mt-1">
          <Markdown source={r} className="leading-relaxed" />
          <p className="text-[10px] text-amber-700 mt-1">
            ⚠ Gerado por IA — revise antes de repassar ao cliente.
          </p>
        </div>
      )}
    </div>
  );
}
