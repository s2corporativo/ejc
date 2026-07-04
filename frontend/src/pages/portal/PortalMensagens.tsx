import { useEffect, useState, useRef, useCallback } from "react";
import { Send, MessageCircle, RefreshCw } from "lucide-react";
import api from "../../lib/api";

interface Mensagem {
  id: string;
  autor_tipo: "cliente" | "escritorio";
  autor_nome: string;
  mensagem: string;
  lida: boolean;
  created_at: string;
}

interface Caso {
  id: string;
  titulo: string;
  numero_processo?: string;
}

function fmtTime(d: string) {
  return new Date(d).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function PortalMensagens() {
  const [casos, setCasos] = useState<Caso[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Mensagem[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get("/portal/meus-casos").then((r) => {
      const cs = r.data?.data ?? [];
      setCasos(cs);
      if (cs.length > 0) setSelectedId(cs[0].id);
    });
  }, []);

  const loadMsgs = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const r = await api.get(`/portal/casos/${selectedId}/mensagens`);
      setMsgs(r.data ?? []);
    } catch {
      setMsgs([]);
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    loadMsgs();
  }, [loadMsgs]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const send = async () => {
    if (!text.trim() || !selectedId || sending) return;
    setSending(true);
    try {
      await api.post(`/portal/casos/${selectedId}/mensagens`, {
        mensagem: text,
      });
      setText("");
      await loadMsgs();
    } finally {
      setSending(false);
    }
  };

  const caso = casos.find((c) => c.id === selectedId);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-slate-800">Mensagens</h1>

      {casos.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-10 text-center">
          <MessageCircle className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-400 text-sm">
            Nenhum processo ativo para enviar mensagens
          </p>
        </div>
      ) : (
        <>
          {/* Case selector */}
          {casos.length > 1 && (
            <select
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white"
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {casos.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.titulo}
                </option>
              ))}
            </select>
          )}

          <div
            className="bg-white rounded-xl border border-slate-200 flex flex-col"
            style={{ minHeight: 400, maxHeight: 500 }}
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-800 truncate">
                {caso?.titulo ?? "Mensagens"}
              </p>
              <button
                onClick={loadMsgs}
                className="p-1 hover:bg-slate-50 rounded"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 text-slate-400 ${loading ? "animate-spin" : ""}`}
                />
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {msgs.length === 0 ? (
                <div className="text-center py-10 text-slate-400 text-sm">
                  Sem mensagens ainda. Envie uma mensagem ao escritório.
                </div>
              ) : (
                msgs.map((m) => (
                  <div
                    key={m.id}
                    className={`flex ${m.autor_tipo === "cliente" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[80%] px-3 py-2 rounded-xl text-sm ${
                        m.autor_tipo === "cliente"
                          ? "bg-primary-600 text-white rounded-br-sm"
                          : "bg-slate-100 text-slate-800 rounded-bl-sm"
                      }`}
                    >
                      {m.autor_tipo === "escritorio" && (
                        <p className="text-[10px] font-semibold opacity-60 mb-0.5">
                          {m.autor_nome}
                        </p>
                      )}
                      <p className="leading-relaxed">{m.mensagem}</p>
                      <p
                        className={`text-[10px] mt-1 ${m.autor_tipo === "cliente" ? "text-primary-200" : "text-slate-400"}`}
                      >
                        {fmtTime(m.created_at)}
                      </p>
                    </div>
                  </div>
                ))
              )}
              <div ref={endRef} />
            </div>

            {/* Input */}
            <div className="px-4 py-3 border-t border-slate-100 flex gap-2">
              <input
                type="text"
                placeholder="Digite sua mensagem..."
                className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
                maxLength={4000}
              />
              <button
                onClick={send}
                disabled={!text.trim() || sending}
                className="btn-primary p-2.5 rounded-xl"
              >
                {sending ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
