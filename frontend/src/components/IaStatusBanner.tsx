// ── Banner global "IA não ativada" ───────────────────────────────────────────
// Faixa discreta e dispensável exibida no Layout quando GET /api/ia/status
// responde `disponivel: false`. Dispensa vale para a sessão (sessionStorage).
import { useState } from "react";
import { Sparkles, X } from "lucide-react";
import { MENSAGEM_IA_NAO_ATIVADA, useIaStatus } from "../lib/iaStatus";

const DISMISS_KEY = "ejc_ia_banner_dispensado";

export default function IaStatusBanner() {
  const { disponivel, mensagem } = useIaStatus();
  const [dispensado, setDispensado] = useState(() => {
    try {
      return sessionStorage.getItem(DISMISS_KEY) === "1";
    } catch {
      return false;
    }
  });

  if (disponivel || dispensado) return null;

  const dispensar = () => {
    try {
      sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // storage indisponível: dispensa só em memória
    }
    setDispensado(true);
  };

  return (
    <div
      role="status"
      className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800 md:px-7"
    >
      <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
      <span className="min-w-0 flex-1">
        {mensagem || MENSAGEM_IA_NAO_ATIVADA} Os recursos de IA aparecem
        desabilitados até a ativação.
      </span>
      <button
        type="button"
        onClick={dispensar}
        aria-label="Dispensar aviso de IA não ativada"
        className="inline-flex min-h-[24px] min-w-[24px] shrink-0 items-center justify-center rounded p-0.5 text-amber-500 hover:bg-amber-100 hover:text-amber-700"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
