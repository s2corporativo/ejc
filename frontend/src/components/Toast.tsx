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
  success: <CheckCircle size={16} className="text-green-500 shrink-0" />,
  error: <XCircle size={16} className="text-red-500 shrink-0" />,
  info: <Info size={16} className="text-blue-500 shrink-0" />,
};

const BG = {
  success: "bg-white dark:bg-gray-800 border-green-200 dark:border-green-800",
  error: "bg-white dark:bg-gray-800 border-red-200   dark:border-red-800",
  info: "bg-white dark:bg-gray-800 border-blue-200  dark:border-blue-800",
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
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-center gap-2.5 px-4 py-3 rounded-lg border shadow-float text-sm text-gray-700 dark:text-gray-200 animate-rise min-w-[220px] max-w-xs ${BG[t.type]}`}
        >
          {ICONS[t.type]}
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() =>
              setToasts((prev) => prev.filter((x) => x.id !== t.id))
            }
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
