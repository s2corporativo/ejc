import { Link } from "react-router-dom";

/**
 * Item 2.4 — página 404 real.
 * Antes, qualquer rota desconhecida caía num <Navigate to="/"> silencioso, o que
 * mandava o usuário ao Dashboard sem indicar que a URL não existe. Agora exibimos
 * um "não encontrado" explícito com caminho de volta.
 */
export default function NotFound() {
  return (
    <div className="min-h-screen grid place-items-center bg-slate-50 px-4">
      <div className="text-center max-w-md">
        <p className="text-6xl font-bold text-navy">404</p>
        <h1 className="mt-3 text-xl font-semibold text-ink">
          Página não encontrada
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          A rota que você tentou acessar não existe ou foi movida.
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <Link to="/" className="btn bg-navy text-white">
            Voltar ao início
          </Link>
          <Link
            to="/login"
            className="btn bg-white border border-slate-200 text-slate-600"
          >
            Ir para o login
          </Link>
        </div>
      </div>
    </div>
  );
}
