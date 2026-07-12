import { useState } from "react";
import api, { logout } from "../lib/api";

export default function TrocarSenha() {
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [conf, setConf] = useState("");
  const [erro, setErro] = useState("");

  const trocar = async () => {
    setErro("");
    if (nova.length < 8) {
      setErro("Mínimo 8 caracteres");
      return;
    }
    if (nova !== conf) {
      setErro("Senhas não conferem");
      return;
    }
    try {
      await api.post("/auth/alterar-senha", {
        senha_atual: atual,
        nova_senha: nova,
      });
      // logout() faz redirect HARD para /login (o toast não sobreviveria à
      // recarga) — o aviso de sucesso é exibido pela tela de login via query.
      logout("/login?motivo=senha-alterada");
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Erro ao trocar a senha");
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
            placeholder="Nova senha (mín. 8)"
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
            onClick={trocar}
          >
            Definir nova senha
          </button>
        </div>
      </div>
    </div>
  );
}
