import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";

export default function RedefinirSenha() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const token = params.get("token") || "";
  const [senha, setSenha] = useState("");
  const [conf, setConf] = useState("");
  const [erro, setErro] = useState("");

  const confirmar = async () => {
    setErro("");
    if (senha.length < 8) {
      setErro("Mínimo 8 caracteres");
      return;
    }
    if (senha !== conf) {
      setErro("Senhas não conferem");
      return;
    }
    try {
      await axios.post("/api/v1/auth/redefinir-senha", {
        token,
        nova_senha: senha,
      });
      alert("Senha redefinida! Faça login.");
      nav("/login");
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Link inválido ou expirado");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-navy px-4">
      <div className="card w-full max-w-sm p-8">
        <img src="/logo.png" alt="" className="h-16 mx-auto mb-5" />
        <h1 className="font-semibold text-navy text-center mb-4">Nova senha</h1>
        {erro && (
          <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 text-sm">
            {erro}
          </div>
        )}
        <div className="space-y-4">
          <input
            className="input"
            type="password"
            placeholder="Nova senha (mín. 8)"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
          <input
            className="input"
            type="password"
            placeholder="Confirmar senha"
            value={conf}
            onChange={(e) => setConf(e.target.value)}
          />
          <button
            className="btn-primary w-full justify-center"
            onClick={confirmar}
          >
            Redefinir
          </button>
        </div>
      </div>
    </div>
  );
}
