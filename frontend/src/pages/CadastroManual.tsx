// ── Cadastro Manual (sem IA) — /cadastro-manual ──────────────────────────────
// Fluxo 100% manual para abrir cliente e caso SEM nenhum recurso de IA, com
// suporte offline: com o app já carregado e autenticado, cadastros feitos sem
// conexão entram numa fila local (stores/cadastroManual.ts) e são enviados
// automaticamente quando a conexão volta (evento `online`), no mount da página
// ou pelo botão "Enviar pendentes agora".
import { useCallback, useEffect, useRef, useState } from "react";
import { CloudOff, RotateCw, Trash2, Wifi, WifiOff } from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { toast } from "../components/Toast";
import { useAuth } from "../stores/auth";
import type { Client } from "../types";
import {
  Alert,
  Button,
  ConfirmModal,
  EmptyState,
  PageHeader,
  SectionCard,
  cn,
} from "../components/UI";
import {
  classificarErro,
  descreverItem,
  useCadastroManualStore,
  type ItemFila,
  type PostFn,
} from "../stores/cadastroManual";

// Enum CaseArea do backend (app/models/case.py) — lista COMPLETA, na ordem do
// modelo. Valor = chave do enum; rótulo em PT-BR.
const AREAS: { k: string; l: string }[] = [
  { k: "civil", l: "Cível" },
  { k: "trabalhista", l: "Trabalhista" },
  { k: "consumidor", l: "Consumidor" },
  { k: "familia", l: "Família" },
  { k: "ambiental", l: "Ambiental" },
  { k: "criminal", l: "Criminal" },
  { k: "previdenciario", l: "Previdenciário" },
  { k: "empresarial", l: "Empresarial" },
  { k: "tributario", l: "Tributário" },
  { k: "administrativo", l: "Administrativo" },
  { k: "bancario", l: "Bancário" },
  { k: "imobiliario", l: "Imobiliário" },
  { k: "sucessoes", l: "Sucessões" },
  { k: "constitucional", l: "Constitucional" },
  { k: "digital_lgpd", l: "Digital / LGPD" },
  { k: "transito", l: "Trânsito" },
  { k: "saude", l: "Saúde" },
  { k: "medico", l: "Médico" },
  { k: "agrario", l: "Agrário" },
  { k: "agronegocio", l: "Agronegócio" },
  { k: "eleitoral", l: "Eleitoral" },
  { k: "internacional", l: "Internacional" },
  { k: "contratual", l: "Contratual" },
  { k: "societario", l: "Societário" },
  { k: "licitacoes", l: "Licitações" },
];

// Enum CasePrioridade do backend (app/models/case.py) — mesmo select de Casos.tsx.
const PRIORIDADES = [
  { k: "baixa", l: "Baixa" },
  { k: "media", l: "Média" },
  { k: "alta", l: "Alta" },
  { k: "critica", l: "Crítica" },
];

const CASE_TYPES = [
  { k: "judicial", l: "Judicial" },
  { k: "extrajudicial", l: "Extrajudicial" },
  { k: "consultoria", l: "Consultoria" },
];

// ── Validação local de CPF/CNPJ (dígito verificador) ─────────────────────────
// Espelha validators_service do backend: evita enfileirar offline um cadastro
// que será rejeitado com 422 quando a conexão voltar.
function validarCpf(cpf: string): boolean {
  const d = cpf.replace(/\D/g, "");
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
  for (const n of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < n; i++) soma += parseInt(d[i]) * (n + 1 - i);
    const dv = ((soma * 10) % 11) % 10;
    if (dv !== parseInt(d[n])) return false;
  }
  return true;
}

function validarCnpj(cnpj: string): boolean {
  const d = cnpj.replace(/\D/g, "");
  if (d.length !== 14 || /^(\d)\1{13}$/.test(d)) return false;
  const calc = (len: number) => {
    const pesos =
      len === 12
        ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    let soma = 0;
    for (let i = 0; i < len; i++) soma += parseInt(d[i]) * pesos[i];
    const resto = soma % 11;
    return resto < 2 ? 0 : 11 - resto;
  };
  return calc(12) === parseInt(d[12]) && calc(13) === parseInt(d[13]);
}

