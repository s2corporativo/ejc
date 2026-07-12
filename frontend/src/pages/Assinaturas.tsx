import { useState, useEffect, useCallback } from "react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";
import { EmptyState, PageHeader, Spinner, Modal } from "../components/UI";
import {
  FileSignature,
  Plus,
  X,
  UserPlus,
  CheckCircle,
  Circle,
} from "lucide-react";

interface Signatario {
  nome: string;
  email: string;
  papel: string;
  assinado?: boolean;
  assinado_em?: string;
}

interface SolicitacaoAssinatura {
  id: number;
  documento_nome: string;
  status: "aguardando" | "parcial" | "concluido";
  signatarios: Signatario[];
  case_id?: number;
  created_at: string;
}

interface NovaAssinaturaForm {
  documento_nome: string;
  case_id: string;
  document_id: string;
  signatarios: { nome: string; email: string; papel: string }[];
}

const STATUS_CONFIG = {
  aguardando: {
    label: "Aguardando",
    className: "bg-yellow-100 text-yellow-800",
  },
  parcial: { label: "Parcial", className: "bg-primary-100 text-primary-800" },
  concluido: { label: "Concluído", className: "bg-green-100 text-green-800" },
};

export default function Assinaturas() {
  const [solicitacoes, setSolicitacoes] = useState<SolicitacaoAssinatura[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalAberto, setModalAberto] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [assinando, setAssinando] = useState<number | null>(null);
  // E-mail do usuário logado vem da sessão já carregada no bootstrap —
  // evita uma chamada redundante (e ruidosa) a /users/me nesta página.
  const userEmail = useAuth((s) => s.user?.email ?? "");

  const [form, setForm] = useState<NovaAssinaturaForm>({
    documento_nome: "",
    case_id: "",
    document_id: "",
    signatarios: [{ nome: "", email: "", papel: "" }],
  });

  const fetchSolicitacoes = useCallback(async () => {
    setLoading(true);
    try {
      // Barra final obrigatória: sem ela o FastAPI responde 307 com Location
      // absoluto e o browser perde o Authorization no redirect (achado M1).
      const res = await api.get("/signatures/");
      // O backend responde envelope { data: [...] } — asList() normaliza
      // (array cru | { items } | { data }) e nunca quebra o .map da lista.
      setSolicitacoes(asList<SolicitacaoAssinatura>(res.data));
    } catch {
      setSolicitacoes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSolicitacoes();
  }, [fetchSolicitacoes]);

  const abrirModal = () => {
    setForm({
      documento_nome: "",
      case_id: "",
      document_id: "",
      signatarios: [{ nome: "", email: "", papel: "" }],
    });
    setModalAberto(true);
  };

  const fecharModal = () => setModalAberto(false);

  const atualizarSignatario = (
    idx: number,
    campo: keyof (typeof form.signatarios)[0],
    valor: string,
  ) => {
    setForm((prev) => {
      const sigs = [...prev.signatarios];
      sigs[idx] = { ...sigs[idx], [campo]: valor };
      return { ...prev, signatarios: sigs };
    });
  };

  const adicionarSignatario = () => {
    setForm((prev) => ({
      ...prev,
      signatarios: [...prev.signatarios, { nome: "", email: "", papel: "" }],
    }));
  };

  const removerSignatario = (idx: number) => {
    setForm((prev) => ({
      ...prev,
      signatarios: prev.signatarios.filter((_, i) => i !== idx),
    }));
  };

  const criarSolicitacao = async (e: React.FormEvent) => {
    e.preventDefault();
    setSalvando(true);
    try {
      const payload: Record<string, unknown> = {
        documento_nome: form.documento_nome,
        signatarios: form.signatarios.filter((s) => s.email && s.nome),
      };
      if (form.case_id) payload.case_id = Number(form.case_id);
      if (form.document_id) payload.document_id = Number(form.document_id);
      // Barra final obrigatória (mesmo motivo do GET acima): evita 307 que
      // derruba o Authorization no redirect.
      await api.post("/signatures/", payload);
      fecharModal();
      await fetchSolicitacoes();
    } finally {
      setSalvando(false);
    }
  };

  const assinar = async (id: number, signatarioEmail: string) => {
    setAssinando(id);
    try {
      await api.post(`/signatures/${id}/assinar`, {
        signatario_email: signatarioEmail,
      });
      await fetchSolicitacoes();
    } finally {
      setAssinando(null);
    }
  };

  const isSignatario = (sol: SolicitacaoAssinatura) =>
    userEmail
      ? sol.signatarios.some(
          (s) =>
            s.email.toLowerCase() === userEmail.toLowerCase() && !s.assinado,
        )
      : false;

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <PageHeader title="Assinaturas" />
        <button onClick={abrirModal} className="btn-primary">
          <Plus className="w-4 h-4" />
          Nova Assinatura
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : solicitacoes.length === 0 ? (
        <EmptyState
          title="Nenhuma solicitação de assinatura"
          message={'Clique em "Nova Assinatura" para criar uma solicitação.'}
          icon={FileSignature}
        />
      ) : (
        <ul className="space-y-3">
          {solicitacoes.map((sol) => {
            const cfg = STATUS_CONFIG[sol.status];
            const podeAssinar = isSignatario(sol);
            return (
              <li key={sol.id} className="card p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <span className="font-semibold text-gray-800 truncate">
                        {sol.documento_nome}
                      </span>
                      <span
                        className={`inline-flex items-center rounded-full text-xs font-semibold px-2 py-0.5 ${cfg.className}`}
                      >
                        {cfg.label}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mb-3">
                      Criado em {formatDate(sol.created_at)}
                      {sol.case_id && (
                        <span className="ml-2 text-gray-400">
                          · Caso #{sol.case_id}
                        </span>
                      )}
                    </p>
                    <div className="flex flex-wrap gap-3">
                      {sol.signatarios.map((sig, idx) => (
                        <div
                          key={idx}
                          className="flex items-center gap-1.5 text-sm text-gray-600"
                        >
                          {sig.assinado ? (
                            <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                          ) : (
                            <Circle className="w-4 h-4 text-gray-300 flex-shrink-0" />
                          )}
                          <span
                            className={sig.assinado ? "text-green-700" : ""}
                          >
                            {sig.nome}
                          </span>
                          {sig.papel && (
                            <span className="text-xs text-gray-400">
                              ({sig.papel})
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                  {podeAssinar && sol.status !== "concluido" && (
                    <button
                      onClick={() => assinar(sol.id, userEmail)}
                      disabled={assinando === sol.id}
                      className="flex-shrink-0 inline-flex items-center gap-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
                    >
                      {assinando === sol.id ? (
                        <Spinner />
                      ) : (
                        <CheckCircle className="w-4 h-4" />
                      )}
                      Assinar
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* MODAL */}
      <Modal
        open={modalAberto}
        onClose={fecharModal}
        title="Nova Solicitação de Assinatura"
      >
        <form onSubmit={criarSolicitacao} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Nome do Documento <span className="text-danger-500">*</span>
            </label>
            <input
              type="text"
              required
              value={form.documento_nome}
              onChange={(e) =>
                setForm((p) => ({ ...p, documento_nome: e.target.value }))
              }
              placeholder="Ex: Contrato de Prestação de Serviços"
              className="input"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                ID do Caso
              </label>
              <input
                type="number"
                value={form.case_id}
                onChange={(e) =>
                  setForm((p) => ({ ...p, case_id: e.target.value }))
                }
                placeholder="Opcional"
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                ID do Documento
              </label>
              <input
                type="number"
                value={form.document_id}
                onChange={(e) =>
                  setForm((p) => ({ ...p, document_id: e.target.value }))
                }
                placeholder="Opcional"
                className="input"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">
                Signatários <span className="text-danger-500">*</span>
              </label>
              <button
                type="button"
                onClick={adicionarSignatario}
                className="inline-flex items-center gap-1 text-xs text-primary-600 hover:text-primary-800 font-medium"
              >
                <UserPlus className="w-3.5 h-3.5" />
                Adicionar
              </button>
            </div>

            <div className="space-y-3">
              {form.signatarios.map((sig, idx) => (
                <div key={idx} className="flex gap-2 items-start">
                  <div className="flex-1 grid grid-cols-3 gap-2">
                    <input
                      type="text"
                      required
                      value={sig.nome}
                      onChange={(e) =>
                        atualizarSignatario(idx, "nome", e.target.value)
                      }
                      placeholder="Nome"
                      className="input px-2 py-1.5"
                    />
                    <input
                      type="email"
                      required
                      value={sig.email}
                      onChange={(e) =>
                        atualizarSignatario(idx, "email", e.target.value)
                      }
                      placeholder="E-mail"
                      className="input px-2 py-1.5"
                    />
                    <input
                      type="text"
                      value={sig.papel}
                      onChange={(e) =>
                        atualizarSignatario(idx, "papel", e.target.value)
                      }
                      placeholder="Papel"
                      className="input px-2 py-1.5"
                    />
                  </div>
                  {form.signatarios.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removerSignatario(idx)}
                      className="mt-1 text-gray-300 hover:text-danger-500 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={fecharModal}
              className="btn-secondary flex-1"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={salvando}
              className="btn-primary flex-1"
            >
              {salvando ? <Spinner /> : <FileSignature className="w-4 h-4" />}
              Criar Solicitação
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
