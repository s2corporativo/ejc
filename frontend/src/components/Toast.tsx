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

const FALLBACK: Record<ToastType, string> = {
  success: "Operação concluída.",
  error: "Ocorreu um erro. Tente novamente.",
  info: "Informação indisponível.",
};

/**
 * Converte respostas estruturadas (especialmente `detail` do FastAPI/Pydantic)
 * em texto seguro para o React. Nunca serializa o objeto inteiro: campos como
 * `input` podem conter dados pessoais ou valores que não pertencem ao toast.
 */
export function normalizarMensagemToast(
  value: unknown,
  fallback = FALLBACK.error,
): string {
  if (typeof value === "string") return value.trim() || fallback;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  if (Array.isArray(value)) {
    const mensagens = value
      .map((item) => normalizarMensagemToast(item, ""))
      .filter(Boolean);
    if (!mensagens.length) return fallback;
    const exibidas = mensagens.slice(0, 3);
    const restante = mensagens.length - exibidas.length;
    return `${exibidas.join(" · ")}${restante > 0 ? ` · +${restante} validação(ões)` : ""}`;
  }

  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    for (const key of ["msg", "mensagem", "message", "detail"] as const) {
      if (obj[key] !== undefined) {
        const texto = normalizarMensagemToast(obj[key], "");
        if (texto) return texto;
      }
    }
  }

  return fallback;
}

export const toast = {
  success: (message: unknown) => fire("success", message),
  error: (message: unknown) => fire("error", message),
  info: (message: unknown) => fire("info", message),
};

function fire(type: ToastType, message: unknown) {
  window.dispatchEvent(
    new CustomEvent("ejc-toast", {
      detail: {
        type,
        message: normalizarMensagemToast(message, FALLBACK[type]),
        id: ++_id,
      },
    }),
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
  "bg-white border-slate-200 dark:bg-[var(--ejc-surface-raised)] dark:border-white/10";

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
