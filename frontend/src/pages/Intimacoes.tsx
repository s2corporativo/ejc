import { useEffect, useState } from "react";
import {
  Inbox,
  RefreshCw,
  CheckCircle2,
  ExternalLink,
  Loader2,
  CalendarClock,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import api from "../lib/api";
import { PageHeader, Modal, Alert, Button, fmtDate } from "../components/UI";
import { toast } from "../components/Toast";

interface SugestaoPrazo {
  tipo_detectado: string;
  dias: number;
  data_sugerida: string;
  fundamentacao?: string | null;
  aviso?: string | null;
}

interface StatusCaptura {
  executado_em: string | null;
  sucesso: boolean | null;
  intimacoes_encontradas: number | null;
  erro: string | null;
}

export default function Intimacoes() {
  const nav = useNavigate();
  const [items, setItems] = useState<any[]>([]);
  const [pendentes, setPendentes] = useState(true);
  const [loading, setLoading] = useState(false);
  const [sugerindo, setSugerindo] = useState<string | null>(null);
  const [sugestao, setSugestao] = useState<{
    com: any;
    dados: SugestaoPrazo;
  } | null>(null);
  const [status, setStatus] = useState<StatusCaptura | null>(null);

  const load = () =>
    api
      .get(`/intimacoes/?apenas_pendentes=${pendentes}`)
      .then((r) => setItems(r.data.data));

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

  const capturar = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/intimacoes/capturar-agora");
      toast.success(data.detail);
      load();
      loadStatus();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Configure sua OAB no menu do avatar");
    } finally {
      setLoading(false);
    }
  };

  const processar = async (id: string) => {
    await api.post(`/intimacoes/${id}/processar`);
    load();
  };

  const irParaNovoPrazo = (com: any) =>
    nav(`/prazos?novo=1&processo=${com.numero_processo || ""}`);

  const criarPrazo = async (com: any) => {
    setSugerindo(com.id);
    try {
      const { data } = await api.post<SugestaoPrazo>(
        `/intimacoes/${com.id}/sugerir-prazo`,
      );
      setSugestao({ com, dados: data });
    } catch {
      // Sem sugestão disponível — cai no fluxo manual atual
      toast.info("Sugestão indisponível — preencha o prazo manualmente.");
      irParaNovoPrazo(com);
    } finally {
      setSugerindo(null);
    }
  };

  const usarSugestao = async () => {
    if (!sugestao) return;
    const { com, dados } = sugestao;
    const resumo = [
      `Título: ${dados.tipo_detectado} — ${com.numero_processo || "processo não identificado"}`,
      `Prazo: ${dados.dias} dias`,
      `Data sugerida: ${fmtDate(dados.data_sugerida)}`,
      dados.fundamentacao ? `Fundamentação: ${dados.fundamentacao}` : null,
    ]
      .filter(Boolean)
      .join("\n");
    try {
      await navigator.clipboard.writeText(resumo);
      toast.info(
        "Sugestão copiada — a tela de Prazos ainda não pré-preenche o formulário; cole os dados no novo prazo.",
      );
    } catch {
      toast.error("Não foi possível copiar a sugestão. Anote os dados antes de continuar.");
    }
    setSugestao(null);
    irParaNovoPrazo(com);
  };

  const preencherManual = () => {
    if (!sugestao) return;
    const { com } = sugestao;
    setSugestao(null);
    irParaNovoPrazo(com);
  };

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
            <button className="btn-primary" disabled={loading} onClick={capturar}>
              <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
              Capturar agora
            </button>
          </div>
        }
      />

      {/* Status da última captura automática (DJEN) */}
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
        <button
          className="btn-ghost"
          disabled={loading}
          onClick={capturar}
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Capturar agora
        </button>
      </div>

      <div className="card divide-y divide-slate-100">
        {items.length === 0 && (
          <div className="p-10 text-center text-slate-400">
            <Inbox className="mx-auto mb-2" />
            Nenhuma intimação {pendentes ? "pendente" : ""}
            <p className="text-xs mt-2">
              Captura automática diária às 06h30 (configure sua OAB no avatar)
            </p>
          </div>
        )}
        {items.map((c) => (
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
              </div>
              <div className="text-sm font-medium mt-1">
                {c.numero_processo || "Processo não identificado"}
              </div>
              <p className="text-xs text-slate-500 mt-1 line-clamp-3">
                {c.texto}
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <button
                className="btn-ghost text-xs"
                disabled={sugerindo === c.id}
                onClick={() => criarPrazo(c)}
              >
                {sugerindo === c.id ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <ExternalLink size={13} />
                )}{" "}
                Criar prazo
              </button>
              {!c.processada && (
                <button
                  className="btn-primary text-xs"
                  onClick={() => processar(c.id)}
                >
                  <CheckCircle2 size={13} /> Tratada
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Sugestão de prazo (IA/heurística do backend) */}
      <Modal
        open={!!sugestao}
        onClose={() => setSugestao(null)}
        title="Sugestão de prazo"
        size="md"
        footer={
          <>
            <Button type="button" variant="secondary" onClick={preencherManual}>
              Preencher manualmente
            </Button>
            <Button
              type="button"
              variant="primary"
              icon={<CalendarClock className="h-4 w-4" />}
              onClick={usarSugestao}
            >
              Usar sugestão
            </Button>
          </>
        }
      >
        {sugestao && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="text-[10px] font-bold uppercase text-slate-500">
                  Tipo detectado
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-900 capitalize">
                  {sugestao.dados.tipo_detectado.replace(/_/g, " ")}
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="text-[10px] font-bold uppercase text-slate-500">
                  Prazo
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-900">
                  {sugestao.dados.dias} dias
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <div className="text-[10px] font-bold uppercase text-slate-500">
                  Data sugerida
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-900">
                  {fmtDate(sugestao.dados.data_sugerida)}
                </div>
              </div>
            </div>

            {sugestao.dados.fundamentacao && (
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
                <span className="font-semibold text-slate-900">
                  Fundamentação:
                </span>{" "}
                {sugestao.dados.fundamentacao}
              </div>
            )}

            <Alert variant="warning" title="Confira antes de criar o prazo">
              {sugestao.dados.aviso ||
                "Sugestão automática — a contagem do prazo é de responsabilidade do advogado. Confira a intimação e a base legal."}
            </Alert>
          </div>
        )}
      </Modal>
    </div>
  );
}
