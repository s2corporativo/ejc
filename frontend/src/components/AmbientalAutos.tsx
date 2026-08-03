// ── src/components/AmbientalAutos.tsx ────────────────────────────────────────
// Seção especial do ramo Ambiental (padrão AnaliseExtratos/ComparadorBacen):
// autos de infração ambiental via backend /environmental. Registrar a ciência
// do auto cria AUTOMATICAMENTE uma deadline crítica de defesa
// (Decreto 6.514/2008 art. 113 — 20 dias corridos).
import { useEffect, useState } from "react";
import { Leaf, AlertTriangle } from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Spinner, StatusBadge, Empty } from "./UI";
import type { Case } from "../types";
import { asList } from "../lib/list";
import { detalheErro } from "../utils/erro";

interface EnvCase {
  id: string;
  case_id: string;
  orgao_autuador: string;
  numero_auto: string;
  data_lavratura: string | null;
  data_ciencia: string | null;
  valor_multa: number | string | null;
  data_prazo_defesa: string | null;
  status_defesa: string;
  created_at: string;
}

const FORM_VAZIO = {
  case_id: "",
  orgao_autuador: "",
  numero_auto: "",
  data_ciencia: "",
  valor_multa: "",
  especie_infracao: "",
};

/** Datas do backend vêm como "YYYY-MM-DD" — formata sem shift de timezone. */
function fmtDia(d: string | null | undefined) {
  if (!d) return "—";
  const [iso] = d.split("T");
  const partes = iso.split("-");
  return partes.length === 3 ? partes.reverse().join("/") : d;
}

