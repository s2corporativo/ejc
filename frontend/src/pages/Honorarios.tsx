import { exportCsv } from "../utils/exportCsv";
import { toast } from "../components/Toast";
import { exportPdf } from "../utils/exportPdf";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import {
  Plus,
  DollarSign,
  Download,
  FileType2,
  Split,
  QrCode,
  History,
} from "lucide-react";
import QRCode from "qrcode";
import api from "../lib/api";
import { asList } from "../lib/list";
import type { Fee, Client, Paged } from "../types";
import {
  StatusBadge,
  Modal,
  Empty,
  ErrorState,
  Spinner,
  fmtDate,
  fmtMoney,
} from "../components/UI";

const STATUS_VALIDOS = ["pendente", "atrasado", "pago"];
const TIPOS_COM_PERCENTUAL = ["exito", "misto"];

function hojeISO(): string {
  const agora = new Date();
  const ano = agora.getFullYear();
  const mes = String(agora.getMonth() + 1).padStart(2, "0");
  const dia = String(agora.getDate()).padStart(2, "0");
  return `${ano}-${mes}-${dia}`;
}

export function quantoCobrar(f: Fee): string {
  const partes: string[] = [];
  if (f.valor != null) partes.push(fmtMoney(f.valor));
  if (f.percentual_exito != null)
    partes.push(`${f.percentual_exito}% de êxito`);
  if (partes.length) return partes.join(" + ");
  return fmtMoney(f.valor);
}

