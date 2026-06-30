import { useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";

export default function RecuperarSenha() {
  const [email, setEmail] = useState("");
  const [ok, setOk] = useState(false);

  const enviar = async () => {
    await axios.post("/api/v1/auth/recuperar-senha", { email }).catch(() => {});
    setOk(true); // sempre sucesso (não revela se e-mail existe)
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-navy px-4">
      <div className="card w-full max-w-sm p-8">
        <img src="/logo.png" alt="" className="h-16 mx-auto mb-5" />
        <h1 className="font-semibold text-navy text-center mb-4">
          Recuperar senha
        </h1>
        {ok ? (
          <div className="text-sm text-emerald-700 bg-emerald-50 rounded-lg p-4 text-center">
            Se o e-mail existir, enviaremos as instruções em instantes.
            Verifique também o spam.
          </div>
        ) : (
          <div className="space-y-4">
            <input
              className="input"
              type="email"
              placeholder="seu@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <button
              className="btn-primary w-full justify-center"
              onClick={enviar}
            >
              Enviar link de recuperação
            </button>
          </div>
        )}
        <div className="text-center mt-5">
          <Link to="/login" className="text-xs text-navy hover:underline">
            ← Voltar ao login
          </Link>
        </div>
      </div>
    </div>
  );
}
