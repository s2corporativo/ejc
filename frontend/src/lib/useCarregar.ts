// ── Um jeito de carregar e um jeito de errar (S7) ────────────────────────────
// Substitui o padrão `api.get(...).then(setD).catch(() => {})` que deixava a
// tela em silêncio (ou com zeros) quando o backend falhava. O hook expõe um
// estado discreto (`carregando | vazio | falhou | ok`), a mensagem de erro já
// traduzida para leigo (`mensagemErroHttp`) e `recarregar()` para o botão
// "Tentar novamente" do `ErrorState`.
import { useCallback, useEffect, useRef, useState } from "react";
import { mensagemErroHttp } from "./iaErro";

export type EstadoCarga = "carregando" | "vazio" | "falhou" | "ok";

export type ResultadoCarga<T> = {
  estado: EstadoCarga;
  /** Último payload carregado com sucesso (mantido durante recarga). */
  dados: T | null;
  /** Mensagem de erro amigável quando `estado === "falhou"`. */
  erro: string | null;
  /** Status HTTP da falha (403 → permissão, 404 → inexistente…). */
  status: number | null;
  carregando: boolean;
  recarregar: () => void;
};

export type OpcoesCarga<T> = {
  /** Decide se o payload conta como vazio. Padrão: array vazio ou null. */
  vazio?: (dados: T) => boolean;
  /** Mensagem padrão quando o backend não entrega `detail` legível. */
  fallbackErro?: string;
  /** Quando `false`, o hook não dispara a carga (ex.: sem id ainda). */
  habilitado?: boolean;
};

const FALLBACK_PADRAO =
  "Não foi possível carregar estes dados. Tente novamente em instantes.";

function statusDoErro(err: unknown): number | null {
  const status = (err as { response?: { status?: number } } | undefined)
    ?.response?.status;
  return typeof status === "number" ? status : null;
}

function vazioPadrao(dados: unknown): boolean {
  if (dados == null) return true;
  if (Array.isArray(dados)) return dados.length === 0;
  return false;
}

/**
 * Carrega dados com estados explícitos.
 *
 * @param carregador função assíncrona que devolve o payload (pode lançar).
 * @param deps dependências que disparam nova carga (ex.: `[caseId]`).
 *
 * @example
 * const partes = useCarregar(
 *   () => api.get(`/cases/${id}/partes`).then((r) => asList(r.data)),
 *   [id],
 * );
 * if (partes.estado === "falhou")
 *   return <ErrorState message={partes.erro} onRetry={partes.recarregar} />;
 */
export function useCarregar<T>(
  carregador: () => Promise<T>,
  deps: readonly unknown[],
  opcoes: OpcoesCarga<T> = {},
): ResultadoCarga<T> {
  const { vazio = vazioPadrao, fallbackErro = FALLBACK_PADRAO } = opcoes;
  const habilitado = opcoes.habilitado ?? true;

  const [estado, setEstado] = useState<EstadoCarga>(
    habilitado ? "carregando" : "vazio",
  );
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const [tick, setTick] = useState(0);

  // Referências estáveis: o chamador passa closures novas a cada render e não
  // queremos que isso dispare recarga nem que uma resposta atrasada de uma
  // carga anterior sobrescreva a mais recente.
  const carregadorRef = useRef(carregador);
  carregadorRef.current = carregador;
  const vazioRef = useRef(vazio);
  vazioRef.current = vazio;
  const requisicaoRef = useRef(0);

  useEffect(() => {
    if (!habilitado) return;
    const id = ++requisicaoRef.current;
    let ativo = true;
    setEstado("carregando");
    setErro(null);
    setStatus(null);
    carregadorRef
      .current()
      .then((resultado) => {
        if (!ativo || id !== requisicaoRef.current) return;
        setDados(resultado);
        setEstado(vazioRef.current(resultado) ? "vazio" : "ok");
      })
      .catch((err: unknown) => {
        if (!ativo || id !== requisicaoRef.current) return;
        setStatus(statusDoErro(err));
        setErro(mensagemErroHttp(err, fallbackErro));
        setEstado("falhou");
      });
    return () => {
      ativo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, habilitado]);

  const recarregar = useCallback(() => setTick((t) => t + 1), []);

  return {
    estado,
    dados,
    erro,
    status,
    carregando: estado === "carregando",
    recarregar,
  };
}

/** Mensagem específica para 403 — a tela existe, o papel não pode vê-la. */
export const MENSAGEM_SEM_PERMISSAO =
  "Seu perfil não tem permissão para ver estes dados. Fale com o administrador do escritório.";

/** Escolhe a mensagem a exibir considerando o status HTTP da falha. */
export function mensagemDaFalha(
  resultado: Pick<ResultadoCarga<unknown>, "erro" | "status">,
): string {
  if (resultado.status === 403) return MENSAGEM_SEM_PERMISSAO;
  return resultado.erro ?? FALLBACK_PADRAO;
}
