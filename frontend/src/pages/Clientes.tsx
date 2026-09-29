import { toast } from "../components/Toast";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  Plus,
  Search,
  ShieldAlert,
  KeyRound,
  FileSignature,
  Trash2,
} from "lucide-react";
import api from "../lib/api";
import { soDigitos } from "../utils/phone";
import type { Client, Paged } from "../types";
import { useAuth } from "../stores/auth";
import {
  PageHeader,
  StatusBadge,
  Modal,
  Empty,
  EmptyState,
  SkeletonTable,
  fmtDate,
  Alert,
  Badge,
  Button,
} from "../components/UI";
import { ClientesStats } from "../components/Dashboards";
import { VerificarReceita } from "../components/Infosimples";

// Resposta de POST /clients/checar-conflito. O NOME vem completo (dever ético:
// sem ele o alerta é inacionável), mas o CPF/CNPJ vem apenas MASCARADO — o
// endpoint cruza a base inteira ignorando a segregação de carteira, então não
// devolve documento em claro de cliente de outro advogado.
type ConflitoNivel = "nenhum" | "atencao" | "critico";
interface ConflitoMatch {
  tipo: string;
  case_id?: string;
  client_id?: string;
  papel: string;
  nome?: string;
  documento_mascarado?: string | null;
  descricao: string;
}
interface ConflitoCheck {
  conflito: boolean;
  nivel: ConflitoNivel;
  matches: ConflitoMatch[];
}
type ResultadoConflito = ConflitoCheck | "indisponivel" | null;

interface PecaAdmissao {
  id: string;
  titulo: string;
  tipo: string;
  status: string;
  admission_kind: string | null;
  created_at: string | null;
}

function openWhatsApp(phone: string, name: string) {
  const digits = soDigitos(phone);
  const br = digits.startsWith("55") ? digits : "55" + digits;
  const msg = encodeURIComponent(`Olá ${name}, tudo bem?`);
  window.open(`https://wa.me/${br}?text=${msg}`, "_blank");
}

