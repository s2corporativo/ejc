import { useEffect, useState } from "react";
import { Inbox, RefreshCw, CheckCircle2, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";

export default function Intimacoes() {
  const nav = useNavigate();
  const [items, setItems] = useState<any[]>([]);
  const [pendentes, setPendentes] = useState(true);
  const [loading, setLoading] = useState(false);

  const load = () =>
    api
      .get(`/intimacoes/?apenas_pendentes=${pendentes}`)
      .then((r) => setItems(r.data.data));
  useEffect(() => {
    load();
  }, [pendentes]);

  const capturar = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/intimacoes/capturar-agora");
      alert(data.detail);
      load();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Configure sua OAB no menu do avatar");
    } finally {
      setLoading(false);
    }
  };

  const processar = async (id: string) => {
    await api.post(`/intimacoes/${id}/processar`);
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <h1 className="page-title">📨 Intimações DJEN</h1>
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
                onClick={() =>
                  nav(`/prazos?novo=1&processo=${c.numero_processo || ""}`)
                }
              >
                <ExternalLink size={13} /> Criar prazo
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
    </div>
  );
}