function fmtBRL(v: number | string | null) {
  const n = Number(v);
  if (v == null || isNaN(n)) return "—";
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function diasRestantes(prazo: string | null): number | null {
  if (!prazo) return null;
  const [y, m, d] = prazo.split("T")[0].split("-").map(Number);
  if (!y || !m || !d) return null;
  const hoje = new Date();
  const alvo = new Date(y, m - 1, d);
  const ref = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
  return Math.round((alvo.getTime() - ref.getTime()) / 86400000);
}

export default function AmbientalAutos({ casos }: { casos: Case[] }) {
  const [lista, setLista] = useState<EnvCase[] | null>(null);
  const [form, setForm] = useState({ ...FORM_VAZIO });
  const [salvando, setSalvando] = useState(false);
  const [criado, setCriado] = useState<EnvCase | null>(null);

  const load = () => {
    api
      .get("/environmental/")
      .then((r) => setLista(asList<EnvCase>(r.data)))
      .catch(() => setLista([]));
  };
  useEffect(load, []);

  const set = (k: keyof typeof FORM_VAZIO) => (e: any) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const registrar = async () => {
    if (!form.case_id) {
      toast.error("Selecione o caso vinculado.");
      return;
    }
    if (!form.orgao_autuador.trim() || !form.numero_auto.trim()) {
      toast.error("Órgão autuador e nº do auto são obrigatórios.");
      return;
    }
    setSalvando(true);
    setCriado(null);
    try {
      const payload: Record<string, unknown> = {
        case_id: form.case_id,
        orgao_autuador: form.orgao_autuador.trim(),
        numero_auto: form.numero_auto.trim(),
      };
      if (form.data_ciencia) payload.data_ciencia = form.data_ciencia;
      if (form.valor_multa) payload.valor_multa = Number(form.valor_multa);
      if (form.especie_infracao.trim())
        payload.especie_infracao = form.especie_infracao.trim();

      const r = await api.post("/environmental/", payload);
      setCriado(r.data as EnvCase);
      setForm({ ...FORM_VAZIO });
      toast.success("Auto de infração registrado.");
      load();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Erro ao registrar o auto."));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="card p-4 mb-4 border-l-4 border-green-500">
      <h2 className="font-serif font-semibold text-navy mb-1 flex items-center gap-2">
        <Leaf size={16} className="text-green-600" /> Autos de Infração
        Ambiental
      </h2>
      <p className="text-xs text-slate-500 mb-4">
        Registro do auto com ciência cria{" "}
        <b>automaticamente o prazo crítico de defesa</b> na agenda — 20 dias
        corridos ·{" "}
        <span className="text-gold-700">Decreto 6.514/2008 art. 113</span>
      </p>

      {/* Formulário de registro */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-3">
        <div className="sm:col-span-2 lg:col-span-3">
          <label className="label text-xs">Caso vinculado *</label>
          <select
            className="input text-sm"
            value={form.case_id}
            onChange={set("case_id")}
          >
            <option value="">Selecione o caso…</option>
            {casos.map((c) => (
              <option key={c.id} value={c.id}>
                {c.numero_interno} — {c.titulo}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label text-xs">Órgão autuador *</label>
          <input
            className="input text-sm"
            placeholder="IBAMA / SEMAD / IEF…"
            value={form.orgao_autuador}
            onChange={set("orgao_autuador")}
          />
        </div>
        <div>
          <label className="label text-xs">Nº do auto *</label>
          <input
            className="input text-sm"
            value={form.numero_auto}
            onChange={set("numero_auto")}
          />
        </div>
        <div>
          <label className="label text-xs">Data de ciência</label>
          <input
            className="input text-sm"
            type="date"
            value={form.data_ciencia}
            onChange={set("data_ciencia")}
          />
          <p className="text-[10px] text-slate-400 mt-0.5">
            Dispara o cálculo do prazo de defesa
          </p>
        </div>
        <div>
          <label className="label text-xs">Valor da multa (R$)</label>
          <input
            className="input text-sm"
            type="number"
            step="0.01"
            value={form.valor_multa}
            onChange={set("valor_multa")}
          />
        </div>
        <div className="sm:col-span-2">
          <label className="label text-xs">Descrição da infração</label>
          <input
            className="input text-sm"
            placeholder="ex: supressão de vegetação nativa sem autorização"
            value={form.especie_infracao}
            onChange={set("especie_infracao")}
          />
        </div>
      </div>
      <button
        className="btn-gold text-sm"
        disabled={salvando}
        onClick={registrar}
      >
        {salvando ? "Registrando…" : "Registrar auto de infração"}
      </button>
      {casos.length === 0 && (
        <p className="text-xs text-warn-600 mt-1">
          Crie antes um caso com área "ambiental" para vincular o auto.
        </p>
      )}

      {/* Destaque do prazo criado automaticamente */}
      {criado && (
        <div className="mt-3 p-3 rounded-lg bg-danger-50 border border-danger-200 flex items-start gap-2">
          <AlertTriangle
            size={16}
            className="text-danger-600 shrink-0 mt-0.5"
          />
          <div className="text-sm text-danger-700">
            {criado.data_prazo_defesa ? (
              <>
                <b>Prazo crítico criado automaticamente</b> na agenda: defesa
                até <b>{fmtDia(criado.data_prazo_defesa)}</b> (prazo legal, com
                meta interna de segurança) — Auto {criado.numero_auto}.
              </>
            ) : (
              <>
                Auto {criado.numero_auto} registrado <b>sem data de ciência</b>{" "}
                — informe a ciência para disparar o prazo de defesa automático.
              </>
            )}
          </div>
        </div>
      )}

      {/* Listagem */}
      <h3 className="font-serif font-semibold text-navy text-sm mt-5 mb-2">
        Autos registrados
      </h3>
      {lista === null ? (
        <Spinner />
      ) : lista.length === 0 ? (
        <Empty message="Nenhum auto de infração ambiental registrado" />
      ) : (
        <div className="space-y-2">
          {lista.map((e) => {
            const dias = diasRestantes(e.data_prazo_defesa);
            return (
              <div
                key={e.id}
                className="flex flex-wrap items-center gap-3 p-3 rounded-lg border border-black/[0.05] dark:border-white/10"
              >
                <div className="flex-1 min-w-[180px]">
                  <div className="text-sm font-medium text-navy">
                    Auto {e.numero_auto}
                  </div>
                  <div className="text-xs text-slate-400">
                    {e.orgao_autuador} · ciência {fmtDia(e.data_ciencia)} ·
                    multa {fmtBRL(e.valor_multa)}
                  </div>
                </div>
                {e.data_prazo_defesa && (
                  <div className="text-right">
                    <div
                      className={`text-xs font-semibold ${
                        dias !== null && dias <= 5
                          ? "text-danger-600"
                          : dias !== null && dias <= 10
                            ? "text-orange-500"
                            : "text-slate-600"
                      }`}
                    >
                      Defesa até {fmtDia(e.data_prazo_defesa)}
                    </div>
                    {dias !== null && (
                      <div className="text-[10px] text-slate-400">
                        {dias >= 0 ? `${dias} dia(s) restantes` : "vencido"}
                      </div>
                    )}
                  </div>
                )}
                <StatusBadge value={e.status_defesa} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
