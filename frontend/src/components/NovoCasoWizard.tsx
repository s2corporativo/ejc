import { useState } from "react";
import { useNavigate } from "react-router";
import {
  Briefcase,
  ChevronDown,
  Link2,
  Search,
  UserPlus,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useAreas } from "../lib/areas";
import { toast } from "./Toast";
import { Badge, Button, Modal, Spinner } from "./UI";
import type { Client } from "../types";

// Taxonomia canônica de áreas: GET /areas via useAreas() (lib/areas.ts),
// com fallback completo do enum CaseArea (25 áreas).
const CASE_TYPES: { k: string; l: string }[] = [
  { k: "judicial", l: "Judicial" },
  { k: "extrajudicial", l: "Extrajudicial" },
  { k: "consultoria", l: "Consultoria" },
];

const soDigitos = (v: string) => v.replace(/\D/g, "");



/**
 * Wizard "Novo Caso" em 2 passos: (1) localizar/deduplicar o cliente por
 * CPF/CNPJ — vinculando um existente ou criando um mínimo — e (2) dados
 * básicos do caso. Ao criar, navega para a Jornada do Caso.
 *
 * DECISÃO: reusa somente endpoints existentes — GET /clients/ (param search
 * cobre nome/razão social/CPF/CNPJ), POST /clients/ e POST /cases/. O caminho
 * documental com IA permanece separado em Casos.tsx via
 * onCadastroCompleto. Este wizard não envia documentos nem chama IA.
 */
