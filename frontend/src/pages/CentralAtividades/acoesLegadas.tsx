// ── Ações que só existiam nas telas legadas, trazidas para a Central ─────────
// Fluxos de intimação (prazo assistido, captura manual) e de suspensão de
// tribunal (criar, excluir, simular). Os endpoints são os mesmos das telas
// legadas — nada foi criado no backend e nenhuma tela legada foi removida.
import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import api from "../../lib/api";
import { toast } from "../../components/Toast";
import { Modal, Spinner } from "../../components/UI";
import { useAuth } from "../../stores/auth";

/** Papéis aceitos por `require_roles` em backend/app/routers/suspensoes.py. */
export const ROLES_SUSPENSAO = ["superadmin", "admin", "socio"] as const;

/** Só admin/sócio criam ou removem suspensão — a UI não mostra o que daria 403. */
export function usePodeGerirSuspensoes(): boolean {
  const role = useAuth((s) => s.user?.role);
  return !!role && (ROLES_SUSPENSAO as readonly string[]).includes(role);
}

function erroDetalhe(e: any, fallback: string): string {
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof detail.mensagem === "string"
  )
    return detail.mensagem;
  return fallback;
}

function fmtData(d?: string | null): string {
  if (!d) return "—";
  const [ano, mes, dia] = String(d).slice(0, 10).split("-");
  return dia && mes && ano ? `${dia}/${mes}/${ano}` : String(d);
}

// ── 1. Prazo assistido da intimação (aceitar / recusar) ──────────────────────

type PrazoSugerido = {
  disponivel?: boolean;
  dias?: number | null;
  data_sugerida?: string | null;
  base_legal?: string | null;
  base_calculo?: string | null;
  motivo?: string | null;
  prazo_sugerido_status?: "nenhum" | "sugerido" | "aceito" | "recusado";
  prazo_deadline_id?: string | null;
};

export type SugestaoAberta = {
  id: string;
  titulo: string;
  dados: PrazoSugerido;
};

/**
 * Modal do prazo assistido: mesmo fluxo de dois passos da tela legada de
 * Intimações (removida na consolidação de 2026-08; ver histórico no git) —
 * a sugestão vem do GET em modo leitura e só então
 * o advogado aceita (cria o Deadline) ou recusa (não cria nada).
 *
 * A recusa NÃO pede motivo: o endpoint `POST /intimacoes/{id}/recusar-prazo`
 * não recebe corpo. O próprio modal é a confirmação, como no legado.
 */
