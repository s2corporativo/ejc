// ── Override do gate de citações (E5) ────────────────────────────────────────
// O backend (services/citation_gate.py) responde 409 `citacoes_nao_verificadas`
// quando o revisor tenta aprovar um output de IA com citações bloqueantes.
// O 409 NÃO é fim de linha: o advogado vê o que bloqueou e pode aprovar com
// `override_citacoes: true` + `justificativa_override` (auditada). Este
// componente extrai o padrão que já existia em `pages/Pecas.tsx` para que
// IA Jurídica (`PATCH /ai/logs/{id}/hitl`) e IA Defensiva
// (`PATCH /ia-defensiva/historico/{id}/status`) usem o mesmo caminho.
import { useCallback, useState, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Modal } from "./UI";

export type CitacaoBloqueante = {
  trecho?: string;
  tipo?: string;
  motivo?: string;
  [chave: string]: unknown;
};

export type BloqueioCitacoes = {
  mensagem: string;
  politica?: string;
  score?: number;
  motivos: string[];
  bloqueantes: CitacaoBloqueante[];
};

/** Campos extras que o override acrescenta ao corpo da requisição. */
export type CamposOverride = {
  override_citacoes?: true;
  justificativa_override?: string;
};

const MENSAGEM_PADRAO_BLOQUEIO =
  "A resposta da IA contém citações que não puderam ser confirmadas.";

/** Detecta o 409 do gate de citações; devolve `null` para qualquer outro erro. */
export function bloqueioDeCitacoes(err: unknown): BloqueioCitacoes | null {
  const response = (
    err as { response?: { status?: number; data?: { detail?: unknown } } }
  )?.response;
  const detail = response?.data?.detail as
    | {
        erro?: unknown;
        mensagem?: unknown;
        politica?: unknown;
        score?: unknown;
        motivos?: unknown;
        bloqueantes?: unknown;
      }
    | undefined;
  if (
    response?.status !== 409 ||
    !detail ||
    typeof detail !== "object" ||
    detail.erro !== "citacoes_nao_verificadas"
  ) {
    return null;
  }
  return {
    mensagem:
      typeof detail.mensagem === "string" && detail.mensagem.trim()
        ? detail.mensagem
        : MENSAGEM_PADRAO_BLOQUEIO,
    politica: typeof detail.politica === "string" ? detail.politica : undefined,
    score: typeof detail.score === "number" ? detail.score : undefined,
    motivos: Array.isArray(detail.motivos)
      ? detail.motivos.filter((m): m is string => typeof m === "string")
      : [],
    bloqueantes: Array.isArray(detail.bloqueantes)
      ? (detail.bloqueantes.filter(
          (b) => b && typeof b === "object",
        ) as CitacaoBloqueante[])
      : [],
  };
}

export const ERRO_JUSTIFICATIVA_OBRIGATORIA =
  "Para aprovar apesar das citações não confirmadas, justifique por escrito — a justificativa fica registrada em auditoria.";

