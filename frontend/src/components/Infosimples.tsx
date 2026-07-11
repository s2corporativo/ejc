/**
 * Integração Infosimples (consultas pagas — TJMG e Receita Federal).
 *
 * Gate por status: GET /infosimples/status → { enabled, configured, ... }.
 * Quando !enabled || !configured os botões NÃO são renderizados — a
 * integração fica invisível para o usuário quando desligada no servidor.
 *
 * Toda chamada passa pelo cliente axios `api` (lib/api.ts). Erros seguem o
 * contrato do backend: 503 desligada, 429 teto diário/rate limit (detail
 * claro), 502 erro do provedor, 404 não localizado, 422 dados inválidos.
 */
import { useEffect, useState } from "react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Badge, ConfirmModal, Modal, fmtMoney } from "./UI";

// ── Tipos do contrato ────────────────────────────────────────────────────────
export interface InfosimplesStatus {
  enabled: boolean;
  configured: boolean;
  consultas_hoje: number;
  limite_diario: number;
}

export interface TJMGParte {
  nome: string;
  tipo?: string;
  advogados?: string[];
}

export interface TJMGMovimento {
  data?: string;
  codigo?: string;
  descricao: string;
}

export interface TJMGProcessoResult {
  numero_processo: string;
  classe?: string;
  assunto?: string;
  situacao?: string;
  valor?: string | number | null;
  orgao?: string;
  partes?: TJMGParte[];
  movimentos?: TJMGMovimento[];
  case_id?: string;
  movimentos_novos: number;
  cache: boolean;
  site_receipts?: string[];
}

export interface ReceitaResult {
  nome?: string;
  razao_social?: string;
  situacao_cadastral?: string;
  atividade_principal?: string;
  endereco?: string;
}

// ── Status (gate) — cache de módulo p/ não repetir o GET a cada mount ───────
let statusPromise: Promise<InfosimplesStatus | null> | null = null;

function fetchStatus(): Promise<InfosimplesStatus | null> {
  statusPromise ??= api
    .get<InfosimplesStatus>("/infosimples/status")
    .then((r) => r.data)
    .catch(() => null);
  return statusPromise;
}

/**
 * Hook do gate: `habilitado` só é true quando o backend responde
 * enabled && configured. Em erro ou integração desligada → false
 * (botões somem, sem toast — invisível quando desligada).
 */
export function useInfosimplesStatus() {
  const [status, setStatus] = useState<InfosimplesStatus | null>(null);
  useEffect(() => {
    let vivo = true;
    fetchStatus().then((s) => {
      if (vivo) setStatus(s);
    });
    return () => {
      vivo = false;
    };
  }, []);
  return {
    status,
    habilitado: Boolean(status?.enabled && status?.configured),
  };
}

// ── Erros ────────────────────────────────────────────────────────────────────
const ERRO_PADRAO: Record<number, string> = {
  503: "Integração Infosimples desligada no servidor.",
  429: "Limite de consultas atingido. Tente novamente mais tarde.",
  502: "O provedor da consulta retornou erro. Tente novamente em instantes.",
  404: "Registro não localizado na fonte consultada.",
  422: "Dados inválidos para esta consulta.",
};

/** Toast de erro padronizado: prioriza o `detail` do backend (429 tem detail claro). */
export function toastErroInfosimples(err: unknown) {
  const e = err as {
    response?: { status?: number; data?: { detail?: unknown } };
  };
  const detail = e.response?.data?.detail;
  const st = e.response?.status;
  toast.error(
    (typeof detail === "string" && detail) ||
      (st != null && ERRO_PADRAO[st]) ||
      "Falha na consulta Infosimples.",
  );
}

