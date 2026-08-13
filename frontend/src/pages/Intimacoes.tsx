import { useEffect, useState } from "react";
import {
  Inbox,
  RefreshCw,
  CheckCircle2,
  ExternalLink,
  Loader2,
  CalendarClock,
  XCircle,
} from "lucide-react";
import { useNavigate } from "react-router";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import api from "../lib/api";
import { asList } from "../lib/list";
import {
  PageHeader,
  Modal,
  Alert,
  Button,
  Badge,
  EmptyState,
  fmtDate,
} from "../components/UI";
import { toast } from "../components/Toast";

type PrazoStatus = "nenhum" | "sugerido" | "aceito" | "recusado";

// Resposta de GET /intimacoes/{id}/prazo-sugerido.
// Na contenção P0 da #968, o backend não calcula vencimento: ele expõe a
// pendência para revisão e aceita somente a data final conferida pelo usuário.
interface PrazoSugerido {
  disponivel: boolean;
  tipo_detectado?: string | null;
  dias?: number | null;
  data_sugerida?: string | null;
  data_base?: string | null;
  data_disponibilizacao?: string | null;
  fundamentacao?: string | null;
  aviso?: string | null;
  revisao_necessaria?: boolean;
  motivo?: string | null;
  prazo_sugerido_status: PrazoStatus;
  prazo_deadline_id?: string | null;
}

interface PrazoLocal {
  status: PrazoStatus;
  deadlineId: string | null;
}

interface StatusCaptura {
  executado_em: string | null;
  sucesso: boolean | null;
  intimacoes_encontradas: number | null;
  erro: string | null;
}

const PRAZO_BADGE: Record<
  PrazoStatus,
  { tone: "slate" | "amber" | "green" | "red"; label: string }
> = {
  nenhum: { tone: "amber", label: "Revisão pendente" },
  sugerido: { tone: "amber", label: "Revisão pendente" },
  aceito: { tone: "green", label: "Prazo aceito" },
  recusado: { tone: "red", label: "Sem prazo — revisado" },
};

