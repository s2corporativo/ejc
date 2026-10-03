// ── Status global da IA (GET /api/ia/status) ─────────────────────────────────
// Consulta UMA vez por sessão (cache em memória de módulo, sem polling) se a
// instalação tem IA ativada. Quando `disponivel === false`, o Layout exibe um
// banner leigo e os principais pontos de entrada de IA desabilitam os botões.
// FAIL-OPEN: se a chamada falhar (endpoint ausente, rede etc.), assume-se IA
// disponível para nunca bloquear indevidamente.
import { useEffect, useState } from "react";
import api from "./api";

export interface IaStatus {
  disponivel: boolean;
  mensagem: string | null;
}

export const MENSAGEM_IA_NAO_ATIVADA =
  "A inteligência artificial ainda não foi ativada nesta instalação. " +
  "Procure o administrador do sistema.";

let cache: IaStatus | null = null;
let inflight: Promise<IaStatus> | null = null;

async function buscarStatus(): Promise<IaStatus | null> {
  try {
    const { data } = await api.get<Partial<IaStatus>>("/ia/status");
    if (data && typeof data.disponivel === "boolean") {
      return { disponivel: data.disponivel, mensagem: data.mensagem ?? null };
    }
  } catch {
    // fail-open — sem status confiável, não bloquear nada.
  }
  return null;
}

function obterStatus(): Promise<IaStatus> {
  if (cache) return Promise.resolve(cache);
  // Só memoriza resposta REAL do backend; uma falha transitória (backend
  // reiniciando, rede) devolve fail-open sem cachear, para retentar na
  // próxima tela em vez de esconder o banner pela sessão inteira.
  inflight ??= buscarStatus()
    .then((status) => {
      if (status) cache = status;
      return status ?? { disponivel: true, mensagem: null };
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/**
 * Hook de status da IA. Enquanto carrega (e em qualquer falha) devolve
 * `disponivel: true` — o estado "indisponível" só aparece com resposta
 * explícita do backend.
 */
export function useIaStatus(): IaStatus & { carregado: boolean } {
  const [status, setStatus] = useState<IaStatus | null>(cache);
  useEffect(() => {
    if (cache) return;
    let ativo = true;
    obterStatus().then((s) => {
      if (ativo) setStatus(s);
    });
    return () => {
      ativo = false;
    };
  }, []);
  return {
    disponivel: status?.disponivel ?? true,
    mensagem: status?.mensagem ?? null,
    carregado: status !== null,
  };
}