// ── Formulários ──────────────────────────────────────────────────────────────
type ClienteForm = {
  tipo: "PF" | "PJ";
  nome: string;
  cpf: string;
  data_nascimento: string;
  profissao: string;
  razao_social: string;
  cnpj: string;
  nome_fantasia: string;
  email: string;
  telefone: string;
  whatsapp: string;
  cep: string;
  logradouro: string;
  numero: string;
  complemento: string;
  bairro: string;
  cidade: string;
  estado: string;
  origem: string;
  observacoes: string;
};

const CLIENTE_VAZIO: ClienteForm = {
  tipo: "PF",
  nome: "",
  cpf: "",
  data_nascimento: "",
  profissao: "",
  razao_social: "",
  cnpj: "",
  nome_fantasia: "",
  email: "",
  telefone: "",
  whatsapp: "",
  cep: "",
  logradouro: "",
  numero: "",
  complemento: "",
  bairro: "",
  cidade: "Betim",
  estado: "MG",
  origem: "",
  observacoes: "",
};

type CasoForm = {
  titulo: string;
  area: string;
  client_id: string;
  prioridade: string;
  case_type: string;
  numero_processo: string;
  tribunal: string;
  comarca: string;
  vara: string;
  parte_contraria: string;
  valor_causa: string;
  descricao_fatos: string;
  // "+ Criar cliente novo junto"
  criar_cliente: boolean;
  novo_tipo: "PF" | "PJ";
  novo_nome: string;
  novo_razao_social: string;
  novo_cpf: string;
  novo_cnpj: string;
  novo_telefone: string;
  novo_email: string;
};

const CASO_VAZIO: CasoForm = {
  titulo: "",
  area: "civil",
  client_id: "",
  prioridade: "media",
  case_type: "judicial",
  numero_processo: "",
  tribunal: "",
  comarca: "",
  vara: "",
  parte_contraria: "",
  valor_causa: "",
  descricao_fatos: "",
  criar_cliente: false,
  novo_tipo: "PF",
  novo_nome: "",
  novo_razao_social: "",
  novo_cpf: "",
  novo_cnpj: "",
  novo_telefone: "",
  novo_email: "",
};

/** Monta payload só com campos preenchidos (backend trata ausência como null). */
function limparVazios(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === "string" && v.trim() === "") continue;
    if (v === undefined || v === null) continue;
    out[k] = v;
  }
  return out;
}

// Campos exclusivos de cada tipo: ao alternar PF↔PJ no formulário, valores já
// digitados do outro tipo ficariam no estado e iriam no payload (ex.: cliente
// PF com cnpj/razão social). Removidos na montagem do payload.
const CAMPOS_SO_PJ = ["razao_social", "cnpj", "nome_fantasia"];
const CAMPOS_SO_PF = ["nome", "cpf", "data_nascimento", "profissao"];

function payloadCliente(f: {
  tipo: "PF" | "PJ";
  [k: string]: unknown;
}): Record<string, unknown> {
  const base = limparVazios(f as Record<string, unknown>);
  for (const k of f.tipo === "PF" ? CAMPOS_SO_PJ : CAMPOS_SO_PF) delete base[k];
  base.tipo = f.tipo;
  return base;
}

/**
 * Normaliza valor monetário digitado à brasileira para o Decimal do backend:
 * "1.234,56" → "1234.56"; "1.500" (ponto de MILHAR, sem vírgula) → "1500";
 * "1234.56" (decimal com ponto) fica como está.
 */
function normalizarValor(v: string): string {
  const s = v.trim();
  if (s.includes(",")) return s.replace(/\./g, "").replace(",", ".");
  if (/^\d{1,3}(\.\d{3})+$/.test(s)) return s.replace(/\./g, "");
  return s;
}

/** Validação local espelhando o backend (router clients + validators). */
function validarClienteLocal(f: {
  tipo: "PF" | "PJ";
  nome?: string;
  razao_social?: string;
  cpf?: string;
  cnpj?: string;
}): string | null {
  if (f.tipo === "PF" && !f.nome?.trim()) return "PF requer nome.";
  if (f.tipo === "PJ" && !f.razao_social?.trim())
    return "PJ requer razão social.";
  if (f.cpf?.trim() && !validarCpf(f.cpf))
    return "CPF inválido (dígito verificador).";
  if (f.cnpj?.trim() && !validarCnpj(f.cnpj))
    return "CNPJ inválido (dígito verificador).";
  return null;
}

