import { toast } from "../components/Toast";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Plus, Search, ShieldAlert } from "lucide-react";
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
  Alert,
  Badge,
  Button,
} from "../components/UI";
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

function openWhatsApp(phone: string, name: string) {
  const digits = soDigitos(phone);
  const br = digits.startsWith("55") ? digits : "55" + digits;
  const msg = encodeURIComponent(`Olá ${name}, tudo bem?`);
  window.open(`https://wa.me/${br}?text=${msg}`, "_blank");
}

export default function Clientes() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<Paged<Client> | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState(false);
  const [mostrarAvancado, setMostrarAvancado] = useState(false);
  const [conflito, setConflito] = useState<ConflitoCheck | null>(null);
  const [conflitoIndisponivel, setConflitoIndisponivel] = useState(false);
  const [conflitoLoading, setConflitoLoading] = useState(false);
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

  const role = user?.role || "";
  const podeRelatorioLgpd = ["superadmin", "admin", "socio"].includes(role);

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

  const limparCadastro = () => {
    setForm({ tipo: "PF", cidade: "Betim", estado: "MG" });
    setConflito(null);
    setConflitoIndisponivel(false);
    setMostrarAvancado(false);
  };

  // Checagem ética é best-effort e não bloqueia o cadastro. Falha técnica,
  // porém, é exibida explicitamente para nunca parecer "nenhum conflito".
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
      const { data: resultado } = await api.post<ConflitoCheck>(
        "/clients/checar-conflito",
        { nome, cpf, cnpj, parte_contraria },
      );
      setConflito(resultado);
      setConflitoIndisponivel(false);
      return resultado;
    } catch {
      setConflito(null);
      setConflitoIndisponivel(true);
      return "indisponivel";
    } finally {
      setConflitoLoading(false);
    }
  };

  const salvar = async () => {
    setSalvando(true);
    try {
      const { data: criado } = await api.post<Client>("/clients/", form);
      setModal(false);
      limparCadastro();
      // Depois do cadastro, a Ficha Mestra é o ponto canônico para continuar
      // o relacionamento: caso, documentos, pendências, Portal e IA.
      navigate(`/clientes/${criado.id}`);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const baixarRelatorioLgpd = async (clientId: string) => {
    try {
      const r = await api.get(`/clients/${clientId}/relatorio-lgpd`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `lgpd_${clientId.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível gerar o relatório LGPD",
      );
    }
  };

  const totalPages = data
    ? Math.max(1, Math.ceil(data.total / Math.max(1, data.page_size)))
    : 1;

  return (
    <div>
      <PageHeader
        title="Clientes"
        subtitle={`${data?.total ?? 0} ${(data?.total ?? 0) === 1 ? "cadastrado" : "cadastrados"} · localize e abra a Ficha Mestra`}
        actions={
          <button className="btn-gold" onClick={() => setModal(true)}>
            <Plus size={16} /> Novo cliente
          </button>
        }
      />

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
        <SkeletonTable rows={6} cols={4} />
      ) : data.data.length === 0 ? (
        <Empty
          titulo="Nenhum cliente cadastrado"
          descricao="Cadastre o primeiro cliente para abrir sua Ficha Mestra e então vincular casos, documentos e atendimentos."
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
                <th className="px-4 py-3">Cliente</th>
                <th className="px-4 py-3">Contato</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Privacidade</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(Array.isArray(data.data) ? data.data : []).map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 min-w-[220px]">
                    <Link
                      to={`/clientes/${c.id}`}
                      className="font-medium text-navy hover:text-bronze hover:underline"
                    >
                      {c.nome || c.razao_social}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                        {c.tipo}
                      </span>
                      <span>{c.documento_exibicao || "Documento não informado"}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    <div className="flex items-center gap-2">
                      <span>{c.whatsapp || c.telefone || c.email || "—"}</span>
                      {(c.whatsapp || c.telefone) && (
                        <button
                          onClick={() =>
                            openWhatsApp(
                              c.whatsapp || c.telefone || "",
                              c.nome || c.razao_social || "",
                            )
                          }
                          className="inline-flex min-h-[28px] min-w-[28px] items-center justify-center rounded-full bg-green-100 p-1 text-green-600 transition-colors hover:bg-green-200"
                          title="Abrir WhatsApp"
                          aria-label={`Abrir WhatsApp de ${c.nome || c.razao_social || "cliente"}`}
                        >
                          <svg
                            className="h-3.5 w-3.5"
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
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {podeRelatorioLgpd ? (
                      <button
                        type="button"
                        className="btn-ghost px-2 py-1 text-xs"
                        title="Gerar relatório LGPD"
                        onClick={() => baixarRelatorioLgpd(String(c.id))}
                      >
                        LGPD
                      </button>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
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
          limparCadastro();
        }}
        title="Novo cliente"
        wide
      >
        <div className="grid gap-4 sm:grid-cols-2">
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
                    className="btn-ghost whitespace-nowrap text-xs"
                    onClick={async () => {
                      try {
                        const { data: receita } = await api.get(
                          `/utils/cnpj/${(form.cnpj || "").replace(/\D/g, "")}`,
                        );
                        setForm({
                          ...form,
                          razao_social: receita.razao_social,
                          cep: receita.cep,
                          logradouro: receita.logradouro,
                          numero: receita.numero,
                          bairro: receita.bairro,
                          cidade: receita.cidade,
                          estado: receita.estado,
                          telefone: receita.telefone,
                        });
                      } catch (e: any) {
                        toast.error(
                          e.response?.data?.detail || "CNPJ não encontrado",
                        );
                      }
                    }}
                  >
                    Receita
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
              type="email"
              value={form.email || ""}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
        </div>

        <div className="mt-4 border-t border-slate-100 pt-3">
          <button
            type="button"
            className="btn-ghost px-0 text-xs"
            onClick={() => setMostrarAvancado((valor) => !valor)}
          >
            {mostrarAvancado
              ? "Ocultar informações adicionais"
              : "Adicionar endereço e dados para conflito"}
          </button>
        </div>

        {mostrarAvancado && (
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">CEP</label>
              <input
                className="input"
                value={form.cep || ""}
                onChange={(e) => setForm({ ...form, cep: e.target.value })}
                onBlur={async () => {
                  const cep = (form.cep || "").replace(/\D/g, "");
                  if (cep.length !== 8) return;
                  try {
                    const { data: endereco } = await api.get(`/utils/cep/${cep}`);
                    setForm((f: any) => ({
                      ...f,
                      logradouro: endereco.logradouro,
                      bairro: endereco.bairro,
                      cidade: endereco.cidade,
                      estado: endereco.estado,
                    }));
                  } catch {
                    // Endereço é complementar; erro de ViaCEP não impede cadastro.
                  }
                }}
              />
            </div>
            <div>
              <label className="label">Logradouro</label>
              <input
                className="input"
                value={form.logradouro || ""}
                onChange={(e) =>
                  setForm({ ...form, logradouro: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Número</label>
              <input
                className="input"
                value={form.numero || ""}
                onChange={(e) => setForm({ ...form, numero: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Bairro</label>
              <input
                className="input"
                value={form.bairro || ""}
                onChange={(e) => setForm({ ...form, bairro: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Cidade</label>
              <input
                className="input"
                value={form.cidade || ""}
                onChange={(e) => setForm({ ...form, cidade: e.target.value })}
              />
            </div>
            <div>
              <label className="label">UF</label>
              <input
                className="input"
                maxLength={2}
                value={form.estado || ""}
                onChange={(e) =>
                  setForm({ ...form, estado: e.target.value.toUpperCase() })
                }
              />
            </div>
            <div className="sm:col-span-2">
              <label className="label">
                Parte contrária (se já conhecida — verificação de conflito)
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
        )}

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
              {conflito.matches.map((match, i) => (
                <li key={i} className="flex flex-wrap items-center gap-1.5">
                  <Badge
                    tone={conflito.nivel === "critico" ? "red" : "amber"}
                  >
                    {match.papel.replace(/_/g, " ")}
                  </Badge>
                  <span>{match.descricao}</span>
                  {match.documento_mascarado && (
                    <span className="font-mono text-xs opacity-70">
                      {match.documento_mascarado}
                    </span>
                  )}
                  {match.case_id && (
                    <Link
                      to={`/casos/${match.case_id}`}
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

        <div className="mt-5 flex justify-between gap-3">
          <Button
            variant="ghost"
            icon={<ShieldAlert size={15} />}
            disabled={conflitoLoading}
            onClick={async () => {
              const resultado = await checarConflito();
              if (resultado === "indisponivel") {
                toast.error("Não foi possível verificar conflito neste momento.");
              } else if (resultado && resultado.nivel === "nenhum") {
                toast.success("Nenhum conflito de interesses encontrado.");
              } else if (!resultado) {
                toast.info(
                  "Informe nome/documento ou parte contrária para verificar.",
                );
              }
            }}
          >
            {conflitoLoading ? "Verificando..." : "Verificar conflito"}
          </Button>
          <Button variant="primary" disabled={salvando} onClick={salvar}>
            {salvando ? "Salvando..." : "Salvar e abrir ficha"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
