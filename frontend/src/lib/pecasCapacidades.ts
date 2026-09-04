// ── Capacidades de Peças (GET /pecas/meta → `capacidades`) ───────────────────
// O backend mantém a exportação do demonstrativo de cálculo atrás da flag
// PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED (default OFF) e agora ANUNCIA esse
// estado em `GET /pecas/meta` (`capacidades.demonstrativo_calculadora`). Sem
// consumir esse contrato, a tela só descobriria a trava no 403 do primeiro
// clique — depois de o advogado montar o cálculo inteiro.
//
// Cache de módulo (mesmo padrão de `iaStatus.ts`), e não `useCarregar`, por
// dois motivos: (1) `RamoBase.tsx` monta VÁRIOS `RamoFerramenta` na mesma
// página e `useCarregar` dispararia um GET por instância; (2) aqui não existe
// estado de erro para exibir — a falha é fail-open silenciosa.
//
// FAIL-OPEN: enquanto carrega, se a chamada falhar, ou se o backend for antigo
// e não devolver `capacidades`, a exportação é tratada como DISPONÍVEL. O 403
// de `POST /pecas/demonstrativo` continua sendo a rede de segurança (também
// para a flag que muda entre a carga da tela e o clique).
import { useEffect, useState } from "react";
import api from "./api";

export interface PecasCapacidades {
  /** `false` = flag desligada no backend: exportação bloqueada para todos. */
  demonstrativo_calculadora: boolean;
}

let cache: PecasCapacidades | null = null;
let inflight: Promise<PecasCapacidades | null> | null = null;

async function buscarCapacidades(): Promise<PecasCapacidades | null> {
  try {
    const { data } = await api.get<{
      capacidades?: Partial<PecasCapacidades>;
    }>("/pecas/meta");
    const valor = data?.capacidades?.demonstrativo_calculadora;
    if (typeof valor === "boolean") return { demonstrativo_calculadora: valor };
  } catch {
    // fail-open — sem resposta confiável, não bloquear nada na tela.
  }
  return null;
}

function obterCapacidades(): Promise<PecasCapacidades | null> {
  if (cache) return Promise.resolve(cache);
  // Só memoriza resposta REAL do backend; falha transitória não fica cacheada
  // pela sessão inteira (retenta na próxima montagem).
  inflight ??= buscarCapacidades()
    .then((capacidades) => {
      if (capacidades) cache = capacidades;
      return capacidades;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/** Somente para testes: limpa o cache de sessão. */
export function _resetPecasCapacidadesCache() {
  cache = null;
  inflight = null;
}

/**
 * Diz se a exportação do demonstrativo está liberada nesta instalação.
 * `disponivel` só é `false` com resposta explícita do backend; `conhecido`
 * distingue "backend disse que sim" de "ainda não sabemos / falhou".
 */
export function useDemonstrativoDisponivel(): {
  disponivel: boolean;
  conhecido: boolean;
} {
  const [capacidades, setCapacidades] = useState<PecasCapacidades | null>(
    cache,
  );
  useEffect(() => {
    if (cache) return;
    let ativo = true;
    void obterCapacidades().then((c) => {
      if (ativo && c) setCapacidades(c);
    });
    return () => {
      ativo = false;
    };
  }, []);
  return {
    disponivel: capacidades?.demonstrativo_calculadora ?? true,
    conhecido: capacidades !== null,
  };
}
