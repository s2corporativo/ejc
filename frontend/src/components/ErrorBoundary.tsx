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
          message: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined,
          component_stack: info?.componentStack,
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
