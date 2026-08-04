/**
 * Toast notification system — estado global via evento customizado.
 * Uso: toast.success("Salvo!") | toast.error("Erro") | toast.info("Info")
 */
import { useEffect, useState } from "react";
import { CheckCircle, XCircle, Info, X } from "lucide-react";

type ToastType = "success" | "error" | "info";

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
}

let _id = 0;

export const toast = {
  success: (message: string) => fire("success", message),
  error: (message: string) => fire("error", message),
  info: (message: string) => fire("info", message),
};

function fire(type: ToastType, message: string) {
  window.dispatchEvent(
    new CustomEvent("ejc-toast", { detail: { type, message, id: ++_id } }),
  );
}

const ICONS = {
  success: <CheckCircle size={16} className="text-success-600 shrink-0" />,
  error: <XCircle size={16} className="text-danger-500 shrink-0" />,
  info: <Info size={16} className="text-info-600 shrink-0" />,
};

// Superfície elevada (branca no claro, grafite quente no escuro) com filete
// de acento à esquerda na cor semântica — mesmo vocabulário dos cards/modais.
const SURFACE =
  "bg-white border-slate-200 dark:bg-[#241E10] dark:border-white/10";

const ACCENT = {
  success: "border-l-success-500",
  error: "border-l-danger-500",
  info: "border-l-info-500",
};

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => {
    const handler = (e: Event) => {
      const item = (e as CustomEvent).detail as ToastItem;
      setToasts((prev) => [...prev, item]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== item.id));
      }, 4000);
    };
    window.addEventListener("ejc-toast", handler);
    return () => window.removeEventListener("ejc-toast", handler);
  }, []);

  if (!toasts.length) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none"
      role="status"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-center gap-2.5 px-4 py-3 rounded-xl border border-l-4 shadow-float text-sm text-slate-700 dark:text-slate-200 animate-rise min-w-[220px] max-w-xs ${SURFACE} ${ACCENT[t.type]}`}
        >
          {ICONS[t.type]}
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() =>
              setToasts((prev) => prev.filter((x) => x.id !== t.id))
            }
            aria-label="Fechar aviso"
            className="rounded-md p-0.5 text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-300"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
