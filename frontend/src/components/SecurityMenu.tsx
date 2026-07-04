// ── Menu do avatar: foto de perfil, segurança e preferências ──
import { useRef, useState } from "react";
import { toast } from "./Toast";
import { useNavigate } from "react-router-dom";
import {
  BellRing,
  Camera,
  KeyRound,
  Gavel,
  ChevronDown,
  CalendarPlus,
  LogOut,
  Trash2,
} from "lucide-react";
import api, { logout } from "../lib/api";
import { useAuth } from "../stores/auth";
import UserAvatar from "./UserAvatar";

export default function SecurityMenu({ user }: { user: any }) {
  const nav = useNavigate();
  const { updateUser } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState<"oab" | null>(null);

  // Foto de perfil — POST /users/me/avatar (multipart `file`)
  const trocarFoto = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post("/users/me/avatar", form);
      // cache-buster: força o UserAvatar a rebuscar o blob
      const url = data?.avatar_url
        ? `${data.avatar_url}?v=${Date.now()}`
        : null;
      updateUser({ avatar_url: url });
      toast.success("Foto de perfil atualizada!");
    } catch (e: any) {
      const st = e?.response?.status;
      toast.error(
        st === 413
          ? "Imagem grande demais (máx. 2MB)"
          : st === 415
            ? "Formato inválido — use JPG, PNG ou WebP"
            : "Falha ao enviar a foto",
      );
    }
  };

  const removerFoto = async () => {
    try {
      await api.delete("/users/me/avatar");
      updateUser({ avatar_url: null });
      toast.success("Foto removida");
    } catch {
      toast.error("Falha ao remover a foto");
    }
  };

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
        className="flex items-center gap-2 rounded-xl px-1 py-0.5 transition-colors hover:bg-slate-50"
      >
        <UserAvatar user={user} size="md" />
        <div className="hidden sm:block text-left">
          <div className="text-sm font-medium leading-tight text-slate-900">
            {user?.full_name}
          </div>
          <div className="text-[11px] text-slate-400 capitalize">
            {user?.role}
          </div>
        </div>
        <ChevronDown size={14} className="text-slate-400" />
      </button>

      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) trocarFoto(f);
          e.target.value = "";
        }}
      />

      {open && (
        <div className="absolute right-0 mt-2 w-64 card z-50 py-1">
          <button
            className="menu-item"
            onClick={() => {
              fileRef.current?.click();
              setOpen(false);
            }}
          >
            <Camera size={15} /> Trocar foto de perfil
          </button>
          {user?.avatar_url && (
            <button
              className="menu-item"
              onClick={() => {
                removerFoto();
                setOpen(false);
              }}
            >
              <Trash2 size={15} /> Remover foto
            </button>
          )}
          <div className="my-1 border-t border-slate-100" />
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
          <div className="my-1 border-t border-slate-100" />
          <button
            className="menu-item hover:!bg-danger-50 hover:!text-danger-600"
            onClick={() => {
              setOpen(false);
              logout();
            }}
          >
            <LogOut size={15} /> Sair
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
