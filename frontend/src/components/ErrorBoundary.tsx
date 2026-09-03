import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

// D7: o backend (`observabilidade.py`) limita `stack`/`component_stack` a
// 8000 caracteres; acima disso devolvia 422 e o crash não era registrado.
export const LIMITE_STACK = 8000;

export function truncarStack(valor: unknown): string | undefined {
  if (typeof valor !== "string" || !valor) return undefined;
  return valor.length > LIMITE_STACK ? valor.slice(0, LIMITE_STACK) : valor;
}

/**
 * Limite de erro reutilizável. Impede que uma exceção de renderização em um
 * módulo/aba derrube toda a tela (tela branca). Registra o erro no console e
 * exibe uma mensagem amigável em pt-BR.
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: unknown): State {
    const message =
      error instanceof Error ? error.message : "Erro desconhecido";
    return { hasError: true, message };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error("[ErrorBoundary] Falha ao renderizar módulo:", error, info);
    // Reporta ao backend (best-effort) para dar visibilidade ao crash sem
    // depender de leitura manual de console. fetch cru (sem o interceptor do
    // axios) para não arriscar recursão caso a falha seja no próprio client.
    try {
      const token = localStorage.getItem("ejc_access");
      if (!token) return; // o endpoint exige autenticação
      fetch("/api/observabilidade/frontend-error", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: truncarStack(
            error instanceof Error ? error.message : String(error),
          ),
          stack: truncarStack(error instanceof Error ? error.stack : undefined),
          component_stack: truncarStack(info?.componentStack),
          url: window.location.pathname,
          user_agent: navigator.userAgent,
        }),
        keepalive: true,
      }).catch(() => {});
    } catch {
      /* telemetria nunca deve derrubar o boundary */
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="m-4 rounded-xl border border-red-200 bg-red-50 p-6 text-center">
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-red-500" />
          <p className="text-sm font-medium text-red-700">
            Erro ao carregar este módulo.
          </p>
          {this.state.message && (
            <p className="mt-1 text-xs text-red-500 break-words">
              {this.state.message}
            </p>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}