export default function Intimacoes() {
  const nav = useNavigate();
  const [items, setItems] = useState<any[]>([]);
  const [pendentes, setPendentes] = useState(true);
  const [loading, setLoading] = useState(false);
  const [sugerindo, setSugerindo] = useState<string | null>(null);
  const [salvando, setSalvando] = useState<null | "aceitar" | "recusar">(null);
  const [sugestao, setSugestao] = useState<{
    com: any;
    dados: PrazoSugerido;
  } | null>(null);
  const [dataManual, setDataManual] = useState("");
  const [prazos, setPrazos] = useState<Record<string, PrazoLocal>>({});
  const [status, setStatus] = useState<StatusCaptura | null>(null);

  const load = () =>
    api
      .get(`/intimacoes/?apenas_pendentes=${pendentes}`)
      .then((r) => setItems(asList(r.data)));

  const loadStatus = () =>
    api
      .get<StatusCaptura>("/intimacoes/status-captura")
      .then((r) => setStatus(r.data))
      .catch(() => setStatus(null));

  useEffect(() => {
    load();
  }, [pendentes]);

  useEffect(() => {
    loadStatus();
  }, []);

  const statusDe = (com: any): PrazoStatus =>
    prazos[com.id]?.status ??
    (com.prazo_sugerido_status as PrazoStatus | undefined) ??
    "nenhum";

  const fecharRevisao = () => {
    if (salvando) return;
    setSugestao(null);
    setDataManual("");
  };

  const capturar = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/intimacoes/capturar-agora");
      toast.success(data.detail);
      load();
      loadStatus();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Configure sua OAB no menu do avatar",
      );
    } finally {
      setLoading(false);
    }
  };

  const processar = async (id: string) => {
    try {
      const { data } = await api.post(`/intimacoes/${id}/processar`);
      toast.success(data.detail || "Intimação marcada como tratada.");
      load();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail ||
          "Revise a necessidade de prazo antes de marcar como tratada.",
      );
    }
  };

  // Passo 1: carrega os dados de revisão. Não persiste e não calcula prazo.
  const revisarPrazo = async (com: any) => {
    setSugerindo(com.id);
    setDataManual("");
    try {
      const { data } = await api.get<PrazoSugerido>(
        `/intimacoes/${com.id}/prazo-sugerido`,
      );
      setPrazos((p) => ({
        ...p,
        [com.id]: {
          status: data.prazo_sugerido_status || "nenhum",
          deadlineId: data.prazo_deadline_id ?? null,
        },
      }));
      setSugestao({ com, dados: data });
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail ||
          "Não foi possível carregar a revisão desta intimação.",
      );
    } finally {
      setSugerindo(null);
    }
  };

  // Passo 2a: aceita uma data final conferida e cria o Deadline vinculado.
  const aceitarPrazo = async () => {
    if (!sugestao) return;
    const { com, dados } = sugestao;
    if (!dados.disponivel && !dataManual) {
      toast.error("Informe o vencimento conferido antes de aceitar o prazo.");
      return;
    }

    setSalvando("aceitar");
    try {
      const payload = dados.disponivel ? undefined : { data_prazo: dataManual };
      const { data } = await api.post(
        `/intimacoes/${com.id}/aceitar-prazo`,
        payload,
      );
      setPrazos((p) => ({
        ...p,
        [com.id]: { status: "aceito", deadlineId: data.deadline_id ?? null },
      }));
      toast.success(
        data.criado === false
          ? "Prazo já estava cadastrado para esta intimação."
          : `Prazo cadastrado para ${fmtDate(data.data_prazo)}.`,
      );
      setSugestao(null);
      setDataManual("");
      load();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível cadastrar o prazo.",
      );
    } finally {
      setSalvando(null);
    }
  };

  // Passo 2b: registra explicitamente que a comunicação não gerará prazo.
  const recusarPrazo = async () => {
    if (!sugestao) return;
    const { com } = sugestao;
    setSalvando("recusar");
    try {
      const { data } = await api.post(`/intimacoes/${com.id}/recusar-prazo`);
      setPrazos((p) => ({
        ...p,
        [com.id]: { status: "recusado", deadlineId: null },
      }));
      toast.info(data.detail || "Revisão concluída sem geração de prazo.");
      setSugestao(null);
      setDataManual("");
      load();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível registrar a decisão.",
      );
    } finally {
      setSalvando(null);
    }
  };

  const sugestaoAtual = sugestao ? statusDe(sugestao.com) : "nenhum";
  const podeAceitar =
    sugestaoAtual !== "recusado" &&
    sugestaoAtual !== "aceito" &&
    Boolean(sugestao?.dados.disponivel || dataManual);

  return (
    <div>
      <PageHeader
        title="Intimações DJEN"
        actions={
          <div className="flex gap-2">
            <button
              className="btn-ghost"
              onClick={() => setPendentes(!pendentes)}
            >
              {pendentes ? "Ver todas" : "Só pendentes"}
            </button>
            <button
              className="btn-primary"
              disabled={loading}
              onClick={capturar}
            >
              <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
              Capturar agora
            </button>
          </div>
        }
      />

      <div className="card mb-5 flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-3">
          <span
            className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${
              status?.executado_em == null
                ? "bg-slate-300"
                : status?.sucesso
                  ? "bg-emerald-500"
                  : "bg-red-500"
            }`}
          />
          <div className="text-sm">
            {status?.executado_em == null ? (
              <p className="text-slate-500">
                Captura automática ainda não executada.
              </p>
            ) : (
              <>
                <p className="font-medium text-slate-700">
                  Última captura em{" "}
                  {format(
                    new Date(status.executado_em),
                    "dd/MM/yyyy 'às' HH:mm",
                    { locale: ptBR },
                  )}
                </p>
                {status.sucesso ? (
                  <p className="text-xs text-slate-500">
                    {status.intimacoes_encontradas ?? 0} intimação(ões)
                    encontrada(s).
                  </p>
                ) : (
                  <p className="text-xs text-red-600">
                    Falha: {status.erro || "erro desconhecido"}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
        <button className="btn-ghost" disabled={loading} onClick={capturar}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Capturar agora
        </button>
      </div>

      <div className="card divide-y divide-slate-100">
        {items.length === 0 && (
          <EmptyState
            title={`Nenhuma intimação${pendentes ? " pendente" : ""}`}
            message="Captura automática diária às 06h30 (configure sua OAB no avatar)"
            icon={Inbox}
          />
        )}
        {items.map((c) => {
          const st = statusDe(c);
          const badge = PRAZO_BADGE[st];
          const local = prazos[c.id];
          const revisaoConcluida = st === "aceito" || st === "recusado";
          return (
            <div
              key={c.id}
              className="p-4 flex flex-wrap gap-3 items-start justify-between"
            >
              <div className="flex-1 min-w-[260px]">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="badge-navy">{c.tribunal || "—"}</span>
                  <span className="text-xs text-slate-500">
                    {c.tipo || "Comunicação"}
                  </span>
                  <span className="text-xs text-slate-400">
                    {c.data &&
                      new Date(c.data + "T12:00").toLocaleDateString("pt-BR")}
                  </span>
                  <Badge tone={badge.tone}>{badge.label}</Badge>
                </div>
                <div className="text-sm font-medium mt-1">
                  {c.numero_processo || "Processo não identificado"}
                </div>
                <p className="text-xs text-slate-500 mt-1 line-clamp-3">
                  {c.texto}
                </p>
                {st === "aceito" && (
                  <button
                    type="button"
                    className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary-600 hover:underline"
                    onClick={() => nav("/prazos")}
                  >
                    <CalendarClock size={12} />
                    {local?.deadlineId || c.prazo_deadline_id
                      ? "Ver prazo cadastrado"
                      : "Ver prazos"}
                  </button>
                )}
              </div>
              <div className="flex flex-col gap-2">
                <button
                  className="btn-ghost text-xs"
                  disabled={sugerindo === c.id}
                  onClick={() => revisarPrazo(c)}
                >
                  {sugerindo === c.id ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : revisaoConcluida ? (
                    <ExternalLink size={13} />
                  ) : (
                    <CalendarClock size={13} />
                  )}{" "}
                  Revisar prazo
                </button>
                {!c.processada && (
                  <button
                    className="btn-primary text-xs disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!revisaoConcluida}
                    title={
                      revisaoConcluida
                        ? "Marcar intimação como tratada"
                        : "Revise primeiro se a intimação gera prazo"
                    }
                    onClick={() => processar(c.id)}
                  >
                    <CheckCircle2 size={13} /> Tratada
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <Modal
        open={!!sugestao}
        onClose={fecharRevisao}
        title="Revisão de prazo"
        size="md"
        footer={
          <>
            <Button
              type="button"
              variant="secondary"
              icon={
                salvando === "recusar" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )
              }
              disabled={
                salvando !== null ||
                sugestaoAtual === "recusado" ||
                sugestaoAtual === "aceito"
              }
              onClick={recusarPrazo}
            >
              Não gera prazo
            </Button>
            <Button
              type="button"
              variant="primary"
              icon={
                salvando === "aceitar" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CalendarClock className="h-4 w-4" />
                )
              }
              disabled={salvando !== null || !podeAceitar}
              onClick={aceitarPrazo}
            >
              {sugestaoAtual === "aceito" ? "Prazo aceito" : "Cadastrar prazo"}
            </Button>
          </>
        }
      >
        {sugestao && (
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-slate-500">
                {sugestao.com.numero_processo || "Processo não identificado"}
              </span>
              <Badge tone={PRAZO_BADGE[sugestaoAtual].tone}>
                {PRAZO_BADGE[sugestaoAtual].label}
              </Badge>
            </div>

            {sugestao.dados.disponivel ? (
              <>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <div className="rounded-lg border border-black/[0.05] bg-slate-50 px-3 py-2">
                    <div className="text-[10px] font-bold uppercase text-slate-500">
                      Tipo detectado
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-900 capitalize">
                      {(sugestao.dados.tipo_detectado || "Prazo").replace(
                        /_/g,
                        " ",
                      )}
                    </div>
                  </div>
                  <div className="rounded-lg border border-black/[0.05] bg-slate-50 px-3 py-2">
                    <div className="text-[10px] font-bold uppercase text-slate-500">
                      Prazo
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-900">
                      {sugestao.dados.dias ?? "—"} dias
                    </div>
                  </div>
                  <div className="rounded-lg border border-black/[0.05] bg-slate-50 px-3 py-2">
                    <div className="text-[10px] font-bold uppercase text-slate-500">
                      Data sugerida
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-900">
                      {fmtDate(sugestao.dados.data_sugerida)}
                    </div>
                  </div>
                </div>

                {sugestao.dados.data_base && (
                  <div className="text-xs text-slate-500">
                    Termo inicial conferido:{" "}
                    <span className="font-medium text-slate-700">
                      {fmtDate(sugestao.dados.data_base)}
                    </span>
                  </div>
                )}

                {sugestao.dados.fundamentacao && (
                  <div className="card rounded-lg px-3 py-2 text-sm text-slate-700">
                    <span className="font-semibold text-slate-900">
                      Fundamentação:
                    </span>{" "}
                    {sugestao.dados.fundamentacao}
                  </div>
                )}

                <Alert
                  variant="warning"
                  title="Confira antes de aceitar o prazo"
                >
                  {sugestao.dados.aviso ||
                    "A contagem do prazo exige conferência da comunicação oficial e revisão do advogado responsável."}
                </Alert>
              </>
            ) : (
              <>
                <Alert variant="warning" title="Cálculo automático bloqueado">
                  {sugestao.dados.aviso ||
                    "Confira a publicação, o termo inicial, o regime processual e o calendário aplicável antes de informar o vencimento."}
                </Alert>

                {sugestao.dados.data_disponibilizacao && (
                  <div className="text-xs text-slate-500">
                    Disponibilização capturada (não usada como termo inicial):{" "}
                    <span className="font-medium text-slate-700">
                      {fmtDate(sugestao.dados.data_disponibilizacao)}
                    </span>
                  </div>
                )}

                {sugestaoAtual !== "aceito" && sugestaoAtual !== "recusado" && (
                  <label className="block">
                    <span className="mb-1 block text-xs font-semibold text-slate-700">
                      Vencimento conferido manualmente
                    </span>
                    <input
                      type="date"
                      className="input w-full"
                      value={dataManual}
                      onChange={(event) => setDataManual(event.target.value)}
                    />
                    <span className="mt-1 block text-xs text-slate-500">
                      Informe somente após conferir a comunicação oficial. O EJC
                      não calcula esta data a partir da disponibilização.
                    </span>
                  </label>
                )}
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