export function PrazoSugeridoModal({
  sugestao,
  onClose,
  onResolvido,
}: {
  sugestao: SugestaoAberta | null;
  onClose: () => void;
  onResolvido: () => void;
}) {
  const [salvando, setSalvando] = useState<"aceitar" | "recusar" | null>(null);
  const dados = sugestao?.dados;
  const status = dados?.prazo_sugerido_status ?? "nenhum";
  const jaResolvido = status === "aceito" || status === "recusado";
  const semBase = dados?.disponivel === false;

  const aceitar = async () => {
    if (!sugestao) return;
    setSalvando("aceitar");
    try {
      const { data } = await api.post(
        `/intimacoes/${sugestao.id}/aceitar-prazo`,
      );
      toast.success(
        data.criado === false
          ? "Prazo já estava cadastrado para esta intimação."
          : `Prazo cadastrado para ${fmtData(data.data_prazo)}.`,
      );
      onResolvido();
      onClose();
    } catch (e: any) {
      // 422 = intimação sem caso vinculado (ou sem base para calcular).
      toast.error(
        e?.response?.status === 422
          ? erroDetalhe(
              e,
              "Intimação sem caso vinculado — vincule um caso antes de gerar o prazo.",
            )
          : erroDetalhe(e, "Não foi possível cadastrar o prazo."),
      );
    } finally {
      setSalvando(null);
    }
  };

  const recusar = async () => {
    if (!sugestao) return;
    setSalvando("recusar");
    try {
      const { data } = await api.post(
        `/intimacoes/${sugestao.id}/recusar-prazo`,
      );
      toast.info(data.detail || "Prazo recusado — nenhum prazo será gerado.");
      onResolvido();
      onClose();
    } catch (e) {
      toast.error(erroDetalhe(e, "Não foi possível recusar o prazo."));
    } finally {
      setSalvando(null);
    }
  };

  return (
    <Modal
      open={sugestao !== null}
      onClose={onClose}
      title="Prazo sugerido para a intimação"
    >
      {sugestao && (
        <div className="space-y-3">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {sugestao.titulo}
          </p>

          {semBase ? (
            <div className="rounded-lg border border-warn-200 bg-warn-50 p-3 text-xs text-warn-800">
              {dados?.motivo ||
                "Sem data de disponibilização não é possível sugerir prazo para esta intimação."}
            </div>
          ) : (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm dark:border-slate-700 dark:bg-slate-800">
              <div className="flex justify-between gap-2">
                <span className="text-slate-500">Data sugerida</span>
                <span className="font-semibold text-slate-800 dark:text-slate-100">
                  {fmtData(dados?.data_sugerida)}
                </span>
              </div>
              {dados?.dias != null && (
                <div className="flex justify-between gap-2 mt-1">
                  <span className="text-slate-500">Prazo</span>
                  <span className="text-slate-700 dark:text-slate-200">
                    {dados.dias} dias úteis forenses
                  </span>
                </div>
              )}
              {(dados?.base_legal || dados?.base_calculo) && (
                <p className="text-[11px] text-slate-500 mt-2 pt-2 border-t border-slate-200 dark:border-slate-700">
                  {dados.base_legal || dados.base_calculo}
                </p>
              )}
            </div>
          )}

          <p className="text-[11px] text-slate-500 italic">
            Sugestão automática — o prazo só é criado depois que você aceita.
          </p>

          {jaResolvido && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
              Esta intimação já teve o prazo{" "}
              <strong>{status === "aceito" ? "aceito" : "recusado"}</strong>.
            </div>
          )}

          <div className="flex gap-2 justify-end pt-1">
            <button onClick={onClose} className="btn-ghost">
              Fechar
            </button>
            <button
              onClick={recusar}
              disabled={salvando !== null || status === "recusado"}
              className="px-4 py-2 rounded-lg border border-danger-300 text-danger-700 text-sm hover:bg-danger-50 disabled:opacity-60"
            >
              {salvando === "recusar" ? "Recusando..." : "Recusar prazo"}
            </button>
            <button
              onClick={aceitar}
              disabled={salvando !== null || semBase || status === "aceito"}
              className="px-4 py-2 bg-success-600 text-white text-sm rounded-lg hover:bg-success-700 disabled:opacity-60"
            >
              {salvando === "aceitar"
                ? "Aceitando..."
                : "Aceitar e criar prazo"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ── 2. Suspensão de tribunal: cadastro (admin/sócio) ─────────────────────────

const FORM_VAZIO = {
  tribunal: "",
  data_inicio: "",
  data_fim: "",
  motivo: "",
  ato_normativo: "",
};

export function SuspensaoFormModal({
  open,
  onClose,
  onCriada,
}: {
  open: boolean;
  onClose: () => void;
  onCriada: () => void;
}) {
  const [form, setForm] = useState({ ...FORM_VAZIO });
  const [tribunais, setTribunais] = useState<string[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!open) return;
    setErro("");
    // Lista de tribunais é conveniência: se falhar, o campo vira texto livre.
    api
      .get("/suspensoes/tribunais")
      .then((r) =>
        setTribunais(Array.isArray(r.data?.tribunais) ? r.data.tribunais : []),
      )
      .catch(() => setTribunais([]));
  }, [open]);

  const salvar = async () => {
    setErro("");
    if (!form.tribunal || !form.data_inicio || !form.data_fim || !form.motivo) {
      setErro("Informe tribunal, período e motivo.");
      return;
    }
    setSalvando(true);
    try {
      await api.post("/suspensoes/", form);
      toast.success("Suspensão registrada.");
      setForm({ ...FORM_VAZIO });
      onCriada();
      onClose();
    } catch (e) {
      setErro(erroDetalhe(e, "Falha ao salvar a suspensão."));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Nova suspensão de prazo">
      <div className="space-y-3">
        <div>
          <label className="label text-xs">Tribunal *</label>
          <input
            className="input"
            list="central-tribunais"
            value={form.tribunal}
            placeholder="TJMG, TRT3, STJ…"
            onChange={(e) => setForm({ ...form, tribunal: e.target.value })}
          />
          <datalist id="central-tribunais">
            {tribunais.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label text-xs">Início *</label>
            <input
              className="input"
              type="date"
              value={form.data_inicio}
              onChange={(e) =>
                setForm({ ...form, data_inicio: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label text-xs">Fim *</label>
            <input
              className="input"
              type="date"
              value={form.data_fim}
              onChange={(e) => setForm({ ...form, data_fim: e.target.value })}
            />
          </div>
        </div>
        <div>
          <label className="label text-xs">Motivo *</label>
          <input
            className="input"
            value={form.motivo}
            placeholder="Recesso forense, portaria, feriado local…"
            onChange={(e) => setForm({ ...form, motivo: e.target.value })}
          />
        </div>
        <div>
          <label className="label text-xs">Ato normativo</label>
          <input
            className="input"
            value={form.ato_normativo}
            placeholder="Portaria 123/2026 (opcional)"
            onChange={(e) =>
              setForm({ ...form, ato_normativo: e.target.value })
            }
          />
        </div>
        {erro && <p className="text-xs text-danger-600">{erro}</p>}
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-ghost">
            Cancelar
          </button>
          <button
            onClick={salvar}
            disabled={salvando}
            className="px-4 py-2 bg-success-600 text-white text-sm rounded-lg hover:bg-success-700 disabled:opacity-60"
          >
            {salvando ? "Salvando..." : "Registrar suspensão"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ── 3. Simulador de prazo (leitura — não grava nada) ─────────────────────────

export function SimularPrazoModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [sim, setSim] = useState({
    data_inicio: "",
    dias: 15,
    contagem: "uteis",
    tribunal: "",
  });
  const [res, setRes] = useState<any>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  const simular = async () => {
    if (!sim.data_inicio) {
      setErro("Informe a data inicial.");
      return;
    }
    setCarregando(true);
    setErro("");
    setRes(null);
    try {
      // POST /suspensoes/simular NÃO persiste — é cálculo de apoio.
      const { data } = await api.post("/suspensoes/simular", {
        ...sim,
        dias: Number(sim.dias),
        tribunal: sim.tribunal || null,
      });
      setRes(data);
    } catch (e) {
      setErro(erroDetalhe(e, "Não foi possível simular o prazo."));
    } finally {
      setCarregando(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Simular vencimento de prazo">
      <div className="space-y-3">
        <p className="text-xs text-slate-500">
          Considera feriados e, se o tribunal for informado, as suspensões dele.
          Simulação de apoio — nada é gravado.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label text-xs">Data inicial *</label>
            <input
              className="input"
              type="date"
              value={sim.data_inicio}
              onChange={(e) => setSim({ ...sim, data_inicio: e.target.value })}
            />
          </div>
          <div>
            <label className="label text-xs">Dias</label>
            <input
              className="input"
              type="number"
              min={1}
              value={sim.dias}
              onChange={(e) => setSim({ ...sim, dias: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label text-xs">Contagem</label>
            <select
              className="input"
              value={sim.contagem}
              onChange={(e) => setSim({ ...sim, contagem: e.target.value })}
            >
              <option value="uteis">Dias úteis</option>
              <option value="corridos">Dias corridos</option>
            </select>
          </div>
          <div>
            <label className="label text-xs">Tribunal</label>
            <input
              className="input"
              value={sim.tribunal}
              placeholder="Opcional"
              onChange={(e) => setSim({ ...sim, tribunal: e.target.value })}
            />
          </div>
        </div>
        {erro && <p className="text-xs text-danger-600">{erro}</p>}
        {res && (
          <div className="rounded-lg border border-gold-200 bg-gold-50 p-3 text-sm">
            <div className="flex justify-between gap-2">
              <span className="text-slate-500">Vencimento</span>
              <span className="font-semibold text-navy">
                {fmtData(res.vencimento ?? res.data_vencimento)}
              </span>
            </div>
            {res.base && (
              <p className="text-[11px] text-slate-500 mt-2">{res.base}</p>
            )}
            {Array.isArray(res.suspensoes_aplicadas) &&
              res.suspensoes_aplicadas.length > 0 && (
                <p className="text-[11px] text-slate-600 mt-1">
                  {res.suspensoes_aplicadas.length} suspensão(ões)
                  considerada(s).
                </p>
              )}
          </div>
        )}
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-ghost">
            Fechar
          </button>
          <button
            onClick={simular}
            disabled={carregando}
            className="px-4 py-2 bg-navy text-white text-sm rounded-lg hover:bg-navy/90 disabled:opacity-60"
          >
            {carregando ? (
              <span className="flex items-center gap-1">
                <Spinner /> Calculando...
              </span>
            ) : (
              "Simular"
            )}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/** Aviso de operação demorada usado pela captura manual de intimações. */
export function AvisoCapturaEmCurso() {
  return (
    <div
      role="status"
      className="mb-4 flex items-center gap-2 rounded-xl border border-warn-200 bg-warn-50 px-4 py-2.5 text-xs text-warn-800"
    >
      <AlertTriangle className="w-4 h-4 shrink-0 text-warn-600" />
      Consultando o DJEN — a busca conversa com um serviço externo e pode levar
      alguns minutos. Você pode continuar usando a tela.
    </div>
  );
}
