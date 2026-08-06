// ── Menu do avatar: foto de perfil, segurança e preferências ──
import { useRef, useState } from "react";
import { toast } from "./Toast";
import { useNavigate } from "react-router";
import {
  BellRing,
  Camera,
  KeyRound,
  Gavel,
  ChevronDown,
  CalendarPlus,
  RotateCcw,
  LogOut,
  Monitor,
  Moon,
  Sun,
  Trash2,
} from "lucide-react";
import api, { logout } from "../lib/api";
import { useAuth } from "../stores/auth";
import { THEME_LABELS, useThemeStore, type ThemeMode } from "../stores/theme";
import UserAvatar from "./UserAvatar";
import { statusErro } from "../utils/erro";

const THEME_OPTIONS: Array<{
  mode: ThemeMode;
  icon: typeof Sun;
}> = [
  { mode: "light", icon: Sun },
  { mode: "dark", icon: Moon },
  { mode: "system", icon: Monitor },
];

export default function SecurityMenu({ user }: { user: any }) {
  const nav = useNavigate();
  const { updateUser } = useAuth();
  const { theme, setTheme } = useThemeStore();
  const fileRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState<"oab" | null>(null);

  const trocarFoto = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post("/users/me/avatar", form);
      const url = data?.avatar_url
        ? `${data.avatar_url}?v=${Date.now()}`
        : null;
      updateUser({ avatar_url: url });
      toast.success("Foto de perfil atualizada!");
    } catch (e: unknown) {
      const status = statusErro(e);
      toast.error(
        status === 413
          ? "Imagem grande demais (máx. 2MB)"
          : status === 415
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

  const [oabNum, setOabNum] = useState("");
  const [oabUf, setOabUf] = useState("MG");

  const ativarPush = async () => {
    try {
      const { data } = await api.get("/notifications/push/vapid-key");
      if (!data.enabled) {
        toast.error("Push não configurado no servidor");
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted") return;
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: data.public_key,
      });
      const serialized = subscription.toJSON() as any;
      await api.post("/notifications/push/subscribe", {
        endpoint: serialized.endpoint,
        p256dh: serialized.keys.p256dh,
        auth: serialized.keys.auth,
      });
      toast.success("Alertas no celular ativados!");
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
    toast.success(
      "OAB salva — intimações DJEN serão capturadas diariamente às 06h30.",
    );
  };

  const copiarIcs = async () => {
    try {
      const { data } = await api.get("/calendar/me/url");
      if (!data?.url) {
        toast.error("Feed de calendário indisponível para esta conta.");
        return;
      }
      await navigator.clipboard.writeText(data.url);
      toast.success(
        "URL do calendário copiada. Adicione-a por URL no Google Agenda, Outlook ou Apple Calendar.",
      );
    } catch {
      toast.error("Não foi possível gerar o link do calendário.");
    }
  };

  const rotacionarIcs = async () => {
    try {
      const { data } = await api.post("/calendar/me/rotate");
      if (!data?.url) {
        toast.error("O novo link do calendário não foi retornado.");
        return;
      }
      await navigator.clipboard.writeText(data.url);
      toast.success(
        "Link anterior revogado. O novo link foi copiado para a área de transferência.",
      );
    } catch {
      toast.error("Não foi possível revogar o link do calendário.");
    }
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

      {/* Input oculto acionado apenas pelo item "Trocar foto de perfil".
          aria-hidden + tabIndex=-1 tiram-no do fluxo de foco/acessibilidade:
          por ser o primeiro input do DOM, automação e leitores de tela
          podiam atingi-lo por engano (achado A11y da auditoria). */}
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        aria-hidden="true"
        tabIndex={-1}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) trocarFoto(file);
          event.target.value = "";
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
              void copiarIcs();
              setOpen(false);
            }}
          >
            <CalendarPlus size={15} /> Copiar link do calendário
          </button>
          <button
            className="menu-item"
            onClick={() => {
              void rotacionarIcs();
              setOpen(false);
            }}
          >
            <RotateCcw size={15} /> Revogar e gerar novo link
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
          <div className="px-3 py-2">
            <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Tema
            </div>
            <div className="flex gap-1">
              {THEME_OPTIONS.map(({ mode, icon: Icon }) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setTheme(mode)}
                  aria-pressed={theme === mode}
                  className={
                    theme === mode
                      ? "flex flex-1 flex-col items-center gap-1 rounded-lg bg-primary-50 px-2 py-1.5 text-[10px] font-semibold text-primary-700 ring-1 ring-inset ring-primary-300/60"
                      : "flex flex-1 flex-col items-center gap-1 rounded-lg px-2 py-1.5 text-[10px] font-medium text-slate-500 hover:bg-slate-100"
                  }
                >
                  <Icon size={14} />
                  {THEME_LABELS[mode]}
                </button>
              ))}
            </div>
          </div>
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

      {modal === "oab" && (
        <div className="modal-backdrop" onClick={() => setModal(null)}>
          <div
            className="card p-6 w-full max-w-sm"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 className="font-semibold text-navy mb-1">
              Captura de intimações
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              O sistema consulta o DJEN diariamente (06h30) pela sua OAB.
            </p>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="Número (só dígitos)"
                value={oabNum}
                onChange={(event) =>
                  setOabNum(event.target.value.replace(/\D/g, ""))
                }
              />
              <select
                className="input w-20"
                value={oabUf}
                onChange={(event) => setOabUf(event.target.value)}
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
                ].map((uf) => (
                  <option key={uf}>{uf}</option>
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