export default function Honorarios() {
  const [data, setData] = useState<Paged<Fee> | null>(null);
  const [resumo, setResumo] = useState<any>(null);
  const [clientes, setClientes] = useState<Client[]>([]);
  const [searchParams] = useSearchParams();
  const [statusF, setStatusF] = useState(() => {
    const s = searchParams.get("status");
    return s && STATUS_VALIDOS.includes(s) ? s : "";
  });
  const [modal, setModal] = useState(false);
  const [pagModal, setPagModal] = useState<Fee | null>(null);
  const [histModal, setHistModal] = useState<any>(null);
  const [form, setForm] = useState<any>({ tipo: "fixo" });
  const [pag, setPag] = useState<any>({});
  const [salvando, setSalvando] = useState(false);
  const [registrando, setRegistrando] = useState(false);
  const [rateioModal, setRateioModal] = useState<any>(null);
  const [pixModal, setPixModal] = useState<any>(null);
  const [pixCfg, setPixCfg] = useState<any>(() => {
    try {
      // Chave PIX pode conter CPF/CNPJ/e-mail/telefone. Não persiste em
      // localStorage: fica apenas na sessão atual do navegador.
      localStorage.removeItem("ejc_pix");
      return JSON.parse(sessionStorage.getItem("ejc_pix") || "{}");
    } catch {
      return {};
    }
  });
  const [pixRes, setPixRes] = useState<any>(null);
  const [pixQr, setPixQr] = useState("");
  const [rateioLoading, setRateioLoading] = useState(false);
  const [error, setError] = useState(false);

  const load = () => {
    setError(false);
    api
      .get("/fees/", {
        params: { status: statusF || undefined, page_size: 50 },
      })
      .then((r) => setData(r.data))
      .catch(() => setError(true));
    api
      .get("/fees/resumo")
      .then((r) => setResumo(r.data))
      .catch(() => {});
  };

  useEffect(() => {
    load();
    api
      .get("/clients/", { params: { page_size: 100 } })
      .then((r) => setClientes(asList<Client>(r.data)))
      .catch(() => setClientes([]));
  }, [statusF]);

  const salvar = async () => {
    if (!form.descricao || !form.client_id) {
      toast.error("Descrição e cliente obrigatórios");
      return;
    }
    setSalvando(true);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).filter(([, v]) => v !== "" && v !== null),
      );
      await api.post("/fees/", payload);
      setModal(false);
      setForm({ tipo: "fixo" });
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro");
    } finally {
      setSalvando(false);
    }
  };

  const abrirRateio = async (fee: any) => {
    setRateioLoading(true);
    setRateioModal({ fee });
    try {
      const r = await api.get(`/honorarios-oab/${fee.id}/rateio`);
      setRateioModal({ fee, calc: r.data });
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao calcular rateio");
      setRateioModal(null);
    } finally {
      setRateioLoading(false);
    }
  };

  const gerarRateio = async () => {
    if (!rateioModal?.fee) return;
    try {
      await api.post(`/honorarios-oab/${rateioModal.fee.id}/rateio`);
      toast.success(
        "Rateio gerado — saque do titular criado em Saques Sócios (pendente de aprovação).",
      );
      setRateioModal(null);
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao gerar rateio");
    }
  };

  const abrirHistorico = async (fee: Fee) => {
    setHistModal({ fee, loading: true });
    try {
      const r = await api.get(`/fees/${fee.id}/pagamentos`);
      setHistModal({ fee, loading: false, data: r.data });
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao carregar pagamentos");
      setHistModal(null);
    }
  };

  const abrirPagamento = async (fee: Fee) => {
    let valor: number | string | undefined = fee.valor ?? undefined;
    try {
      const r = await api.get(`/fees/${fee.id}/pagamentos`);
      if (r.data?.saldo != null) valor = r.data.saldo;
    } catch {
      // O backend continua protegendo contra overpayment, mas o modal de baixa
      // pode ser aberto para correção manual se o subledger estiver indisponível.
    }
    setPagModal(fee);
    setPag({ valor, data_pagamento: hojeISO() });
  };

  const registrarPag = async () => {
    if (!pagModal || !pag.valor || !pag.data_pagamento || registrando) return;
    setRegistrando(true);
    try {
      await api.post(`/fees/${pagModal.id}/pagamentos`, pag);
      setPagModal(null);
      setPag({});
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao registrar pagamento");
    } finally {
      setRegistrando(false);
    }
  };

  const abrirPix = async (fee: Fee) => {
    // Cobrança deve ser fail-closed: nunca gerar PIX pelo valor bruto quando há
    // pagamentos parciais. Consulta o subledger antes de abrir o modal.
    try {
      const r = await api.get(`/fees/${fee.id}/pagamentos`);
      const saldo = r.data?.saldo;
      if (saldo == null) {
        toast.error("Saldo monetário ainda não está apurado para este honorário.");
        return;
      }
      if (Number(saldo) <= 0) {
        toast.error("Este honorário não possui saldo disponível para cobrança.");
        return;
      }
      setPixModal({ ...fee, saldo });
      setPixRes(null);
      setPixQr("");
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Não foi possível apurar o saldo para PIX");
    }
  };

  const gerarPix = async (fee: any) => {
    if (!pixCfg.chave) {
      toast.error("Informe a chave PIX do escritório (campo abaixo).");
      return;
    }
    sessionStorage.setItem("ejc_pix", JSON.stringify(pixCfg));
    setPixRes(null);
    setPixQr("");
    try {
      // Revalida imediatamente antes de gerar para reduzir risco de cobrar um
      // saldo já baixado em outra sessão desde a abertura do modal.
      const ledger = await api.get(`/fees/${fee.id}/pagamentos`);
      const saldo = ledger.data?.saldo;
      if (saldo == null || Number(saldo) <= 0) {
        toast.error("Não há saldo monetário disponível para gerar esta cobrança.");
        setPixModal(null);
        return;
      }
      setPixModal((atual: any) => (atual ? { ...atual, saldo } : atual));
      const { data } = await api.post("/pix/cobranca", {
        chave: pixCfg.chave,
        nome: pixCfg.nome || "Escritorio",
        cidade: pixCfg.cidade || "Betim",
        valor: saldo,
        txid: (fee.id || "").replace(/-/g, "").slice(0, 25),
        descricao: (fee.descricao || "Honorarios").slice(0, 25),
      });
      setPixRes(data);
      const url = await QRCode.toDataURL(data.copia_e_cola, {
        width: 240,
        margin: 1,
      });
      setPixQr(url);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao gerar PIX");
    }
  };

  return (
    <div>
      <div className="flex gap-2 items-center justify-end flex-wrap mb-4">
        <button
          onClick={() => {
            const rows = (data?.data ?? []).map((f) => ({
              descricao: f.descricao,
              tipo: f.tipo,
              valor: f.valor,
              percentual_exito: f.percentual_exito ?? "",
              cobranca: quantoCobrar(f),
              vencimento: f.data_vencimento,
              status: f.status,
              cliente: (f as any).client_nome ?? "",
            }));
            exportCsv(rows as any, "honorarios.csv");
          }}
          className="btn-secondary px-3 py-1.5 text-xs"
        >
          <Download size={13} /> CSV
        </button>
        <button
          onClick={() => {
            const rows = (data?.data ?? []).map((f) => [
              f.descricao,
              f.tipo,
              quantoCobrar(f),
              f.data_vencimento ?? "",
              f.status,
              (f as any).client_nome ?? "",
            ]);
            exportPdf(
              "Honorários",
              [
                "Descrição",
                "Tipo",
                "Valor ou %",
                "Vencimento",
                "Status",
                "Cliente",
              ],
              rows,
            );
          }}
          className="btn-secondary px-3 py-1.5 text-xs"
        >
          <FileType2 size={13} /> PDF
        </button>
        <button className="btn-gold" onClick={() => setModal(true)}>
          <Plus size={16} /> Novo lançamento
        </button>
      </div>

      {resumo && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4 mb-6">
          <div className="card p-4">
            <div className="text-xs text-slate-400 uppercase font-semibold">Pendente</div>
            <div className="text-xl font-bold text-navy">{fmtMoney(resumo.pendente)}</div>
          </div>
          <div className="card p-4">
            <div className="text-xs text-slate-400 uppercase font-semibold">Em atraso</div>
            <div className="text-xl font-bold text-danger-600">{fmtMoney(resumo.atrasado)}</div>
          </div>
          <div className="card p-4">
            <div className="text-xs text-slate-400 uppercase font-semibold">Recebido no mês</div>
            <div className="text-xl font-bold text-success-600">{fmtMoney(resumo.recebido_mes)}</div>
          </div>
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {["", "pendente", "atrasado", "pago"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusF(s)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium ${statusF === s ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
          >
            {s || "Todos"}
          </button>
        ))}
      </div>

      {error ? (
        <ErrorState message="Não foi possível carregar os honorários. Tente novamente." onRetry={load} />
      ) : !data ? (
        <Spinner />
      ) : data.data.length === 0 ? (
        <Empty message="Nenhum lançamento" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Descrição</th>
                <th className="px-4 py-3">Tipo</th>
                <th className="px-4 py-3">Valor</th>
                <th className="px-4 py-3">Vencimento</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(Array.isArray(data.data) ? data.data : []).map((f) => (
                <tr key={f.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-navy">{f.descricao}</td>
                  <td className="px-4 py-3 text-xs capitalize">{f.tipo.replace(/_/g, " ")}</td>
                  <td className="px-4 py-3 font-semibold">{quantoCobrar(f)}</td>
                  <td className="px-4 py-3 text-slate-500">{fmtDate(f.data_vencimento)}</td>
                  <td className="px-4 py-3"><StatusBadge value={f.status} /></td>
                  <td className="px-4 py-3">
                    <button className="btn-ghost px-2 py-1 text-slate-500" title="Histórico de pagamentos" onClick={() => abrirHistorico(f)}>
                      <History size={15} />
                    </button>
                    {f.status !== "pago" && f.status !== "cancelado" && (
                      <button className="btn-ghost px-2 py-1 text-success-700" title="Registrar pagamento" onClick={() => abrirPagamento(f)}>
                        <DollarSign size={15} />
                      </button>
                    )}
                    {f.status !== "pago" && f.status !== "cancelado" && f.valor != null && (
                      <button className="btn-ghost px-2 py-1 text-teal-600" title="Cobrar via PIX" onClick={() => abrirPix(f)}>
                        <QrCode size={15} />
                      </button>
                    )}
                    {f.tipo === "exito" && f.status === "pago" && (
                      <button className="btn-ghost px-2 py-1 text-bronze-deep" title="Rateio de êxito 50/50" onClick={() => abrirRateio(f)}>
                        <Split size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Novo lançamento" wide>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="label">Descrição *</label>
            <input className="input" value={form.descricao || ""} onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
          </div>
          <div>
            <label className="label">Cliente *</label>
            <select className="input" value={form.client_id || ""} onChange={(e) => setForm({ ...form, client_id: e.target.value })}>
              <option value="">Selecione...</option>
              {clientes.map((c) => <option key={c.id} value={c.id}>{c.nome || c.razao_social}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Tipo</label>
            <select
              className="input"
              value={form.tipo}
              onChange={(e) => {
                const tipo = e.target.value;
                setForm({ ...form, tipo, ...(TIPOS_COM_PERCENTUAL.includes(tipo) ? {} : { percentual_exito: "" }) });
              }}
            >
              <option value="fixo">Fixo</option>
              <option value="exito">Êxito</option>
              <option value="sucumbencia">Sucumbência</option>
              <option value="misto">Misto</option>
              <option value="por_hora">Por hora</option>
              <option value="custas_despesas">Custas/despesas</option>
            </select>
          </div>
          <div>
            <label className="label">Valor (R$)</label>
            <input type="number" step="0.01" min="0" className="input" value={form.valor || ""} onChange={(e) => setForm({ ...form, valor: e.target.value })} />
          </div>
          {TIPOS_COM_PERCENTUAL.includes(form.tipo) && (
            <div>
              <label className="label">Percentual de êxito (%)</label>
              <input type="number" step="0.01" min="0" max="100" className="input" value={form.percentual_exito || ""} onChange={(e) => setForm({ ...form, percentual_exito: e.target.value })} />
            </div>
          )}
          <div className="sm:col-span-2 -mt-1">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {TIPOS_COM_PERCENTUAL.includes(form.tipo)
                ? "Informe o valor em reais ou o percentual de êxito. Se o contrato combinar os dois, o EJC registra ambos; a base econômica do percentual e o teto aplicável exigem conferência jurídica antes da quitação."
                : "Informe o valor em reais. O percentual de êxito só se aplica aos tipos Êxito e Misto."}
            </p>
          </div>
          <div>
            <label className="label">Vencimento</label>
            <input type="date" className="input" value={form.data_vencimento || ""} onChange={(e) => setForm({ ...form, data_vencimento: e.target.value })} />
          </div>
        </div>
        <div className="flex justify-end mt-5">
          <button className="btn-primary" disabled={salvando} onClick={salvar}>{salvando ? "Salvando..." : "Lançar"}</button>
        </div>
      </Modal>

      <Modal open={!!pagModal} onClose={() => setPagModal(null)} title="Registrar pagamento">
        <div className="space-y-4">
          <div>
            <label className="label">Valor pago (R$)</label>
            <input type="number" step="0.01" min="0.01" className="input" value={pag.valor || ""} onChange={(e) => setPag({ ...pag, valor: e.target.value })} />
          </div>
          <div>
            <label className="label">Data do pagamento</label>
            <input type="date" className="input" value={pag.data_pagamento || ""} onChange={(e) => setPag({ ...pag, data_pagamento: e.target.value })} />
          </div>
          <div>
            <label className="label">Forma</label>
            <select className="input" value={pag.forma || ""} onChange={(e) => setPag({ ...pag, forma: e.target.value })}>
              <option value="">—</option>
              <option value="pix">PIX</option>
              <option value="transferencia">Transferência</option>
              <option value="dinheiro">Dinheiro</option>
              <option value="cartao">Cartão</option>
              <option value="boleto">Boleto</option>
              <option value="outro">Outro</option>
            </select>
          </div>
          <button className="btn-primary w-full justify-center" onClick={registrarPag} disabled={registrando}>
            {registrando ? "Registrando..." : "Confirmar"}
          </button>
        </div>
      </Modal>

      <Modal open={!!histModal} onClose={() => setHistModal(null)} title="Histórico de pagamentos">
        {histModal?.loading ? (
          <Spinner />
        ) : histModal?.data ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="card p-3">
                <div className="text-xs text-slate-400">Total recebido</div>
                <div className="font-bold text-success-700">{fmtMoney(histModal.data.total_pago)}</div>
              </div>
              <div className="card p-3">
                <div className="text-xs text-slate-400">Saldo</div>
                <div className="font-bold text-navy">{histModal.data.saldo == null ? "A apurar" : fmtMoney(histModal.data.saldo)}</div>
              </div>
            </div>
            {histModal.data.pagamentos?.length ? (
              <div className="overflow-x-auto border border-slate-100 rounded-lg">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-xs text-slate-500 uppercase">
                    <tr><th className="p-2 text-left">Data</th><th className="p-2 text-left">Forma</th><th className="p-2 text-right">Valor</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {histModal.data.pagamentos.map((p: any) => (
                      <tr key={p.id}>
                        <td className="p-2">{fmtDate(p.data_pagamento)}</td>
                        <td className="p-2 capitalize">{(p.forma || "—").replace(/_/g, " ")}</td>
                        <td className="p-2 text-right font-semibold">{fmtMoney(p.valor)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Empty message="Nenhum pagamento registrado" />}
          </div>
        ) : null}
      </Modal>

      <Modal open={!!rateioModal} onClose={() => setRateioModal(null)} title="Rateio de Êxito — 50% Titular / 50% Escritório">
        {rateioLoading || !rateioModal?.calc ? (
          <Spinner />
        ) : (
          <div className="space-y-4">
            <div className="text-sm text-slate-600">{rateioModal.calc.fee?.caso_titulo || "Caso"} · Titular: <b>{rateioModal.calc.titular?.nome || "—"}</b></div>
            <div className="space-y-2 text-sm">
              {[
                ["Honorário de êxito (bruto)", rateioModal.calc.bruto, "text-navy"],
                ["(−) Despesas do caso", rateioModal.calc.despesas_caso, "text-danger-500"],
                ["(=) Líquido a ratear", rateioModal.calc.liquido, "text-navy font-bold"],
                ["Titular do caso (50%)", rateioModal.calc.titular?.valor, "text-success-600 font-bold"],
                ["Escritório (50%)", rateioModal.calc.escritorio?.valor, "text-bronze-deep font-bold"],
              ].map(([l, v, cls]: any) => (
                <div key={l} className="flex justify-between border-b border-slate-100 pb-1.5">
                  <span className="text-slate-500">{l}</span><span className={cls}>{fmtMoney(Number(v))}</span>
                </div>
              ))}
            </div>
            {!rateioModal.calc.titular?.partner_id && <p className="text-xs text-warn-600">⚠ Titular não é sócio cadastrado — gere o saque manualmente.</p>}
            <button className="btn-primary w-full justify-center" disabled={!rateioModal.calc.titular?.partner_id} onClick={gerarRateio}>Gerar saque do titular (pendente)</button>
          </div>
        )}
      </Modal>

      <Modal open={!!pixModal} onClose={() => setPixModal(null)} title="Cobrança via PIX">
        {pixModal && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">{pixModal.descricao} · saldo a cobrar: <b>{fmtMoney(pixModal.saldo)}</b></p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div className="sm:col-span-3">
                <label className="label">Chave PIX do escritório *</label>
                <input className="input" value={pixCfg.chave || ""} onChange={(e) => setPixCfg({ ...pixCfg, chave: e.target.value })} placeholder="CPF/CNPJ, e-mail, telefone ou aleatória" />
                <p className="text-[11px] text-slate-400 mt-1">A configuração fica somente nesta sessão do navegador.</p>
              </div>
              <div className="sm:col-span-2">
                <label className="label">Recebedor</label>
                <input className="input" value={pixCfg.nome || ""} onChange={(e) => setPixCfg({ ...pixCfg, nome: e.target.value })} placeholder="Nome do escritório" />
              </div>
              <div>
                <label className="label">Cidade</label>
                <input className="input" value={pixCfg.cidade || ""} onChange={(e) => setPixCfg({ ...pixCfg, cidade: e.target.value })} placeholder="Betim" />
              </div>
            </div>
            <button className="btn-primary w-full justify-center" onClick={() => gerarPix(pixModal)}>Gerar cobrança PIX</button>
            {pixRes && (
              <div className="text-center space-y-2 pt-2 border-t border-slate-100">
                {pixQr && <img src={pixQr} alt="QR PIX" className="mx-auto rounded-lg border border-black/[0.05] shadow-sm" />}
                <p className="text-xs text-slate-500">PIX copia e cola:</p>
                <textarea readOnly className="input w-full text-[11px] font-mono" rows={3} value={pixRes.copia_e_cola} onClick={(e) => (e.target as HTMLTextAreaElement).select()} />
                <button className="btn-secondary text-sm" onClick={() => navigator.clipboard?.writeText(pixRes.copia_e_cola)}>Copiar código</button>
                <p className="text-[11px] text-slate-400">Após a confirmação do pagamento, registre a baixa pelo botão $ na lista.</p>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
