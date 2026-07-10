import { toast } from "../components/Toast";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Search, ShieldAlert, KeyRound } from "lucide-react";
import api from "../lib/api";
import { soDigitos } from "../utils/phone";
import type { Client, Paged } from "../types";
import {
  PageHeader,
  StatusBadge,
  Modal,
  Empty,
  EmptyState,
  Spinner,
  fmtDate,
  Alert,
  Badge,
  Button,
} from "../components/UI";
import { ClientesStats } from "../components/Dashboards";

// Resposta de POST /clients/checar-conflito (nome/documento completos —
// o advogado precisa saber com quem é o conflito; endpoint restrito ao CRM).
type ConflitoNivel = "nenhum" | "atencao" | "critico";
interface ConflitoMatch {
  tipo: string;
  case_id?: string;
  client_id?: string;
  papel: string;
  nome?: string;
  documento?: string;
  descricao: string;
}
interface ConflitoCheck {
  conflito: boolean;
  nivel: ConflitoNivel;
  matches: ConflitoMatch[];
}

function openWhatsApp(phone: string, name: string) {
  const digits = soDigitos(phone);
  const br = digits.startsWith("55") ? digits : "55" + digits;
  const msg = encodeURIComponent(`Olá ${name}, tudo bem?`);
  window.open(`https://wa.me/${br}?text=${msg}`, "_blank");
}