export default function NovoCasoWizard({
  open,
  onClose,
  onCadastroCompleto,
}: {
  open: boolean;
  onClose: () => void;
  onCadastroCompleto?: () => void;
}) {
  const nav = useNavigate();
  const [passo, setPasso] = useState<1 | 2>(1);
  const areas = useAreas();

  // ── Passo 1 — cliente ──
  const [doc, setDoc] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [resultados, setResultados] = useState<Client[] | null>(null);
  const [cliente, setCliente] = useState<Client | null>(null);
  const [novoCliente, setNovoCliente] = useState<{
    nome: string;
    email: string;
    telefone: string;
  }>({ nome: "", email: "", telefone: "" });
  const [criandoCliente, setCriandoCliente] = useState(false);

  // ── Passo 2 — caso ──
  const [caso, setCaso] = useState<Record<string, string>>({
    titulo: "",
    area: "civil",
    case_type: "judicial",
    parte_contraria: "",
    numero_processo: "",
    valor_causa: "",
    descricao_fatos: "",
    proxima_acao: "",
  });
  const [criandoCaso, setCriandoCaso] = useState(false);
  // Erro inline do campo título (validação junto ao campo, além do toast).
  const [tituloErro, setTituloErro] = useState<string | null>(null);
  // Busca por nome pode trazer homônimos que NÃO são o cliente: sem esta
  // saída, o usuário ficava preso (o form de criação só abria com 0 achados).
  const [cadastrarNovo, setCadastrarNovo] = useState(false);

  const digitos = soDigitos(doc);
  // Comprimento EXATO: 11=CPF, 14=CNPJ. 12-13 dígitos era classificado como
  // CNPJ e o POST devolvia 422 com rótulo confuso ("CNPJ inválido" para quem
  // digitou um CPF com dígito a mais) — melhor barrar antes com aviso claro.
  const ehCnpj = digitos.length === 14;
  const docValido =
    digitos.length === 0 || digitos.length === 11 || digitos.length === 14;

  const reset = () => {
    setPasso(1);
    setDoc("");
    setResultados(null);
    setCliente(null);
    setCadastrarNovo(false);
    setNovoCliente({ nome: "", email: "", telefone: "" });
    setTituloErro(null);
    setCaso({
      titulo: "",
      area: "civil",
      case_type: "judicial",
      parte_contraria: "",
      numero_processo: "",
      valor_causa: "",
      descricao_fatos: "",
      proxima_acao: "",
    });
  };

  const fechar = () => {
    reset();
    onClose();
  };

  const buscar = async () => {
    const termo = digitos || doc.trim();
    if (!termo) {
      toast.error("Informe o CPF/CNPJ (ou nome) do cliente para buscar.");
      return;
    }
    setBuscando(true);
    setCliente(null);
    setCadastrarNovo(false);
    try {
      // GET /clients/?search= já cobre nome, razão social, CPF e CNPJ (ilike).
      const { data } = await api.get("/clients/", {
        params: { search: termo, page_size: 10 },
      });
      setResultados(asList<Client>(data));
    } catch {
      toast.error("Falha ao buscar clientes");
      setResultados(null);
    } finally {
      setBuscando(false);
    }
  };

  const vincular = (c: Client) => {
    setCliente(c);
    setPasso(2);
  };

  const criarClienteEContinuar = async () => {
    if (!novoCliente.nome.trim()) {
      toast.error("Informe o nome / razão social do cliente.");
      return;
    }
    if (!docValido) {
      toast.error(
        `Documento com ${digitos.length} dígitos — CPF tem 11 e CNPJ tem 14. Confira o número.`,
      );
      return;
    }
    setCriandoCliente(true);
    try {
      // POST /clients/ — mesmo endpoint do cadastro de Clientes.tsx (dedup de
      // CPF/CNPJ é garantido pelo UNIQUE do backend, que retorna erro claro).
      const payload: Record<string, string> = {
        tipo: ehCnpj ? "PJ" : "PF",
        ...(ehCnpj
          ? { razao_social: novoCliente.nome.trim() }
          : { nome: novoCliente.nome.trim() }),
      };
      if (digitos) payload[ehCnpj ? "cnpj" : "cpf"] = digitos;
      if (novoCliente.email.trim()) payload.email = novoCliente.email.trim();
      if (novoCliente.telefone.trim())
        payload.telefone = novoCliente.telefone.trim();
      const { data } = await api.post("/clients/", payload);
      setCliente(data as Client);
      setPasso(2);
    } catch (e: any) {
      // 409 = documento já cadastrado: em vez de beco sem saída, refaz a
      // busca (agora com índice cego por hash no backend) para oferecer o
      // vínculo ao cadastro existente.
      if (e.response?.status === 409) {
        toast.error(
          "CPF/CNPJ já cadastrado — localizando o cliente para vincular.",
        );
        await buscar();
      } else {
        toast.error(e.response?.data?.detail || "Erro ao criar o cliente");
      }
    } finally {
      setCriandoCliente(false);
    }
  };

  const criarCaso = async () => {
    if (!cliente) return;
    if (!caso.titulo.trim()) {
      // Validação junto ao campo (borda vermelha + mensagem) além do toast —
      // o toast sozinho aparecia longe do formulário (usabilidade §3.8).
      setTituloErro("Informe o título do caso.");
      toast.error("Informe o título do caso.");
      return;
    }
    if (!caso.proxima_acao.trim()) {
      toast.error("Informe a próxima ação — é obrigatória para casos ativos.");
      return;
    }
    setCriandoCaso(true);
    try {
      // POST /cases/ — mesmo endpoint do modal completo; campos vazios omitidos.
      const payload: Record<string, unknown> = { client_id: cliente.id };
      for (const [k, v] of Object.entries(caso)) {
        if (v !== "") payload[k] = v;
      }
      // Unificação Fase 2 (QA): honorários não nascem mais no wizard —
      // o registro financeiro do caso fica exclusivamente no Financeiro do caso,
      // com controle de contrato, cobrança e auditoria no módulo próprio.
      const { data: novo } = await api.post("/cases/", payload);
      toast.success("Caso criado — acompanhe a jornada.");
      fechar();
      nav(`/casos/${novo.id}/jornada`);
    } catch (e: any) {
      toast.error(extrairErroCriacaoCaso(e));
    } finally {
      setCriandoCaso(false);
    }
  };

  // E02 (auditoria funcional): erros 422 do FastAPI/Pydantic chegam como
  // {detail: [{loc, msg}]} — extrair o nome do campo para o usuário corrigir
  // exatamente o ponto em vez de receber a string bruta do validador.
  const extrairErroCriacaoCaso = (e: any): string => {
    const resp = e?.response?.data;
    const status = e?.response?.status;
    const detail = resp?.detail;
    if (Array.isArray(detail) && detail.length) {
      return detail
        .map((d: any) => {
          const loc = Array.isArray(d?.loc) ? d.loc : [];
          const campo = loc.length ? String(loc[loc.length - 1]) : null;
          const rotulo = campo ? campo.replace(/_/g, " ") : null;
          return rotulo ? `${rotulo}: ${String(d.msg ?? d)}` : String(d.msg ?? d);
        })
        .join("; ");
    }
    if (typeof detail === "string" && detail) return detail;
    if (status === 422 || status === 400)
      return "Algum campo está em formato inválido ou ausente. Revise os campos destacados e tente novamente.";
    return e?.response?.data?.detail || "Erro ao criar o caso";
  };

  const nomeCliente = (c: Client) => c.nome || c.razao_social || "Sem nome";

  return (
    <Modal open={open} onClose={fechar} title="Novo caso manual — sem IA" wide>
      <div className="mb-5 rounded-xl border border-success-200 bg-success-50 px-4 py-3">
        <p className="text-sm font-semibold text-success-800">
          Cadastro rápido e totalmente manual
        </p>
        <p className="mt-1 text-xs leading-5 text-success-700">
          Nenhum documento é enviado para análise. Você informa apenas os dados
          necessários do cliente e do caso e pode completar a jornada depois.
        </p>
      </div>

      {/* Indicador dos passos */}
      <div className="mb-5 flex items-center gap-2 text-xs font-medium">
        {[
          { n: 1, l: "Cliente" },
          { n: 2, l: "Caso" },
        ].map((p, i) => (
          <div key={p.n} className="flex items-center gap-2">
            {i > 0 && <span className="h-px w-8 bg-slate-200" />}
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold ${
                passo >= p.n
                  ? "bg-primary-600 text-white"
                  : "bg-slate-100 text-slate-500"
              }`}
            >
              {p.n}
            </span>
            <span
              className={passo >= p.n ? "text-slate-900" : "text-slate-400"}
            >
              {p.l}
            </span>
          </div>
        ))}
      </div>

      {passo === 1 && (
        <div>
          <label className="label">CPF / CNPJ do cliente</label>
          <div className="flex gap-2">
            <input
              className="input flex-1"
              placeholder="000.000.000-00 ou 00.000.000/0000-00 (ou nome)"
              value={doc}
              onChange={(e) => {
                setDoc(e.target.value);
                setResultados(null);
              }}
              onKeyDown={(e) => e.key === "Enter" && buscar()}
            />
            <Button
              variant="secondary"
              disabled={buscando}
              onClick={buscar}
              icon={<Search className="h-4 w-4" />}
            >
              {buscando ? "Buscando..." : "Buscar"}
            </Button>
          </div>
          <p className="mt-1.5 text-xs text-slate-400">
            A busca evita cadastros duplicados: se o cliente já existir, basta
            vincular.
          </p>

          {buscando && (
            <div className="py-6">
              <Spinner />
            </div>
          )}

          {!buscando && resultados && resultados.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Clientes encontrados
              </p>
              {resultados.map((c) => (
                <div
                  key={c.id}
                  className="card flex items-center justify-between gap-3 px-4 py-3"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-slate-900">
                      {nomeCliente(c)}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                      <Badge tone="slate">{c.tipo}</Badge>
                      <span>{c.cpf || c.cnpj || "sem documento"}</span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => vincular(c)}
                    icon={<Link2 className="h-3.5 w-3.5" />}
                  >
                    Vincular automaticamente
                  </Button>
                </div>
              ))}
              {!cadastrarNovo && (
                <button
                  type="button"
                  className="text-xs font-medium text-slate-500 underline underline-offset-2 hover:text-slate-700"
                  onClick={() => setCadastrarNovo(true)}
                >
                  Não é nenhum destes — cadastrar novo cliente
                </button>
              )}
            </div>
          )}

          {!buscando &&
            resultados &&
            (resultados.length === 0 || cadastrarNovo) && (
              <div className="card mt-4 bg-slate-50 p-4">
                <p className="mb-3 flex items-center gap-2 text-sm text-slate-600">
                  <UserPlus className="h-4 w-4 text-slate-400" />
                  {resultados && resultados.length > 0
                    ? "Cadastrar novo cliente — preencha o mínimo para continuar"
                    : "Nenhum cliente encontrado — cadastre o mínimo para continuar"}
                  {digitos ? ` (${ehCnpj ? "CNPJ" : "CPF"}: ${digitos})` : ""}.
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label className="label">
                      {ehCnpj ? "Razão social *" : "Nome completo *"}
                    </label>
                    <input
                      className="input"
                      value={novoCliente.nome}
                      onChange={(e) =>
                        setNovoCliente({ ...novoCliente, nome: e.target.value })
                      }
                    />
                  </div>
                  <div>
                    <label className="label">E-mail</label>
                    <input
                      className="input"
                      type="email"
                      value={novoCliente.email}
                      onChange={(e) =>
                        setNovoCliente({
                          ...novoCliente,
                          email: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="label">Telefone</label>
                    <input
                      className="input"
                      value={novoCliente.telefone}
                      onChange={(e) =>
                        setNovoCliente({
                          ...novoCliente,
                          telefone: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>
                <div className="mt-3 flex justify-end">
                  <Button
                    disabled={criandoCliente}
                    onClick={criarClienteEContinuar}
                  >
                    {criandoCliente
                      ? "Criando..."
                      : "Criar cliente e continuar"}
                  </Button>
                </div>
              </div>
            )}

          {onCadastroCompleto && (
            <div className="mt-5 border-t border-slate-100 pt-3 text-right">
              <button
                type="button"
                className="text-xs font-medium text-primary-600 hover:underline"
                onClick={() => {
                  fechar();
                  onCadastroCompleto();
                }}
              >
                Usar um documento e preencher o caso com IA
              </button>
            </div>
          )}
        </div>
      )}

      {passo === 2 && cliente && (
        <div>
          <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-success-200 bg-success-50 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-success-700">
              <Briefcase className="h-4 w-4" />
              Cliente vinculado:{" "}
              <span className="font-semibold">{nomeCliente(cliente)}</span>
            </div>
            <button
              type="button"
              className="text-xs font-medium text-primary-600 hover:underline"
              onClick={() => {
                setCliente(null);
                setPasso(1);
              }}
            >
              Trocar cliente
            </button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="label">Título do caso *</label>
              <input
                className={`input ${
                  tituloErro
                    ? "border-danger-500 focus:border-danger-500 focus:ring-danger-200"
                    : ""
                }`}
                value={caso.titulo}
                aria-invalid={!!tituloErro}
                aria-describedby={tituloErro ? "titulo-caso-erro" : undefined}
                onChange={(e) => {
                  setCaso({ ...caso, titulo: e.target.value });
                  if (e.target.value.trim()) setTituloErro(null);
                }}
              />
              {tituloErro && (
                <p
                  id="titulo-caso-erro"
                  className="mt-1 text-xs text-danger-600"
                >
                  {tituloErro}
                </p>
              )}
            </div>
            <div>
              <label className="label">Área</label>
              <select
                className="input"
                value={caso.area}
                onChange={(e) => setCaso({ ...caso, area: e.target.value })}
              >
                {areas.map((a) => (
                  <option key={a.slug} value={a.slug}>
                    {a.nome}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Tipo de caso</label>
              <select
                className="input"
                value={caso.case_type}
                onChange={(e) =>
                  setCaso({ ...caso, case_type: e.target.value })
                }
              >
                {CASE_TYPES.map((t) => (
                  <option key={t.k} value={t.k}>
                    {t.l}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Parte contrária</label>
              <input
                className="input"
                value={caso.parte_contraria}
                onChange={(e) =>
                  setCaso({ ...caso, parte_contraria: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Nº do processo (se houver)</label>
              <input
                className="input"
                placeholder="0000000-00.0000.0.00.0000"
                value={caso.numero_processo}
                onChange={(e) =>
                  setCaso({ ...caso, numero_processo: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Valor da causa (R$)</label>
              <input
                className="input"
                type="number"
                value={caso.valor_causa}
                onChange={(e) =>
                  setCaso({ ...caso, valor_causa: e.target.value })
                }
              />
            </div>
            <div className="sm:col-span-2">
              <label className="label">Descrição dos fatos</label>
              <textarea
                className="input min-h-[90px]"
                value={caso.descricao_fatos}
                onChange={(e) =>
                  setCaso({ ...caso, descricao_fatos: e.target.value })
                }
              />
            </div>
            <div className="sm:col-span-2">
              <label className="label">Próxima ação *</label>
              <input
                className="input"
                placeholder="Ex.: Protocolar contestação, Agendar reunião, Entrar em contato com perito"
                value={caso.proxima_acao}
                onChange={(e) =>
                  setCaso({ ...caso, proxima_acao: e.target.value })
                }
              />
              <p className="mt-1 text-xs text-slate-400">
                O que precisa ser feito agora neste caso? Obrigatório para casos
                ativos.
              </p>
            </div>

          </div>

          <div className="mt-5 flex justify-between">
            <Button variant="ghost" onClick={() => setPasso(1)}>
              Voltar
            </Button>
            <Button disabled={criandoCaso} onClick={criarCaso}>
              {criandoCaso ? "Criando caso..." : "Criar caso e ver jornada"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
