// src/components/ExtratoSocio.tsx
// Modal de extrato financeiro do advogado/sócio: honorários + saques de êxito + distribuições.
import { useState } from "react";
import { BarChart2, TrendingUp, Wallet, PieChart } from "lucide-react";
import api from "../lib/api";
import { Modal } from "./UI";

const fmtR = (v: number) =>
  (v ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const fmtDt = (s?: string) =>
  s ? new Date(s).toLocaleDateString("pt-BR") : "—";

interface Props {
  userId: string;
  nome: string;
  isSocio?: boolean;
}

export default function ExtratoSocio({ userId, nome, isSocio = false }: Props) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (data) {
      setOpen(true);
      return;
    }
    setLoading(true);
    try {
      const endpoint = isSocio
        ? `/extratos/socio/${userId}`
        : `/extratos/advogado/${userId}`;
      const r = await api.get(endpoint);
      setData(r.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
      setOpen(true);
    }
  };

  return (
    <>
      <button
        onClick={load}
        disabled={loading}
        className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md border border-bronze/30 text-bronze hover:bg-bronze/5 transition"
        title="Ver extrato financeiro"
      >
        <BarChart2 size={13} />
        {loading ? "…" : "Extrato"}
      </button>

      {open && data && (
        <Modal
          open={open}
          onClose={() => setOpen(false)}
          title={`Extrato — ${data.advogado ?? data.socio?.full_name ?? nome}`}
        >
          <>
            {data.socio && (
              <p className="text-xs text-slate-500 -mt-2 mb-3">
                Participação:{" "}
                {((data.socio.participacao_percentual ?? 0) * 100).toFixed(2)}%
                {data.socio.pro_labore
                  ? ` · Pró-labore: ${fmtR(data.socio.pro_labore)}`
                  : ""}
              </p>
            )}

            {/* KPI strip */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 -mx-5 px-5 pb-4">
              {data.resumo?.honorarios_recebidos !== undefined && (
                <Kpi
                  icon={TrendingUp}
                  label="Honorários recebidos"
                  value={fmtR(data.resumo.honorarios_recebidos)}
                />
              )}
              {data.resumo?.saques_exito !== undefined && (
                <Kpi
                  icon={Wallet}
                  label="Saques de êxito"
                  value={fmtR(data.resumo.saques_exito)}
                />
              )}
              {data.resumo?.a_receber !== undefined && (
                <Kpi
                  icon={PieChart}
                  label="A receber"
                  value={fmtR(data.resumo.a_receber)}
                />
              )}
            </div>

            {/* Honorários */}
            {data.honorarios?.length > 0 && (
              <Section title="Honorários por caso">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-slate-500 border-b">
                      <th className="py-1.5 pr-3">Caso</th>
                      <th className="py-1.5 pr-3">Tipo</th>
                      <th className="py-1.5 pr-3">Status</th>
                      <th className="py-1.5 text-right">Valor</th>
                      <th className="py-1.5 pl-3">Pagamento</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.honorarios.map((h: any, i: number) => (
                      <tr
                        key={i}
                        className="border-b border-slate-50 hover:bg-slate-50/50"
                      >
                        <td className="py-1.5 pr-3 text-slate-700 max-w-[12rem] truncate">
                          {h.caso ?? "—"}
                        </td>
                        <td className="py-1.5 pr-3 capitalize text-slate-600">
                          {h.tipo}
                        </td>
                        <td className="py-1.5 pr-3">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              h.status === "pago"
                                ? "bg-success-50 text-success-700"
                                : h.status === "atrasado"
                                  ? "bg-danger-50 text-danger-600"
                                  : "bg-warn-50 text-warn-700"
                            }`}
                          >
                            {h.status}
                          </span>
                        </td>
                        <td className="py-1.5 text-right font-medium tabular-nums">
                          {fmtR(h.valor)}
                        </td>
                        <td className="py-1.5 pl-3 text-slate-500">
                          {fmtDt(h.data_pagamento)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
            )}

            {/* Saques de êxito */}
            {data.saques?.length > 0 && (
              <Section title="Saques de êxito">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-slate-500 border-b">
                      <th className="py-1.5 pr-3">Descrição</th>
                      <th className="py-1.5 pr-3">Status</th>
                      <th className="py-1.5 text-right">Parte sócio</th>
                      <th className="py-1.5 pl-3">Data</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.saques.map((s: any, i: number) => (
                      <tr
                        key={i}
                        className="border-b border-slate-50 hover:bg-slate-50/50"
                      >
                        <td className="py-1.5 pr-3 text-slate-700">
                          {s.description ?? "Êxito"}
                        </td>
                        <td className="py-1.5 pr-3">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              s.status === "paid"
                                ? "bg-primary-50 text-primary-700"
                                : s.status === "approved"
                                  ? "bg-success-50 text-success-700"
                                  : "bg-warn-50 text-warn-700"
                            }`}
                          >
                            {s.status}
                          </span>
                        </td>
                        <td className="py-1.5 text-right font-medium tabular-nums">
                          {fmtR(s.partner_share)}
                        </td>
                        <td className="py-1.5 pl-3 text-slate-500">
                          {fmtDt(s.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
            )}

            {/* Distribuições (sócio) */}
            {data.distribuicoes?.length > 0 && (
              <Section title="Distribuições de lucro">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-slate-500 border-b">
                      <th className="py-1.5 pr-3">Mês ref.</th>
                      <th className="py-1.5 pr-3">Status</th>
                      <th className="py-1.5 text-right">Total distribuído</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.distribuicoes.map((d: any, i: number) => (
                      <tr
                        key={i}
                        className="border-b border-slate-50 hover:bg-slate-50/50"
                      >
                        <td className="py-1.5 pr-3 text-slate-700">
                          {d.mes_referencia}
                        </td>
                        <td className="py-1.5 pr-3">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-primary-50 text-primary-700">
                            {d.status ?? "registrado"}
                          </span>
                        </td>
                        <td className="py-1.5 text-right font-medium tabular-nums">
                          {fmtR(d.valor_total)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
            )}

            {data.honorarios?.length === 0 && data.saques?.length === 0 && (
              <p className="text-center text-sm text-slate-400 py-8">
                Nenhum lançamento registrado ainda.
              </p>
            )}

            <div className="-mx-5 px-5 pt-3 text-[10px] text-warn-700 border-t">
              Instrumento interno — dados em tempo real do banco. Saldo de
              distribuições por sócio calculado no momento do rateio.
            </div>
          </>
        </Modal>
      )}
    </>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
}: {
  icon: any;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
      <div className="flex items-center gap-1.5 text-slate-500 mb-1">
        <Icon size={13} />
        <span className="text-[10px] font-medium uppercase tracking-wide">
          {label}
        </span>
      </div>
      <p className="text-sm font-semibold text-navy tabular-nums">{value}</p>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="pb-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 mb-2">
        {title}
      </h3>
      {children}
    </div>
  );
}
