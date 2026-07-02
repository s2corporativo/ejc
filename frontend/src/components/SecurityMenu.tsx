// ── Menu do avatar: segurança e preferências do usuário ──
import { useState } from "react";
import { toast } from "./Toast";
import { useNavigate } from "react-router-dom";
import {
  BellRing,
  KeyRound,
  Gavel,
  ChevronDown,
  CalendarPlus,
} from "lucide-react";
import api from "../lib/api";

export default function SecurityMenu({ user }: { user: any }) {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState<"oab" | null>(null);

  // OAB DJEN
  const [oabNum, setOabNum] = useState("");
  const [oabUf, setOabUf] = useState("MG");

  const ativarPush = async () => {
    try {
      const { data } = await api.get("/notifications/push/vapid-key");
      if (!data.enabled) {
        toast.error("Push não configurado no servidor (.env VAPID)");
        return;
      }
      const perm = await Notification.requestPermission();
      if (perm !== "granted") return;
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: data.public_key,
      });
      const j = sub.toJSON() as any;
      await api.post("/notifications/push/subscribe", {
        endpoint: j.endpoint,
        p256dh: j.keys.p256dh,
        auth: j.keys.auth,
      });
      toast.success("📱 Alertas no celular ativados!");
    } catch {
      toast.error("Falha ao ativar push");
    }
  };

  const salvarOab = async () => {
    await api.patch(`/users/${user.id}`, {
      djen_oab_numero: oabNum,
      djen_oab_uf: oabUf,
    });
    setModal(null);
    toast.success("OAB salva — intimações DJEN serão capturadas diariamente às 06h30.");
  };

  const copiarIcs = async () => {
    const { data } = await api
      .get("/users/me/calendar-url")
      .catch(() => ({ data: null }));
    const url =
      data?.url ||
      `${window.location.origin}/api/calendar/${user.id}/TOKEN.ics`;
    navigator.clipboard.writeText(url);
    toast.success(
      "URL do calendário copiada!\nGoogle Agenda → Adicionar agenda → Por URL.",
    );
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2"
      >
        <div className="w-8 h-8 rounded-full bg-navy text-gold flex items-center justify-center text-sm font-bold">
          {user?.full_name?.[0] || "U"}
        </div>
        <div className="hidden sm:block text-left">
          <div className="text-sm font-medium leading-tight">
            {user?.full_name}
          </div>
          <div className="text-[11px] text-slate-400 capitalize">
            {user?.role}
          </div>
        </div>
        <ChevronDown size={14} className="text-slate-400" />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-64 card z-50 py-1">
          <button
            className="menu-item"
            onClick={() => {
              ativarPush();
              setOpen(false);
            }}
          >
            <BellRing size={15} /> Alertas no celular (push)
          </button>
          <button
            className="menu-item"
            onClick={() => {
              setModal("oab");
              setOpen(false);
            }}
          >
            <Gavel size={15} /> Minha OAB (intimações DJEN)
          </button>
          <button
            className="menu-item"
            onClick={() => {
              copiarIcs();
              setOpen(false);
            }}
          >
            <CalendarPlus size={15} /> Calendário (Google/Outlook)
          </button>
          <button
            className="menu-item"
            onClick={() => {
              nav("/trocar-senha");
              setOpen(false);
            }}
          >
            <KeyRound size={15} /> Trocar senha
          </button>
        </div>
      )}

      {/* Modal OAB */}
      {modal === "oab" && (
        <div className="modal-backdrop" onClick={() => setModal(null)}>
          <div
            className="card p-6 w-full max-w-sm"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold text-navy mb-1">
              ⚖️ Captura de intimações
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              O sistema consulta o DJEN diariamente (06h30) pela sua OAB.
            </p>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="Número (só dígitos)"
                value={oabNum}
                onChange={(e) => setOabNum(e.target.value.replace(/\D/g, ""))}
              />
              <select
                className="input w-20"
                value={oabUf}
                onChange={(e) => setOabUf(e.target.value)}
              >
                {[
                  "MG",
                  "SP",
                  "RJ",
                  "ES",
                  "BA",
                  "DF",
                  "GO",
                  "PR",
                  "RS",
                  "SC",
                ].map((u) => (
                  <option key={u}>{u}</option>
                ))}
              </select>
            </div>
            <button
              className="btn-primary w-full justify-center mt-4"
              onClick={salvarOab}
            >
              Salvar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