// ── Consulta profunda TJMG (aba Processos do caso) ───────────────────────────
export function ConsultaProfundaTJMG({ caseId }: { caseId: string }) {
  const { habilitado } = useInfosimplesStatus();
  const [confirmando, setConfirmando] = useState(false);
  const [consultando, setConsultando] = useState(false);
  const [resultado, setResultado] = useState<TJMGProcessoResult | null>(null);

  if (!habilitado) return null;

  const consultar = async () => {
    setConsultando(true);
    try {
      const { data } = await api.post<TJMGProcessoResult>(
        "/infosimples/tjmg/processo",
        { case_id: caseId },
      );
      setConfirmando(false);
      setResultado(data);
      if (data.movimentos_novos > 0) {
        toast.success(
          `${data.movimentos_novos} movimento(s) novo(s) adicionados à timeline.`,
        );
      }
    } catch (err) {
      toastErroInfosimples(err);
    } finally {
      setConsultando(false);
    }
  };

  const movimentos = resultado?.movimentos ?? [];
  const partes = resultado?.partes ?? [];

  return (
    <>
      <button
        onClick={() => setConfirmando(true)}
        className="btn-secondary text-sm"
      >
        Consulta profunda TJMG
      </button>

      <ConfirmModal
        open={confirmando}
        onClose={() => setConfirmando(false)}
        onConfirm={consultar}
        variant="primary"
        title="Consulta profunda TJMG"
        message="Esta consulta é cobrada por execução (tarifa Infosimples). Consultas repetidas no mesmo dia usam cache sem custo. Continuar?"
        confirmLabel={consultando ? "Consultando…" : "Continuar"}
        loading={consultando}
      />

      <Modal
        open={!!resultado}
        onClose={() => setResultado(null)}
        title={`Processo ${resultado?.numero_processo || ""} — TJMG`}
        size="lg"
      >
        {resultado && (
          <div className="space-y-4 text-sm">
            {resultado.cache && (
              <Badge tone="green">resultado do cache do dia (sem custo)</Badge>
            )}

            <div className="grid grid-cols-2 gap-3">
              {(
                [
                  ["Classe", resultado.classe],
                  ["Assunto", resultado.assunto],
                  ["Situação", resultado.situacao],
                  ["Órgão", resultado.orgao],
                  [
                    "Valor",
                    typeof resultado.valor === "number"
                      ? fmtMoney(resultado.valor)
                      : resultado.valor,
                  ],
                ] as const
              ).map(([label, valor]) => (
                <div key={label}>
                  <p className="text-xs uppercase text-slate-400">{label}</p>
                  <p className="text-slate-700 dark:text-slate-200">
                    {valor || "—"}
                  </p>
                </div>
              ))}
            </div>

            {partes.length > 0 && (
              <div>
                <h4 className="mb-1 font-semibold">Partes</h4>
                <ul className="space-y-1">
                  {partes.map((p, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-1.5">
                      {p.tipo && <Badge tone="slate">{p.tipo}</Badge>}
                      <span>{p.nome}</span>
                      {p.advogados && p.advogados.length > 0 && (
                        <span className="text-xs text-slate-400">
                          adv.: {p.advogados.join(", ")}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {movimentos.length > 0 && (
              <div>
                <h4 className="mb-1 font-semibold">
                  Últimos movimentos
                  {resultado.movimentos_novos > 0 &&
                    ` — ${resultado.movimentos_novos} novo(s) na timeline`}
                </h4>
                <ul className="max-h-64 space-y-1.5 overflow-y-auto">
                  {movimentos.slice(0, 15).map((m, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="shrink-0 text-xs text-slate-400">
                        {m.data || "—"}
                      </span>
                      <span className="text-slate-700 dark:text-slate-200">
                        {m.descricao}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}

// ── Verificação na Receita (cadastro de cliente) ─────────────────────────────
/** Só dígitos (CPF = 11, CNPJ = 14). */
function digitos(doc: string) {
  return (doc || "").replace(/\D/g, "");
}

/**
 * Botão "Verificar na Receita" ao lado do campo CPF/CNPJ do cadastro de
 * cliente. Só aparece quando a integração está habilitada E o documento tem
 * 11 (CPF) ou 14 (CNPJ) dígitos. CPF exige data de nascimento (mini-form).
 * `onUsarNome` preenche o campo nome/razão social do formulário chamador.
 */
export function VerificarReceita({
  tipo,
  documento,
  onUsarNome,
}: {
  tipo: "cpf" | "cnpj";
  documento: string;
  onUsarNome: (nome: string) => void;
}) {
  const { habilitado } = useInfosimplesStatus();
  const [aberto, setAberto] = useState(false);
  const [nascimento, setNascimento] = useState("");
  const [consultando, setConsultando] = useState(false);
  const [resultado, setResultado] = useState<ReceitaResult | null>(null);

  const doc = digitos(documento);
  const docOk = tipo === "cpf" ? doc.length === 11 : doc.length === 14;
  if (!habilitado || !docOk) return null;

  const consultar = async () => {
    setConsultando(true);
    try {
      const { data } =
        tipo === "cpf"
          ? await api.post<ReceitaResult>("/infosimples/receita/cpf", {
              cpf: doc,
              data_nascimento: nascimento,
            })
          : await api.post<ReceitaResult>("/infosimples/receita/cnpj", {
              cnpj: doc,
            });
      setResultado(data);
    } catch (err) {
      toastErroInfosimples(err);
    } finally {
      setConsultando(false);
    }
  };

  const abrir = () => {
    setResultado(null);
    setNascimento("");
    setAberto(true);
    // CNPJ não pede dado extra — consulta direto ao abrir o modal.
    if (tipo === "cnpj") consultar();
  };

  const nomeEncontrado = resultado?.nome || resultado?.razao_social || "";

  return (
    <>
      <button
        type="button"
        onClick={abrir}
        className="btn-secondary text-xs whitespace-nowrap"
      >
        Verificar na Receita
      </button>

      <Modal
        open={aberto}
        onClose={() => setAberto(false)}
        title={`Verificar ${tipo === "cpf" ? "CPF" : "CNPJ"} na Receita Federal`}
        size="sm"
      >
        <div className="space-y-3 text-sm">
          <p className="text-xs text-slate-500">
            Consulta paga por execução (tarifa Infosimples). Documento:{" "}
            <span className="font-mono">{documento}</span>
          </p>

          {tipo === "cpf" && !resultado && (
            <div>
              <label className="label">Data de nascimento *</label>
              <input
                className="input"
                placeholder="dd/mm/aaaa"
                value={nascimento}
                onChange={(e) => setNascimento(e.target.value)}
              />
              <button
                type="button"
                disabled={
                  consultando || !/^\d{2}\/\d{2}\/\d{4}$/.test(nascimento)
                }
                onClick={consultar}
                className="btn-primary mt-3 text-sm disabled:opacity-50"
              >
                {consultando ? "Consultando…" : "Consultar"}
              </button>
            </div>
          )}

          {tipo === "cnpj" &&
            !resultado &&
            (consultando ? (
              <p className="text-slate-500">Consultando…</p>
            ) : (
              <button
                type="button"
                onClick={consultar}
                className="btn-primary text-sm"
              >
                Tentar novamente
              </button>
            ))}

          {resultado && (
            <div className="space-y-2">
              <div>
                <p className="text-xs uppercase text-slate-400">
                  {tipo === "cpf" ? "Nome" : "Razão social"}
                </p>
                <p className="font-medium text-slate-800 dark:text-slate-100">
                  {nomeEncontrado || "—"}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase text-slate-400">
                  Situação cadastral
                </p>
                <Badge
                  tone={
                    (resultado.situacao_cadastral || "")
                      .toLowerCase()
                      .includes("ativ")
                      ? "green"
                      : "amber"
                  }
                >
                  {resultado.situacao_cadastral || "—"}
                </Badge>
              </div>
              {resultado.atividade_principal && (
                <div>
                  <p className="text-xs uppercase text-slate-400">
                    Atividade principal
                  </p>
                  <p>{resultado.atividade_principal}</p>
                </div>
              )}
              {resultado.endereco && (
                <div>
                  <p className="text-xs uppercase text-slate-400">Endereço</p>
                  <p>{resultado.endereco}</p>
                </div>
              )}
              {nomeEncontrado && (
                <button
                  type="button"
                  className="btn-primary mt-2 text-sm"
                  onClick={() => {
                    onUsarNome(nomeEncontrado);
                    setAberto(false);
                  }}
                >
                  Usar este nome
                </button>
              )}
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