export function OverrideCitacoesDialog({
  bloqueio,
  onCancelar,
  onConfirmar,
  enviando = false,
  erro,
}: {
  bloqueio: BloqueioCitacoes | null;
  onCancelar: () => void;
  onConfirmar: (justificativa: string) => void;
  enviando?: boolean;
  erro?: string | null;
}) {
  const [justificativa, setJustificativa] = useState("");
  const [erroLocal, setErroLocal] = useState<string | null>(null);

  const confirmar = () => {
    const texto = justificativa.trim();
    if (!texto) {
      setErroLocal(ERRO_JUSTIFICATIVA_OBRIGATORIA);
      return;
    }
    setErroLocal(null);
    onConfirmar(texto);
  };

  return (
    <Modal
      open={bloqueio !== null}
      onClose={onCancelar}
      title="Citações não confirmadas"
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={onCancelar}
            disabled={enviando}
          >
            Voltar e corrigir
          </button>
          <button
            type="button"
            className="btn-primary text-sm"
            onClick={confirmar}
            disabled={enviando}
          >
            {enviando ? "Registrando…" : "Aprovar com justificativa"}
          </button>
        </div>
      }
    >
      {bloqueio && (
        <div className="space-y-3 text-sm">
          <div className="flex items-start gap-2 rounded-lg border border-warn-200 bg-warn-50 p-3 text-warn-800">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-semibold">{bloqueio.mensagem}</p>
              {(bloqueio.politica || bloqueio.score != null) && (
                <p className="mt-1 text-xs text-warn-700">
                  {bloqueio.politica ? `Política: ${bloqueio.politica}` : ""}
                  {bloqueio.politica && bloqueio.score != null ? " · " : ""}
                  {bloqueio.score != null
                    ? `Score de verificação: ${bloqueio.score}`
                    : ""}
                </p>
              )}
            </div>
          </div>
          {bloqueio.motivos.length > 0 && (
            <ul className="list-disc space-y-1 pl-5 text-slate-700">
              {bloqueio.motivos.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          )}
          {bloqueio.bloqueantes.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase text-slate-500">
                Citações bloqueantes
              </p>
              <ul className="space-y-1">
                {bloqueio.bloqueantes.map((b, i) => (
                  <li
                    key={i}
                    className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-xs text-slate-700"
                  >
                    {typeof b.trecho === "string" ? b.trecho : ""}
                    {typeof b.motivo === "string" ? ` — ${b.motivo}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <label className="block">
            <span className="label">Justificativa do advogado *</span>
            <textarea
              className="input w-full"
              rows={3}
              value={justificativa}
              onChange={(e) => setJustificativa(e.target.value)}
              placeholder="Ex.: citações conferidas manualmente no site do tribunal em DD/MM."
              aria-label="Justificativa do override"
            />
          </label>
          {(erroLocal || erro) && (
            <p className="text-xs text-danger-600" role="alert">
              {erroLocal || erro}
            </p>
          )}
          <p className="text-xs text-slate-500">
            O override fica registrado em auditoria com seu usuário, data e a
            justificativa acima.
          </p>
        </div>
      )}
    </Modal>
  );
}

/**
 * Executa uma mutação HITL e, se o backend devolver o 409 do gate, abre o
 * diálogo de override; ao confirmar, reenvia a MESMA mutação com
 * `override_citacoes: true` + `justificativa_override`.
 *
 * @example
 * const override = useOverrideCitacoes();
 * const marcar = (id, status) =>
 *   override.executar((extra) =>
 *     api.patch(`/ai/logs/${id}/hitl`, { status, ...extra }),
 *   );
 * // no JSX: {override.dialogo}
 */
export function useOverrideCitacoes() {
  const [bloqueio, setBloqueio] = useState<BloqueioCitacoes | null>(null);
  const [pendente, setPendente] = useState<
    ((extra: CamposOverride) => Promise<unknown>) | null
  >(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const fechar = useCallback(() => {
    setBloqueio(null);
    setPendente(null);
    setErro(null);
  }, []);

  /**
   * Chama `enviar({})`. Em 409 do gate, guarda `enviar` e abre o diálogo;
   * qualquer outro erro é relançado para o chamador tratar (toast etc.).
   * Resolve `true` quando a mutação foi aplicada, `false` quando ficou
   * aguardando a justificativa.
   */
  const executar = useCallback(
    async (
      enviar: (extra: CamposOverride) => Promise<unknown>,
    ): Promise<boolean> => {
      try {
        await enviar({});
        return true;
      } catch (err) {
        const gate = bloqueioDeCitacoes(err);
        if (!gate) throw err;
        setBloqueio(gate);
        setPendente(() => enviar);
        setErro(null);
        return false;
      }
    },
    [],
  );

  const confirmar = useCallback(
    async (justificativa: string, aoConcluir?: () => void) => {
      if (!pendente) return;
      setEnviando(true);
      setErro(null);
      try {
        await pendente({
          override_citacoes: true,
          justificativa_override: justificativa,
        });
        fechar();
        aoConcluir?.();
      } catch (err) {
        const detail = (
          err as { response?: { status?: number; data?: { detail?: unknown } } }
        )?.response;
        // 422 = justificativa rejeitada pelo backend: fica no diálogo.
        if (detail?.status === 422 && typeof detail.data?.detail === "string") {
          setErro(detail.data.detail);
        } else {
          setErro(
            "Não foi possível registrar o override. Tente novamente em instantes.",
          );
        }
      } finally {
        setEnviando(false);
      }
    },
    [pendente, fechar],
  );

  return {
    bloqueio,
    enviando,
    erro,
    executar,
    confirmar,
    fechar,
    /** Renderize onde quiser; o diálogo só aparece quando há bloqueio. */
    dialogo: (aoConcluir?: () => void): ReactNode => (
      <OverrideCitacoesDialog
        bloqueio={bloqueio}
        onCancelar={fechar}
        onConfirmar={(j) => void confirmar(j, aoConcluir)}
        enviando={enviando}
        erro={erro}
      />
    ),
  };
}
