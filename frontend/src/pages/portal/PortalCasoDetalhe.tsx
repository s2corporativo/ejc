import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, CalendarClock, MessageSquare } from "lucide-react";
import api from "../../lib/api";
import { toast } from "../../components/Toast";
import { Spinner } from "../../components/UI";
import { asList } from "../../lib/list";

function MensagensCliente({ caseId }: { caseId: string }) {
  const [msgs, setMsgs] = useState<any[]>([]);
  const [txt, setTxt] = useState("");
  const [sending, setSending] = useState(false);
  const carregar = () =>
    api
      .get(`/portal/casos/${caseId}/mensagens`)
      .then((r) => setMsgs(asList(r.data)))
      .catch(() => {});
  useEffect(() => {
    carregar();
  }, [caseId]);
  const enviar = async () => {
    if (!txt.trim()) return;
    setSending(true);
    try {
      await api.post(`/portal/casos/${caseId}/mensagens`, { mensagem: txt });
      setTxt("");
      carregar();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail ||
          "Não foi possível enviar a mensagem. Tente novamente.",
      );
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="card p-5 mt-4">
      <h2 className="font-medium text-navy mb-3 flex items-center gap-2">
        <MessageSquare size={16} /> Mensagens com o escritório
      </h2>
      <div className="max-h-80 overflow-auto space-y-2 mb-3">
        {msgs.map((m) => (
          <div
            key={m.id}
            className={`flex ${m.autor_tipo === "cliente" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[78%] rounded-lg px-3 py-2 text-sm ${m.autor_tipo === "cliente" ? "bg-navy text-white" : "bg-slate-100 text-slate-800"}`}
            >
              <p className="whitespace-pre-wrap">{m.mensagem}</p>
              <p
                className={`text-[10px] mt-1 ${m.autor_tipo === "cliente" ? "text-slate-200" : "text-slate-400"}`}
              >
                {m.autor_tipo === "cliente"
                  ? "Você"
                  : m.autor_nome || "Escritório"}{" "}
                ·{" "}
                {m.created_at
                  ? new Date(m.created_at).toLocaleDateString("pt-BR")
                  : ""}
              </p>
            </div>
          </div>
        ))}
        {msgs.length === 0 && (
          <p className="text-center text-slate-400 text-sm py-6">
            Nenhuma mensagem ainda. Envie uma dúvida ao escritório.
          </p>
        )}
      </div>
      <div className="flex gap-2">
        <input
          value={txt}
          onChange={(e) => setTxt(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && enviar()}
          placeholder="Escreva sua mensagem…"
          maxLength={4000}
          className="input flex-1"
        />
        <button
          onClick={enviar}
          disabled={sending || !txt.trim()}
          className="btn-primary text-sm"
        >
          Enviar
        </button>
      </div>
    </div>
  );
}

export default function PortalCasoDetalhe() {
  const { id } = useParams();
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api.get(`/portal/casos/${id}`).then((r) => setData(r.data));
  }, [id]);

  if (!data) return <Spinner />;
  const { caso, andamentos, proximas_datas } = data;

  return (
    <div>
      <Link
        to="/portal"
        className="text-sm text-navy flex items-center gap-1 mb-3"
      >
        <ArrowLeft size={15} /> Voltar
      </Link>
      <div className="card p-5 mb-4">
        <h1 className="text-lg font-semibold text-navy">{caso.titulo}</h1>
        <div className="text-sm text-slate-500 mt-1">
          {caso.numero_processo || caso.numero_interno}
          {caso.comarca && ` · ${caso.comarca}`}
          {caso.vara && ` · ${caso.vara}`}
        </div>
      </div>

      {Array.isArray(proximas_datas) && proximas_datas.length > 0 && (
        <div className="card p-5 mb-4">
          <h2 className="font-medium text-navy mb-3 flex items-center gap-2">
            <CalendarClock size={16} /> Próximas datas
          </h2>
          {(Array.isArray(proximas_datas) ? proximas_datas : []).map((d: any, i: number) => (
            <div
              key={i}
              className="flex justify-between py-2 border-b border-slate-100 last:border-0 text-sm"
            >
              <span>{d.titulo}</span>
              <span className="font-medium">
                {new Date(d.data + "T12:00").toLocaleDateString("pt-BR")}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="card p-5">
        <h2 className="font-medium text-navy mb-3">Andamentos</h2>
        <div className="space-y-3">
          {(!Array.isArray(andamentos) || andamentos.length === 0) && (
            <p className="text-sm text-slate-400">Sem andamentos registrados</p>
          )}
          {(Array.isArray(andamentos) ? andamentos : []).map((m: any, i: number) => (
            <div key={i} className="flex gap-3 text-sm">
              <div className="w-2 h-2 rounded-full bg-gold mt-1.5 shrink-0" />
              <div>
                <div className="text-xs text-slate-400">
                  {m.data && new Date(m.data).toLocaleDateString("pt-BR")}
                </div>
                <div>{m.descricao}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <MensagensCliente caseId={id!} />
    </div>
  );
}
