import { useState } from "react";
import { useNavigate } from "react-router";
import api, { logout, setAccessToken } from "../lib/api";
import { toast } from "../components/Toast";
import { useAuth } from "../stores/auth";

export default function TrocarSenha() {
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [conf, setConf] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const nav = useNavigate();
  const bootstrap = useAuth((state) => state.bootstrap);

  const trocar = async () => {
    setErro("");
    const senhaForte =
      nova.length >= 10 &&
      /[A-Za-z]/.test(nova) &&
      /\d/.test(nova) &&
      /[^A-Za-z0-9]/.test(nova);
    if (!senhaForte) {
      setErro("Use no mínimo 10 caracteres, com letra, número e símbolo.");
      return;
    }
    if (nova !== conf) {
      setErro("Senhas não conferem");
      return;
    }
    setSalvando(true);
    try {
      const { data } = await api.post("/auth/alterar-senha", {
        senha_atual: atual,
        nova_senha: nova,
      });
      if (data?.access_token) {
        // Backend devolve tokens novos (mesmo formato do login): mantém a
        // sessão em vez de derrubar o usuário de volta ao /login logo após
        // ele criar a senha. O refresh novo vem no cookie httpOnly.
        setAccessToken(data.access_token);
        if (data.precisa_configurar_2fa) {
          toast.success("Senha alterada. Agora proteja a conta com o 2FA.");
          nav("/configurar-2fa", { replace: true });
          return;
        }
        await bootstrap();
        toast.success("Senha alterada com sucesso — você continua conectado.");
        nav("/", { replace: true });
        return;
      }
      // Fallback (backend antigo, sem tokens na resposta): logout() faz
      // redirect HARD para /login — o aviso de sucesso é exibido pela tela
      // de login via query string.
      logout("/login?motivo=senha-alterada");
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Erro ao trocar a senha");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-navy px-4">
      <div className="card w-full max-w-sm p-8">
        <img src="/logo.png" alt="" className="h-16 mx-auto mb-4" />
        <h1 className="font-semibold text-navy text-center">
          Troca de senha obrigatória
        </h1>
        <p className="text-xs text-slate-500 text-center mb-5">
          Por segurança, defina sua senha pessoal antes de continuar.
        </p>
        {erro && (
          <div className="mb-3 px-3 py-2 rounded-lg bg-danger-50 text-danger-700 text-sm">
            {erro}
          </div>
        )}
        <div className="space-y-4">
          <input
            className="input"
            type="password"
            placeholder="Senha atual (inicial)"
            value={atual}
            onChange={(e) => setAtual(e.target.value)}
          />
          <input
            className="input"
            type="password"
            placeholder="Nova senha (mín. 10, com letra, número e símbolo)"
            value={nova}
            onChange={(e) => setNova(e.target.value)}
          />
          <input
            className="input"
            type="password"
            placeholder="Confirmar nova senha"
            value={conf}
            onChange={(e) => setConf(e.target.value)}
          />
          <button
            className="btn-primary w-full justify-center"
            disabled={salvando}
            onClick={trocar}
          >
            {salvando ? "Salvando..." : "Definir nova senha"}
          </button>
        </div>
      </div>
    </div>
  );
}
