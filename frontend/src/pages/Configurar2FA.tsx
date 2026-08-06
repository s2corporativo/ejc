import { useEffect, useState } from "react";
import { Copy, Loader2, LogOut, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router";
import api, { logout } from "../lib/api";
import type { LoginResponse } from "../types";
import { useAuth } from "../stores/auth";

type SetupResponse = {
  secret: string;
  qr_data_url: string;
};

export default function Configurar2FA() {
  const [setup, setSetup] = useState<SetupResponse | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const bootstrap = useAuth((state) => state.bootstrap);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    api
      .post<SetupResponse>("/auth/totp/setup")
      .then(({ data }) => active && setSetup(data))
      .catch((err) => {
        if (active) {
          setError(
            err?.response?.data?.detail ||
              "Não foi possível iniciar a configuração do 2FA.",
          );
        }
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const verify = async () => {
    if (!/^\d{6}$/.test(code)) {
      setError("Informe o código de 6 dígitos do aplicativo autenticador.");
      return;
    }
    setError("");
    setVerifying(true);
    try {
      const { data } = await api.post<LoginResponse>("/auth/totp/verificar", {
        codigo: code,
      });
      localStorage.setItem("ejc_access", data.access_token);
      await bootstrap();
      navigate("/", { replace: true });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : detail?.message || "Código inválido ou expirado.",
      );
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas px-5 py-10 text-slate-950">
      <div className="mx-auto max-w-3xl rounded-xl border border-border bg-white p-6 shadow-card">
        <div className="flex items-start gap-3">
          <span className="rounded-xl bg-primary-50 p-3 text-primary-700">
            <ShieldCheck className="h-6 w-6" />
          </span>
          <div>
            <p className="eyebrow">Proteção obrigatória</p>
            <h1 className="mt-1 text-2xl font-semibold">
              Configure a autenticação em duas etapas
            </h1>
            <p className="mt-2 text-sm text-slate-500">
              A sessão completa somente será liberada após a confirmação do
              código temporário.
            </p>
          </div>
        </div>

        {error && (
          <div className="mt-5 rounded-xl bg-danger-50 px-4 py-3 text-sm text-danger-700">
            {error}
          </div>
        )}

        {loading ? (
          <div className="grid min-h-64 place-items-center text-slate-400">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : setup ? (
          <div className="mt-6 grid gap-6 md:grid-cols-[240px_1fr]">
            <div className="rounded-xl border border-border p-4">
              <img
                src={setup.qr_data_url}
                alt="QR Code para ativar a autenticação em duas etapas"
                className="mx-auto h-52 w-52"
              />
            </div>
            <div className="space-y-5">
              <div>
                <h2 className="font-semibold">1. Leia o QR Code</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Use Google Authenticator, Microsoft Authenticator, 1Password
                  ou outro aplicativo TOTP compatível.
                </p>
              </div>
              <div>
                <h2 className="font-semibold">2. Chave manual</h2>
                <div className="mt-2 flex items-center gap-2 rounded-xl border border-border px-3 py-2">
                  <code className="min-w-0 flex-1 break-all text-xs">
                    {setup.secret}
                  </code>
                  <button
                    type="button"
                    className="btn-ghost p-2"
                    title="Copiar chave"
                    onClick={() => navigator.clipboard.writeText(setup.secret)}
                  >
                    <Copy className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div>
                <label className="label">3. Confirme o código atual</label>
                <div className="mt-2 flex flex-wrap gap-2">
                  <input
                    className="input max-w-48 font-mono text-center tracking-[0.3em]"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    value={code}
                    onChange={(event) =>
                      setCode(event.target.value.replace(/\D/g, ""))
                    }
                    placeholder="000000"
                  />
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={verifying}
                    onClick={() => void verify()}
                  >
                    {verifying && <Loader2 className="h-4 w-4 animate-spin" />}
                    Ativar e entrar
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-6 border-t border-border pt-4">
          <button
            type="button"
            className="btn-ghost text-sm"
            onClick={() => logout("/login")}
          >
            <LogOut className="h-4 w-4" />
            Sair
          </button>
        </div>
      </div>
    </div>
  );
}
