import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Copy,
  KeyRound,
  Loader2,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  XCircle,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { SectionCard, fmtDateTime } from "./UI";
import { useAuth } from "../stores/auth";

type SecurityStatus = {
  permissions: string[];
  totp_enabled: boolean;
  active_sessions: number;
  two_factor_available: boolean;
};

type SessionItem = {
  id: string;
  created_at: string;
  expires_at: string;
  current: boolean;
};

type SetupResponse = {
  secret: string;
  uri: string;
  aviso?: string;
};

export default function AccountSecurity() {
  const updateUser = useAuth((state) => state.updateUser);
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [setup, setSetup] = useState<SetupResponse | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [verifyCode, setVerifyCode] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [securityResponse, sessionsResponse] = await Promise.all([
        api.get<SecurityStatus>("/users/me/security"),
        api.get<{ data: SessionItem[] }>("/users/me/sessions"),
      ]);
      setStatus(securityResponse.data);
      setSessions(sessionsResponse.data.data ?? []);
      updateUser({ permissions: securityResponse.data.permissions });
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          "Não foi possível carregar as configurações de segurança.",
      );
    } finally {
      setLoading(false);
    }
  }, [updateUser]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(
    () => () => {
      if (qrUrl) URL.revokeObjectURL(qrUrl);
    },
    [qrUrl],
  );

  const permissionLabel = useMemo(() => {
    if (!status) return "—";
    if (status.permissions.includes("*")) return "Acesso integral";
    return `${status.permissions.length} permissões funcionais`;
  }, [status]);

  const startTotp = async () => {
    setBusy("setup");
    try {
      const { data } = await api.post<SetupResponse>("/auth/totp/setup");
      const qr = await api.get("/users/me/totp-qr", { responseType: "blob" });
      if (qrUrl) URL.revokeObjectURL(qrUrl);
      setSetup(data);
      setQrUrl(URL.createObjectURL(qr.data as Blob));
      setVerifyCode("");
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "Falha ao iniciar o 2FA.");
    } finally {
      setBusy(null);
    }
  };

  const verifyTotp = async () => {
    if (!/^\d{6}$/.test(verifyCode)) {
      toast.error("Informe o código de 6 dígitos do aplicativo autenticador.");
      return;
    }
    setBusy("verify");
    try {
      await api.post("/auth/totp/verificar", { codigo: verifyCode });
      if (qrUrl) URL.revokeObjectURL(qrUrl);
      setQrUrl(null);
      setSetup(null);
      setVerifyCode("");
      toast.success("Autenticação em duas etapas ativada.");
      await load();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "Código inválido.");
    } finally {
      setBusy(null);
    }
  };

  const disableTotp = async () => {
    if (!/^\d{6}$/.test(disableCode)) {
      toast.error("Informe o código atual de 6 dígitos.");
      return;
    }
    setBusy("disable");
    try {
      await api.post("/auth/totp/desativar", { codigo: disableCode });
      setDisableCode("");
      toast.success("Autenticação em duas etapas desativada.");
      await load();
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail || "Não foi possível desativar o 2FA.",
      );
    } finally {
      setBusy(null);
    }
  };

  const revokeSession = async (sessionId: string) => {
    setBusy(sessionId);
    try {
      await api.post(`/users/me/sessions/${sessionId}/revoke`);
      toast.success("Sessão remota revogada.");
      await load();
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail || "Falha ao revogar a sessão.",
      );
    } finally {
      setBusy(null);
    }
  };

  const revokeOthers = async () => {
    setBusy("revoke-others");
    try {
      const { data } = await api.post("/users/me/sessions/revoke-others");
      toast.success(`${data.revoked ?? 0} sessão(ões) remota(s) revogada(s).`);
      await load();
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail || "Falha ao revogar as outras sessões.",
      );
    } finally {
      setBusy(null);
    }
  };

  if (loading && !status) {
    return (
      <div className="flex justify-center py-16 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <SectionCard
        title="Autenticação em duas etapas"
        subtitle="Protege o login com um código temporário gerado no aplicativo autenticador."
      >
        <div className="card flex items-start gap-3 p-4">
          <span
            className={`rounded-xl p-3 ${
              status?.totp_enabled
                ? "bg-success-50 text-success-700"
                : "bg-warn-50 text-warn-700"
            }`}
          >
            <ShieldCheck className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <div className="font-semibold text-slate-800">
                2FA {status?.totp_enabled ? "ativado" : "desativado"}
              </div>
              <span
                className={`badge ${
                  status?.totp_enabled ? "badge-success" : "badge-warn"
                }`}
              >
                {status?.totp_enabled ? "Protegido" : "Atenção"}
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              O segredo nunca é retornado após a ativação e o QR Code usa
              resposta sem cache.
            </p>
          </div>
          {!status?.totp_enabled && !setup && (
            <button
              type="button"
              className="btn-primary"
              disabled={busy === "setup"}
              onClick={startTotp}
            >
              {busy === "setup" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Smartphone className="h-4 w-4" />
              )}
              Configurar
            </button>
          )}
        </div>

        {setup && !status?.totp_enabled && (
          <div className="mt-4 grid gap-5 rounded-xl border border-primary-200 bg-primary-50/40 p-5 md:grid-cols-[220px_1fr]">
            <div className="card p-3">
              {qrUrl ? (
                <img
                  src={qrUrl}
                  alt="QR Code temporário para configurar o 2FA"
                  className="mx-auto h-48 w-48"
                />
              ) : (
                <div className="grid h-48 place-items-center text-slate-400">
                  QR indisponível
                </div>
              )}
            </div>
            <div className="space-y-4">
              <div>
                <div className="text-sm font-semibold text-slate-800">
                  1. Leia o QR Code no aplicativo autenticador
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  Google Authenticator, Microsoft Authenticator, 1Password ou
                  aplicativo TOTP compatível.
                </p>
              </div>
              <div>
                <div className="text-sm font-semibold text-slate-800">
                  2. Alternativa manual
                </div>
                <div className="card mt-2 flex items-center gap-2 px-3 py-2">
                  <code className="min-w-0 flex-1 break-all text-xs text-slate-700">
                    {setup.secret}
                  </code>
                  <button
                    type="button"
                    className="btn-ghost p-2"
                    title="Copiar segredo temporário"
                    onClick={async () => {
                      await navigator.clipboard.writeText(setup.secret);
                      toast.success("Segredo temporário copiado.");
                    }}
                  >
                    <Copy className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div>
                <label className="label">3. Confirme o primeiro código</label>
                <div className="flex flex-wrap gap-2">
                  <input
                    className="input max-w-48 font-mono tracking-[0.3em]"
                    inputMode="numeric"
                    maxLength={6}
                    value={verifyCode}
                    onChange={(event) =>
                      setVerifyCode(event.target.value.replace(/\D/g, ""))
                    }
                    placeholder="000000"
                  />
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={busy === "verify"}
                    onClick={verifyTotp}
                  >
                    {busy === "verify" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4" />
                    )}
                    Ativar
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      if (qrUrl) URL.revokeObjectURL(qrUrl);
                      setQrUrl(null);
                      setSetup(null);
                      setVerifyCode("");
                    }}
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {status?.totp_enabled && (
          <div className="mt-4 rounded-xl border border-danger-200 bg-danger-50/40 p-4">
            <div className="text-sm font-semibold text-slate-800">
              Desativar 2FA
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Exige um código atual do aplicativo autenticador.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <input
                className="input max-w-48 font-mono tracking-[0.3em]"
                inputMode="numeric"
                maxLength={6}
                value={disableCode}
                onChange={(event) =>
                  setDisableCode(event.target.value.replace(/\D/g, ""))
                }
                placeholder="000000"
              />
              <button
                type="button"
                className="btn-secondary text-danger-700"
                disabled={busy === "disable"}
                onClick={disableTotp}
              >
                {busy === "disable" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                Desativar
              </button>
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Sessões ativas"
        subtitle="A versão atual registra criação e expiração; dispositivo e IP ainda não fazem parte do modelo de sessão."
      >
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm text-slate-500">
            {sessions.length} sessão(ões) refresh ativa(s)
          </div>
          <div className="flex gap-2">
            <button type="button" className="btn-ghost" onClick={load}>
              <RefreshCw className="h-4 w-4" /> Atualizar
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy === "revoke-others" || sessions.length <= 1}
              onClick={revokeOthers}
            >
              {busy === "revoke-others" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <LogOut className="h-4 w-4" />
              )}
              Revogar outras
            </button>
          </div>
        </div>

        <div className="card divide-y divide-slate-100 overflow-hidden">
          {sessions.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-400">
              Nenhuma sessão refresh ativa encontrada.
            </div>
          ) : (
            sessions.map((session) => (
              <div
                key={session.id}
                className="flex flex-wrap items-center gap-3 px-4 py-3"
              >
                <KeyRound className="h-4 w-4 text-slate-400" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-800">
                    Sessão iniciada em {fmtDateTime(session.created_at)}
                    {session.current && (
                      <span className="badge badge-success">Atual</span>
                    )}
                  </div>
                  <div className="mt-0.5 text-xs text-slate-400">
                    Expira em {fmtDateTime(session.expires_at)}
                  </div>
                </div>
                {!session.current && (
                  <button
                    type="button"
                    className="btn-ghost text-danger-700"
                    disabled={busy === session.id}
                    onClick={() => revokeSession(session.id)}
                  >
                    {busy === session.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <LogOut className="h-4 w-4" />
                    )}
                    Revogar
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </SectionCard>

      <SectionCard
        title="Permissões efetivas"
        subtitle="Derivadas da matriz central do backend; a interface não concede permissões por conta própria."
      >
        <div className="card flex items-center gap-3 p-4">
          <ShieldCheck className="h-5 w-5 text-primary-600" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-slate-800">
              {permissionLabel}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {status?.permissions.includes("*")
                ? "Perfil superadministrador."
                : status?.permissions.join(" · ") ||
                  "Nenhuma permissão retornada."}
            </div>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
