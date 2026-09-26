import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Link } from "react-router";

import api from "../lib/api";
import { toast } from "../components/Toast";
import { useAuth } from "../stores/auth";
import { Badge, Card } from "../components/UI";

type Integridade = {
  contagens: Record<string, number | null>;
  total_casos_pendentes: number;
  itens: Array<{
    tipo: string;
    case_id: string | null;
    numero_interno: string | null;
    titulo: string;
    mensagem: string;
  }>;
  somente_sinalizacao: boolean;
};

type DivergenciaDataJud = {
  id: number;
  numero_cnj: string;
  tipo: string;
  valor_interno: unknown;
  valor_datajud: unknown;
  observacao?: string | null;
  tratada: boolean;
};

const ROTULOS: Record<string, string> = {
  sem_responsavel: "Sem responsável",
  pre_processual_com_cnj: "Pré-processual com CNJ",
  protocolado_sem_processo: "Protocolado sem Processo",
  processo_sem_principal: "Processo sem principal",
  judicial_sem_valor_causa: "Judicial sem valor da causa",
  sem_atualizacao_60d: "Sem atualização há 60 dias",
  aguardando_despacho: "Aguardando despacho",
  aguardando_julgamento: "Aguardando julgamento/sentença",
  divergencias_datajud: "Divergências DataJud",
  duplicatas_cnj: "Duplicatas de CNJ",
  recebimentos_sem_rateio: "Recebimentos sem rateio",
  recebimentos_sem_caso: "Recebimentos sem caso",
  numeros_invalidos: "Números inválidos",
};

export default function RadarIntegridade() {
  const user = useAuth((state) => state.user);
  const podeAplicar = new Set(["superadmin", "admin", "socio", "advogado"]).has(
    user?.role || "",
  );
  const [data, setData] = useState<Integridade | null>(null);
  const [divergencias, setDivergencias] = useState<DivergenciaDataJud[]>([]);
  const [aplicando, setAplicando] = useState<number | null>(null);
  const [erro, setErro] = useState(false);

  const carregar = async () => {
    setErro(false);
    try {
      const [integridadeResp, divergenciasResp] = await Promise.all([
        api.get("/saneamento/integridade"),
        api.get("/saneamento/divergencias", {
          params: { tratada: false, page: 1, page_size: 50 },
        }),
      ]);
      setData(integridadeResp.data as Integridade);
      setDivergencias(
        Array.isArray(divergenciasResp.data)
          ? (divergenciasResp.data as DivergenciaDataJud[])
          : [],
      );
    } catch {
      setErro(true);
    }
  };

  useEffect(() => {
    void carregar();
  }, []);

  const confirmarAplicacao = async (item: DivergenciaDataJud) => {
    const aplicavel = new Set([
      "classe_divergente",
      "orgao_divergente",
      "data_ajuizamento_divergente",
    ]);
    if (!aplicavel.has(item.tipo)) return;
    if (
      !window.confirm(
        `Aplicar ao processo o dado oficial do DataJud para ${item.tipo.replace(/_/g, " ")}?`,
      )
    ) {
      return;
    }
    setAplicando(item.id);
    try {
      await api.post(`/saneamento/divergencias/${item.id}/aplicar`, {
        confirmar: true,
      });
      toast.success("Metadado confirmado e atualizado com trilha de auditoria.");
      await carregar();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Não foi possível aplicar a divergência.",
      );
    } finally {
      setAplicando(null);
    }
  };

  if (erro) {
    return (
      <Card className="p-5">
        <p className="text-sm text-slate-600">
          Não foi possível carregar a fila de integridade processual.
        </p>
      </Card>
    );
  }

  if (!data) {
    return <p className="text-sm text-slate-500">Carregando integridade…</p>;
  }

  const contagens = Object.entries(data.contagens).filter(([, valor]) => valor != null);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {contagens.map(([chave, valor]) => (
          <Card key={chave} className="p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {ROTULOS[chave] ?? chave.replace(/_/g, " ")}
            </p>
            <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">
              {valor}
            </p>
          </Card>
        ))}
      </div>

      <Card className="p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Fila de correção
            </p>
            <p className="mt-1 text-xs text-slate-500">
              O radar apenas sinaliza. Nenhum caso é alterado automaticamente.
            </p>
          </div>
          <Badge tone={data.total_casos_pendentes > 0 ? "amber" : "green"}>
            {data.total_casos_pendentes} pendência
            {data.total_casos_pendentes === 1 ? "" : "s"}
          </Badge>
        </div>

        {data.itens.length === 0 ? (
          <div className="mt-4 flex items-center gap-2 text-sm text-slate-600">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            Nenhuma inconsistência operacional de caso encontrada.
          </div>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100 dark:divide-slate-800">
            {data.itens.map((item) => (
              <li key={`${item.tipo}-${item.case_id ?? item.titulo}`} className="py-3">
                <div className="flex items-start gap-3">
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                      {item.numero_interno ? `${item.numero_interno} · ` : ""}
                      {item.titulo}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-500">
                      {item.mensagem}
                    </span>
                    {item.case_id && (
                      <Link
                        to={`/casos/${item.case_id}`}
                        className="mt-1 inline-block text-xs font-medium text-primary-600 hover:underline"
                      >
                        Abrir caso
                      </Link>
                    )}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Divergências DataJud
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Dados oficiais são comparados automaticamente, mas só alteram o processo após confirmação humana.
            </p>
          </div>
          <Badge tone={divergencias.length > 0 ? "amber" : "green"}>
            {divergencias.length} pendente{divergencias.length === 1 ? "" : "s"}
          </Badge>
        </div>

        {divergencias.length === 0 ? (
          <div className="mt-4 flex items-center gap-2 text-sm text-slate-600">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            Nenhuma divergência DataJud pendente.
          </div>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100 dark:divide-slate-800">
            {divergencias.map((item) => {
              const aplicavel = new Set([
                "classe_divergente",
                "orgao_divergente",
                "data_ajuizamento_divergente",
              ]).has(item.tipo);
              return (
                <li key={item.id} className="py-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                        {item.numero_cnj} · {item.tipo.replace(/_/g, " ")}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        Interno: {String(item.valor_interno ?? "—")} · DataJud: {String(item.valor_datajud ?? "—")}
                      </p>
                      {item.observacao && (
                        <p className="mt-1 text-xs text-slate-500">{item.observacao}</p>
                      )}
                    </div>
                    {aplicavel && podeAplicar ? (
                      <button
                        type="button"
                        className="btn-secondary shrink-0"
                        disabled={aplicando === item.id}
                        onClick={() => void confirmarAplicacao(item)}
                      >
                        {aplicando === item.id ? "Aplicando..." : "Revisar e aplicar"}
                      </button>
                    ) : (
                      <span className="text-xs font-medium text-slate-400">
                        Revisão manual
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