export default function Clientes() {
  const { user } = useAuth();
  const [data, setData] = useState<Paged<Client> | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState(false);
  const [conflito, setConflito] = useState<ResultadoConflito>(null);
  const [conflitoLoading, setConflitoLoading] = useState(false);
  const [conflitoIndisponivel, setConflitoIndisponivel] = useState(false);
  const [acessoModal, setAcessoModal] = useState<any>(null);
  // Exclusão de cliente: modal de confirmação + dependências bloqueantes.
  // O backend responde 409 com { mensagem, bloqueios } quando há caso em
  // representação ativa; ?forcar=true prossegue com decisão registrada.
  const [excluirAlvo, setExcluirAlvo] = useState<Client | null>(null);
  const [excluirBloqueios, setExcluirBloqueios] = useState<string[]>([]);
  const [excluirForcar, setExcluirForcar] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
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
  const seq = useRef(0);

  const role = user?.role || "";
  const podeCriarAcesso = ["superadmin", "admin", "socio", "advogado"].includes(
    role,
  );
  const podeRelatorioLgpd = ["superadmin", "admin", "socio"].includes(role);
  // Exclusão de cliente (soft delete com trilha de auditoria): o backend
  // exige admin/sócio via require_roles — superadmin passa pela hierarquia
  // de níveis. O botão espelha o gate; quem não pode, não vê a ação.
  const podeExcluir = ["superadmin", "admin", "socio"].includes(role);
  // Emissão/consulta de procuração e contrato é ato jurídico: o backend exige
  // advogado+ (requer_advogado). O botão espelha esse gate — não o substitui.
  const podeVerAdmissao = ["superadmin", "admin", "socio", "advogado"].includes(
    role,
  );
  const [admissaoModal, setAdmissaoModal] = useState<Client | null>(null);
  const [admissaoPecas, setAdmissaoPecas] = useState<PecaAdmissao[] | null>(
    null,
  );
  const [admissaoLoading, setAdmissaoLoading] = useState(false);
  const admissaoReq = useRef(0);
  const [admissaoPoderes, setAdmissaoPoderes] = useState({
    tipo_poderes: "ad_judicia",
    permite_substabelecimento: true,
    poderes_especiais: "",
  });

  const load = () => {
    const my = ++seq.current;
    setErro(false);
    return api
      .get("/clients/", {
        params: { search: search || undefined, page, page_size: 50 },
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
    const t = setTimeout(load, search ? 350 : 0);
    return () => clearTimeout(t);
  }, [search, page]);

  // Exclusão: 1ª tentativa sem forcar; 409 devolve bloqueios e o modal
  // passa a oferecer a confirmação forçada (decisão explícita, auditable).
  const confirmarExclusao = async () => {
    if (!excluirAlvo) return;
    setExcluindo(true);
    try {
      // forcar via params do axios: o extrator de contrato FE↔BE
      // (app/utils/api_contract.py) lê o path literal — query condicional
      // no template quebraria o match com DELETE /clients/{client_id}.
      await api.delete(
        `/clients/${excluirAlvo.id}`,
        excluirForcar ? { params: { forcar: true } } : undefined,
      );
      toast.success(
        "Cliente excluído. A decisão ficou registrada na trilha de auditoria.",
      );
      setExcluirAlvo(null);
      load();
    } catch (e: any) {
      const det = e.response?.data?.detail;
      if (e.response?.status === 409 && det?.bloqueios) {
        setExcluirBloqueios(
          Array.isArray(det.bloqueios)
            ? det.bloqueios.map(String)
            : [String(det.bloqueios)],
        );
        toast.error(det.mensagem || "Exclusão bloqueada pelas dependências.");
      } else {
        toast.error(
          typeof det === "string" ? det : "Não foi possível excluir o cliente",
        );
      }
    } finally {
      setExcluindo(false);
    }
  };

  // Checagem assistiva de conflito de interesses. Base ética: Código de Ética
  // e Disciplina da OAB (Res. CFOAB 02/2015), especialmente arts. 19 a 22.
  // Falha técnica nunca equivale a ausência de conflito e não decide a admissão.
  const checarConflito = async (): Promise<ResultadoConflito> => {
    const nome = (form.nome || form.razao_social || "").trim();
    const cpf = form.cpf;
    const cnpj = form.cnpj;
    const parte_contraria = form.parte_contraria;
    if (!cpf && !cnpj && nome.length < 4 && !parte_contraria) {
      setConflito(null);
      setConflitoIndisponivel(false);
      return null;
    }
    setConflitoLoading(true);
    try {
      const { data } = await api.post<ConflitoCheck>(
        "/clients/checar-conflito",
        {
          nome,
          cpf,
          cnpj,
          parte_contraria,
        },
      );
      setConflito(data);
      setConflitoIndisponivel(false);
      return data;
    } catch {
      // Falha da checagem NÃO parece "nenhum conflito": fica explícita que a
      // verificação não pôde ser feita (CED/OAB, arts. 19 a 22).
      setConflito(null);
      setConflitoIndisponivel(true);
      return "indisponivel";
    } finally {
      setConflitoLoading(false);
    }
  };

  const carregarAdmissao = async (c: Client) => {
    const req = ++admissaoReq.current;
    setAdmissaoModal(c);
    setAdmissaoPecas(null);
    setAdmissaoLoading(true);
    try {
      const { data } = await api.get<PecaAdmissao[]>(
        `/clients/${c.id}/pecas-geradas`,
      );
      if (req !== admissaoReq.current) return;
      setAdmissaoPecas(Array.isArray(data) ? data : []);
    } catch (e: any) {
      if (req !== admissaoReq.current) return;
      setAdmissaoPecas([]);
      toast.error(
        e.response?.data?.detail ||
          "Falha ao carregar os documentos de admissão",
      );
    } finally {
      if (req === admissaoReq.current) setAdmissaoLoading(false);
    }
  };

  const regerarAdmissao = async () => {
    if (!admissaoModal) return;
    const alvo = admissaoModal;
    setAdmissaoLoading(true);
    try {
      await api.post(`/clients/${alvo.id}/gerar-documentos`, {
        forcar_novo: true,
        tipo_poderes: admissaoPoderes.tipo_poderes,
        permite_substabelecimento: admissaoPoderes.permite_substabelecimento,
        poderes_especiais: admissaoPoderes.poderes_especiais.trim() || null,
      });
      toast.success("Procuração e contrato regerados como novos rascunhos.");
      await carregarAdmissao(alvo);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao regerar os documentos");
      setAdmissaoLoading(false);
    }
  };

  const baixarPecaPdf = async (peca: PecaAdmissao) => {
    try {
      const r = await api.get(`/legal-docs/${peca.id}/pdf-minuta`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${peca.admission_kind || "documento"}-${peca.id.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao baixar o PDF");
    }
  };

  const navigate = useNavigate();

  const salvar = async () => {
    setSalvando(true);
    try {
      const { data: criado } = await api.post<Client>("/clients/", form);
      setModal(false);
      setForm({ tipo: "PF", cidade: "Betim", estado: "MG" });
      setConflito(null);
      setConflitoIndisponivel(false);
      if (page !== 1) setPage(1);
      else load();
      toast.success("Cliente cadastrado.");
      if (criado?.id) navigate(`/clientes/${criado.id}`);

      if (criado?.id && podeVerAdmissao) {
        void api
          .get<PecaAdmissao[]>(`/clients/${criado.id}/pecas-geradas`)
          .then(({ data: pecas }) => {
            if (Array.isArray(pecas) && pecas.length) {
              toast.success(
                "Procuração e contrato de honorários gerados como rascunho.",
              );
            }
          })
          .catch(() => {
            /* confirmação acessória: cadastro já concluído */
          });
      }
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const totalPages = data
    ? Math.max(1, Math.ceil(data.total / Math.max(1, data.page_size)))
    : 1;

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
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
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
        <SkeletonTable rows={6} cols={6} />
      ) : data.data.length === 0 ? (
        <Empty
          titulo="Nenhum cliente cadastrado"
          descricao="O cadastro de clientes centraliza contatos, documentos e casos de cada pessoa ou empresa. Cadastre o primeiro para vinculá-lo aos casos."
          acao={
            <Button
              variant="primary"
              icon={<Plus size={16} />}
              onClick={() => setModal(true)}
            >
              Cadastrar um cliente
            </Button>
          }
        />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Nome / Razão</th>
                <th className="px-4 py-3">Tipo</th>
                <th className="px-4 py-3">CPF / CNPJ</th>
                <th className="px-4 py-3 text-right">Ações</th>
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
                    {c.documento_exibicao || "—"}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button
                      title="Dossiê Digital"
                      className="text-bronze hover:text-bronze-dark inline-flex min-h-[24px] min-w-[24px] items-center justify-center px-1.5 font-medium text-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        window.location.href = `/clientes/${c.id}`;
                      }}
                    >
                      📋
                    </button>
                    {podeCriarAcesso && (
                      <button
                        title="Acesso ao Portal"
                        className="text-navy hover:text-gold inline-flex min-h-[24px] min-w-[24px] items-center justify-center px-1.5"
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
                    )}
                    {podeVerAdmissao && (
                      <button
                        title="Procuração e contrato de honorários"
                        className="text-navy hover:text-gold inline-flex min-h-[24px] min-w-[24px] items-center justify-center px-1.5"
                        onClick={(e) => {
                          e.stopPropagation();
                          carregarAdmissao(c);
                        }}
                      >
                        <FileSignature size={14} />
                      </button>
                    )}
                    {podeRelatorioLgpd && (
                      <button
                        title="Relatório LGPD"
                        className="text-navy hover:text-gold inline-flex min-h-[24px] min-w-[24px] items-center justify-center px-1.5"
                        onClick={async (e) => {
                          e.stopPropagation();
                          try {
                            const r = await api.get(
                              `/clients/${c.id}/relatorio-lgpd`,
                              {
                                responseType: "blob",
                              },
                            );
                            const url = URL.createObjectURL(r.data);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = `lgpd_${c.id.slice(0, 8)}.pdf`;
                            a.click();
                            URL.revokeObjectURL(url);
                          } catch (e: any) {
                            toast.error(
                              e.response?.data?.detail ||
                                "Não foi possível gerar o relatório LGPD",
                            );
                          }
                        }}
                      >
                        📄
                      </button>
                    )}
                    {podeExcluir && (
                      <button
                        title="Excluir cliente"
                        className="inline-flex min-h-[24px] min-w-[24px] items-center justify-center px-1.5 text-red-500/70 hover:text-red-600"
                        onClick={(e) => {
                          e.stopPropagation();
                          setExcluirBloqueios([]);
                          setExcluirForcar(false);
                          setExcluirAlvo(c);
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    <div className="flex min-w-[180px] items-center gap-2">
                      <span className="min-w-0 truncate">
                        {c.whatsapp || c.telefone || c.email || "—"}
                      </span>
                      {(c.whatsapp || c.telefone) && (
                        <button
                          onClick={() =>
                            openWhatsApp(
                              c.whatsapp || c.telefone || "",
                              c.nome || "",
                            )
                          }
                          className="inline-flex min-h-[24px] min-w-[24px] items-center justify-center rounded-full bg-green-100 p-1 text-green-600 transition-colors hover:bg-green-200"
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
                    </div>
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
          {totalPages > 1 && (
            <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-4 py-3 text-sm">
              <span className="text-slate-500">
                Página {data.page} de {totalPages}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  disabled={data.page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Anterior
                </Button>
                <Button
                  variant="ghost"
                  disabled={data.page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  Próxima
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      <Modal
        open={modal}
        onClose={() => {
          setModal(false);
          setConflito(null);
          setConflitoIndisponivel(false);
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
                <div className="flex gap-2">
                  <input
                    className="input flex-1"
                    value={form.cpf || ""}
                    onChange={(e) => setForm({ ...form, cpf: e.target.value })}
                    onBlur={checarConflito}
                  />
                  <VerificarReceita
                    tipo="cpf"
                    documento={form.cpf || ""}
                    onUsarNome={(nome) => setForm((f: any) => ({ ...f, nome }))}
                  />
                </div>
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
                  <VerificarReceita
                    tipo="cnpj"
                    documento={form.cnpj || ""}
                    onUsarNome={(razao_social) =>
                      setForm((f: any) => ({ ...f, razao_social }))
                    }
                  />
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

        {conflitoIndisponivel && (
          <Alert
            className="mt-4"
            variant="warning"
            title="Conflito não pôde ser verificado"
          >
            A consulta de conflito está indisponível neste momento. O cadastro
            continua permitido, mas a análise de conflito deve ser realizada
            antes da atuação no caso.
          </Alert>
        )}

        {conflito &&
          conflito !== "indisponivel" &&
          conflito.conflito &&
          conflito.nivel !== "nenhum" && (
            <Alert
              className="mt-4"
              variant={conflito.nivel === "critico" ? "danger" : "warning"}
              title={
                conflito.nivel === "critico"
                  ? "Conflito de interesses crítico"
                  : "Atenção: possível conflito de interesses"
              }
            >
              <ul className="space-y-1.5">
                {conflito.matches.map((m, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-1.5">
                    <Badge
                      tone={conflito.nivel === "critico" ? "red" : "amber"}
                    >
                      {m.papel.replace(/_/g, " ")}
                    </Badge>
                    <span>{m.descricao}</span>
                    {m.documento_mascarado && (
                      <span className="font-mono text-xs opacity-70">
                        {m.documento_mascarado}
                      </span>
                    )}
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
              if (r && r !== "indisponivel" && r.nivel === "nenhum")
                toast.success("Nenhum conflito de interesses encontrado.");
              else if (!r)
                toast.info(
                  "Informe nome/documento ou parte contrária para verificar.",
                );
            }}
          >
            {conflitoLoading ? "Verificando..." : "Verificar conflito"}
          </Button>
          <Button variant="primary" disabled={salvando} onClick={salvar}>
            {salvando ? "Salvando..." : "Salvar cliente"}
          </Button>
        </div>
      </Modal>

      {admissaoModal && podeVerAdmissao && (
        <Modal
          open
          onClose={() => setAdmissaoModal(null)}
          title="Documentos de admissão"
        >
          <p className="text-xs text-slate-500 mb-3">
            {admissaoModal.nome || admissaoModal.razao_social} — procuração e
            contrato de honorários emitidos no cadastro. Saem em papel timbrado
            do escritório e permanecem <strong>rascunho</strong> até a revisão e
            a assinatura do advogado.
          </p>
          {admissaoLoading && (
            <p className="text-sm text-slate-500">Carregando…</p>
          )}
          {!admissaoLoading && admissaoPecas?.length === 0 && (
            <Alert variant="warning">
              Nenhum documento de admissão para este cliente. Use "Gerar
              novamente" para emitir a procuração e o contrato.
            </Alert>
          )}
          {!admissaoLoading && !!admissaoPecas?.length && (
            <ul className="divide-y divide-slate-100 text-sm">
              {admissaoPecas.map((peca) => (
                <li
                  key={peca.id}
                  className="flex items-center justify-between gap-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-navy">
                      {peca.titulo}
                    </p>
                    <p className="text-xs text-slate-500">
                      {peca.tipo} · {peca.status}
                      {peca.created_at ? ` · ${fmtDate(peca.created_at)}` : ""}
                    </p>
                  </div>
                  <Button
                    variant="secondary"
                    onClick={() => baixarPecaPdf(peca)}
                  >
                    PDF
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-5 rounded-lg border border-slate-200 p-3">
            <p className="mb-2 text-xs font-semibold text-navy">
              Poderes da nova procuração
            </p>
            <p className="mb-3 text-xs text-slate-500">
              Gerar novamente cria uma versão nova{" "}
              <strong>com estes poderes</strong> — confira antes, porque é o que
              o cliente assinará. A versão anterior continua no histórico.
            </p>
            <div className="space-y-2">
              <select
                className="input w-full"
                value={admissaoPoderes.tipo_poderes}
                onChange={(e) =>
                  setAdmissaoPoderes({
                    ...admissaoPoderes,
                    tipo_poderes: e.target.value,
                  })
                }
              >
                <option value="ad_judicia">Ad judicia (foro em geral)</option>
                <option value="ad_judicia_et_extra">
                  Ad judicia et extra (judicial e extrajudicial)
                </option>
                <option value="especiais">Poderes especiais</option>
              </select>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={admissaoPoderes.permite_substabelecimento}
                  onChange={(e) =>
                    setAdmissaoPoderes({
                      ...admissaoPoderes,
                      permite_substabelecimento: e.target.checked,
                    })
                  }
                />
                Permite substabelecimento
              </label>
              <input
                className="input w-full"
                placeholder="Poderes especiais (art. 105 do CPC) — opcional"
                value={admissaoPoderes.poderes_especiais}
                onChange={(e) =>
                  setAdmissaoPoderes({
                    ...admissaoPoderes,
                    poderes_especiais: e.target.value,
                  })
                }
              />
            </div>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setAdmissaoModal(null)}>
              Fechar
            </Button>
            <Button
              variant="primary"
              disabled={admissaoLoading}
              onClick={regerarAdmissao}
            >
              Gerar novamente
            </Button>
          </div>
        </Modal>
      )}

      {acessoModal && podeCriarAcesso && (
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
                type="password"
                autoComplete="new-password"
                placeholder="Senha inicial (mín. 10, com letra, número e símbolo)"
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
                    toast.success(
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

      {excluirAlvo && podeExcluir && (
        <div className="modal-backdrop" onClick={() => setExcluirAlvo(null)}>
          <div
            className="card p-6 w-full max-w-sm"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold text-navy mb-1 flex items-center gap-1.5">
              <Trash2 size={16} /> Excluir cliente
            </h3>
            <p className="text-xs text-slate-500 mb-3">
              {excluirAlvo.nome || excluirAlvo.razao_social} — o cliente sai da
              listagem (exclusão lógica). Documentos, casos e a trilha de
              auditoria permanecem preservados, conforme a LGPD.
            </p>
            {excluirBloqueios.length > 0 && (
              <Alert
                variant="warning"
                title="Exclusão bloqueada pelas dependências"
                className="mb-3"
              >
                <ul className="list-disc pl-4 text-xs">
                  {excluirBloqueios.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              </Alert>
            )}
            {excluirBloqueios.length > 0 && (
              <label className="mb-3 flex items-start gap-2 text-xs text-slate-600">
                <input
                  type="checkbox"
                  checked={excluirForcar}
                  onChange={(e) => setExcluirForcar(e.target.checked)}
                  className="mt-0.5"
                />
                Confirmar mesmo assim (forçar) — a decisão é registrada na
                auditoria e fica associada ao seu usuário.
              </label>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="ghost"
                disabled={excluindo}
                onClick={() => setExcluirAlvo(null)}
              >
                Cancelar
              </Button>
              <Button
                variant="danger"
                disabled={
                  excluindo || (excluirBloqueios.length > 0 && !excluirForcar)
                }
                onClick={confirmarExclusao}
              >
                {excluindo ? "Excluindo..." : "Excluir"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