export default function Clientes() {
  const [data, setData] = useState<Paged<Client> | null>(null);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const [conflito, setConflito] = useState<ConflitoCheck | null>(null);
  const [conflitoLoading, setConflitoLoading] = useState(false);
  const [acessoModal, setAcessoModal] = useState<any>(null); // cliente alvo
  const [acessoForm, setAcessoForm] = useState({
    email: "",
    senha_inicial: "",
  });
  const [form, setForm] = useState<any>({
    tipo: "PF",
    cidade: "Betim",
    estado: "MG",
  });
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(false);
  // Guarda de sequência: só a resposta do load mais recente aplica setData,
  // evitando que uma resposta antiga (busca com debounce) sobrescreva a nova.
  const seq = useRef(0);

  const load = () => {
    const my = ++seq.current;
    setErro(false);
    return api
      .get("/clients/", {
        params: { search: search || undefined, page_size: 50 },
      })
      .then((r) => {
        if (my === seq.current) setData(r.data);
      })
      .catch(() => {
        if (my !== seq.current) return;
        setErro(true);
        toast.error("Falha ao carregar clientes");
      });
  };

  useEffect(() => {
    load();
  }, []);
  useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [search]);

  // Checagem de conflito de interesses em tempo real (EOAB arts. 34-35).
  // Fail-safe: qualquer erro é silencioso e NÃO impede o cadastro.
  const checarConflito = async (): Promise<ConflitoCheck | null> => {
    const nome = (form.nome || form.razao_social || "").trim();
    const cpf = form.cpf;
    const cnpj = form.cnpj;
    const parte_contraria = form.parte_contraria;
    // Nada relevante digitado ainda → limpa e não chama a API.
    if (!cpf && !cnpj && nome.length < 4 && !parte_contraria) {
      setConflito(null);
      return null;
    }
    setConflitoLoading(true);
    try {
      const { data } = await api.post<ConflitoCheck>(
        "/clients/checar-conflito",
        { nome, cpf, cnpj, parte_contraria },
      );
      setConflito(data);
      return data;
    } catch {
      // Aviso ético é best-effort: falha na checagem não trava o formulário.
      setConflito(null);
      return null;
    } finally {
      setConflitoLoading(false);
    }
  };

  const salvar = async () => {
    // O alerta de conflito é apenas um aviso ético — NÃO bloqueia o cadastro.
    setSalvando(true);
    try {
      await api.post("/clients/", form);
      setModal(false);
      setForm({ tipo: "PF", cidade: "Betim", estado: "MG" });
      setConflito(null);
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Clientes"
        subtitle={`${data?.total ?? 0} ${(data?.total ?? 0) === 1 ? "cadastrado" : "cadastrados"}`}
        actions={
          <button className="btn-gold" onClick={() => setModal(true)}>
            <Plus size={16} /> Novo cliente
          </button>
        }
      />

      <ClientesStats />

      <div className="relative mb-4 max-w-md">
        <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
        <input
          className="input pl-9"
          placeholder="Buscar por nome, CPF, CNPJ..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {erro && !data ? (
        <EmptyState
          title="Falha ao carregar clientes"
          message="Não foi possível carregar a lista. Verifique sua conexão e tente novamente."
          action={
            <Button variant="primary" onClick={load}>
              Tentar novamente
            </Button>
          }
        />
      ) : !data ? (
        <Spinner />
      ) : data.data.length === 0 ? (
        <Empty message="Nenhum cliente encontrado" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Nome / Razão</th>
                <th className="px-4 py-3">Tipo</th>
                <th className="px-4 py-3">CPF / CNPJ</th>
                <th className="px-4 py-3">Contato</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Desde</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(Array.isArray(data.data) ? data.data : []).map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-navy">
                    <Link
                      to={`/clientes/${c.id}`}
                      className="hover:text-bronze hover:underline"
                    >
                      {c.nome || c.razao_social}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{c.tipo}</td>
                  <td className="px-4 py-3 text-slate-500">
                    {c.cpf || c.cnpj || "—"}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button
                      title="Dossiê Digital"
                      className="text-bronze hover:text-bronze-dark px-1.5 font-medium text-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        window.location.href = `/clientes/${c.id}/dossie`;
                      }}
                    >
                      📋
                    </button>
                    <button
                      title="Acesso ao Portal"
                      className="text-navy hover:text-gold px-1.5"
                      onClick={(e) => {
                        e.stopPropagation();
                        setAcessoModal(c);
                        setAcessoForm({
                          email: c.email || "",
                          senha_inicial: "",
                        });
                      }}
                    >
                      <KeyRound size={14} />
                    </button>
                    <button
                      title="Relatório LGPD"
                      className="text-navy hover:text-gold px-1.5"
                      onClick={async (e) => {
                        e.stopPropagation();
                        const r = await api.get(
                          `/clients/${c.id}/relatorio-lgpd`,
                          { responseType: "blob" },
                        );
                        const url = URL.createObjectURL(r.data);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `lgpd_${c.id.slice(0, 8)}.pdf`;
                        a.click();
                      }}
                    >
                      📄
                    </button>
                  </td>
                  <td className="px-4 py-3 text-slate-500 flex items-center gap-2">
                    <span>{c.whatsapp || c.telefone || c.email || "—"}</span>
                    {(c.whatsapp || c.telefone) && (
                      <button
                        onClick={() =>
                          openWhatsApp(
                            c.whatsapp || c.telefone || "",
                            c.nome || "",
                          )
                        }
                        className="p-1 rounded-full bg-green-100 text-green-600 hover:bg-green-200 transition-colors"
                        title="Abrir WhatsApp"
                      >
                        <svg
                          className="w-3.5 h-3.5"
                          viewBox="0 0 24 24"
                          fill="currentColor"
                        >
                          <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z" />
                          <path d="M12 0C5.373 0 0 5.373 0 12c0 2.125.557 4.126 1.535 5.858L.057 23.486a.5.5 0 0 0 .612.612l5.63-1.477A11.95 11.95 0 0 0 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.886 0-3.655-.497-5.191-1.367l-.372-.217-3.858 1.012 1.013-3.842-.228-.384A9.96 9.96 0 0 1 2 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z" />
                        </svg>
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={c.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {fmtDate(c.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={modal}
        onClose={() => {
          setModal(false);
          setConflito(null);
        }}
        title="Novo cliente"
        wide
      >
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Tipo</label>
            <select
              className="input"
              value={form.tipo}
              onChange={(e) => setForm({ ...form, tipo: e.target.value })}
            >
              <option value="PF">Pessoa Física</option>
              <option value="PJ">Pessoa Jurídica</option>
            </select>
          </div>
          {form.tipo === "PF" ? (
            <>
              <div>
                <label className="label">Nome completo *</label>
                <input
                  className="input"
                  value={form.nome || ""}
                  onChange={(e) => setForm({ ...form, nome: e.target.value })}
                />
              </div>
              <div>
                <label className="label">CPF</label>
                <input
                  className="input"
                  value={form.cpf || ""}
                  onChange={(e) => setForm({ ...form, cpf: e.target.value })}
                  onBlur={checarConflito}
                />
              </div>
            </>
          ) : (
            <>
              <div>
                <label className="label">Razão social *</label>
                <input
                  className="input"
                  value={form.razao_social || ""}
                  onChange={(e) =>
                    setForm({ ...form, razao_social: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="label">CNPJ</label>
                <div className="flex gap-2">
                  <input
                    className="input flex-1"
                    value={form.cnpj || ""}
                    onChange={(e) => setForm({ ...form, cnpj: e.target.value })}
                    onBlur={checarConflito}
                  />
                  <button
                    type="button"
                    className="btn-ghost text-xs whitespace-nowrap"
                    onClick={async () => {
                      try {
                        const { data } = await api.get(
                          `/utils/cnpj/${(form.cnpj || "").replace(/\D/g, "")}`,
                        );
                        setForm({
                          ...form,
                          razao_social: data.razao_social,
                          cep: data.cep,
                          logradouro: data.logradouro,
                          numero: data.numero,
                          bairro: data.bairro,
                          cidade: data.cidade,
                          estado: data.estado,
                          telefone: data.telefone,
                        });
                      } catch (e: any) {
                        toast.error(
                          e.response?.data?.detail || "CNPJ não encontrado",
                        );
                      }
                    }}
                  >
                    🔍 Receita
                  </button>
                </div>
              </div>
            </>
          )}
          <div>
            <label className="label">WhatsApp</label>
            <input
              className="input"
              value={form.whatsapp || ""}
              onChange={(e) => setForm({ ...form, whatsapp: e.target.value })}
            />
          </div>
          <div>
            <label className="label">E-mail</label>
            <input
              className="input"
              value={form.email || ""}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>

          {/* Endereço com busca CEP (ViaCEP) */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="label">CEP</label>
              <div className="flex gap-1">
                <input
                  className="input flex-1"
                  value={form.cep || ""}
                  onChange={(e) => setForm({ ...form, cep: e.target.value })}
                  onBlur={async () => {
                    const cep = (form.cep || "").replace(/\D/g, "");
                    if (cep.length !== 8) return;
                    try {
                      const { data } = await api.get(`/utils/cep/${cep}`);
                      setForm((f: any) => ({
                        ...f,
                        logradouro: data.logradouro,
                        bairro: data.bairro,
                        cidade: data.cidade,
                        estado: data.estado,
                      }));
                    } catch {}
                  }}
                />
              </div>
            </div>
            <div className="col-span-2">
              <label className="label">Logradouro</label>
              <input
                className="input"
                value={form.logradouro || ""}
                onChange={(e) =>
                  setForm({ ...form, logradouro: e.target.value })
                }
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="label">Número</label>
              <input
                className="input"
                value={form.numero || ""}
                onChange={(e) => setForm({ ...form, numero: e.target.value })}
              />
            </div>
            <div className="col-span-2">
              <label className="label">Bairro</label>
              <input
                className="input"
                value={form.bairro || ""}
                onChange={(e) => setForm({ ...form, bairro: e.target.value })}
              />
            </div>
          </div>
          <div className="sm:col-span-2">
            <label className="label">
              Parte contrária (se já conhecida — p/ verificação de conflito)
            </label>
            <input
              className="input"
              value={form.parte_contraria || ""}
              onChange={(e) =>
                setForm({ ...form, parte_contraria: e.target.value })
              }
              onBlur={checarConflito}
            />
          </div>
        </div>

        {conflito && conflito.conflito && conflito.nivel !== "nenhum" && (
          <Alert
            className="mt-4"
            variant={conflito.nivel === "critico" ? "danger" : "warning"}
            title={
              conflito.nivel === "critico"
                ? "Conflito de interesses crítico (EOAB arts. 34-35)"
                : "Atenção: possível conflito de interesses"
            }
          >
            <ul className="space-y-1.5">
              {conflito.matches.map((m, i) => (
                <li key={i} className="flex flex-wrap items-center gap-1.5">
                  <Badge tone={conflito.nivel === "critico" ? "red" : "amber"}>
                    {m.papel.replace(/_/g, " ")}
                  </Badge>
                  <span>{m.descricao}</span>
                  {m.case_id && (
                    <Link
                      to={`/casos/${m.case_id}`}
                      className="font-medium underline hover:no-underline"
                    >
                      ver caso
                    </Link>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs opacity-80">
              Aviso ético — o cadastro não é bloqueado, mas registre a análise
              de conflito antes de prosseguir.
            </p>
          </Alert>
        )}

        <div className="flex justify-between mt-5">
          <Button
            variant="ghost"
            icon={<ShieldAlert size={15} />}
            disabled={conflitoLoading}
            onClick={async () => {
              const r = await checarConflito();
              if (r && r.nivel === "nenhum")
                toast.success("Nenhum conflito de interesses encontrado.");
              else if (!r)
                toast.info(
                  "Informe nome/documento ou parte contrária para verificar.",
                );
              // r.nivel !== "nenhum" → o Alert inline já exibe o conflito
            }}
          >
            {conflitoLoading ? "Verificando..." : "Verificar conflito"}
          </Button>
          <Button variant="primary" disabled={salvando} onClick={salvar}>
            {salvando ? "Salvando..." : "Salvar cliente"}
          </Button>
        </div>
      </Modal>
      {/* Modal: criar acesso ao Portal do Cliente */}
      {acessoModal && (
        <div className="modal-backdrop" onClick={() => setAcessoModal(null)}>
          <div
            className="card p-6 w-full max-w-sm"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold text-navy mb-1 flex items-center gap-1.5">
              <KeyRound size={16} /> Acesso ao Portal
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              {acessoModal.nome || acessoModal.razao_social} — o cliente trocará
              a senha no 1º login.
            </p>
            <div className="space-y-3">
              <input
                className="input"
                type="email"
                placeholder="E-mail de login"
                value={acessoForm.email}
                onChange={(e) =>
                  setAcessoForm({ ...acessoForm, email: e.target.value })
                }
              />
              <input
                className="input"
                type="text"
                placeholder="Senha inicial (mín. 8)"
                value={acessoForm.senha_inicial}
                onChange={(e) =>
                  setAcessoForm({
                    ...acessoForm,
                    senha_inicial: e.target.value,
                  })
                }
              />
              <button
                className="btn-primary w-full justify-center"
                onClick={async () => {
                  try {
                    await api.post(
                      `/clients/${acessoModal.id}/criar-acesso`,
                      acessoForm,
                    );
                    toast.error(
                      "Acesso criado! Informe o e-mail e a senha inicial ao cliente.",
                    );
                    setAcessoModal(null);
                  } catch (e: any) {
                    toast.error(e.response?.data?.detail || "Erro");
                  }
                }}
              >
                Criar acesso
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
