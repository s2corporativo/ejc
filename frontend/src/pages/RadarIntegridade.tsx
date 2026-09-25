import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import api from "../lib/api";
import { Badge, Card } from "../components/UI";

type Integridade = {
  contagens: Record<string, number | null>;
  total_casos_pendentes: number;
  itens: Array<{
    tipo: string;
    case_id: string;
    numero_interno: string | null;
    titulo: string;
    mensagem: string;
  }>;
  somente_sinalizacao: boolean;
};

const ROTULOS: Record<string, string> = {
  sem_responsavel: "Sem responsável",
  pre_processual_com_cnj: "Pré-processual com CNJ",
  protocolado_sem_processo: "Protocolado sem Processo",
  processo_sem_principal: "Processo sem principal",
  divergencias_datajud: "Divergências DataJud",
  duplicatas_cnj: "Duplicatas de CNJ",
  recebimentos_sem_rateio: "Recebimentos sem rateio",
  numeros_invalidos: "Números inválidos",
};

export default function RadarIntegridade() {
  const [data, setData] = useState<Integridade | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    api
      .get("/saneamento/integridade")
      .then((r) => setData(r.data as Integridade))
      .catch(() => setErro(true));
  }, []);

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
              {ROTULOS[chave] ?? chave.replaceAll("_", " ")}
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
              <li key={`${item.tipo}-${item.case_id}`} className="py-3">
                <a
                  href={`/casos/${item.case_id}`}
                  className="flex items-start gap-3 hover:opacity-80"
                >
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
                    aria-hidden="true"
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                      {item.numero_interno ? `${item.numero_interno} · ` : ""}
                      {item.titulo}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-500">
                      {item.mensagem}
                    </span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
