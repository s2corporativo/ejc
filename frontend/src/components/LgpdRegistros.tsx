// ── src/components/LgpdRegistros.tsx ─────────────────────────────────────────
// Vertical LGPD como produto: Registro de Operações de Tratamento (ROPA,
// LGPD art. 37) por cliente + gerador de RIPD (art. 38) em PDF Visual Law.
// Padrão client-scoped espelhado de SociedadesCliente.tsx: seletor de cliente,
// header de resumo, tabela do ROPA com linha expansível, forms de criar/editar
// e download de PDF via blob (padrão TributarioFiscal.tsx / SalaDeGuerra.tsx).
//
// O registro guarda apenas METADADOS da operação (categorias de dados e de
// titulares), nunca dados pessoais de titulares reais.
import { useEffect, useState, type ReactNode } from "react";
import {
  ShieldCheck,
  Plus,
  Trash2,
  Pencil,
  FileText,
  Loader2,
  AlertTriangle,
  Database,
  Globe,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Modal, Spinner, Empty } from "./UI";
import type { Client } from "../types";

// ── Tipos do contrato /lgpd/registros ────────────────────────────────────────
type Risco = "baixo" | "medio" | "alto";

interface RegistroTratamento {
  id: number;
  client_id: number | string;
  nome_operacao: string;
  finalidade: string;
  base_legal: string;
  categorias_dados: string;
  categorias_titulares: string;
  dados_sensiveis: boolean;
  compartilhamento: string | null;
  transferencia_internacional: boolean;
  paises_transferencia: string | null;
  prazo_retencao: string | null;
  medidas_seguranca: string | null;
  risco: Risco;
  fatores_risco: string[] | null;
  created_at: string;
}

interface Resumo {
  total_operacoes: number;
  com_dados_sensiveis: number;
  com_transferencia_internacional: number;
  distribuicao_risco: { baixo: number; medio: number; alto: number };
}

// Bases legais do tratamento — art. 7º (dados comuns) e art. 11 (sensíveis).
const BASES_LEGAIS: { valor: string; label: string }[] = [
  { valor: "consentimento", label: "Consentimento (art. 7º I / 11 I)" },
  { valor: "contrato", label: "Execução de contrato (art. 7º V)" },
  { valor: "obrigacao_legal", label: "Obrigação legal/regulatória (art. 7º II)" },
  { valor: "legitimo_interesse", label: "Legítimo interesse (art. 7º IX)" },
  { valor: "exercicio_direitos", label: "Exercício de direitos em processo (art. 7º VI)" },
  { valor: "protecao_vida", label: "Proteção da vida (art. 7º VII)" },
  { valor: "tutela_saude", label: "Tutela da saúde (art. 7º VIII / 11 II f)" },
  { valor: "politica_publica", label: "Execução de política pública (art. 7º III)" },
  { valor: "pesquisa", label: "Estudos por órgão de pesquisa (art. 7º IV)" },
  { valor: "credito", label: "Proteção ao crédito (art. 7º X)" },
];

const BASE_LABEL: Record<string, string> = Object.fromEntries(
  BASES_LEGAIS.map((b) => [b.valor, b.label]),
);

const RISCO_BADGE: Record<Risco, string> = {
  baixo: "bg-success-100 text-success-700 border border-success-200",
  medio: "bg-warn-100 text-warn-700 border border-warn-200",
  alto: "bg-danger-100 text-danger-700 border border-danger-200",
};

const RISCO_BARRA: Record<Risco, string> = {
  baixo: "bg-success-500",
  medio: "bg-warn-500",
  alto: "bg-danger-500",
};

const FORM_VAZIO = {
  nome_operacao: "",
  finalidade: "",
  base_legal: "consentimento",
  categorias_dados: "",
  categorias_titulares: "",
  dados_sensiveis: false,
  compartilhamento: "",
  transferencia_internacional: false,
  paises_transferencia: "",
  prazo_retencao: "",
  medidas_seguranca: "",
};

type FormState = typeof FORM_VAZIO;

function baseLabel(v: string) {
  return BASE_LABEL[v] || v.replace(/_/g, " ");
}

function truncar(s: string, n = 90) {
  if (!s) return "—";
  return s.length > n ? `${s.slice(0, n).trimEnd()}…` : s;
}

function nomeCliente(c: Client) {
  return c.nome || c.razao_social || c.cnpj || c.cpf || c.id;
}