const MSG_FILA =
  "Sem conexão — cadastro salvo na fila, será enviado automaticamente quando a conexão voltar.";

const STATUS_FILA: Record<ItemFila["status"], { label: string; cls: string }> =
  {
    pendente: { label: "Pendente", cls: "bg-slate-100 text-slate-600" },
    enviando: { label: "Enviando…", cls: "bg-primary-100 text-primary-700" },
    erro: { label: "Erro", cls: "bg-danger-50 text-danger-700" },
  };

export default function CadastroManual() {
  const {
    rascunhoCliente,
    rascunhoCaso,
    fila,
    clientesCache,
    setRascunhoCliente,
    setRascunhoCaso,
    limparRascunhoCliente,
    limparRascunhoCaso,
    setClientesCache,
    enfileirar,
    descartarItem,
    reativarItem,
    sincronizar,
    vincularUsuario,
  } = useCadastroManualStore();
  const usuarioId = useAuth((s) => s.user?.id);

  // Vincula o estado persistido ao usuário logado ANTES de qualquer envio:
  // fila/rascunhos de OUTRO usuário na mesma estação são descartados (nunca
  // enviados com o token da sessão atual) — aviso claro quando isso ocorre.
  useEffect(() => {
    if (!usuarioId) return;
    const descartados = vincularUsuario(usuarioId);
    if (descartados > 0) {
      toast.error(
        `${descartados} cadastro(s) pendente(s) de outro usuário foram descartados da fila offline desta estação.`,
      );
    }
  }, [usuarioId, vincularUsuario]);

  const [aba, setAba] = useState<"cliente" | "caso">("cliente");
  const [online, setOnline] = useState<boolean>(navigator.onLine);
  const [formCliente, setFormCliente] = useState<ClienteForm>({
    ...CLIENTE_VAZIO,
    ...(rascunhoCliente as Partial<ClienteForm>),
  });
  const [formCaso, setFormCaso] = useState<CasoForm>({
    ...CASO_VAZIO,
    ...(rascunhoCaso as Partial<CasoForm>),
  });
  const [erroCliente, setErroCliente] = useState<string | null>(null);
  const [erroCaso, setErroCaso] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [descartando, setDescartando] = useState<ItemFila | null>(null);

  // Transporte injetado no store: sempre o axios central (lib/api.ts).
  const post: PostFn = useCallback(
    async (path, body) => (await api.post(path, body)).data,
    [],
  );

  const sincronizandoRef = useRef(false);
  const rodarSync = useCallback(async () => {
    if (!navigator.onLine || sincronizandoRef.current) return;
    if (!usuarioId) return; // sem sessão resolvida, nada é enviado
    sincronizandoRef.current = true;
    try {
      // Garantia final antes do envio (o effect acima já rodou no mount, mas
      // o evento `online` pode disparar após troca de conta em outra aba).
      vincularUsuario(usuarioId);
      const r = await sincronizar(post);
      for (const item of r.enviados) {
        toast.success(
          `${item.tipo === "cliente" ? "Cliente" : "Caso"} "${descreverItem(item)}" sincronizado.`,
        );
      }
    } finally {
      sincronizandoRef.current = false;
    }
  }, [sincronizar, post, usuarioId, vincularUsuario]);

  // Lista de clientes: online atualiza o cache persistido; offline usa o cache.
  const atualizarCacheClientes = useCallback(() => {
    if (!navigator.onLine) return;
    api
      .get("/clients/", { params: { page_size: 100 } })
      .then((r) => {
        const lista = asList<Client>(r.data).map((c) => ({
          id: c.id,
          nome: c.nome || c.razao_social || c.id.slice(0, 8),
        }));
        setClientesCache(lista);
      })
      .catch(() => {
        /* cache persistido segue valendo */
      });
  }, [setClientesCache]);

  // Gatilhos de sync: mount + evento online (que também renova o cache de
  // clientes — sem isso, quem montou a página offline ficaria com o select
  // desatualizado até remontar). Indicador de conexão.
  useEffect(() => {
    const aoConectar = () => {
      setOnline(true);
      void rodarSync();
      atualizarCacheClientes();
    };
    const aoDesconectar = () => setOnline(false);
    window.addEventListener("online", aoConectar);
    window.addEventListener("offline", aoDesconectar);
    void rodarSync();
    atualizarCacheClientes();
    return () => {
      window.removeEventListener("online", aoConectar);
      window.removeEventListener("offline", aoDesconectar);
    };
  }, [rodarSync, atualizarCacheClientes]);

  // ── Auto-save dos rascunhos a cada mudança ─────────────────────────────────
  const mudarCliente = (patch: Partial<ClienteForm>) => {
    setFormCliente((f) => {
      const novo = { ...f, ...patch };
      setRascunhoCliente(novo);
      return novo;
    });
  };
  const mudarCaso = (patch: Partial<CasoForm>) => {
    setFormCaso((f) => {
      const novo = { ...f, ...patch };
      setRascunhoCaso(novo);
      return novo;
    });
  };

  const resetCliente = () => {
    setFormCliente(CLIENTE_VAZIO);
    limparRascunhoCliente();
  };
  const resetCaso = () => {
    setFormCaso(CASO_VAZIO);
    limparRascunhoCaso();
  };

  // ── Submits ────────────────────────────────────────────────────────────────
  const submitCliente = async () => {
    setErroCliente(null);
    const invalido = validarClienteLocal(formCliente);
    if (invalido) {
      setErroCliente(invalido);
      return;
    }
    const payload = payloadCliente(formCliente);
    if (!navigator.onLine) {
      enfileirar("cliente", payload);
      resetCliente();
      toast.info(MSG_FILA);
      return;
    }
    setSalvando(true);
    try {
      await api.post("/clients/", payload);
      toast.success("Cliente cadastrado.");
      resetCliente();
    } catch (err) {
      const c = classificarErro(err);
      if (c.acao === "pendente") {
        // Erro de REDE no meio do envio: enfileira (sem duplicidade — não
        // chegou ao servidor) e mantém o fluxo do usuário.
        enfileirar("cliente", payload);
        resetCliente();
        toast.info(MSG_FILA);
      } else {
        setErroCliente(c.mensagem);
      }
    } finally {
      setSalvando(false);
    }
  };

  const submitCaso = async () => {
    setErroCaso(null);
    if (!formCaso.titulo.trim()) {
      setErroCaso("Informe o título do caso.");
      return;
    }
    if (!formCaso.area) {
      setErroCaso("Selecione a área do caso.");
      return;
    }
    const clienteNovo = formCaso.criar_cliente
      ? {
          tipo: formCaso.novo_tipo,
          nome: formCaso.novo_nome,
          razao_social: formCaso.novo_razao_social,
          cpf: formCaso.novo_cpf,
          cnpj: formCaso.novo_cnpj,
          telefone: formCaso.novo_telefone,
          email: formCaso.novo_email,
        }
      : null;
    if (clienteNovo) {
      const invalido = validarClienteLocal(clienteNovo);
      if (invalido) {
        setErroCaso(`Cliente novo: ${invalido}`);
        return;
      }
    } else if (!formCaso.client_id) {
      setErroCaso(
        "Selecione o cliente do caso (ou crie um cliente novo junto).",
      );
      return;
    }

    const payloadCaso = limparVazios({
      titulo: formCaso.titulo,
      area: formCaso.area,
      client_id: clienteNovo ? "" : formCaso.client_id,
      prioridade: formCaso.prioridade,
      case_type: formCaso.case_type,
      numero_processo: formCaso.numero_processo,
      tribunal: formCaso.tribunal,
      comarca: formCaso.comarca,
      vara: formCaso.vara,
      parte_contraria: formCaso.parte_contraria,
      valor_causa: normalizarValor(formCaso.valor_causa),
      descricao_fatos: formCaso.descricao_fatos,
    });
    const payloadCli = clienteNovo ? payloadCliente(clienteNovo) : null;

    const enfileirarTudo = () => {
      if (payloadCli) {
        const idLocal = enfileirar("cliente", payloadCli);
        enfileirar("caso", { ...payloadCaso, client_id: "" }, idLocal);
      } else {
        enfileirar("caso", payloadCaso);
      }
      resetCaso();
      toast.info(MSG_FILA);
    };

    if (!navigator.onLine) {
      enfileirarTudo();
      return;
    }

    setSalvando(true);
    try {
      let clientId = formCaso.client_id;
      if (payloadCli) {
        try {
          const { data } = await api.post("/clients/", payloadCli);
          clientId = data.id;
          toast.success("Cliente cadastrado.");
        } catch (errCli) {
          const c = classificarErro(errCli);
          if (c.acao === "pendente") {
            enfileirarTudo();
          } else {
            setErroCaso(`Cliente novo: ${c.mensagem}`);
          }
          return;
        }
      }
      try {
        await api.post("/cases/", { ...payloadCaso, client_id: clientId });
        toast.success("Caso aberto.");
        resetCaso();
      } catch (errCaso) {
        const c = classificarErro(errCaso);
        if (c.acao === "pendente") {
          // Cliente (se houve) já foi criado com id real; só o caso fica na fila.
          enfileirar("caso", { ...payloadCaso, client_id: clientId });
          resetCaso();
          toast.info(MSG_FILA);
        } else {
          setErroCaso(
            payloadCli
              ? `Cliente criado, mas o caso foi rejeitado: ${c.mensagem}`
              : c.mensagem,
          );
        }
      }
    } finally {
      setSalvando(false);
    }
  };

  const tentarItem = (item: ItemFila) => {
    if (item.status === "erro") reativarItem(item.id);
    void rodarSync();
  };

  const pendentes = fila.filter((f) => f.status !== "erro").length;
  const comErro = fila.length - pendentes;

  return (
    <div>
      <PageHeader
        title="Cadastro Manual"
        subtitle="Cadastre clientes e abra casos sem IA — com fila offline quando faltar conexão."
        actions={
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium",
              online
                ? "bg-green-50 text-green-700"
                : "bg-warn-100 text-warn-700",
            )}
          >
            {online ? <Wifi size={13} /> : <WifiOff size={13} />}
            {online ? "Online" : "Offline"}
          </span>
        }
      />

      <Alert variant="info" className="mb-4">
        O modo offline funciona apenas com o app já carregado e autenticado
        neste navegador. Recarregar a página sem rede não abre o sistema, e a
        sessão expira em cerca de 8 horas — as pendências da fila são enviadas
        automaticamente quando houver conexão e sessão válida. Rascunhos e itens
        da fila (incluindo dados do cliente) ficam armazenados neste navegador
        até o envio: use um dispositivo pessoal e descarte pendências que não
        serão enviadas.
      </Alert>

      <div className="mb-4 flex gap-2">
        {(
          [
            { k: "cliente", l: "Novo cliente" },
            { k: "caso", l: "Novo caso" },
          ] as const
        ).map((t) => (
          <button
            key={t.k}
            type="button"
            onClick={() => setAba(t.k)}
            className={cn(
              "rounded-xl px-4 py-2 text-sm font-medium transition-colors",
              aba === t.k
                ? "bg-primary-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200",
            )}
          >
            {t.l}
          </button>
        ))}
      </div>

      {aba === "cliente" && (
        <SectionCard
          title="Novo cliente"
          subtitle="Rascunho salvo automaticamente neste navegador."
        >
          <div className="mb-4 flex gap-2">
            {(["PF", "PJ"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => mudarCliente({ tipo: t })}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors",
                  formCliente.tipo === t
                    ? "bg-primary-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200",
                )}
              >
                {t === "PF" ? "Pessoa Física" : "Pessoa Jurídica"}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {formCliente.tipo === "PF" ? (
              <>
                <div className="lg:col-span-2">
                  <label className="label">Nome completo *</label>
                  <input
                    className="input"
                    value={formCliente.nome}
                    onChange={(e) => mudarCliente({ nome: e.target.value })}
                  />
                </div>
                <div>
                  <label className="label">CPF</label>
                  <input
                    className="input"
                    value={formCliente.cpf}
                    onChange={(e) => mudarCliente({ cpf: e.target.value })}
                  />
                </div>
                <div>
                  <label className="label">Data de nascimento</label>
                  <input
                    type="date"
                    className="input"
                    value={formCliente.data_nascimento}
                    onChange={(e) =>
                      mudarCliente({ data_nascimento: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="label">Profissão</label>
                  <input
                    className="input"
                    value={formCliente.profissao}
                    onChange={(e) =>
                      mudarCliente({ profissao: e.target.value })
                    }
                  />
                </div>
              </>
            ) : (
              <>
                <div className="lg:col-span-2">
                  <label className="label">Razão social *</label>
                  <input
                    className="input"
                    value={formCliente.razao_social}
                    onChange={(e) =>
                      mudarCliente({ razao_social: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="label">CNPJ</label>
                  <input
                    className="input"
                    value={formCliente.cnpj}
                    onChange={(e) => mudarCliente({ cnpj: e.target.value })}
                  />
                </div>
                <div>
                  <label className="label">Nome fantasia</label>
                  <input
                    className="input"
                    value={formCliente.nome_fantasia}
                    onChange={(e) =>
                      mudarCliente({ nome_fantasia: e.target.value })
                    }
                  />
                </div>
              </>
            )}

            <div>
              <label className="label">E-mail</label>
              <input
                type="email"
                className="input"
                value={formCliente.email}
                onChange={(e) => mudarCliente({ email: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Telefone</label>
              <input
                className="input"
                value={formCliente.telefone}
                onChange={(e) => mudarCliente({ telefone: e.target.value })}
              />
            </div>
            <div>
              <label className="label">WhatsApp</label>
              <input
                className="input"
                value={formCliente.whatsapp}
                onChange={(e) => mudarCliente({ whatsapp: e.target.value })}
              />
            </div>
            <div>
              <label className="label">CEP</label>
              <input
                className="input"
                value={formCliente.cep}
                onChange={(e) => mudarCliente({ cep: e.target.value })}
              />
            </div>
            <div className="lg:col-span-2">
              <label className="label">Logradouro</label>
              <input
                className="input"
                value={formCliente.logradouro}
                onChange={(e) => mudarCliente({ logradouro: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Número</label>
              <input
                className="input"
                value={formCliente.numero}
                onChange={(e) => mudarCliente({ numero: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Complemento</label>
              <input
                className="input"
                value={formCliente.complemento}
                onChange={(e) => mudarCliente({ complemento: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Bairro</label>
              <input
                className="input"
                value={formCliente.bairro}
                onChange={(e) => mudarCliente({ bairro: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Cidade</label>
              <input
                className="input"
                value={formCliente.cidade}
                onChange={(e) => mudarCliente({ cidade: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Estado (UF)</label>
              <input
                className="input"
                maxLength={2}
                value={formCliente.estado}
                onChange={(e) =>
                  mudarCliente({ estado: e.target.value.toUpperCase() })
                }
              />
            </div>
            <div>
              <label className="label">Origem</label>
              <input
                className="input"
                placeholder="Indicação, site…"
                value={formCliente.origem}
                onChange={(e) => mudarCliente({ origem: e.target.value })}
              />
            </div>
            <div className="sm:col-span-2 lg:col-span-3">
              <label className="label">Observações</label>
              <textarea
                className="input min-h-20 resize-y"
                value={formCliente.observacoes}
                onChange={(e) => mudarCliente({ observacoes: e.target.value })}
              />
            </div>
          </div>

          {erroCliente && (
            <Alert variant="danger" className="mt-4">
              {erroCliente}
            </Alert>
          )}

          <div className="mt-5 flex items-center gap-2">
            <Button type="button" onClick={submitCliente} disabled={salvando}>
              {online ? "Cadastrar cliente" : "Salvar na fila offline"}
            </Button>
            <Button type="button" variant="secondary" onClick={resetCliente}>
              Limpar formulário
            </Button>
          </div>
        </SectionCard>
      )}

      {aba === "caso" && (
        <SectionCard
          title="Novo caso"
          subtitle="Rascunho salvo automaticamente neste navegador."
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <label className="label">Título do caso *</label>
              <input
                className="input"
                value={formCaso.titulo}
                onChange={(e) => mudarCaso({ titulo: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Área *</label>
              <select
                className="input"
                value={formCaso.area}
                onChange={(e) => mudarCaso({ area: e.target.value })}
              >
                {AREAS.map((a) => (
                  <option key={a.k} value={a.k}>
                    {a.l}
                  </option>
                ))}
              </select>
            </div>

            <div className="lg:col-span-2">
              <label className="label">
                Cliente {formCaso.criar_cliente ? "(novo, abaixo)" : "*"}
              </label>
              <select
                className="input"
                disabled={formCaso.criar_cliente}
                value={formCaso.client_id}
                onChange={(e) => mudarCaso({ client_id: e.target.value })}
              >
                <option value="">— Selecione —</option>
                {clientesCache.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nome}
                  </option>
                ))}
              </select>
              {!online && (
                <p className="mt-1 text-[11px] text-slate-400">
                  Offline: lista usa o último cache de clientes salvo.
                </p>
              )}
            </div>
            <div className="flex items-end pb-1">
              <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={formCaso.criar_cliente}
                  onChange={(e) =>
                    mudarCaso({ criar_cliente: e.target.checked })
                  }
                />
                + Criar cliente novo junto
              </label>
            </div>

            {formCaso.criar_cliente && (
              <div className="sm:col-span-2 lg:col-span-3 rounded-xl border border-dashed border-slate-300 p-4">
                <div className="mb-3 flex gap-2">
                  {(["PF", "PJ"] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => mudarCaso({ novo_tipo: t })}
                      className={cn(
                        "rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors",
                        formCaso.novo_tipo === t
                          ? "bg-primary-600 text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200",
                      )}
                    >
                      {t === "PF" ? "Pessoa Física" : "Pessoa Jurídica"}
                    </button>
                  ))}
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {formCaso.novo_tipo === "PF" ? (
                    <>
                      <div>
                        <label className="label">Nome completo *</label>
                        <input
                          className="input"
                          value={formCaso.novo_nome}
                          onChange={(e) =>
                            mudarCaso({ novo_nome: e.target.value })
                          }
                        />
                      </div>
                      <div>
                        <label className="label">CPF</label>
                        <input
                          className="input"
                          value={formCaso.novo_cpf}
                          onChange={(e) =>
                            mudarCaso({ novo_cpf: e.target.value })
                          }
                        />
                      </div>
                    </>
                  ) : (
                    <>
                      <div>
                        <label className="label">Razão social *</label>
                        <input
                          className="input"
                          value={formCaso.novo_razao_social}
                          onChange={(e) =>
                            mudarCaso({ novo_razao_social: e.target.value })
                          }
                        />
                      </div>
                      <div>
                        <label className="label">CNPJ</label>
                        <input
                          className="input"
                          value={formCaso.novo_cnpj}
                          onChange={(e) =>
                            mudarCaso({ novo_cnpj: e.target.value })
                          }
                        />
                      </div>
                    </>
                  )}
                  <div>
                    <label className="label">Telefone</label>
                    <input
                      className="input"
                      value={formCaso.novo_telefone}
                      onChange={(e) =>
                        mudarCaso({ novo_telefone: e.target.value })
                      }
                    />
                  </div>
                  <div>
                    <label className="label">E-mail</label>
                    <input
                      type="email"
                      className="input"
                      value={formCaso.novo_email}
                      onChange={(e) =>
                        mudarCaso({ novo_email: e.target.value })
                      }
                    />
                  </div>
                </div>
              </div>
            )}

            <div>
              <label className="label">Prioridade</label>
              <select
                className="input"
                value={formCaso.prioridade}
                onChange={(e) => mudarCaso({ prioridade: e.target.value })}
              >
                {PRIORIDADES.map((p) => (
                  <option key={p.k} value={p.k}>
                    {p.l}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Tipo de caso</label>
              <select
                className="input"
                value={formCaso.case_type}
                onChange={(e) => mudarCaso({ case_type: e.target.value })}
              >
                {CASE_TYPES.map((t) => (
                  <option key={t.k} value={t.k}>
                    {t.l}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Nº do processo</label>
              <input
                className="input"
                value={formCaso.numero_processo}
                onChange={(e) => mudarCaso({ numero_processo: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Tribunal</label>
              <input
                className="input"
                value={formCaso.tribunal}
                onChange={(e) => mudarCaso({ tribunal: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Comarca</label>
              <input
                className="input"
                value={formCaso.comarca}
                onChange={(e) => mudarCaso({ comarca: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Vara</label>
              <input
                className="input"
                value={formCaso.vara}
                onChange={(e) => mudarCaso({ vara: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Parte contrária</label>
              <input
                className="input"
                value={formCaso.parte_contraria}
                onChange={(e) => mudarCaso({ parte_contraria: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Valor da causa (R$)</label>
              <input
                className="input"
                inputMode="decimal"
                placeholder="0,00"
                value={formCaso.valor_causa}
                onChange={(e) => mudarCaso({ valor_causa: e.target.value })}
              />
            </div>
            <div className="sm:col-span-2 lg:col-span-3">
              <label className="label">Descrição dos fatos</label>
              <textarea
                className="input min-h-24 resize-y"
                value={formCaso.descricao_fatos}
                onChange={(e) => mudarCaso({ descricao_fatos: e.target.value })}
              />
            </div>
          </div>

          {erroCaso && (
            <Alert variant="danger" className="mt-4">
              {erroCaso}
            </Alert>
          )}

          <div className="mt-5 flex items-center gap-2">
            <Button type="button" onClick={submitCaso} disabled={salvando}>
              {online ? "Abrir caso" : "Salvar na fila offline"}
            </Button>
            <Button type="button" variant="secondary" onClick={resetCaso}>
              Limpar formulário
            </Button>
          </div>
        </SectionCard>
      )}

      <SectionCard
        title={`Fila offline (${fila.length})`}
        subtitle={
          fila.length
            ? `${pendentes} pendente(s), ${comErro} com erro. Itens com erro não são reenviados automaticamente.`
            : undefined
        }
        actions={
          fila.length > 0 ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              icon={<RotateCw size={14} />}
              disabled={!online}
              onClick={() => void rodarSync()}
            >
              Enviar pendentes agora
            </Button>
          ) : undefined
        }
        className="mt-6"
      >
        {fila.length === 0 ? (
          <EmptyState
            icon={CloudOff}
            title="Nenhum cadastro na fila"
            message="Cadastros feitos sem conexão aparecem aqui até serem enviados."
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {fila.map((item) => (
              <li
                key={item.id}
                className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      {item.tipo === "cliente" ? "Cliente" : "Caso"}
                    </span>
                    <span className="truncate text-sm font-medium text-slate-800">
                      {descreverItem(item)}
                    </span>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[11px] font-medium",
                        STATUS_FILA[item.status].cls,
                      )}
                    >
                      {STATUS_FILA[item.status].label}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-400">
                    Criado em {new Date(item.criado_em).toLocaleString("pt-BR")}
                    {item.clientePendenteId &&
                      " — vinculado a cliente pendente na fila"}
                  </p>
                  {item.erro && (
                    <p className="mt-1 text-xs text-danger-600">{item.erro}</p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    icon={<RotateCw size={13} />}
                    disabled={!online || item.status === "enviando"}
                    onClick={() => tentarItem(item)}
                  >
                    Tentar agora
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="danger"
                    icon={<Trash2 size={13} />}
                    disabled={item.status === "enviando"}
                    onClick={() => setDescartando(item)}
                  >
                    Descartar
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <ConfirmModal
        open={Boolean(descartando)}
        onClose={() => setDescartando(null)}
        onConfirm={() => {
          if (descartando) descartarItem(descartando.id);
          setDescartando(null);
        }}
        title="Descartar cadastro pendente"
        message={
          descartando
            ? `Descartar ${descartando.tipo === "cliente" ? "o cliente" : "o caso"} "${descreverItem(descartando)}" da fila? O cadastro NÃO será enviado ao sistema.`
            : undefined
        }
        confirmLabel="Descartar"
      />
    </div>
  );
}
