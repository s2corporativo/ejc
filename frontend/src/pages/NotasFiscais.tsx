// ── NFS-e — aba do FinanceiroWorkspace ────────────────────
// Caminho gratuito: a nota é emitida no Emissor Nacional (gov.br) e
// registrada aqui via POST /nfse/manual. Funciona com NFSE_ENABLED=false —
// nada de emissão via API de provedor é exibido nesta tela.
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import {
  Ban,
  Download,
  ExternalLink,
  FileCode2,
  Plus,
  Receipt,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { toast } from "../components/Toast";
import type {
  Client,
  Fee,
  NfseStatusInfo,
  NotaFiscal,
  NotaFiscalListResponse,
  Paged,
} from "../types";
import {
  Badge,
  Empty,
  ErrorState,
  Modal,
  Spinner,
  fmtDate,
  fmtMoney,
} from "../components/UI";

const EMISSOR_NACIONAL_FALLBACK = "https://www.nfse.gov.br/EmissorNacional";
const STATUS_VALIDOS = [
  "rascunho",
  "processando",
  "autorizada",
  "rejeitada",
  "cancelada",
];
const STATUS_TONE = {
  rascunho: "slate",
  processando: "amber",
  autorizada: "green",
  rejeitada: "red",
  cancelada: "red",
} as const;
const LIMIT = 20;

interface FormNota {
  numero: string;
  data_emissao: string;
  valor: string;
  descricao: string;
  chave_acesso: string;
  competencia: string;
  client_id: string;
  fee_id: string;
}

const EMPTY_FORM: FormNota = {
  numero: "",
  data_emissao: "",
  valor: "",
  descricao: "",
  chave_acesso: "",
  competencia: "",
  client_id: "",
  fee_id: "",
};

function statusFiscalLabel(nota: NotaFiscal): string {
  if (nota.provider === "manual" && nota.status === "cancelada") {
    return "registro encerrado";
  }
  return nota.status;
}

function statusFiscalTitle(nota: NotaFiscal): string | undefined {
  if (nota.provider === "manual" && nota.status === "cancelada") {
    return (
      "Registro encerrado somente no EJC. Isso NÃO confirma cancelamento fiscal " +
      "no Emissor Nacional; confira a situação oficial no gov.br."
    );
  }
  if (nota.status === "rejeitada" && nota.mensagem_erro) {
    return nota.mensagem_erro;
  }
  if (nota.status === "cancelada" && nota.motivo_cancelamento) {
    return nota.motivo_cancelamento;
  }
  return undefined;
}

export default function NotasFiscais() {
  const [statusInfo, setStatusInfo] = useState<NfseStatusInfo | null>(null);
  const [data, setData] = useState<NotaFiscalListResponse | null>(null);
  const [clientes, setClientes] = useState<Client[]>([]);
  const [fees, setFees] = useState<Fee[]>([]);
  const [error, setError] = useState(false);
  const [searchParams] = useSearchParams();
  const [statusF, setStatusF] = useState(() => {
    const s = searchParams.get("status");
    return s && STATUS_VALIDOS.includes(s) ? s : "";
  });
  const [offset, setOffset] = useState(0);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<FormNota>({ ...EMPTY_FORM });
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [xmlFile, setXmlFile] = useState<File | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [cancelNota, setCancelNota] = useState<NotaFiscal | null>(null);
  const [motivo, setMotivo] = useState("");
  const [cancelando, setCancelando] = useState(false);

  const load = useCallback(async () => {
    setError(false);
    try {
      const r = await api.get<NotaFiscalListResponse>("/nfse", {
        params: { limit: LIMIT, offset, status: statusF || undefined },
      });
      if (r.data.items.length === 0 && offset > 0) {
        setOffset(0);
        return;
      }
      setData(r.data);
    } catch {
      setError(true);
    }
  }, [statusF, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    api
      .get<NfseStatusInfo>("/nfse/status")
      .then((r) => setStatusInfo(r.data))
      .catch(() => {});
    api
      .get("/clients/", { params: { page_size: 100 } })
      .then((r) => setClientes(asList<Client>(r.data)))
      .catch(() => setClientes([]));
    api
      .get<Paged<Fee>>("/fees/", { params: { page_size: 100 } })
      .then((r) => setFees(Array.isArray(r.data.data) ? r.data.data : []))
      .catch(() => setFees([]));
  }, []);

  const emissorUrl = statusInfo?.emissor_nacional_url?.startsWith(
    "https://www.nfse.gov.br",
  )
    ? statusInfo.emissor_nacional_url
    : EMISSOR_NACIONAL_FALLBACK;

  const clienteNome = (id?: string | null) => {
    if (!id) return "—";
    const c = clientes.find((cl) => cl.id === id);
    return c ? c.nome || c.razao_social || "—" : "—";
  };

  const setFiltro = (s: string) => {
    setStatusF(s);
    setOffset(0);
  };

  const recarregarDoInicio = () => {
    if (offset !== 0) setOffset(0);
    else void load();
  };

  const registrar = async () => {
    const valorNum = Number(String(form.valor).replace(",", "."));
    if (!form.numero.trim() || !form.data_emissao || !form.descricao.trim()) {
      toast.error("Número, data de emissão e descrição são obrigatórios.");
      return;
    }
    if (!Number.isFinite(valorNum) || valorNum <= 0) {
      toast.error("Informe um valor maior que zero.");
      return;
    }
    setSalvando(true);
    try {
      const fd = new FormData();
      fd.append("numero", form.numero.trim());
      fd.append("data_emissao", form.data_emissao);
      fd.append("valor", String(valorNum));
      fd.append("descricao", form.descricao.trim());
      if (form.chave_acesso.trim())
        fd.append("chave_acesso", form.chave_acesso.trim());
      if (form.competencia) fd.append("competencia", form.competencia);
      if (form.client_id) fd.append("client_id", form.client_id);
      if (form.fee_id) fd.append("fee_id", form.fee_id);
      if (pdfFile) fd.append("pdf", pdfFile);
      if (xmlFile) fd.append("xml", xmlFile);
      await api.post("/nfse/manual", fd);
      toast.success("Nota registrada.");
      setModal(false);
      setForm({ ...EMPTY_FORM });
      setPdfFile(null);
      setXmlFile(null);
      recarregarDoInicio();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao registrar a nota.");
    } finally {
      setSalvando(false);
    }
  };

  const baixar = async (n: NotaFiscal, kind: "pdf" | "xml") => {
    try {
      const resp = await api.get(`/nfse/${n.id}/${kind}`, {
        responseType: "blob",
      });
      const blobUrl = URL.createObjectURL(resp.data as Blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `nfse_${n.numero || n.id}.${kind}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch {
      toast.error(`Falha ao baixar o ${kind.toUpperCase()} da nota.`);
    }
  };

  const cancelar = async () => {
    if (!cancelNota || cancelando) return;
    if (motivo.trim().length < 3) {
      toast.error("Informe o motivo do encerramento local (mínimo 3 caracteres).");
      return;
    }
    setCancelando(true);
    try {
      await api.post(`/nfse/manual/${cancelNota.id}/cancelar`, {
        motivo: motivo.trim(),
      });
      toast.success(
        "Registro encerrado no EJC. Isso não confirma cancelamento fiscal no Emissor Nacional.",
      );
      setCancelNota(null);
      setMotivo("");
      void load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao encerrar o registro local.");
    } finally {
      setCancelando(false);
    }
  };

  return (
    <div>
      <div className="card mb-4 flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-semibold text-navy">
            <Receipt size={16} /> Emissão gratuita no Emissor Nacional
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            Emita a NFS-e no portal gov.br e depois registre a nota emitida aqui
            pelo botão &quot;Registrar nota emitida&quot;.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            className="btn-gold"
            href={emissorUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            <ExternalLink size={15} /> Emitir no Emissor Nacional (gov.br)
          </a>
          <button className="btn-primary" onClick={() => setModal(true)}>
            <Plus size={16} /> Registrar nota emitida
          </button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {["", ...STATUS_VALIDOS].map((s) => (
          <button
            key={s}
            onClick={() => setFiltro(s)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium capitalize ${statusF === s ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
          >
            {s || "Todas"}
          </button>
        ))}
      </div>

      {error ? (
        <ErrorState
          message="Não foi possível carregar as notas fiscais. Tente novamente."
          onRetry={() => void load()}
        />
      ) : !data ? (
        <Spinner />
      ) : data.items.length === 0 ? (
        statusF ? (
          <Empty
            titulo="Nenhuma nota para o filtro atual"
            descricao={`Não há notas com status "${statusF}". Selecione "Todas" para ver as demais notas.`}
          />
        ) : (
          <Empty
            titulo="Nenhuma nota registrada"
            descricao="Emita a NFS-e no Emissor Nacional (gov.br) e registre-a aqui para manter o controle fiscal do escritório."
          />
        )
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Número</th>
                <th className="px-4 py-3">Emissão</th>
                <th className="px-4 py-3">Tomador</th>
                <th className="px-4 py-3">Valor</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Origem</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((n) => (
                <tr key={n.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-navy">
                    <span title={n.chave_acesso || undefined}>
                      {n.numero || "—"}
                    </span>
                    {n.descricao && (
                      <div className="max-w-56 truncate text-xs font-normal text-slate-500">
                        {n.descricao}
                      </div>
                    )}
                  </td>
                  <td
                    className="px-4 py-3 text-slate-500"
                    title={
                      n.competencia
                        ? `Competência: ${fmtDate(n.competencia)}`
                        : undefined
                    }
                  >
                    {fmtDate(n.data_emissao)}
                  </td>
                  <td className="px-4 py-3">{clienteNome(n.client_id)}</td>
                  <td className="px-4 py-3 font-semibold">
                    {n.valor == null ? "—" : fmtMoney(Number(n.valor))}
                  </td>
                  <td className="px-4 py-3" title={statusFiscalTitle(n)}>
                    <Badge tone={STATUS_TONE[n.status] ?? "slate"}>
                      {statusFiscalLabel(n)}
                    </Badge>
                    {n.provider === "manual" && n.status === "cancelada" && (
                      <div className="mt-1 max-w-48 text-[10px] leading-4 text-danger-600">
                        Apenas no EJC; confira o estado fiscal no gov.br.
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {n.provider === "manual" ? (
                      <Badge tone="slate">Manual</Badge>
                    ) : (
                      <Badge tone="blue">{n.provider}</Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {n.tem_pdf && (
                      <button
                        className="btn-ghost px-2 py-1 text-navy"
                        title="Baixar PDF"
                        onClick={() => void baixar(n, "pdf")}
                      >
                        <Download size={15} />
                      </button>
                    )}
                    {n.tem_xml && (
                      <button
                        className="btn-ghost px-2 py-1 text-teal-600"
                        title="Baixar XML"
                        onClick={() => void baixar(n, "xml")}
                      >
                        <FileCode2 size={15} />
                      </button>
                    )}
                    {n.provider === "manual" && n.status !== "cancelada" && (
                      <button
                        className="btn-ghost px-2 py-1 text-danger-600"
                        title="Encerrar somente o registro local no EJC"
                        onClick={() => {
                          setCancelNota(n);
                          setMotivo("");
                        }}
                      >
                        <Ban size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > LIMIT && (
        <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
          <span>
            {offset + 1}–{Math.min(offset + LIMIT, data.total)} de {data.total}
          </span>
          <div className="flex gap-2">
            <button
              className="btn-secondary px-3 py-1.5 text-xs"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - LIMIT))}
            >
              Anterior
            </button>
            <button
              className="btn-secondary px-3 py-1.5 text-xs"
              disabled={offset + LIMIT >= data.total}
              onClick={() => setOffset(offset + LIMIT)}
            >
              Próxima
            </button>
          </div>
        </div>
      )}

      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title="Registrar nota emitida"
        wide
      >
        <p className="mb-4 text-xs text-slate-500">
          Registre aqui a NFS-e já emitida no Emissor Nacional (gov.br). Anexe o
          PDF (DANFSe) e o XML quando tiver os arquivos.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Número da nota *</label>
            <input
              className="input"
              value={form.numero}
              onChange={(e) => setForm({ ...form, numero: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Data de emissão *</label>
            <input
              type="date"
              className="input"
              value={form.data_emissao}
              onChange={(e) =>
                setForm({ ...form, data_emissao: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Valor (R$) *</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              className="input"
              value={form.valor}
              onChange={(e) => setForm({ ...form, valor: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Competência</label>
            <input
              type="date"
              className="input"
              value={form.competencia}
              onChange={(e) =>
                setForm({ ...form, competencia: e.target.value })
              }
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Descrição do serviço *</label>
            <textarea
              className="input min-h-20 resize-y"
              value={form.descricao}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Chave de acesso</label>
            <input
              className="input font-mono text-xs"
              value={form.chave_acesso}
              onChange={(e) =>
                setForm({ ...form, chave_acesso: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Cliente (tomador)</label>
            <select
              className="input"
              value={form.client_id}
              onChange={(e) => setForm({ ...form, client_id: e.target.value })}
            >
              <option value="">Selecione...</option>
              {clientes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome || c.razao_social}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Honorário vinculado</label>
            <select
              className="input"
              value={form.fee_id}
              onChange={(e) => setForm({ ...form, fee_id: e.target.value })}
            >
              <option value="">Nenhum</option>
              {fees.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.descricao} · {fmtMoney(f.valor)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">PDF da nota (DANFSe)</label>
            <input
              type="file"
              accept="application/pdf"
              className="input"
              onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div>
            <label className="label">XML da nota</label>
            <input
              type="file"
              accept=".xml,text/xml,application/xml"
              className="input"
              onChange={(e) => setXmlFile(e.target.files?.[0] ?? null)}
            />
          </div>
        </div>
        <div className="mt-5 flex justify-end">
          <button
            className="btn-primary"
            disabled={salvando}
            onClick={() => void registrar()}
          >
            {salvando ? "Registrando..." : "Registrar nota"}
          </button>
        </div>
      </Modal>

      <Modal
        open={!!cancelNota}
        onClose={() => setCancelNota(null)}
        title={`Encerrar registro local da nota ${cancelNota?.numero || ""}`}
      >
        <div className="space-y-4">
          <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-800">
            Esta ação <b>não cancela a NFS-e perante o Fisco</b>. Ela apenas encerra
            o registro administrativo dentro do EJC. Se a nota precisar ser
            cancelada fiscalmente, faça o procedimento no Emissor Nacional
            (gov.br) e confira a situação oficial.
          </div>
          <div>
            <label className="label">Motivo do encerramento local *</label>
            <textarea
              className="input min-h-20 resize-y"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Ex.: registro substituído após correção da nota no emissor"
            />
          </div>
          <button
            className="btn-primary w-full justify-center"
            disabled={cancelando}
            onClick={() => void cancelar()}
          >
            {cancelando ? "Encerrando..." : "Confirmar encerramento local"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