function detalheErro(e: any, fallback: string) {
  return e?.response?.data?.detail || fallback;
}

export default function LgpdRegistros() {
  // Cliente selecionado (client-scoped)
  const [clientes, setClientes] = useState<Client[]>([]);
  const [clientId, setClientId] = useState("");

  // Dados do ROPA
  const [lista, setLista] = useState<RegistroTratamento[] | null>(null);
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [expandido, setExpandido] = useState<number | null>(null);

  // Formulário criar/editar
  const [modal, setModal] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>({ ...FORM_VAZIO });
  const [salvando, setSalvando] = useState(false);
  const [erroForm, setErroForm] = useState<string | null>(null);

  // RIPD PDF
  const [gerandoRipd, setGerandoRipd] = useState(false);

  useEffect(() => {
    api
      .get("/clients/", { params: { page_size: 100 } })
      .then((r) => setClientes(r.data?.data ?? []))
      .catch(() => setClientes([]));
  }, []);

  const carregar = () => {
    if (!clientId) {
      setLista(null);
      setResumo(null);
      return;
    }
    setLista(null);
    api
      .get("/lgpd/registros", { params: { client_id: clientId } })
      .then((r) => setLista(Array.isArray(r.data) ? r.data : (r.data?.data ?? [])))
      .catch(() => setLista([]));
    api
      .get(`/lgpd/registros/${clientId}/resumo`)
      .then((r) => setResumo(r.data))
      .catch(() => setResumo(null));
  };
  useEffect(carregar, [clientId]);

  // ── Ações ──────────────────────────────────────────────────────────────
  const abrirNovo = () => {
    if (!clientId) {
      toast.error("Selecione o cliente antes de registrar uma operação.");
      return;
    }
    setEditId(null);
    setForm({ ...FORM_VAZIO });
    setErroForm(null);
    setModal(true);
  };

  const abrirEdicao = (r: RegistroTratamento) => {
    setEditId(r.id);
    setForm({
      nome_operacao: r.nome_operacao,
      finalidade: r.finalidade,
      base_legal: r.base_legal,
      categorias_dados: r.categorias_dados,
      categorias_titulares: r.categorias_titulares,
      dados_sensiveis: r.dados_sensiveis,
      compartilhamento: r.compartilhamento ?? "",
      transferencia_internacional: r.transferencia_internacional,
      paises_transferencia: r.paises_transferencia ?? "",
      prazo_retencao: r.prazo_retencao ?? "",
      medidas_seguranca: r.medidas_seguranca ?? "",
    });
    setErroForm(null);
    setModal(true);
  };

  const salvar = async () => {
    setErroForm(null);
    if (!form.nome_operacao.trim()) {
      setErroForm("Informe o nome da operação de tratamento.");
      return;
    }
    if (!form.finalidade.trim()) {
      setErroForm("Descreva a finalidade do tratamento (art. 6º I — finalidade).");
      return;
    }
    if (form.transferencia_internacional && !form.paises_transferencia.trim()) {
      setErroForm("Informe os países de transferência internacional (art. 33).");
      return;
    }
    setSalvando(true);
    try {
      const campos = {
        nome_operacao: form.nome_operacao.trim(),
        finalidade: form.finalidade.trim(),
        base_legal: form.base_legal,
        categorias_dados: form.categorias_dados.trim(),
        categorias_titulares: form.categorias_titulares.trim(),
        dados_sensiveis: form.dados_sensiveis,
        compartilhamento: form.compartilhamento.trim() || null,
        transferencia_internacional: form.transferencia_internacional,
        paises_transferencia: form.transferencia_internacional
          ? form.paises_transferencia.trim() || null
          : null,
        prazo_retencao: form.prazo_retencao.trim() || null,
        medidas_seguranca: form.medidas_seguranca.trim() || null,
      };
      if (editId != null) {
        await api.patch(`/lgpd/registros/${editId}`, campos);
        toast.success("Operação de tratamento atualizada.");
      } else {
        await api.post("/lgpd/registros", { client_id: clientId, ...campos });
        toast.success("Operação de tratamento registrada.");
      }
      setModal(false);
      setForm({ ...FORM_VAZIO });
      setEditId(null);
      carregar();
    } catch (e: any) {
      setErroForm(detalheErro(e, "Erro ao salvar a operação de tratamento."));
    } finally {
      setSalvando(false);
    }
  };

  const excluir = async (r: RegistroTratamento) => {
    if (
      !window.confirm(
        `Remover a operação "${r.nome_operacao}" do registro (ROPA)?`,
      )
    )
      return;
    try {
      await api.delete(`/lgpd/registros/${r.id}`);
      toast.success("Operação removida do registro.");
      if (expandido === r.id) setExpandido(null);
      carregar();
    } catch (e: any) {
      toast.error(detalheErro(e, "Erro ao remover a operação."));
    }
  };

  // Mesmo padrão dos demais PDFs Visual Law (TributarioFiscal.tsx): POST → download_url → blob
  const gerarRipd = async () => {
    if (!clientId) return;
    setGerandoRipd(true);
    try {
      const r = await api.post(`/lgpd/registros/${clientId}/ripd`);
      const downloadUrl: string | undefined = r.data?.download_url;
      if (!downloadUrl) throw new Error("download_url ausente na resposta");
      // baseURL do client é /api — remove o prefixo se o backend devolver a URL completa
      const blob = await api.get(downloadUrl.replace(/^\/api/, ""), {
        responseType: "blob",
      });
      const url = URL.createObjectURL(blob.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "ripd-relatorio-impacto.pdf";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("RIPD (Visual Law) gerado.");
    } catch (e: any) {
      toast.error(detalheErro(e, "Falha ao gerar o RIPD em PDF."));
    } finally {
      setGerandoRipd(false);
    }
  };

  const distrib = resumo?.distribuicao_risco ?? { baixo: 0, medio: 0, alto: 0 };
  const totalRisco = distrib.baixo + distrib.medio + distrib.alto || 1;

  return (
    <div
      id="lgpd-registros"
      className="card p-4 mb-4 border-l-4 border-primary-500 scroll-mt-4"
    >
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <h2 className="font-serif font-semibold text-navy flex items-center gap-2">
          <ShieldCheck size={16} className="text-gold-600" /> Registro de
          Operações de Tratamento (ROPA)
        </h2>
        <div className="ml-auto flex items-center gap-2">
          <button
            className="btn-secondary text-sm flex items-center gap-1"
            disabled={gerandoRipd || !clientId || !(resumo?.total_operacoes ?? 0)}
            onClick={gerarRipd}
            title="Relatório de Impacto à Proteção de Dados (art. 38)"
          >
            {gerandoRipd ? (
              <>
                <Loader2 size={14} className="animate-spin" /> Gerando…
              </>
            ) : (
              <>
                <FileText size={14} /> Gerar RIPD (Visual Law)
              </>
            )}
          </button>
          <button
            className="btn-gold text-sm flex items-center gap-1"
            onClick={abrirNovo}
          >
            <Plus size={14} /> Nova operação
          </button>
        </div>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Registro das atividades de tratamento por cliente (LGPD art. 37) — base
        para o RIPD e para a prestação de contas ao encarregado (DPO) e à ANPD.
      </p>

      {/* Aviso de privacidade: só metadados */}
      <div className="mb-4 p-2.5 rounded-lg bg-primary-50 border border-primary-100 flex items-start gap-2 text-xs text-primary-800">
        <AlertTriangle size={14} className="shrink-0 mt-0.5 text-primary-600" />
        <span>
          Este registro guarda apenas <b>metadados</b> da operação (categorias de
          dados e de titulares, finalidade, base legal). <b>Nunca</b> insira aqui
          dados pessoais de titulares reais — nomes, CPFs ou documentos.
        </span>
      </div>

      {/* Seletor de cliente */}
      <div className="flex flex-wrap items-end gap-2 mb-4">
        <div className="flex-1 min-w-[220px]">
          <label className="label text-xs">Cliente (controlador)</label>
          <select
            className="input text-sm"
            value={clientId}
            onChange={(e) => {
              setClientId(e.target.value);
              setExpandido(null);
            }}
          >
            <option value="">Selecione o cliente…</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>
                {nomeCliente(c)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {!clientId ? (
        <Empty message="Selecione um cliente para ver o registro de tratamento" />
      ) : (
        <>
          {/* Header de resumo */}
          {resumo && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-4">
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-500">
                  <Database size={12} /> Operações
                </div>
                <div className="text-2xl font-bold text-navy mt-1">
                  {resumo.total_operacoes}
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-500">
                  <AlertTriangle size={12} /> Dados sensíveis
                </div>
                <div className="text-2xl font-bold text-navy mt-1">
                  {resumo.com_dados_sensiveis}
                </div>
                <div className="text-[10px] text-slate-400">art. 11</div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-500">
                  <Globe size={12} /> Transf. internacional
                </div>
                <div className="text-2xl font-bold text-navy mt-1">
                  {resumo.com_transferencia_internacional}
                </div>
                <div className="text-[10px] text-slate-400">art. 33</div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1.5">
                  Distribuição de risco
                </div>
                <div className="flex h-2.5 rounded-full overflow-hidden bg-slate-100 mb-1.5">
                  {(["baixo", "medio", "alto"] as Risco[]).map((r) =>
                    distrib[r] > 0 ? (
                      <div
                        key={r}
                        className={RISCO_BARRA[r]}
                        style={{ width: `${(distrib[r] / totalRisco) * 100}%` }}
                        title={`${r}: ${distrib[r]}`}
                      />
                    ) : null,
                  )}
                </div>
                <div className="flex items-center gap-2 text-[10px] text-slate-500">
                  <span className="text-success-700">B {distrib.baixo}</span>
                  <span className="text-warn-700">M {distrib.medio}</span>
                  <span className="text-danger-700">A {distrib.alto}</span>
                </div>
              </div>
            </div>
          )}

          {/* Tabela do ROPA */}
          {lista === null ? (
            <Spinner />
          ) : lista.length === 0 ? (
            <Empty message="Nenhuma operação de tratamento registrada para este cliente" />
          ) : (
            <div className="space-y-2">
              {lista.map((r) => {
                const aberto = expandido === r.id;
                return (
                  <div
                    key={r.id}
                    className="rounded-lg border border-slate-200 overflow-hidden"
                  >
                    <div className="flex flex-wrap items-center gap-3 p-3">
                      <button
                        className="flex-1 min-w-[200px] text-left flex items-start gap-2"
                        onClick={() => setExpandido(aberto ? null : r.id)}
                      >
                        <span className="text-slate-300 mt-0.5">
                          {aberto ? (
                            <ChevronUp size={14} />
                          ) : (
                            <ChevronDown size={14} />
                          )}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm font-medium text-navy">
                            {r.nome_operacao}
                          </span>
                          <span className="block text-xs text-slate-400">
                            {truncar(r.finalidade)}
                          </span>
                        </span>
                      </button>
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                        {baseLabel(r.base_legal)}
                      </span>
                      {r.dados_sensiveis && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-danger-50 text-danger-700 border border-danger-100">
                          Sensível
                        </span>
                      )}
                      <span
                        className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${RISCO_BADGE[r.risco]}`}
                      >
                        {r.risco}
                      </span>
                      <div className="flex items-center gap-1">
                        <button
                          className="text-slate-300 hover:text-primary-600"
                          title="Editar operação"
                          onClick={() => abrirEdicao(r)}
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          className="text-slate-300 hover:text-danger-600"
                          title="Remover operação"
                          onClick={() => excluir(r)}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>

                    {/* Detalhes expandidos */}
                    {aberto && (
                      <div className="border-t border-slate-100 bg-slate-50 p-3 grid sm:grid-cols-2 gap-3 text-xs">
                        <Campo label="Categorias de dados">
                          {r.categorias_dados || "—"}
                        </Campo>
                        <Campo label="Categorias de titulares">
                          {r.categorias_titulares || "—"}
                        </Campo>
                        <Campo label="Compartilhamento">
                          {r.compartilhamento || "—"}
                        </Campo>
                        <Campo label="Transferência internacional">
                          {r.transferencia_internacional
                            ? `Sim — ${r.paises_transferencia || "países não informados"}`
                            : "Não"}
                        </Campo>
                        <Campo label="Prazo de retenção">
                          {r.prazo_retencao || "—"}
                        </Campo>
                        <Campo label="Medidas de segurança">
                          {r.medidas_seguranca || "—"}
                        </Campo>
                        {r.fatores_risco && r.fatores_risco.length > 0 && (
                          <div className="sm:col-span-2">
                            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                              Fatores de risco (avaliação do backend)
                            </div>
                            <ul className="list-disc list-inside space-y-0.5 text-slate-700">
                              {r.fatores_risco.map((f, i) => (
                                <li key={i}>{f}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Modal criar/editar */}
      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title={
          editId != null
            ? "Editar operação de tratamento"
            : "Nova operação de tratamento (ROPA)"
        }
        wide
      >
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="label">Nome da operação *</label>
            <input
              className="input"
              placeholder="ex: Folha de pagamento"
              value={form.nome_operacao}
              onChange={(e) =>
                setForm({ ...form, nome_operacao: e.target.value })
              }
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Finalidade *</label>
            <textarea
              className="input"
              rows={2}
              placeholder="Para que os dados são tratados"
              value={form.finalidade}
              onChange={(e) => setForm({ ...form, finalidade: e.target.value })}
            />
            <p className="text-xs text-slate-400 mt-1">
              Princípio da finalidade — art. 6º I.
            </p>
          </div>
          <div>
            <label className="label">Base legal *</label>
            <select
              className="input"
              value={form.base_legal}
              onChange={(e) => setForm({ ...form, base_legal: e.target.value })}
            >
              {BASES_LEGAIS.map((b) => (
                <option key={b.valor} value={b.valor}>
                  {b.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-slate-400 mt-1">
              Hipótese autorizativa — art. 7º (dados comuns) / art. 11 (sensíveis).
            </p>
          </div>
          <div>
            <label className="label">Prazo de retenção</label>
            <input
              className="input"
              placeholder="ex: 5 anos após desligamento"
              value={form.prazo_retencao}
              onChange={(e) =>
                setForm({ ...form, prazo_retencao: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Categorias de dados</label>
            <input
              className="input"
              placeholder="ex: nome, CPF, salário (categorias, não valores)"
              value={form.categorias_dados}
              onChange={(e) =>
                setForm({ ...form, categorias_dados: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Categorias de titulares</label>
            <input
              className="input"
              placeholder="ex: funcionários, clientes"
              value={form.categorias_titulares}
              onChange={(e) =>
                setForm({ ...form, categorias_titulares: e.target.value })
              }
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Compartilhamento</label>
            <input
              className="input"
              placeholder="ex: contabilidade terceirizada, operador de folha"
              value={form.compartilhamento}
              onChange={(e) =>
                setForm({ ...form, compartilhamento: e.target.value })
              }
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Medidas de segurança</label>
            <textarea
              className="input"
              rows={2}
              placeholder="ex: criptografia, controle de acesso (RBAC), logs"
              value={form.medidas_seguranca}
              onChange={(e) =>
                setForm({ ...form, medidas_seguranca: e.target.value })
              }
            />
            <p className="text-xs text-slate-400 mt-1">
              Segurança e prevenção — art. 46.
            </p>
          </div>

          {/* Toggles */}
          <label className="flex items-start gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={form.dados_sensiveis}
              onChange={(e) =>
                setForm({ ...form, dados_sensiveis: e.target.checked })
              }
            />
            <span>
              Trata <b>dados sensíveis</b>
              <span className="block text-xs text-slate-400">
                Origem racial, saúde, biometria etc. — art. 11.
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={form.transferencia_internacional}
              onChange={(e) =>
                setForm({
                  ...form,
                  transferencia_internacional: e.target.checked,
                })
              }
            />
            <span>
              Há <b>transferência internacional</b>
              <span className="block text-xs text-slate-400">
                Dados enviados para fora do país — art. 33.
              </span>
            </span>
          </label>

          {form.transferencia_internacional && (
            <div className="sm:col-span-2">
              <label className="label">Países de transferência *</label>
              <input
                className="input"
                placeholder="ex: Estados Unidos, Irlanda"
                value={form.paises_transferencia}
                onChange={(e) =>
                  setForm({ ...form, paises_transferencia: e.target.value })
                }
              />
            </div>
          )}
        </div>

        {erroForm && (
          <div className="mt-4 p-2 rounded bg-danger-50 text-danger-700 text-xs">
            {erroForm}
          </div>
        )}

        <div className="flex justify-end mt-5">
          <button className="btn-primary" disabled={salvando} onClick={salvar}>
            {salvando
              ? "Salvando…"
              : editId != null
                ? "Salvar alterações"
                : "Registrar operação"}
          </button>
        </div>
      </Modal>
    </div>
  );
}

function Campo({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="text-slate-700 mt-0.5">{children}</div>
    </div>
  );
}
