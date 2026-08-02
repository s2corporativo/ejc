// ── Aba Prazos do caso — formulário inline (Tela C, Bloco 3) ─────────────────
// A aba age EM LUGAR: três campos (título, data, responsável) criam o prazo
// via POST /deadlines/ com case_id — sem navegar para /atividades.
// Schema confirmado em backend/app/routers/deadlines.py (criar, 201):
// titulo obrigatório; data_prazo OU (data_intimacao + dias_prazo);
// responsavel_id opcional (o backend usa o usuário logado como default).
import { useCallback, useEffect, useState } from "react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { Empty, fmtDate } from "../../components/UI";
import { useAuth } from "../../stores/auth";

function detalheErro(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { mensagem?: unknown }).mensagem === "string"
  ) {
    return (detail as { mensagem: string }).mensagem;
  }
  return fallback;
}

interface Responsavel {
  id: string;
  nome?: string;
  full_name?: string;
}

export default function TabPrazos({ caseId }: { caseId: string }) {
  const { user } = useAuth();
  const [prazos, setPrazos] = useState<any[]>([]);
  const [responsaveis, setResponsaveis] = useState<Responsavel[]>([]);
  const [titulo, setTitulo] = useState("");
  const [data, setData] = useState("");
  const [responsavelId, setResponsavelId] = useState(user?.id ?? "");
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(() => {
    api
      .get(`/deadlines/?case_id=${caseId}&status=`)
      .then((r) => setPrazos(asList(r.data)))
      .catch(() => setPrazos([]));
  }, [caseId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  useEffect(() => {
    // Lista de equipe para atribuir responsável (mesma fonte da Central de
    // Atividades). Sem permissão (403), o select mostra só o usuário logado.
    api
      .get("/atendimentos/responsaveis")
      .then((r) => setResponsaveis(asList(r.data)))
      .catch(() => setResponsaveis([]));
  }, []);

  const criar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!titulo.trim() || !data) {
      toast.error("Informe o título e a data do prazo.");
      return;
    }
    setSalvando(true);
    try {
      await api.post("/deadlines/", {
        titulo: titulo.trim(),
        data_prazo: data,
        case_id: caseId,
        responsavel_id: responsavelId || undefined,
      });
      toast.success("Prazo criado no caso.");
      setTitulo("");
      setData("");
      setResponsavelId(user?.id ?? "");
      carregar();
    } catch (error) {
      toast.error(detalheErro(error, "Não foi possível criar o prazo."));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Formulário inline — a ação acontece dentro do caso */}
      <form onSubmit={criar} className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-slate-700">
          Novo prazo neste caso
        </h3>
        <div className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr_auto]">
          <input
            className="input w-full text-sm"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Título do prazo (ex.: Contestar em 15 dias)"
            required
          />
          <input
            type="date"
            className="input w-full text-sm"
            value={data}
            onChange={(e) => setData(e.target.value)}
            aria-label="Data do prazo"
            required
          />
          <select
            className="input text-sm"
            value={responsavelId}
            onChange={(e) => setResponsavelId(e.target.value)}
            aria-label="Responsável pelo prazo"
          >
            {/* O usuário logado é sempre uma opção (e o default). */}
            {user && !responsaveis.some((r) => r.id === user.id) && (
              <option value={user.id}>{user.full_name} (você)</option>
            )}
            {responsaveis.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nome || r.full_name || r.id}
                {user && r.id === user.id ? " (você)" : ""}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={salvando}
            className="btn-primary text-sm disabled:opacity-50"
          >
            {salvando ? "Criando…" : "Criar prazo"}
          </button>
        </div>
      </form>

      {/* Lista existente */}
      <h2 className="font-semibold">Prazos ({prazos.length})</h2>
      <div className="space-y-2">
        {prazos.map((d, i) => (
          <div
            key={d.id || i}
            className="card p-3 flex justify-between items-center text-sm"
          >
            <span className="text-gray-800">{d.titulo}</span>
            <span
              className={`font-medium text-xs ${
                (d.dias_restantes ?? 1) <= 0
                  ? "text-danger-600"
                  : (d.dias_restantes ?? 99) <= 7
                    ? "text-orange-600"
                    : "text-gray-500"
              }`}
            >
              {fmtDate(d.data_prazo)}
            </span>
          </div>
        ))}
        {prazos.length === 0 && <Empty message="Nenhum prazo cadastrado" />}
      </div>
    </div>
  );
}
