import { useState, useEffect, useCallback, useRef } from "react";
import {
  MessageCircle, Send, RefreshCw, Wifi, WifiOff, QrCode,
  Phone, User, Clock, Check, CheckCheck
} from "lucide-react";
import api from "../lib/api";

interface Chat {
  id: string;
  name?: string;
  phone?: string;
  lastMessage?: string;
  lastMessageTime?: number;
  unreadCount?: number;
}

interface Message {
  key: { fromMe: boolean; id: string };
  message?: { conversation?: string; extendedTextMessage?: { text: string } };
  messageTimestamp: number;
  status?: string;
}

function getMessageText(msg: Message): string {
  return msg.message?.conversation
    || msg.message?.extendedTextMessage?.text
    || "";
}

function fmtPhone(jid: string): string {
  return (jid || "").replace("@s.whatsapp.net", "").replace("@g.us", "");
}

function fmtTime(ts: number): string {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function fmtDate(ts: number): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString("pt-BR");
}

export default function WhatsApp() {
  const [status, setStatus] = useState<string>("loading");
  const [qrcode, setQrcode] = useState<string | null>(null);
  const [chats, setChats] = useState<Chat[]>([]);
  const [selectedChat, setSelectedChat] = useState<Chat | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newMsg, setNewMsg] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingChats, setLoadingChats] = useState(false);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [searchPhone, setSearchPhone] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const checkStatus = useCallback(async () => {
    try {
      const res = await api.get("/v1/whatsapp/status");
      const state = res.data?.instance?.state ?? res.data?.state ?? "unknown";
      setStatus(state);
      if (state === "open") {
        setQrcode(null);
      }
    } catch { setStatus("error"); }
  }, []);

  const loadQR = async () => {
    try {
      const res = await api.get("/v1/whatsapp/qrcode");
      const qr = res.data?.base64 ?? res.data?.qrcode?.base64 ?? null;
      if (qr) setQrcode(qr);
    } catch {}
  };

  const loadChats = useCallback(async () => {
    if (status !== "open") return;
    setLoadingChats(true);
    try {
      const res = await api.get("/v1/whatsapp/chats");
      const data = Array.isArray(res.data) ? res.data : res.data?.chats ?? [];
      setChats(data.slice(0, 50));
    } catch { setChats([]); }
    finally { setLoadingChats(false); }
  }, [status]);

  const loadMessages = useCallback(async (chat: Chat) => {
    setLoadingMsgs(true);
    setMessages([]);
    const phone = fmtPhone(chat.id);
    try {
      const res = await api.post("/v1/whatsapp/messages", { phone, limit: 40 });
      const msgs = Array.isArray(res.data) ? res.data : res.data?.messages ?? [];
      setMessages(msgs.sort((a: Message, b: Message) => a.messageTimestamp - b.messageTimestamp));
    } catch { setMessages([]); }
    finally { setLoadingMsgs(false); }
  }, []);

  const sendMessage = async () => {
    if (!newMsg.trim() || !selectedChat) return;
    setSending(true);
    const phone = fmtPhone(selectedChat.id);
    try {
      await api.post("/v1/whatsapp/send", { phone, message: newMsg });
      setNewMsg("");
      setTimeout(() => loadMessages(selectedChat), 1000);
    } catch {} finally { setSending(false); }
  };

  const openNewChat = async () => {
    if (!searchPhone.trim()) return;
    const phone = searchPhone.replace(/\D/g, "");
    const chat: Chat = { id: phone + "@s.whatsapp.net", name: phone, phone };
    setSelectedChat(chat);
    setSearchPhone("");
    await loadMessages(chat);
  };

  useEffect(() => { checkStatus(); }, [checkStatus]);
  useEffect(() => { if (status === "open") loadChats(); }, [status, loadChats]);
  useEffect(() => { if (selectedChat) loadMessages(selectedChat); }, [selectedChat, loadMessages]);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Poll status every 8s when not connected
  useEffect(() => {
    if (status === "open") return;
    const t = setInterval(checkStatus, 8000);
    return () => clearInterval(t);
  }, [status, checkStatus]);

  const connected = status === "open";

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 pt-5 pb-3 flex items-center justify-between flex-shrink-0 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${connected ? "bg-emerald-500" : "bg-slate-300"}`} />
          <h1 className="text-lg font-bold text-slate-800">WhatsApp</h1>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            connected ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"
          }`}>
            {connected ? "Conectado" : status === "loading" ? "Verificando..." : "Desconectado"}
          </span>
        </div>
        <div className="flex gap-2">
          {!connected && (
            <button onClick={loadQR}
              className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-sm hover:bg-slate-50">
              <QrCode className="w-4 h-4" /> Conectar
            </button>
          )}
          <button onClick={() => { checkStatus(); loadChats(); }}
            className="p-2 border border-slate-200 rounded-lg hover:bg-slate-50">
            <RefreshCw className="w-4 h-4 text-slate-400" />
          </button>
        </div>
      </div>

      {!connected ? (
        /* Not connected view */
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-sm">
            {qrcode ? (
              <div>
                <p className="text-slate-600 mb-4 font-medium">Escaneie o QR Code com o WhatsApp</p>
                <img src={`data:image/png;base64,${qrcode}`}
                  className="w-64 h-64 mx-auto rounded-xl border border-slate-200 shadow-sm"
                  alt="QR Code WhatsApp" />
                <p className="text-xs text-slate-400 mt-3">
                  WhatsApp &gt; Dispositivos conectados &gt; Conectar dispositivo
                </p>
              </div>
            ) : (
              <div>
                <WifiOff className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <p className="text-slate-500 text-sm mb-4">WhatsApp não conectado</p>
                <button onClick={loadQR}
                  className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 text-sm mx-auto">
                  <QrCode className="w-4 h-4" /> Gerar QR Code
                </button>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Connected view */
        <div className="flex flex-1 overflow-hidden">
          {/* Chat list */}
          <div className="w-72 flex-shrink-0 border-r border-slate-200 flex flex-col overflow-hidden">
            {/* New chat search */}
            <div className="p-3 border-b border-slate-100">
              <div className="flex gap-2">
                <input
                  type="tel" placeholder="Número (ex: 31999999999)"
                  className="flex-1 text-xs border border-slate-200 rounded-lg px-3 py-1.5"
                  value={searchPhone}
                  onChange={e => setSearchPhone(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && openNewChat()}
                />
                <button onClick={openNewChat}
                  className="p-1.5 bg-green-500 text-white rounded-lg hover:bg-green-600">
                  <MessageCircle className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            {/* Chats */}
            <div className="flex-1 overflow-y-auto">
              {loadingChats ? (
                <div className="flex items-center justify-center py-8 text-slate-400 text-sm">Carregando...</div>
              ) : chats.length === 0 ? (
                <div className="flex items-center justify-center py-8 text-slate-300 text-sm">
                  Sem conversas recentes
                </div>
              ) : (
                chats.map(chat => (
                  <div key={chat.id}
                    onClick={() => setSelectedChat(chat)}
                    className={`flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-slate-50 border-b border-slate-50 ${
                      selectedChat?.id === chat.id ? "bg-slate-100" : ""
                    }`}>
                    <div className="w-9 h-9 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0">
                      <User className="w-4 h-4 text-green-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">
                        {chat.name || fmtPhone(chat.id)}
                      </p>
                      {chat.lastMessage && (
                        <p className="text-xs text-slate-400 truncate mt-0.5">{chat.lastMessage}</p>
                      )}
                    </div>
                    {chat.unreadCount && chat.unreadCount > 0 ? (
                      <span className="text-[10px] bg-green-500 text-white rounded-full w-5 h-5 flex items-center justify-center flex-shrink-0">
                        {chat.unreadCount}
                      </span>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Message area */}
          <div className="flex-1 flex flex-col overflow-hidden bg-slate-50">
            {selectedChat ? (
              <>
                {/* Chat header */}
                <div className="px-4 py-3 bg-white border-b border-slate-200 flex items-center gap-3">
                  <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
                    <User className="w-4 h-4 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">
                      {selectedChat.name || fmtPhone(selectedChat.id)}
                    </p>
                    <p className="text-xs text-slate-400">{fmtPhone(selectedChat.id)}</p>
                  </div>
                  <a href={`tel:+${fmtPhone(selectedChat.id)}`}
                    className="ml-auto p-2 hover:bg-slate-100 rounded-lg">
                    <Phone className="w-4 h-4 text-slate-400" />
                  </a>
                </div>

                {/* Messages */}
                <div className="flex-1 overflow-y-auto p-4 space-y-2">
                  {loadingMsgs ? (
                    <div className="text-center text-slate-400 text-sm py-8">Carregando mensagens...</div>
                  ) : messages.length === 0 ? (
                    <div className="text-center text-slate-300 text-sm py-8">Sem mensagens</div>
                  ) : (
                    <>
                      {messages.map((msg, i) => {
                        const text = getMessageText(msg);
                        if (!text) return null;
                        const fromMe = msg.key.fromMe;
                        const showDate = i === 0 || fmtDate(msg.messageTimestamp) !== fmtDate(messages[i-1].messageTimestamp);
                        return (
                          <div key={msg.key.id}>
                            {showDate && (
                              <div className="text-center text-xs text-slate-400 my-3">
                                {fmtDate(msg.messageTimestamp)}
                              </div>
                            )}
                            <div className={`flex ${fromMe ? "justify-end" : "justify-start"}`}>
                              <div className={`max-w-[70%] px-3 py-2 rounded-2xl text-sm ${
                                fromMe
                                  ? "bg-green-500 text-white rounded-br-sm"
                                  : "bg-white text-slate-800 border border-slate-200 rounded-bl-sm"
                              }`}>
                                <p className="leading-relaxed">{text}</p>
                                <div className={`flex items-center gap-1 mt-0.5 ${fromMe ? "justify-end" : ""}`}>
                                  <span className={`text-[10px] ${fromMe ? "text-green-100" : "text-slate-400"}`}>
                                    {fmtTime(msg.messageTimestamp)}
                                  </span>
                                  {fromMe && <CheckCheck className="w-3 h-3 text-green-100" />}
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                      <div ref={messagesEndRef} />
                    </>
                  )}
                </div>

                {/* Input */}
                <div className="px-4 py-3 bg-white border-t border-slate-200 flex gap-3">
                  <input
                    type="text"
                    placeholder="Digite uma mensagem..."
                    className="flex-1 border border-slate-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-300"
                    value={newMsg}
                    onChange={e => setNewMsg(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendMessage()}
                  />
                  <button onClick={sendMessage} disabled={!newMsg.trim() || sending}
                    className="p-2.5 bg-green-500 text-white rounded-xl hover:bg-green-600 disabled:opacity-50 transition-colors">
                    {sending
                      ? <RefreshCw className="w-4 h-4 animate-spin" />
                      : <Send className="w-4 h-4" />
                    }
                  </button>
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center">
                  <MessageCircle className="w-12 h-12 text-slate-200 mx-auto mb-3" />
                  <p className="text-slate-400 text-sm">Selecione uma conversa ou inicie uma nova</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
